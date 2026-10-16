"""TEST DOUBLES ONLY - local stand-ins for the real upstreams, to test the code paths without GPUs or credentials.

This file lives under backend/tests/ and is not part of the app image. It is never a "live" service: every response
carries the header `X-Atelier-Fake-Upstream: 1`, and Atelier's /api/health then reports the endpoint as
"FAKE UPSTREAM - not real" (in red in the dashboard) and never shows the AMD / Evolus credits for it.

    uv run python tests/fake_upstreams.py            # vLLM :18900, diffusion :18901, Evolus :18902,
                                                     # Shopify dev store :18903
    uv run python tests/fake_upstreams.py --atelier-url http://localhost:8787 --webhook-secret s3cret
        # + a fake inbound mailbox: POST a quote PDF to :18902/fake/inbound-email -> extractor -> webhook

They follow the same wire formats as the real things (OpenAI-compatible vLLM incl. streaming + usage;
deploy/diffusion_server.py; the Evolus REST API from evolus.ai/developers), but every response is canned.
Numbers they produce are NOT measurements of anything - they only prove the plumbing works.

Tests use the same apps in-process via `RoutingTransport` (no sockets).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import re
import secrets
import struct
import time
import zlib
from html import escape as html_escape
from typing import Any

import httpx
from fastapi import FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

FAKE_DEVICE = "FAKE-GPU (local test double)"
FAKE_HEADER = "X-Atelier-Fake-Upstream"


def mark_fake(app: FastAPI) -> FastAPI:
    """Every response of a fake says so (Atelier's health check reads this header)."""

    @app.middleware("http")
    async def _marker(request: Request, call_next):
        response = await call_next(request)
        response.headers[FAKE_HEADER] = "1"
        return response

    return app


def tiny_png(rgb: tuple[int, int, int] = (200, 180, 150)) -> bytes:
    raw = b"\x00" + bytes(rgb)
    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


# --------------------------------------------------------------------------- canned model replies

TECHPACK = {
    "garmentName": "Fake Test Jacket", "description": "Canned tech pack from the local fake vLLM server.",
    "billOfMaterials": [
        {"material": "Selvedge denim shell", "quantity": "2.4 m", "targetCostPerUnit": 42.0},
        {"material": "Cupro lining", "quantity": "1.6 m", "targetCostPerUnit": 12.2},
        {"material": "Shank buttons", "quantity": "8 pcs", "targetCostPerUnit": 2.8},
        {"material": "CMT", "quantity": "1 unit", "targetCostPerUnit": 38.0},
    ],
    "measurements": {"chest": "46in", "shoulder": "19.5in", "body length": "28in", "sleeve": "25in"},
    "targetSupplierRegion": "fake region", "targetRetailPrice": 389,
}
TREND = {
    "trendName": "Fake Indigo Utility", "summary": "Canned trend from the local fake VLM.",
    "garmentType": "jacket", "coreSilhouettes": ["boxy", "cropped"], "colorPalette": ["#1F2A44", "#C9B79C", "#E8E1D3"],
    "keyFabrics": ["selvedge denim", "cotton twill"], "commercialViabilityScore": 77,
}


def _reply_for(messages: list[dict]) -> str:
    text = ""
    has_image = False
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            text += c
        elif isinstance(c, list):
            for part in c:
                if part.get("type") == "text":
                    text += part.get("text", "")
                if part.get("type") == "image_url":
                    has_image = True
    low = text.lower()
    if has_image:
        return json.dumps(TREND)
    if "write a counter-offer email" in low:  # v4/v5: state the facts the prompt gives, in the mill's language
        ref = (re.search(r"'rfqReference': '([^']+)'", text) or re.search(r"(ATL-run_[0-9a-f]+)", text))
        qn = re.search(r"'quoteNumber': '([^']+)'", text)
        tgt = re.search(r"'price': \{'target_(?:usd|brand)': [\d.]+, (?:'brand_currency': '\w*', )?'target_local': ([\d.]+)", text) or \
            re.search(r"'price': \(([\d.]+)", text)
        lang = re.search(r"in (Italian|Portuguese|English) \(formal", text)
        facts = " ".join(x for x in [f"{float(tgt.group(1)):.2f}" if tgt else "", qn.group(1) if qn else "",
                                     ref.group(1) if ref else ""] if x)
        local = {"Italian": "Gentile team, grazie per la vostra offerta. Per il nostro ordine siamo in grado di "
                            "procedere a queste condizioni, con la stessa quantità: {f}. Cordiali saluti.",
                 "Portuguese": "Caros colegas, obrigado pela vossa cotação. Para o nosso pedido conseguimos avançar "
                               "com esta condição, mantendo a quantidade: {f}. Com os melhores cumprimentos."}
        en = ("Dear team, thank you for your quote. We can proceed with our order at this price, keeping the "
              "quantity and specification: {f}. Kind regards, Atelier Sourcing Agent (fake model)")
        body = local.get(lang.group(1) if lang else "English", en).format(f=facts)
        return json.dumps({"subject": f"Counter-proposal (fake model) [{ref.group(1) if ref else ''}]",
                           "body": body, "subjectEnglish": "Counter-proposal (fake model)",
                           "bodyEnglish": en.format(f=facts)})
    if "plan a coherent" in low:
        n = int((re.search(r"coherent (\d)-piece", low) or re.search(r"(\d)", "4")).group(1))
        kinds = ["jacket", "wide-leg trousers", "ribbed knit top", "longline coat", "column skirt"]
        return json.dumps({"name": "Fake Capsule", "story": "Canned collection story from the fake model. Second "
                           "sentence.", "pieces": [{"garmentType": kinds[i % 5], "fabric": "", "note":
                                                    f"Canned look {i + 1} (fake model)"} for i in range(n)]})
    if "turning customer feedback into tech-pack changes" in low:
        ids = re.findall(r'"id": "(chg_[a-z_]+)"', text)
        return json.dumps({"summary": "Canned summary of the customer findings (fake model).",
                           "rationales": {i: "Canned rationale (fake model)." for i in ids},
                           "instructions": {i: "Canned instruction: to be confirmed on the fit sample (fake model)."
                                            for i in ids}})
    if "translate this note" in low:
        return json.dumps({"english": "Canned English translation of the mill's note (fake model)."})
    if "rfq" in low and "language" in low and "supplierName" in text and "tech pack" in low:
        sups = []
        for line in text.splitlines():
            if line.strip().startswith("[") and "supplierName" in line:
                try:
                    sups = json.loads(line.strip())
                except ValueError:
                    pass
        canned = {"Italian": "Gentile team di {n}, questo è il testo di prova della richiesta di offerta per il "
                             "nostro modello. Cordiali saluti.",
                  "Portuguese": "Caros colegas da {n}, este é o texto de teste do pedido de cotação para o nosso "
                                "modelo. Com os melhores cumprimentos."}
        out = []
        for x in sups or [{"supplierName": "Supplier", "language": "English"}]:
            lang, n = x.get("language", "English"), x["supplierName"]
            en = f"Dear {n} team, this is the canned RFQ body. Kind regards."
            out.append({"supplierName": n, "language": lang, "subject": f"RFQ for {n}",
                        "body": canned.get(lang, en).format(n=n), "subjectEnglish": f"RFQ for {n}", "bodyEnglish": en})
        return json.dumps({"emails": out, "sources": [1]})
    if "creative director says" in low:
        return json.dumps({"interpretation": "I'll deepen the palette and crop the body (canned).",
                           "promptAdditions": ["deeper palette"], "promptRemovals": [],
                           "paletteAfter": ["#101418", "#3A3F47", "#8A8F96"], "fabricsAfter": [],
                           "silhouetteChanges": ["cropped"], "techPackHints": ["Shorten body length 4cm"],
                           "references": [], "sources": [1]})
    if "explain why" in low:
        return json.dumps({"rationale": "Canned rationale: best weighted score on price, MOQ fit and lead time.",
                           "sources": [1]})
    if "document text:" in low:  # quote extraction over PDF text: copy what the document says, nothing else
        doc = text.split("Document text:", 1)[-1]
        fields = fake_extract_text(doc)
        keys = {"supplier_name": "supplierName", "quote_number": "quoteNumber", "rfq_reference": "rfqReference",
                "currency": "currency", "unit_price": "unitPrice", "moq": "moq", "lead_time": "leadTime",
                "sample_cost": "sampleCost", "payment_terms": "paymentTerms", "valid_until": "validUntil",
                "notes": "notes"}
        return json.dumps({"fields": {keys[k]: v for k, v in fields.items() if k in keys}})
    if "tech pack" in low and "rfq" not in low:
        return json.dumps({**TECHPACK, "constructionNotes": ["Canned construction note from the fake model."],
                           "sources": [1, 2]})
    if "rfq" in low:
        names = []
        for line in text.splitlines():
            if line.strip().startswith("[") and "supplierName" in line:
                try:
                    names = [x["supplierName"] for x in json.loads(line.strip())]
                except ValueError:
                    pass
        names = names or ["Supplier"]
        return json.dumps([{"supplierName": n, "subject": f"RFQ for {n}", "body": "Canned RFQ body."} for n in names])
    return json.dumps({"ok": True, "echo": text[-80:]})


# v6: the default plan serves Gemma 4, so the double reports a gemma-4 id - prefixed "fake/" so it can never be
# mistaken for the real model (and /api/health marks it FAKE anyway).
FAKE_LLM_MODEL = "fake/gemma-4-26B-A4B-it"
# What Gemma 4 emits when thinking leaks into `content` (vllm-project/vllm#39043).
LEAKED_THOUGHT = "<|channel>thought\nThe user wants JSON. {Let me} draft it [carefully].<channel|>"


def _fake_tool_call(tool: dict) -> dict:
    """A tool call for the first tool offered: every required parameter filled with a canned value."""
    fn = tool.get("function") or {}
    props = (fn.get("parameters") or {}).get("properties") or {}
    required = (fn.get("parameters") or {}).get("required") or list(props)
    args = {k: (1 if (props.get(k) or {}).get("type") in ("number", "integer") else "fake") for k in required}
    return {"id": f"call_{secrets.token_hex(4)}", "type": "function",
            "function": {"name": fn.get("name", "tool"), "arguments": json.dumps(args)}}


def create_openai_app(api_key: str = "", model: str = FAKE_LLM_MODEL, delay: float = 0.0,
                      leak_reasoning: bool = False) -> FastAPI:
    """Fake vLLM. Tool calling: offered `tools` and no tool result yet -> a tool call (finish_reason
    "tool_calls"); after a `tool` message -> a plain answer quoting it. `leak_reasoning` prefixes every answer
    with a Gemma 4 thought block, as a server without a working reasoning parser would. Requests are kept in
    `app.state.requests` for assertions."""
    app = FastAPI(title="fake vLLM")
    app.state.requests = []

    def auth(authorization: str | None) -> None:
        if api_key and authorization != f"Bearer {api_key}":
            raise HTTPException(401, "bad key")

    @app.get("/v1/models")
    async def models(authorization: str | None = Header(None)):
        auth(authorization)
        return {"object": "list", "data": [{"id": model, "object": "model", "owned_by": "fake"}]}

    @app.post("/v1/chat/completions")
    async def chat(request: Request, authorization: str | None = Header(None)):
        auth(authorization)
        body = await request.json()
        app.state.requests.append(body)
        msgs = body.get("messages", [])
        if body.get("tools") and not any(m.get("role") == "tool" for m in msgs):
            call = _fake_tool_call(body["tools"][0])
            usage = {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}
            return {"id": f"chatcmpl-{secrets.token_hex(4)}", "object": "chat.completion",
                    "created": int(time.time()), "model": body.get("model"),
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": None, "tool_calls": [call]},
                                 "finish_reason": "tool_calls"}], "usage": usage}
        tool_result = next((m.get("content") for m in reversed(msgs) if m.get("role") == "tool"), None)
        if tool_result is not None:
            content = f"Canned answer from the tool result (fake model): {str(tool_result)[:80]}"
        else:
            content = _reply_for(msgs)
        if leak_reasoning:
            content = LEAKED_THOUGHT + "\n" + content
        # 1 "token" per 4 chars - a canned count, not a real tokenizer.
        pt = sum(len(json.dumps(m.get("content", ""))) for m in body.get("messages", [])) // 4
        ct = max(1, len(content) // 4)
        usage = {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct}
        cid = f"chatcmpl-{secrets.token_hex(4)}"
        if delay:
            await asyncio.sleep(delay)
        if not body.get("stream"):
            return {"id": cid, "object": "chat.completion", "created": int(time.time()), "model": body.get("model"),
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                                 "finish_reason": "stop"}], "usage": usage}

        async def events():
            base = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": body.get("model")}
            for i in range(0, len(content), 24):
                yield "data: " + json.dumps({**base, "choices": [{"index": 0, "delta": {"content": content[i:i + 24]},
                                                                  "finish_reason": None}]}) + "\n\n"
            yield "data: " + json.dumps({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}) + "\n\n"
            if (body.get("stream_options") or {}).get("include_usage"):
                yield "data: " + json.dumps({**base, "choices": [], "usage": usage}) + "\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    return mark_fake(app)


def create_diffusion_app(model: str = "fake/fake-diffusion") -> FastAPI:
    app = FastAPI(title="fake diffusion")

    @app.get("/health")
    async def health():
        return {"status": "ok", "model": model, "device": FAKE_DEVICE}

    @app.post("/generate")
    async def generate(request: Request):
        body = await request.json()
        if not body.get("prompt"):
            raise HTTPException(422, "prompt required")
        return {"images": [base64.b64encode(tiny_png()).decode()], "model": model, "device": FAKE_DEVICE,
                "elapsedMs": 12.5, "steps": 4, "seed": body.get("seed")}

    return mark_fake(app)


def create_evolus_app(api_key: str = "test-key", app_id: str = "app_test", polls_until_done: int = 2,
                      fail: bool = False, reject_parameters: bool = False, agent_down: bool = False,
                      webhook_url: str = "", webhook_secret: str = "") -> FastAPI:
    """Fake of the documented Evolus API: workflows (execute -> 202, poll), agent chat (OpenAI-compatible and
    REST /ask with citations), knowledge libraries, the document extractor (ask-file), AI Tools, and the
    provisioning endpoints. Shapes: docs/EVOLUS_API_NOTES.md."""
    app = FastAPI(title="fake Evolus")
    executions: dict[str, dict[str, Any]] = {}
    app.state.executions = executions

    def auth(x_apikey: str | None, x_application_id: str | None) -> None:
        if x_apikey != api_key or x_application_id != app_id:
            raise HTTPException(401, "invalid api key or application id")

    @app.get("/api/v1/ai-tools")
    async def tools(x_apikey: str | None = Header(None), x_application_id: str | None = Header(None)):
        auth(x_apikey, x_application_id)
        return [{"tool": "email"}, {"tool": "summarize"}]

    @app.post("/api/v1/workflows/{workflow_id}/execute", status_code=202)
    async def execute(workflow_id: str, input: str = Form(""), parameters: str | None = Form(None),
                      x_apikey: str | None = Header(None), x_application_id: str | None = Header(None)):
        auth(x_apikey, x_application_id)
        if workflow_id == "wf_off":
            raise HTTPException(409, "workflow is disabled")
        if parameters is not None and reject_parameters:
            raise HTTPException(400, "unknown parameter")
        params = json.loads(parameters) if parameters else {}
        if any(isinstance(v, (dict, list)) for v in params.values()):
            raise HTTPException(400, "parameters must be a flat object")
        for k, v in params.items():  # like Evolus: a parameter holds at most 500 characters
            if isinstance(v, str) and len(v) > 500:
                raise HTTPException(400, f"The execution parameter '{k}' exceeds 500 characters.")
        for k in [k for k in params if k.endswith("__parts")]:  # join pieces, like the workflow script does
            base = k[: -len("__parts")]
            params[base] = params.get(base, "") + "".join(params.get(f"{base}__{i}", "")
                                                          for i in range(2, int(params[k]) + 1))
        eid = f"exe_{secrets.token_hex(3)}"
        executions[eid] = {"workflow": workflow_id, "input": input, "parameters": params, "polls": 0}
        return JSONResponse({"jobId": f"job_{eid}", "executionId": eid, "enqueuedAt": "2026-10-12T00:00:00Z",
                             "traceId": "t"}, status_code=202, headers={"X-Workflow-Execution-Id": eid})

    @app.get("/api/v1/workflows/{workflow_id}/executions/{eid}")
    async def status(workflow_id: str, eid: str, x_apikey: str | None = Header(None),
                     x_application_id: str | None = Header(None)):
        auth(x_apikey, x_application_id)
        ex = executions.get(eid)
        if ex is None:
            raise HTTPException(404, "execution not found")
        ex["polls"] += 1
        if ex["polls"] < polls_until_done:
            return {"executionId": eid, "status": "Running"}
        if fail:
            return {"executionId": eid, "status": "Failed", "error": "step 2 (send email) failed"}
        params = ex["parameters"]
        output: dict[str, Any] = {"summary": "done"}
        if "title" in params:
            handle = params.get("handle") or "fake-product"
            output = {"product": {"id": "gid://shopify/Product/4242", "handle": handle,
                                  "onlineStoreUrl": f"https://fake-shop.test/products/{handle}"}}
        elif "rfq_emails" in params:
            output = {"emailStatus": "sent", "count": len(json.loads(params["rfq_emails"]))}
            if params.get("kind") == "purchase_order":
                output["poNumber"] = params.get("po_number")
        return {"executionId": eid, "status": "Completed", "output": json.dumps(output)}

    @app.get("/v1/models")
    async def agents(authorization: str | None = Header(None)):
        if authorization != f"Bearer {api_key}":
            raise HTTPException(401, "bad key")
        return {"object": "list", "data": [{"id": f"{app_id}:agent_sourcing", "object": "model"}]}

    @app.post("/v1/chat/completions")
    async def agent_chat(request: Request, authorization: str | None = Header(None)):
        if authorization != f"Bearer {api_key}":
            raise HTTPException(401, "bad key")
        body = await request.json()
        model = str(body.get("model") or "")
        if ":" not in model:
            return JSONResponse({"error": {"message": "Invalid model format. Expected: {applicationId}:{agentId}",
                                           "type": "invalid_request_error", "param": "model"}}, status_code=400)
        if agent_down:
            return JSONResponse({"error": {"message": "agent model endpoint unreachable", "type": "server_error"}},
                                status_code=502)
        msgs = body.get("messages", [])
        if any(not isinstance(m.get("content"), str) for m in msgs):
            return JSONResponse({"error": {"message": "content must be text", "type": "invalid_request_error"}},
                                status_code=400)
        app.state.chat_calls.append(body)
        last = msgs[-1]["content"] if msgs else ""
        content = "pong" if "single word" in last else _reply_for(msgs)
        n = max(1, len(content) // 4)
        return JSONResponse({"id": "c", "object": "chat.completion", "model": model,
                             "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                                          "finish_reason": "stop"}],
                             "usage": {"prompt_tokens": 100, "completion_tokens": n, "total_tokens": 100 + n}},
                            headers={"X-Conversation-Id": f"conv_{secrets.token_hex(2)}"})

    # ---- v3: REST agent chat with citations, libraries, extractor, AI Tools, provisioning ------------------
    app.state.chat_calls = []
    app.state.documents = {"lib_1": [{"id": "doc_brand", "title": "Fake library - Brand Book",
                                      "ingestionStatus": 2, "chunkCount": 24},
                                     {"id": "doc_suppliers", "title": "Fake library - Supplier Catalogue",
                                      "ingestionStatus": 2, "chunkCount": 18}]}
    app.state.created = []
    app.state.extractions = []

    def rest_auth(x_apikey: str | None, x_application_id: str | None, x_user_apikey: str | None = None) -> None:
        if x_user_apikey == api_key and x_application_id == app_id:
            return
        auth(x_apikey, x_application_id)

    @app.post("/api/v1/agents/{agent_id}/ask")
    async def ask(agent_id: str, request: Request, x_apikey: str | None = Header(None),
                  x_application_id: str | None = Header(None)):
        rest_auth(x_apikey, x_application_id)
        body = await request.json()
        content = str(body.get("content") or "")
        answer = _reply_for([{"role": "user", "content": content}])
        return {"agentId": agent_id, "answer": answer, "conversationId": f"conv_{secrets.token_hex(2)}",
                "question": content[:80], "totalTokenCount": 321,
                "citations": [{"documentId": "doc_brand", "sourceUrl": None, "startIndex": 0, "endIndex": 10,
                               "textToReplace": "Fit blocks (sample size M)"}]}

    @app.get("/api/v1/memories")
    async def memories(x_apikey: str | None = Header(None), x_application_id: str | None = Header(None),
                       x_user_apikey: str | None = Header(None)):
        rest_auth(x_apikey, x_application_id, x_user_apikey)
        return [{"id": k, "name": f"Library {k}"} for k in app.state.documents]

    @app.post("/api/v1/memories/simple", status_code=201)
    async def create_memory(request: Request, x_apikey: str | None = Header(None),
                            x_application_id: str | None = Header(None), x_user_apikey: str | None = Header(None)):
        rest_auth(x_apikey, x_application_id, x_user_apikey)
        body = await request.json()
        mid = f"lib_{secrets.token_hex(2)}"
        app.state.documents[mid] = []
        app.state.created.append(("memory", body))
        return {"id": mid, "name": body.get("name")}

    @app.get("/api/v1/memories/{library_id}/documents")
    async def list_docs(library_id: str, x_apikey: str | None = Header(None),
                        x_application_id: str | None = Header(None), x_user_apikey: str | None = Header(None)):
        rest_auth(x_apikey, x_application_id, x_user_apikey)
        if library_id not in app.state.documents:
            raise HTTPException(404, "library not found")
        return app.state.documents[library_id]

    @app.post("/api/v1/memories/{library_id}/documents", status_code=201)
    async def upload_doc(library_id: str, request: Request, x_apikey: str | None = Header(None),
                         x_application_id: str | None = Header(None), x_user_apikey: str | None = Header(None)):
        rest_auth(x_apikey, x_application_id, x_user_apikey)
        if library_id not in app.state.documents:
            raise HTTPException(404, "library not found")
        form = await request.form()
        f = form.get("file")
        if f is None or not hasattr(f, "filename"):
            raise HTTPException(400, "file required")
        doc = {"id": f"doc_{secrets.token_hex(2)}", "title": f.filename, "ingestionStatus": 1,
               "language": request.query_params.get("language")}
        app.state.documents[library_id].append(doc)
        return doc

    @app.post("/api/v1/agents", status_code=201)
    async def create_agent(request: Request, x_apikey: str | None = Header(None),
                           x_application_id: str | None = Header(None)):
        auth(x_apikey, x_application_id)
        body = await request.json()
        if not body.get("name"):
            raise HTTPException(400, "name required")
        aid = f"agent_{secrets.token_hex(2)}"
        app.state.created.append(("agent", body))
        return {"agentId": aid, "id": aid, "name": body["name"]}

    @app.post("/api/v1/agents/{agent_id}/memories")
    async def attach(agent_id: str, request: Request, x_apikey: str | None = Header(None),
                     x_application_id: str | None = Header(None)):
        auth(x_apikey, x_application_id)
        app.state.created.append(("attach", {"agentId": agent_id, **(await request.json())}))
        return {"ok": True}

    @app.post("/api/v1/agents/{agent_id}/json", status_code=201)
    async def create_extractor(agent_id: str, request: Request, x_apikey: str | None = Header(None),
                               x_application_id: str | None = Header(None)):
        auth(x_apikey, x_application_id)
        body = await request.json()
        eid = f"ext_{secrets.token_hex(2)}"
        app.state.created.append(("extractor", {"agentId": agent_id, **body}))
        return {"id": eid, "title": body.get("title")}

    @app.post("/api/v1/webhooks", status_code=201)
    async def create_webhook(request: Request, x_apikey: str | None = Header(None),
                             x_application_id: str | None = Header(None)):
        auth(x_apikey, x_application_id)
        body = await request.json()
        app.state.created.append(("webhook", body))
        return {"id": f"wh_{secrets.token_hex(2)}", **{k: v for k, v in body.items() if k != "apiKeyValue"}}

    @app.post("/api/v1/agents/{agent_id}/json/{extractor_id}/ask-file")
    async def ask_file(agent_id: str, extractor_id: str, request: Request, x_apikey: str | None = Header(None),
                       x_application_id: str | None = Header(None)):
        auth(x_apikey, x_application_id)
        if request.query_params.get("useWebhook") not in ("false", "False", None):
            raise HTTPException(400, "bad useWebhook")
        form = await request.form()
        f = form.get("file")
        if f is None or not hasattr(f, "read"):
            raise HTTPException(400, "file required")
        data = await f.read()
        out = fake_extract(data)
        app.state.extractions.append({"agentId": agent_id, "extractorId": extractor_id, "filename": f.filename})
        exe = f"askx_{secrets.token_hex(3)}"
        return JSONResponse(out, headers={"X-AskFile-Execution-Id": exe, "X-AskFile-Audit-Id": f"aud_{exe}"})

    @app.post("/api/v1/ai-tools/{tool}/run")
    async def run_tool(tool: str, request: Request, x_apikey: str | None = Header(None),
                       x_application_id: str | None = Header(None)):
        auth(x_apikey, x_application_id)
        body = await request.json()
        if not body.get("text"):
            raise HTTPException(400, "text required")
        return {"tool": tool, "output": body["text"].rstrip() + "\n\n(polished by the fake AI Tool)",
                "creditsConsumed": 3, "truncated": False}

    @app.post("/fake/inbound-email")
    async def inbound_email(request: Request):
        """Local rehearsal of the email path: 'deliver' a quote PDF to the role-play inbox. The fake runs the
        extractor and calls Atelier's webhook exactly like the Evolus workflow would (static secret header)."""
        if not webhook_url:
            raise HTTPException(400, "start the fake with --atelier-url and --webhook-secret")
        form = await request.form()
        f = form.get("file")
        if f is None or not hasattr(f, "read"):
            raise HTTPException(400, "file required")
        fields = fake_extract(await f.read())
        payload = {"from": str(form.get("from") or ""), "subject": str(form.get("subject") or ""),
                   "filename": f.filename, "extraction": fields}
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(webhook_url, json=payload, headers={"X-Atelier-Webhook-Secret": webhook_secret})
        return JSONResponse({"webhookStatus": r.status_code, "webhookBody": r.json() if r.content else None})

    return mark_fake(app)


def create_shopify_app(token: str = "shpat_fake", client_id: str = "", client_secret: str = "",
                       scopes: tuple[str, ...] = ("write_products", "read_products", "read_orders",
                                                  "write_publications", "read_publications"),
                       version: str = "2026-10", shop: str = "fake-shop.myshopify.com",
                       public_base: str = "", webhook_url: str = "", webhook_secret: str = "",
                       storefront_password: str = "") -> FastAPI:
    """Fake of a Shopify dev store: the Admin GraphQL operations Atelier sends (by operation name), the
    client-credentials token endpoint, staged uploads, plus a tiny storefront (/products/{handle}) whose
    "Pre-order" button places a test order - so the whole loop can be rehearsed with a phone and no store.

    v4: products have options + variants like the real Admin API. productCreate with productOptions creates only
    the first option value's variant; productVariantsBulkCreate adds the rest (strategy DEFAULT /
    REMOVE_STANDALONE_VARIANT / PRESERVE_STANDALONE_VARIANT, duplicates rejected); orders carry the variant
    (title + selectedOptions) per line item, and the storefront has a size picker.

    State is on app.state: products, orders, uploads, calls (operation names), variables (per call),
    place_order(product_id, quantity, size=..., lines=[(size, qty), …]).
    """
    app = FastAPI(title="fake Shopify")
    st = app.state
    st.products: dict[str, dict[str, Any]] = {}
    st.orders: list[dict[str, Any]] = []
    st.uploads: dict[str, bytes] = {}
    st.calls: list[str] = []
    st.variables: list[tuple[str, dict[str, Any]]] = []  # (operation name, variables) per GraphQL call
    st.issued_tokens: set[str] = set()
    st.fail_ops: set[str] = set()  # operation names that should return userErrors
    seq = {"product": 9_100_000, "order": 5_500_000, "n": 1000}
    publication = "gid://shopify/Publication/1"

    def _mirror(p: dict[str, Any]) -> None:
        """Keep the pre-v4 flat fields (first variant) that older tests and scripts read."""
        first = p["variants"][0] if p["variants"] else {"id": None, "price": "0.00", "inventoryPolicy": "DENY",
                                                         "tracked": True}
        p["variant"], p["price"] = first["id"], first["price"]
        p["inventoryPolicy"], p["tracked"] = first["inventoryPolicy"], first["tracked"]
        p["sizes"] = [o["value"] for x in p["variants"] for o in x["selectedOptions"] if o["name"] == "Size"]

    def base(request: Request) -> str:
        return public_base or f"{request.url.scheme}://{request.url.netloc}"

    def authed(tok: str | None) -> bool:
        return bool(tok) and (tok == token or tok in st.issued_tokens)

    @app.post("/admin/oauth/access_token")
    async def oauth(request: Request):
        form = await request.form()  # application/x-www-form-urlencoded, as documented
        if (form.get("grant_type") != "client_credentials" or not client_id
                or form.get("client_id") != client_id or form.get("client_secret") != client_secret):
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        tok = f"shpca_{secrets.token_hex(8)}"
        st.issued_tokens.add(tok)
        return {"access_token": tok, "scope": ",".join(scopes), "expires_in": 86399}

    @app.put("/staged/{key}")
    async def staged_put(key: str, request: Request):
        st.uploads[key] = await request.body()
        return JSONResponse({}, status_code=200)

    def _variant(p: dict[str, Any], size: str | None) -> dict[str, Any]:
        if size is None:
            return p["variants"][0]
        v = next((x for x in p["variants"] if any(o["name"] == "Size" and o["value"].lower() == str(size).lower()
                                                  for o in x["selectedOptions"])), None)
        if v is None:
            raise KeyError(f"no {size} variant on {p['id']} (sizes: {[x['title'] for x in p['variants']]})")
        return v

    def place_order(product_id: str, quantity: int = 1, first_name: str = "Ada", city: str = "Lisbon",
                    last_name: str = "Lovelace", test: bool = True, deliver_webhook: bool = True,
                    size: str | None = None, lines: list[tuple[str | None, int]] | None = None) -> dict[str, Any]:
        """One test order. `size` picks the variant (default: the first); `lines` makes a multi-line order."""
        p = st.products.get(product_id) or next((x for x in st.products.values()
                                                 if x["id"].endswith("/" + str(product_id))), None)
        if p is None:
            raise KeyError(product_id)
        picked = [(_variant(p, sz), int(q)) for sz, q in (lines or [(size, quantity)])]
        seq["order"] += 1
        seq["n"] += 1
        o = {"id": f"gid://shopify/Order/{seq['order']}", "name": f"#{seq['n']}",
             "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "test": test, "cancelledAt": None,
             "currencyCode": "USD", "customer": {"firstName": first_name},
             "shippingAddress": {"firstName": first_name, "lastName": last_name, "city": city,
                                 "address1": "1 Private Street"},
             "billingAddress": None,
             "lineItems": {"nodes": [{
                 "quantity": q, "product": {"id": p["id"]}, "variantTitle": v["title"],
                 "variant": {"id": v["id"], "title": v["title"], "selectedOptions": v["selectedOptions"]},
                 "discountedTotalSet": {"shopMoney": {"amount": f"{float(v['price']) * q:.2f}", "currencyCode": "USD"}}}
                 for v, q in picked]}}
        st.orders.append(o)
        if deliver_webhook and webhook_url and webhook_secret:
            asyncio.get_event_loop().create_task(_deliver(o, p, picked))
        return o

    st.place_order = place_order

    async def _deliver(o: dict[str, Any], p: dict[str, Any], picked: list[tuple[dict[str, Any], int]]) -> None:
        import base64 as b64
        import hashlib
        import hmac

        payload = {"id": int(o["id"].rsplit("/", 1)[1]), "admin_graphql_api_id": o["id"], "name": o["name"],
                   "created_at": o["createdAt"], "test": o["test"], "currency": "USD",
                   "shipping_address": {"first_name": o["shippingAddress"]["firstName"],
                                        "last_name": o["shippingAddress"]["lastName"],
                                        "city": o["shippingAddress"]["city"]},
                   "line_items": [{"product_id": int(p["id"].rsplit("/", 1)[1]),
                                   "variant_id": int(v["id"].rsplit("/", 1)[1]), "variant_title": v["title"],
                                   "quantity": q, "price": f"{float(v['price']):.2f}", "properties": [],
                                   "discount_allocations": []} for v, q in picked]}
        raw = json.dumps(payload).encode()
        sig = b64.b64encode(hmac.new(webhook_secret.encode(), raw, hashlib.sha256).digest()).decode()
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                await c.post(webhook_url, content=raw, headers={
                    "Content-Type": "application/json", "X-Shopify-Hmac-Sha256": sig, "X-Shopify-Topic": "orders/create",
                    "X-Shopify-Shop-Domain": shop, "X-Shopify-Webhook-Id": secrets.token_hex(8)})
        except httpx.HTTPError:
            pass

    @app.post(f"/admin/api/{version}/graphql.json")
    async def graphql(request: Request, x_shopify_access_token: str | None = Header(None)):
        if not authed(x_shopify_access_token):
            return JSONResponse({"errors": "[API] Invalid API key or access token (unrecognized login or wrong "
                                           "password)"}, status_code=401)
        body = await request.json()
        q: str = body.get("query", "")
        v: dict[str, Any] = body.get("variables") or {}
        import re as _re

        m = _re.search(r"(query|mutation)\s+(\w+)", q)
        op = m.group(2) if m else "anonymous"
        st.calls.append(op)
        st.variables.append((op, v))

        def need(scope: str):
            if scope not in scopes:
                return JSONResponse({"errors": [{"message": f"Access denied for {op}. Required access: `{scope}`",
                                                 "extensions": {"code": "ACCESS_DENIED"}}]})
            return None

        def uerr(name: str, payload: dict[str, Any]) -> dict[str, Any]:
            if op in st.fail_ops:
                return {"data": {name: {**{k: None for k in payload}, "userErrors": [
                    {"field": ["input"], "message": "fake failure"}]}}}
            return {"data": {name: {**payload, "userErrors": []}}}

        if op == "AtelierShop":
            return {"data": {"shop": {"name": "Fake Atelier Dev Store", "myshopifyDomain": shop, "currencyCode": "USD",
                                      "primaryDomain": {"url": f"https://{shop}", "host": shop}},
                             "currentAppInstallation": {"accessScopes": [{"handle": x} for x in scopes]}}}
        if op == "AtelierStagedUpload":
            if (r := need("write_products")):
                return r
            key = secrets.token_hex(6)
            inp = v["input"][0]
            return uerr("stagedUploadsCreate", {"stagedTargets": [{
                "url": f"{base(request)}/staged/{key}", "resourceUrl": f"{base(request)}/staged/{key}/{inp['filename']}",
                "parameters": [{"name": "content_type", "value": inp["mimeType"]}, {"name": "acl", "value": "private"}]}]})
        if op == "AtelierProductCreate":
            if (r := need("write_products")):
                return r
            seq["product"] += 1
            pin = v["product"]
            pid = f"gid://shopify/Product/{seq['product']}"
            import re as _r

            handle = _r.sub(r"[^a-z0-9]+", "-", pin["title"].lower()).strip("-")
            if any(x["handle"] == handle for x in st.products.values()):
                handle = f"{handle}-{len(st.products) + 1}"
            # productOptions -> options; only the first value of each option gets a variant (as documented)
            opts = [{"id": f"gid://shopify/ProductOption/{seq['product']}{i}", "name": o["name"],
                     "optionValues": [{"id": f"gid://shopify/ProductOptionValue/{seq['product']}{i}{j}",
                                       "name": x["name"]} for j, x in enumerate(o.get("values") or [])]}
                    for i, o in enumerate(pin.get("productOptions") or [])]
            first = [{"name": o["name"], "value": o["optionValues"][0]["name"]} for o in opts if o["optionValues"]]
            p = {"id": pid, "handle": handle, "title": pin["title"], "status": pin.get("status", "DRAFT"),
                 "descriptionHtml": pin.get("descriptionHtml"), "tags": pin.get("tags"), "media": v.get("media") or [],
                 "options": opts or [{"id": f"gid://shopify/ProductOption/{seq['product']}0", "name": "Title",
                                      "optionValues": [{"id": "x", "name": "Default Title"}]}],
                 "variants": [], "published": False}
            seq["variant"] = seq.get("variant", 70_000_000) + 1
            p["variants"].append({"id": f"gid://shopify/ProductVariant/{seq['variant']}",
                                  "title": " / ".join(x["value"] for x in first) or "Default Title",
                                  "selectedOptions": first or [{"name": "Title", "value": "Default Title"}],
                                  "price": "0.00", "inventoryPolicy": "DENY", "tracked": True})
            _mirror(p)
            st.products[pid] = p
            return uerr("productCreate", {"product": {
                "id": pid, "handle": handle, "title": p["title"], "status": p["status"], "onlineStoreUrl": None,
                "options": p["options"], "variants": {"nodes": [{"id": p["variants"][0]["id"]}]}}})
        if op == "AtelierVariantsCreate":
            if (r := need("write_products")):
                return r
            p = st.products.get(v["productId"])
            if p is None:
                return {"data": {"productVariantsBulkCreate": {"productVariants": None, "userErrors": [
                    {"field": ["productId"], "message": "Product does not exist"}]}}}
            if op in st.fail_ops:  # userErrors -> nothing changes (the mutation is all-or-nothing)
                return uerr("productVariantsBulkCreate", {"productVariants": None})
            strategy = v.get("strategy") or "DEFAULT"
            standalone = len(p["variants"]) == 1
            default_only = standalone and p["variants"][0]["title"] == "Default Title"
            if standalone and (strategy == "REMOVE_STANDALONE_VARIANT" or (strategy == "DEFAULT" and default_only)):
                if default_only:
                    p["options"] = []
                p["variants"] = []
            created, errors = [], []
            for i, var in enumerate(v["variants"]):
                sel = []
                for ov in var.get("optionValues") or []:
                    opt = next((o for o in p["options"] if o["name"] == ov.get("optionName")), None)
                    if opt is None:
                        if p["options"]:
                            errors.append({"field": ["variants", str(i), "optionValues"],
                                           "message": f"Option does not exist: {ov.get('optionName')}"})
                            continue
                        opt = {"id": "gid://shopify/ProductOption/new", "name": ov.get("optionName"), "optionValues": []}
                        p["options"].append(opt)
                    if not any(x["name"] == ov["name"] for x in opt["optionValues"]):
                        opt["optionValues"].append({"id": f"gid://shopify/ProductOptionValue/n{i}", "name": ov["name"]})
                    sel.append({"name": opt["name"], "value": ov["name"]})
                title = " / ".join(x["value"] for x in sel)
                if any(x["title"] == title for x in p["variants"] + created):
                    errors.append({"field": ["variants", str(i)], "message": f"The variant '{title}' already exists."})
                    continue
                seq["variant"] = seq.get("variant", 70_000_000) + 1
                created.append({"id": f"gid://shopify/ProductVariant/{seq['variant']}", "title": title,
                                "selectedOptions": sel, "price": str(var.get("price", "0.00")),
                                "inventoryPolicy": var.get("inventoryPolicy", "DENY"),
                                "tracked": (var.get("inventoryItem") or {}).get("tracked", True)})
            if errors:
                return {"data": {"productVariantsBulkCreate": {"productVariants": [], "userErrors": errors}}}
            p["variants"].extend(created)
            _mirror(p)
            return uerr("productVariantsBulkCreate", {"productVariants": [
                {k: x[k] for k in ("id", "title", "price", "inventoryPolicy", "selectedOptions")} for x in created]})
        if op == "AtelierVariantsUpdate":
            if (r := need("write_products")):
                return r
            p = st.products.get(v["productId"])
            if p is None:
                return {"data": {"productVariantsBulkUpdate": {"productVariants": None, "userErrors": [
                    {"field": ["productId"], "message": "Product does not exist"}]}}}
            out = []
            for var in v["variants"]:
                tgt = next((x for x in p["variants"] if x["id"] == var.get("id")), None)
                if tgt is None:
                    return {"data": {"productVariantsBulkUpdate": {"productVariants": None, "userErrors": [
                        {"field": ["variants", "id"], "message": "Product variant does not exist"}]}}}
                tgt["price"] = str(var.get("price", tgt["price"]))
                tgt["inventoryPolicy"] = var.get("inventoryPolicy", tgt["inventoryPolicy"])
                if "inventoryItem" in var:
                    tgt["tracked"] = var["inventoryItem"].get("tracked", tgt["tracked"])
                out.append({"id": tgt["id"], "price": tgt["price"], "inventoryPolicy": tgt["inventoryPolicy"]})
            _mirror(p)
            return uerr("productVariantsBulkUpdate", {"productVariants": out})
        if op == "AtelierPublications":
            if (r := need("read_publications")):
                return r
            return {"data": {"publications": {"nodes": [{"id": "gid://shopify/Publication/9", "catalog": {"title": "Point of Sale"}},
                                                        {"id": publication, "catalog": {"title": "Online Store"}}]}}}
        if op == "AtelierPublish":
            if (r := need("write_publications")):
                return r
            p = st.products.get(v["id"])
            if p is not None and any(i["publicationId"] == publication for i in v["input"]):
                p["published"] = True
            return uerr("publishablePublish", {})
        if op == "AtelierProduct":
            p = st.products.get(v["id"])
            if p is None:
                return {"data": {"product": None}}
            url = f"{base(request)}/products/{p['handle']}" if p["published"] else None
            return {"data": {"product": {"id": p["id"], "handle": p["handle"], "title": p["title"],
                                         "status": p["status"], "onlineStoreUrl": url,
                                         "variants": {"nodes": [
                                             {k: x[k] for k in ("id", "title", "price", "selectedOptions")}
                                             for x in p["variants"]]}}}}
        if op == "AtelierProductDelete":
            pid = v["input"]["id"]
            st.products.pop(pid, None)
            return uerr("productDelete", {"deletedProductId": pid})
        if op == "AtelierOrders":
            if (r := need("read_orders")):
                return r
            m2 = _re.search(r"created_at:>='?([^' ]+)'?", v.get("query", ""))
            since = m2.group(1) if m2 else ""
            nodes = [o for o in st.orders if o["createdAt"] >= since]
            return {"data": {"orders": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}}
        if op == "AtelierWebhookCreate":
            return uerr("webhookSubscriptionCreate", {"webhookSubscription": {"id": "gid://shopify/WebhookSubscription/1"}})
        return JSONResponse({"errors": [{"message": f"fake Shopify: unknown operation {op}"}]})

    # ---- a tiny storefront for rehearsals (scan the QR code with a phone on the same network) ----
    from fastapi.responses import HTMLResponse

    @app.get("/products/{handle}", response_class=HTMLResponse)
    async def storefront(handle: str):
        p = next((x for x in st.products.values() if x["handle"] == handle), None)
        if p is None or not p["published"]:
            raise HTTPException(404, "product not found")
        lock = f"<p style='color:#a88'>(password page skipped - real store password: {storefront_password})</p>" \
            if storefront_password else ""
        return (f"<!doctype html><meta name=viewport content='width=device-width'><title>{p['title']}</title>"
                f"<body style='font-family:system-ui;background:#111;color:#eee;padding:24px'>"
                f"<p style='letter-spacing:.2em;font-size:11px;color:#c9b79c'>FAKE SHOPIFY · REHEARSAL STORE</p>"
                f"<h1 style='font-weight:300'>{p['title']}</h1><p>${float(p['price']):,.2f} · Pre-order</p>{lock}"
                f"<form method=post action='/products/{handle}/preorder'>"
                + (f"<p>Size: " + " ".join(
                    f"<label style='margin-right:10px'><input type=radio name=size value='{html_escape(sz)}'"
                    f"{' checked' if i == min(2, len(p['sizes']) - 1) else ''}> {html_escape(sz)}</label>"
                    for i, sz in enumerate(p["sizes"])) + "</p>" if p.get("sizes") else "")
                + f"<input name=first_name placeholder='First name' value='Ada'> "
                f"<input name=city placeholder='City' value='Lisbon'> "
                f"<input name=quantity type=number value=1 min=1 max=5 style='width:4em'> "
                f"<button style='padding:8px 16px'>Pre-order (test card 1)</button></form>")

    @app.post("/products/{handle}/preorder", response_class=HTMLResponse)
    async def preorder(handle: str, first_name: str = Form("Ada"), city: str = Form("Lisbon"), quantity: int = Form(1),
                       size: str | None = Form(None)):
        p = next((x for x in st.products.values() if x["handle"] == handle), None)
        if p is None:
            raise HTTPException(404, "product not found")
        try:
            o = place_order(p["id"], max(1, min(5, quantity)), first_name=first_name, city=city,
                            size=size if p.get("sizes") else None)
        except KeyError as e:
            raise HTTPException(422, str(e)) from e
        what = f" · size {html_escape(size)}" if size and p.get("sizes") else ""
        return (f"<body style='font-family:system-ui;background:#111;color:#eee;padding:24px'>Thank you - order "
                f"{o['name']}{what} placed (test).")

    @app.post("/_fake/orders")
    async def inject(request: Request):
        b = await request.json()
        lines = [(x.get("size"), int(x.get("quantity", 1))) for x in b["lines"]] if b.get("lines") else None
        try:
            o = place_order(b["productId"], int(b.get("quantity", 1)), first_name=b.get("firstName", "Ada"),
                            city=b.get("city", "Lisbon"), test=bool(b.get("test", True)), size=b.get("size"),
                            lines=lines)
        except KeyError as e:
            raise HTTPException(422, str(e)) from e
        return o

    return mark_fake(app)


FAKE_ECB_XML = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
<gesmes:subject>Reference rates (FAKE test double)</gesmes:subject>
<Cube><Cube time='2026-10-12'>
<Cube currency='USD' rate='1.1000'/><Cube currency='JPY' rate='165.00'/><Cube currency='GBP' rate='0.8500'/>
<Cube currency='CNY' rate='7.8000'/><Cube currency='INR' rate='92.000'/><Cube currency='CHF' rate='0.9500'/>
</Cube></Cube></gesmes:Envelope>"""


def create_ecb_app(xml: str = FAKE_ECB_XML, down: bool = False) -> FastAPI:
    """Fake of the ECB daily reference-rates XML (round, made-up test rates: 1 EUR = 1.10 USD)."""
    app = FastAPI(title="fake ECB")

    @app.get("/stats/eurofxref/eurofxref-daily.xml")
    async def daily():
        if down:
            raise HTTPException(503, "down")
        from fastapi.responses import Response

        return Response(content=xml, media_type="text/xml")

    return mark_fake(app)


def fake_extract(pdf: bytes) -> dict[str, Any]:
    """The fake extractor: reads the PDF's text and returns schema-shaped JSON (snake_case keys, as an Evolus
    extractor schema might define them). Deliberately its own simple parsing, independent of the app's."""
    import io

    from pypdf import PdfReader

    try:
        text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)
    except Exception:  # noqa: BLE001
        return {"error": "unreadable document"}
    return fake_extract_text(text)


def fake_extract_text(text: str) -> dict[str, Any]:
    import re

    text = re.sub(r"\n\s*:\s*", ": ", text)

    def grab(pat: str) -> str | None:
        m = re.search(pat, text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    def notes() -> str | None:  # the labelled note plus its wrapped lines, up to the sign-off
        m = re.search(r"(?:Notes|Note|Notas): ([^\n]+(?:\n(?!Kind regards|Cordiali saluti|Com os melhores)[^\n]+)*)",
                      text)
        return " ".join(x.strip() for x in m.group(1).splitlines()) if m else None

    first = text.strip().splitlines()[0].strip() if text.strip() else None
    # A real extractor reads any language; the fake knows the English, Italian and Portuguese labels (v4).
    return {
        "supplier_name": first,
        "quote_number": grab(r"(?:Quote No\.|Offerta n\.|Cotação n\.º)\s*([A-Z0-9\-]+)"),
        "rfq_reference": grab(r"(ATL-run_[0-9a-f]+)"),
        "currency": grab(r"(?:Currency|Valuta|Moeda): ([A-Z]{3})"),
        "unit_price": grab(r"(?:Unit price|Prezzo unitario|Preço unitário): [A-Z]{3} ([\d.,]+)"),
        "moq": grab(r"(?:MOQ|Minimo d'ordine \(MOQ\)|Quantidade mínima \(MOQ\)): ([\d,.]+)"),
        "lead_time": grab(r"(?:Lead time|Tempi di consegna|Prazo de entrega): ([^\n]+)"),
        "sample_cost": grab(r"(?:Sample cost|Costo campionatura|Custo da amostra): [A-Z]{3} ([\d.,]+)"),
        "payment_terms": grab(r"(?:Payment terms|Condizioni di pagamento|Condições de pagamento): ([^\n]+)"),
        "valid_until": grab(r"(?:Valid until|Valida fino al|Válida até)\s*([0-9-]+)"),
        "notes": notes(),
    }


class RoutingTransport(httpx.AsyncBaseTransport):
    """Route requests to in-process ASGI apps by host[:port] (tests)."""

    def __init__(self, routes: dict[str, FastAPI]):
        self.routes = {k: httpx.ASGITransport(app=v) for k, v in routes.items()}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        key = request.url.netloc.decode() if isinstance(request.url.netloc, bytes) else request.url.netloc
        t = self.routes.get(key) or self.routes.get(request.url.host)
        if t is None:
            raise httpx.ConnectError(f"no fake upstream for {key}", request=request)
        return await t.handle_async_request(request)


async def _serve(port_base: int, api_key: str, evolus_key: str, evolus_app: str, host: str,
                 shopify_token: str, shopify_webhook_url: str, shopify_webhook_secret: str, atelier_url: str,
                 webhook_secret: str) -> None:
    import uvicorn

    hook = f"{atelier_url.rstrip('/')}/api/webhooks/evolus/quote" if atelier_url and webhook_secret else ""
    apps = [create_openai_app(api_key=api_key), create_diffusion_app(),
            create_evolus_app(api_key=evolus_key, app_id=evolus_app, webhook_url=hook, webhook_secret=webhook_secret),
            create_shopify_app(token=shopify_token, webhook_url=shopify_webhook_url,
                               webhook_secret=shopify_webhook_secret, storefront_password="(none - fake store)")]
    servers = [uvicorn.Server(uvicorn.Config(a, host=host if i == 3 else "127.0.0.1", port=port_base + i,
                                             log_level="warning"))
               for i, a in enumerate(apps)]
    evo = f"http://127.0.0.1:{port_base + 2}"
    print(f"fake vLLM       http://127.0.0.1:{port_base}/v1   (api key: {api_key or 'none'})")
    print(f"fake diffusion  http://127.0.0.1:{port_base + 1}/generate")
    print(f"fake Evolus     {evo}   (X-ApiKey {evolus_key}, X-Application-Id {evolus_app})")
    print(f"                agent model {evolus_app}:agent_sourcing · library lib_1 · extractor agent_x / ext_quote")
    if hook:
        print(f"fake inbox      curl -F file=@quote.pdf -F from=team+prato@example.com {evo}/fake/inbound-email")
        print(f"                -> extractor -> POST {hook}")
    print(f"fake Shopify    http://{host}:{port_base + 3}   (SHOPIFY_STORE_DOMAIN=http://{host}:{port_base + 3} "
          f"SHOPIFY_ADMIN_TOKEN={shopify_token}){'  webhooks -> ' + shopify_webhook_url if shopify_webhook_url else ''}")
    print("                 storefront: /products/<handle> has a Pre-order button that places a test order")
    await asyncio.gather(*(s.serve() for s in servers))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=18900)
    ap.add_argument("--api-key", default="fake-vllm-key")
    ap.add_argument("--evolus-key", default="test-key")
    ap.add_argument("--evolus-app", default="app_test")
    ap.add_argument("--shopify-host", default="127.0.0.1",
                    help="bind the fake Shopify here (your LAN IP lets a phone scan the QR code)")
    ap.add_argument("--shopify-token", default="shpat_fake")
    ap.add_argument("--shopify-webhook-url", default="",
                    help="e.g. http://127.0.0.1:8787/api/webhooks/shopify/orders-create")
    ap.add_argument("--shopify-webhook-secret", default="fake-webhook-secret")
    ap.add_argument("--atelier-url", default="", help="Atelier backend, for the fake inbound-email -> webhook path")
    ap.add_argument("--webhook-secret", default="", help="must match EVOLUS_WEBHOOK_SECRET in the backend")
    a = ap.parse_args()
    asyncio.run(_serve(a.port, a.api_key, a.evolus_key, a.evolus_app, a.shopify_host, a.shopify_token,
                       a.shopify_webhook_url, a.shopify_webhook_secret, a.atelier_url, a.webhook_secret))
