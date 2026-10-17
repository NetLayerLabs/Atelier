"""Evolus business-agent adapter (supplier outreach + Shopify pre-order workflows).

API shape from the public Evolus developer docs, https://evolus.ai/developers (read 2026-10-12):

    REST base   https://api.evolus.ai/api/v1
    Auth        X-ApiKey: <application API key>   X-Application-Id: <workspace/space id>
    Execute     POST /api/v1/workflows/{workflowId}/execute        (multipart/form-data)
                fields: input (text), file (0..n), parameters (flat JSON object, validated
                against the parameters the workflow declares), optional callbackUrl/...
                -> 202 Accepted  {"jobId","executionId","enqueuedAt","traceId"}
                   + header X-Workflow-Execution-Id;  409 if the workflow is switched off
    Status      GET  /api/v1/workflows/{workflowId}/executions/{executionId}
                status in Pending | Running | Completed | Failed
    Limits      60 req/min per event workspace; 402 when platform credits run out

STILL UNVERIFIED (not in the public docs; check the in-workspace API reference at app.evolus.ai):
  * the field names of the execution-status body other than `status` (output / result / error).
    Parsing below is therefore lenient: it searches the whole body for the values it needs.
  * (verified 2026-10-16) `parameters` accepts undeclared keys but every value must be a STRING (400 otherwise:
    _flatten stringifies). On 400/422 we still retry once with `input` only (the full payload is in `input` too).

v3 additions (docs/EVOLUS_API_NOTES.md has the sources, verified vs inferred):
    Agent chat  POST https://api.evolus.ai/v1/chat/completions   Authorization: Bearer <app key>
                model "<applicationId>:<agentId>"; X-Conversation-Id header; temperature is ignored  [docs]
                or REST POST /api/v1/agents/{agentId}/ask {content, skipChatHistory}
                -> {answer, citations[{documentId, sourceUrl, ...}], conversationId, totalTokenCount}  [app client]
    Extractor   POST /api/v1/agents/{agentId}/json/{extractorId}/ask-file?useWebhook=false  multipart `file`
                -> the extracted JSON (shaped by the schema); X-AskFile-Execution-Id header  [docs]
    Library     GET  /api/v1/memories/{libraryId}/documents -> [{id, title, ingestionStatus, ...}]  [docs]
    AI Tools    POST /api/v1/ai-tools/{tool}/run {text, secondaryText, options} -> {tool, output, ...}  [docs]

Paths and header names are env-configurable (EVOLUS_EXECUTE_PATH, EVOLUS_STATUS_PATH, …) so they
can be corrected on site without code changes. Everything Evolus-specific lives in this file.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Awaitable, Callable, Optional

import httpx

from ..config import get_settings, host_of
from ..models import InferenceCall
from . import telemetry
from .hedge import hedged
from .http import async_client

log = logging.getLogger("atelier.evolus")

TERMINAL = {"completed", "failed"}
StatusCallback = Callable[[str, int], Awaitable[None]]


class EvolusError(RuntimeError):
    pass


class EvolusStatusUnknown(EvolusError):
    """QA M3: the workflow was started (it has an execution id) but its status could not be read (poll error /
    timeout). Its emails may already have gone out: callers report "status unknown" and never re-send blindly."""

    def __init__(self, execution_id: str, message: str):
        super().__init__(message)
        self.execution_id = execution_id


def headers() -> dict[str, str]:
    s = get_settings()
    h = {s.evolus_api_key_header: s.evolus_api_key, "Accept": "application/json"}
    if s.evolus_workspace_id:
        h[s.evolus_app_id_header] = s.evolus_workspace_id
    return h


def _url(path: str) -> str:
    return f"{get_settings().evolus_api_base.rstrip('/')}/{path.lstrip('/')}"


def _flatten(params: dict[str, Any]) -> dict[str, Any]:
    """Evolus wants a *flat* object of STRING parameters (verified live 2026-10-16: a number gets 400 "The execution
    parameter 'production_quantity' must be a string"): nested values become JSON strings, numbers and booleans
    their JSON text ("300", "42.5", "true")."""
    out: dict[str, Any] = {}
    for k, v in params.items():
        if v is None:
            continue
        text = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        parts = _chunks(text)
        out[k] = parts[0]
        if len(parts) > 1:  # Evolus rejects a parameter over 500 characters: send `k`, `k__2`, … `k__parts`
            for i, part in enumerate(parts[1:], start=2):
                out[f"{k}__{i}"] = part
            out[f"{k}__parts"] = str(len(parts))
    return out


PARAM_CHUNK = 480  # Evolus: "The execution parameter '…' exceeds 500 characters" (verified live 2026-10-16)


def _chunks(text: str, size: int = PARAM_CHUNK) -> list[str]:
    """Split into pieces of at most `size` characters, never at whitespace (so a trimmed piece loses nothing).
    The workflow script joins `k` + `k__2` + … in order (scripts/provision_evolus_workflows.py)."""
    parts: list[str] = []
    while len(text) > size:
        cut = size
        while cut > 1 and (text[cut - 1].isspace() or text[cut].isspace()):
            cut -= 1
        parts.append(text[:cut])
        text = text[cut:]
    parts.append(text)
    return parts


def default_input_text(params: dict[str, Any]) -> str:
    return "Atelier pipeline request. Payload (JSON):\n" + json.dumps(params, ensure_ascii=False, indent=1)


def _explain(r: httpx.Response) -> str:
    hint = {
        401: "API key rejected (check EVOLUS_API_KEY and EVOLUS_WORKSPACE_ID / X-Application-Id)",
        403: "forbidden (key lacks access to this workspace or workflow)",
        404: "not found (check the workflow id and EVOLUS_API_BASE / paths)",
        402: "out of Evolus platform credits",
        409: "workflow is switched off in Evolus - turn it on",
        429: "rate limited (60 requests/min per workspace)",
    }.get(r.status_code, "")
    body = r.text[:600].replace("\n", " ")
    return f"Evolus HTTP {r.status_code}{' - ' + hint if hint else ''}: {body}"


def _json(r: httpx.Response) -> dict[str, Any]:
    try:
        data = r.json()
    except ValueError:
        return {"raw": r.text[:2000]}
    return data if isinstance(data, dict) else {"result": data}


async def _post_execute(client: httpx.AsyncClient, workflow_id: str, input_text: str,
                        params: Optional[dict[str, Any]]) -> httpx.Response:
    s = get_settings()
    fields: dict[str, tuple[None, str]] = {"input": (None, input_text)}
    if params:
        fields["parameters"] = (None, json.dumps(_flatten(params), ensure_ascii=False))
    url = _url(s.evolus_execute_path.format(workflow_id=workflow_id))
    return await client.post(url, files=fields, headers=headers())  # files= forces multipart/form-data


# The parameters Atelier's email workflows declare (scripts/provision_evolus_workflows.py). Evolus rejects an
# undeclared parameter ("Unknown execution parameter …"), so only these go in `parameters`; the full payload is in
# the `input` text.
EMAIL_WORKFLOW_PARAMS = frozenset({"rfq_emails", "rfq_ref", "kind"})
# What the workflow script reads from each drafted email (the English copy and the language stay in the app).
EMAIL_FIELDS = ("toEmail", "subject", "body", "supplierName", "rfqRef", "kind")


def workflow_emails(emails: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The drafted emails as the email workflows take them: only the fields they send (keeps them small)."""
    return [{k: e[k] for k in EMAIL_FIELDS if e.get(k) is not None} for e in emails]


async def execute_workflow(workflow_id: str, inputs: dict[str, Any], *, input_text: Optional[str] = None,
                           purpose: str = "workflow", on_status: Optional[StatusCallback] = None,
                           wait: bool = True, param_keys: Optional[frozenset[str]] = None) -> dict[str, Any]:
    """Start a workflow run and (by default) poll it to a terminal state.

    Returns a dict: {"executionId", "status" ("Completed" | "Running" | "Pending" | …), "timedOut",
    "polls", "accepted": <202 body>, "execution": <last status body>}. Raises EvolusError on HTTP
    errors or a Failed execution - callers surface it as an error (no fallback).
    """
    s = get_settings()
    timer = telemetry.Timer()
    host = host_of(s.evolus_api_base)
    try:
        params = {k: v for k, v in inputs.items() if k in param_keys} if param_keys is not None else inputs
        result = await _execute(workflow_id, params, input_text or default_input_text(inputs), on_status, wait)
    except Exception as e:  # noqa: BLE001
        telemetry.failed_live(service="evolus", purpose=purpose, model=f"workflow {workflow_id}", host=host,
                              timer=timer, error=f"{e.__class__.__name__}: {e}")
        raise
    telemetry.record(InferenceCall(
        id=telemetry.new_call_id(), service="evolus", purpose=purpose,
        model=f"workflow {workflow_id}", endpoint_host=host, latency_ms=timer.ms,
        detail=f"execution {result['executionId']} · {result['status']}"
               f"{' (still running)' if result['timedOut'] else ''} · {result['polls']} polls",
    ))
    return result


async def _execute(workflow_id: str, inputs: dict[str, Any], input_text: str,
                   on_status: Optional[StatusCallback], wait: bool) -> dict[str, Any]:
    s = get_settings()
    async with async_client(s.atelier_evolus_timeout) as client:
        params = inputs if s.evolus_send_parameters else None
        r = await _post_execute(client, workflow_id, input_text, params)
        if r.status_code in (400, 422) and params:
            first = r
            log.warning("Evolus rejected `parameters` (%s); retrying with `input` only: %s",
                        r.status_code, r.text[:300])
            r = await _post_execute(client, workflow_id, input_text, None)
            if r.status_code >= 400:  # report why the parameters were rejected, not the fallback's error
                raise EvolusError(_explain(first))
        if r.status_code >= 400:
            raise EvolusError(_explain(r))
        accepted = _json(r)
        exec_id = (r.headers.get("X-Workflow-Execution-Id") or accepted.get("executionId")
                   or execution_id(accepted))
        result: dict[str, Any] = {"executionId": exec_id, "status": "Pending" if r.status_code == 202 else "Completed",
                                  "timedOut": False, "polls": 0, "accepted": accepted, "execution": {}}
        if r.status_code != 202:  # a synchronous answer (not documented, but harmless to accept)
            result["execution"] = accepted
            result["status"] = str(find_key(accepted, "status") or "Completed")
            return result
        if not exec_id:
            raise EvolusError("Evolus accepted the run but returned no executionId")
        if not wait:
            return result
        status_url = _url(s.evolus_status_path.format(workflow_id=workflow_id, execution_id=exec_id))
        deadline = time.monotonic() + max(0.0, s.evolus_poll_timeout)
        last = ""
        while True:
            await asyncio.sleep(max(0.05, s.evolus_poll_interval))
            try:
                pr = await client.get(status_url, headers=headers())
            except httpx.HTTPError as e:  # QA M3: started, outcome unknown
                raise EvolusStatusUnknown(str(exec_id), f"Evolus execution {exec_id} started, but its status could "
                                                        f"not be read ({e.__class__.__name__})") from e
            result["polls"] += 1
            if pr.status_code == 429:  # back off politely, keep polling
                await asyncio.sleep(max(1.0, s.evolus_poll_interval * 2))
            elif pr.status_code >= 400:
                raise EvolusStatusUnknown(str(exec_id), f"Evolus execution {exec_id} started, but its status could "
                                                        f"not be read: {_explain(pr)}")
            else:
                body = _json(pr)
                result["execution"] = body
                status = str(body.get("status") or find_key(body, "status", "state") or "Running")
                result["status"] = status
                if on_status and status != last:
                    await on_status(status, result["polls"])
                last = status
                if status.lower() in TERMINAL:
                    if status.lower() == "failed":
                        err = find_key(body, "error", "errorMessage", "message", "reason")
                        raise EvolusError(f"Evolus execution {exec_id} failed: {str(err or 'no error detail')[:200]}")
                    return result
            if time.monotonic() >= deadline:
                result["timedOut"] = True
                log.warning("Evolus execution %s still %s after %.0fs; not waiting any longer",
                            exec_id, result["status"], s.evolus_poll_timeout)
                return result


async def probe() -> tuple[bool, str, float]:
    """Cheap authenticated GET (EVOLUS_PROBE_PATH). Returns (ok, detail, latency ms)."""
    s = get_settings()
    t = telemetry.Timer()
    try:
        async with async_client(s.atelier_health_timeout) as c:
            r = await c.get(_url(s.evolus_probe_path), headers=headers())
    except Exception as e:  # noqa: BLE001
        return False, f"{host_of(s.evolus_api_base)} · unreachable: {e.__class__.__name__}", t.ms
    if r.status_code < 400:
        return True, f"{host_of(s.evolus_api_base)} · authenticated", t.ms
    return False, _explain(r)[:160], t.ms


async def chat_agent(model: str, message: str) -> tuple[str, dict[str, Any]]:
    """Talk to an Evolus agent via the OpenAI-compatible endpoint (sync; used by scripts/check_evolus.py)."""
    s = get_settings()
    async with async_client(s.atelier_evolus_timeout) as c:
        r = await c.post(f"{s.chat_base}{s.evolus_chat_path}",
                         headers={"Authorization": f"Bearer {s.evolus_api_key}"},
                         json={"model": model, "messages": [{"role": "user", "content": message}]})
    if r.status_code >= 400:
        raise EvolusError(_explain(r))
    data = _json(r)
    try:
        text = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        text = ""
    return text, {"conversationId": r.headers.get("X-Conversation-Id"), "raw": data}


async def list_agents() -> list[str]:
    s = get_settings()
    async with async_client(s.atelier_evolus_timeout) as c:
        r = await c.get(f"{s.chat_base}/v1/models", headers={"Authorization": f"Bearer {s.evolus_api_key}"})
    if r.status_code >= 400:
        raise EvolusError(_explain(r))
    return [str(m.get("id")) for m in _json(r).get("data", []) if isinstance(m, dict) and m.get("id")]


# --------------------------------------------------------------------------- v3: the agent as the brain


def agent_id() -> str:
    """"<applicationId>:<agentId>" -> agentId (the REST API takes the agent id alone)."""
    m = get_settings().evolus_agent_model.strip()
    return m.split(":", 1)[1] if ":" in m else m


def _chat_headers() -> dict[str, str]:
    s = get_settings()
    return {"Authorization": f"Bearer {s.evolus_api_key}", "Accept": "application/json"}


def _flatten_messages(messages: list[dict]) -> str:
    """Evolus chat content is plain text; the REST /ask takes one `content` string."""
    parts = []
    for m in messages:
        c = m.get("content")
        text = c if isinstance(c, str) else " ".join(p.get("text", "") for p in c or [] if isinstance(p, dict))
        parts.append(text if m.get("role") == "user" else f"[{m.get('role', 'system')} instructions]\n{text}")
    return "\n\n".join(parts)


_doc_titles: dict[str, str] = {}


def library_headers() -> dict[str, str]:
    """Library ("memories") calls: the app key (verified live 2026-10-16: it lists and uploads documents, while a
    personal key gets 401 "missing the required scope: Api" on REST); the personal key only when no app key is set."""
    s = get_settings()
    if s.evolus_user_api_key and not s.evolus_api_key:
        return {"X-User-ApiKey": s.evolus_user_api_key, s.evolus_app_id_header: s.evolus_workspace_id,
                "Accept": "application/json"}
    return headers()


async def library_documents(client: Optional[httpx.AsyncClient] = None) -> list[dict[str, Any]]:
    """GET /api/v1/memories/{libraryId}/documents -> [{id, title, ingestionStatus, chunkCount, ...}]."""
    s = get_settings()
    own = client is None
    c = client or async_client(s.atelier_evolus_timeout)
    try:
        r = await c.get(_url(f"/api/v1/memories/{s.evolus_library_id}/documents"), headers=library_headers())
    finally:
        if own:
            await c.aclose()
    if r.status_code >= 400:
        raise EvolusError(_explain(r))
    data = r.json()
    items = data if isinstance(data, list) else (find_key(data, "items", "documents", "data", "value") or [])
    docs = [d for d in items if isinstance(d, dict)]
    for d in docs:
        if d.get("id") is not None:
            _doc_titles[str(d["id"])] = str(d.get("title") or d.get("name") or d.get("fileName") or d["id"])
    return docs


async def _citations(raw: Any) -> list[Any]:
    """REST /ask `citations[]` -> Citation(library="evolus"), titled from the library's document list."""
    from ..models import Citation

    items = find_key(raw, "citations", "sources") if isinstance(raw, dict) else None
    if not isinstance(items, list) or not items:
        return []
    s = get_settings()
    if s.evolus_library_id and not _doc_titles:
        try:
            await library_documents()
        except Exception as e:  # noqa: BLE001
            log.info("could not list library documents for citation titles: %s", e)
    out = []
    for it in items[:8]:
        if not isinstance(it, dict):
            continue
        doc = str(it.get("documentId") or it.get("id") or "")
        title = _doc_titles.get(doc) or it.get("title") or it.get("sourceUrl") or (f"library document {doc}" if doc else "")
        if not title:
            continue
        snippet = it.get("textToReplace") or it.get("text") or it.get("snippet")
        if all(o.source != title for o in out):
            out.append(Citation(source=str(title), snippet=str(snippet)[:400] if snippet else None, library="evolus",
                                document_id=doc or None))
    return out


async def agent_chat_json(*, messages_for_attempt: Callable[[int], list[dict]], validate: Callable[[Any], Any],
                          purpose: str, max_tokens: int = 1500, temperature: float = 0.4,
                          attempts: int = 2) -> tuple[Any, dict[str, Any]]:
    """Ask the Evolus agent (whose model is our AMD vLLM endpoint) for JSON; validate; retry once.

    Every attempt is recorded in telemetry as service "llm", route "evolus-agent → AMD vLLM".
    Returns (validated value, {"citations": [...], "conversationId": ...}). Raises on failure.
    """
    from .openai_compat import extract_json

    s = get_settings()
    model = s.evolus_agent_model.strip()
    rest = s.evolus_agent_transport.strip().lower() == "rest"
    host = host_of(s.evolus_api_base if rest else s.chat_base)
    on = s.evolus_agent_label or s.amd_vllm_model or s.evolus_agent_backend
    last: Exception | None = None
    async with async_client(s.evolus_agent_timeout) as client:
        for attempt in range(attempts):
            timer = telemetry.Timer()
            usage: dict | None = None
            conv = None
            try:
                msgs = messages_for_attempt(attempt)
                if rest:
                    url = _url(s.evolus_ask_path.format(agent_id=agent_id()))
                    req = {"headers": headers(), "json": {"content": _flatten_messages(msgs), "skipChatHistory": True}}
                else:
                    # Message content must be text; temperature etc. are not applied by Evolus (sent anyway:
                    # harmless, and correct if that changes).
                    url = f"{s.chat_base}{s.evolus_chat_path}"
                    req = {"headers": _chat_headers(), "json": {"model": model, "messages": [
                        {"role": m.get("role", "user"), "content": m.get("content") if isinstance(
                            m.get("content"), str) else _flatten_messages([m])} for m in msgs],
                        "max_tokens": max_tokens, "temperature": temperature, "stream": False}}

                async def send(url: str = url, req: dict = req) -> httpx.Response:
                    r = await client.post(url, **req)
                    if r.status_code >= 400:  # inside the hedge: an error reply must not beat a request still running
                        raise EvolusError(_explain(r))
                    return r

                r = await hedged(send, after=s.atelier_hedge_brain_after, label=f"evolus-agent/{purpose}")
                data = _json(r)
                conv = r.headers.get("X-Conversation-Id") or data.get("conversationId")
                if rest:
                    text = str(data.get("answer") or "")
                    tok = data.get("totalTokenCount")
                    usage = {"total_tokens": tok} if isinstance(tok, int) else None
                else:
                    try:
                        text = data["choices"][0]["message"]["content"] or ""
                    except (KeyError, IndexError, TypeError):
                        text = ""
                    usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
                value = validate(extract_json(text))
            except Exception as e:  # noqa: BLE001
                last = e
                telemetry.live_llm_call(service="llm", purpose=purpose, model=model, host=host, timer=timer,
                                        usage=usage, ok=False, attempt=attempt + 1, route=f"evolus-agent → {s_backend()}",
                                        error=f"{e.__class__.__name__}: {e}", detail=f"agent on {on}")
                log.warning("evolus agent %s attempt %d/%d failed: %s", purpose, attempt + 1, attempts, e)
                if _no_retry(e):  # QA M12: timeouts / connection / server errors fail fast (no second wait)
                    break
                continue
            telemetry.live_llm_call(service="llm", purpose=purpose, model=model, host=host, timer=timer, usage=usage,
                                    ok=True, attempt=attempt + 1, route=f"evolus-agent → {s_backend()}",
                                    detail=f"agent on {on} · {'REST /ask' if rest else '/v1/chat/completions'}"
                                           + (f" · conversation {conv}" if conv else ""))
            return value, {"citations": await _citations(data), "conversationId": conv}
    assert last is not None
    raise last


def _no_retry(e: BaseException) -> bool:
    from .openai_compat import no_retry

    return no_retry(e) or (isinstance(e, EvolusError) and bool(re.match(r"Evolus HTTP 5\d\d", str(e))))


# --------------------------------------------------------------------------- v3: document extractor


async def run_extractor(data: bytes, filename: str, content_type: str) -> dict[str, Any]:
    """Run the Evolus document extractor on one file (synchronously: ?useWebhook=false).

    Returns {"fields": <extracted JSON>, "extractionId", "confidence": None (Evolus reports none)}.
    """
    s = get_settings()
    timer = telemetry.Timer()
    host = host_of(s.evolus_api_base)
    label = f"extractor {s.evolus_extractor_id}"
    url = _url(s.evolus_extract_path.format(agent_id=s.evolus_extractor_agent_id, extractor_id=s.evolus_extractor_id))
    try:
        async with async_client(s.atelier_extractor_timeout) as c:
            r = await c.post(url, headers=headers(),
                             files={"file": (filename or "quote.pdf", data, content_type or "application/pdf")})
        if r.status_code >= 400:
            raise EvolusError(_explain(r))
        body: Any
        try:
            body = r.json()
        except ValueError:
            body = r.text
        if isinstance(body, dict) and isinstance(body.get("output"), str):  # an execution record, not raw data
            body = _maybe_json(body["output"])
        exec_id = r.headers.get("X-AskFile-Execution-Id")
    except Exception as e:  # noqa: BLE001
        telemetry.failed_live(service="evolus", purpose="quote_extraction", model=label, host=host, timer=timer,
                              error=f"{e.__class__.__name__}: {e}", route="evolus-extractor")
        raise
    telemetry.record(InferenceCall(
        id=telemetry.new_call_id(), service="evolus", purpose="quote_extraction",
        model=label, endpoint_host=host, latency_ms=timer.ms, route="evolus-extractor",
        detail=f"{filename} · execution {exec_id or '?'}"))
    return {"fields": body, "extractionId": exec_id, "confidence": None}


# --------------------------------------------------------------------------- v3: AI Tools


async def run_ai_tool(tool: str, text: str, options: Optional[dict[str, Any]] = None, *,
                      secondary_text: Optional[str] = None, purpose: str = "ai_tool") -> str:
    """POST /api/v1/ai-tools/{tool}/run -> output text (e.g. tool "email", options {"mode": "write"})."""
    s = get_settings()
    timer = telemetry.Timer()
    host = host_of(s.evolus_api_base)
    body: dict[str, Any] = {"text": text, "options": options or {}}
    if secondary_text:
        body["secondaryText"] = secondary_text
    try:
        async with async_client(s.atelier_evolus_timeout) as c:
            r = await c.post(_url(f"/api/v1/ai-tools/{tool}/run"), headers=headers(), json=body)
        if r.status_code >= 400:
            raise EvolusError(_explain(r))
        data = _json(r)
        out = str(data.get("output") or "")
        if not out:
            raise EvolusError(f"AI Tool {tool} returned no output")
    except Exception as e:  # noqa: BLE001
        telemetry.failed_live(service="evolus", purpose=purpose, model=f"ai-tool {tool}", host=host, timer=timer,
                              error=f"{e.__class__.__name__}: {e}", route="evolus-ai-tool")
        raise
    telemetry.record(InferenceCall(
        id=telemetry.new_call_id(), service="evolus", purpose=purpose,
        model=f"ai-tool {tool}", endpoint_host=host, latency_ms=timer.ms, route="evolus-ai-tool",
        detail=f"{data.get('creditsConsumed', '?')} credits"))
    return out


# --------------------------------------------------------------------------- lenient parsing


def find_key(obj: Any, *keys: str) -> Any:
    """Breadth-first search for the first non-empty value under any of `keys`."""
    wanted = {k.lower() for k in keys}
    stack = [obj]
    while stack:
        cur = stack.pop(0)
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k.lower() in wanted and v not in (None, "", [], {}):
                    return v
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def _find_all(obj: Any, *keys: str) -> list[Any]:
    wanted = {k.lower() for k in keys}
    out, stack = [], [obj]
    while stack:
        cur = stack.pop(0)
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k.lower() in wanted and isinstance(v, (str, bool)):
                    out.append(v)
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return out


def _maybe_json(v: Any) -> Any:
    """Workflow outputs are often JSON serialised into a string; parse it when we can."""
    if isinstance(v, str) and v.strip()[:1] in ("{", "["):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def _expand(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _expand(_maybe_json(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand(_maybe_json(v)) for v in obj]
    return _maybe_json(obj)


def execution_id(resp: dict) -> str | None:
    v = find_key(resp, "executionId", "execution_id", "runId", "run_id", "id")
    return str(v) if v is not None else None


def parse_shopify(resp: dict) -> dict[str, str | None]:
    resp = _expand(resp.get("execution") or resp) if isinstance(resp, dict) else resp
    product = find_key(resp, "product", "shopifyProduct", "shopify_product")
    scope = product if isinstance(product, dict) else resp
    pid = find_key(scope, "productId", "product_id", "admin_graphql_api_id", "shopifyProductId")
    if pid is None and isinstance(product, dict):
        pid = product.get("id")
    url = find_key(scope, "productUrl", "product_url", "onlineStoreUrl", "online_store_url", "url")
    handle = find_key(scope, "handle")
    if handle is None and isinstance(url, str):
        m = re.search(r"/products/([^/?#]+)", url)
        handle = m.group(1) if m else None
    return {"productId": str(pid) if pid is not None else None,
            "url": str(url) if url is not None else None,
            "handle": str(handle) if handle is not None else None}


def outreach_status(resp: dict) -> str:
    """"sent" only if the run's output says the emails went out; a Completed run alone means "queued"."""
    values = _find_all(_expand(resp), "emailStatus", "deliveryStatus", "status", "state")
    if any(isinstance(v, str) and v.lower() in ("sent", "delivered") for v in values):
        return "sent"
    if any(v is True for v in _find_all(_expand(resp), "sent", "emailsSent", "delivered")):
        return "sent"
    return "queued"


def s_backend() -> str:
    """Where the agent's own model is served (EVOLUS_AGENT_BACKEND), for the telemetry route."""
    return get_settings().evolus_agent_backend
