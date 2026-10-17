"""Shared helpers for OpenAI-compatible endpoints (vLLM on AMD Developer Cloud)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, TypeVar
from urllib.parse import urlparse

from openai import AsyncOpenAI

from ..config import get_settings
from . import telemetry
from .hedge import hedged
from .http import async_client

log = logging.getLogger("atelier.openai")
T = TypeVar("T")

_model_cache: dict[str, str] = {}


def normalize_base_url(endpoint: str) -> str:
    """Accept `http://host:8000`, `http://host:8000/v1` or `.../v1/chat/completions`."""
    url = endpoint.strip().rstrip("/")
    for suffix in ("/chat/completions", "/completions"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    if not urlparse(url).path:
        url += "/v1"
    return url


def make_client(endpoint: str, api_key: str, timeout: float) -> AsyncOpenAI:
    return AsyncOpenAI(base_url=normalize_base_url(endpoint), api_key=api_key or "EMPTY",
                       timeout=timeout, max_retries=0, http_client=async_client(timeout))


async def resolve_model(client: AsyncOpenAI, configured: str) -> str:
    """Use the configured model, else the first one the vLLM server reports."""
    if configured:
        return configured
    key = str(client.base_url)
    if key not in _model_cache:
        models = await client.models.list()
        if not models.data:
            raise RuntimeError("endpoint reports no models")
        _model_cache[key] = models.data[0].id
    return _model_cache[key]


_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)

# Reasoning / tool-call markup that can leak into `content` (e.g. Gemma 4 on vLLM, vllm-project/vllm#39043, or a
# server started without --reasoning-parser). Whole thought blocks go first, then any stray control tag.
_THOUGHT_BLOCKS = (
    re.compile(r"<\|channel>.*?<channel\|>", re.DOTALL),  # Gemma 4: <|channel>thought\n…<channel|>
    re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE),  # Qwen3 / DeepSeek style
    re.compile(r"<\|tool_call>.*?<tool_call\|>", re.DOTALL),  # Gemma 4 tool-call markup
)
# Single tags with a pipe (<|think|>, <|turn>, <turn|>, <channel|>, <|im_end|>…), </think>, <eos>… - never plain
# <b>-style tags, which can legitimately appear inside JSON strings.
_STRAY_TAG = re.compile(r"<\|[A-Za-z0-9_/]{0,40}\|?>|<[A-Za-z0-9_]{1,40}\|>|</?think>|<(?:eos|bos|end_of_turn|start_of_turn)>",
                        re.IGNORECASE)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def strip_reasoning(text: str) -> str:
    """Remove leaked reasoning blocks and model control tags from a completion."""
    t = text
    for pat in _THOUGHT_BLOCKS:
        t = pat.sub("", t)
    # An unterminated thought block (generation cut, or the closing tag was eaten by a parser):
    # drop everything from the opener up to the first JSON-looking character after it.
    m = re.search(r"<\|channel>|<think>", t, re.IGNORECASE)
    if m:
        rest = t[m.end():]
        j = min([i for i in (rest.find("{"), rest.find("[")) if i >= 0], default=-1)
        t = t[: m.start()] + (rest[j:] if j >= 0 else "")
    return _STRAY_TAG.sub("", t).strip()


def _decode_candidates(t: str) -> tuple[int, Any]:
    """(span, value) of the longest JSON object/array that parses in `t` (stray prose around it is ignored)."""
    dec = json.JSONDecoder()
    best: tuple[int, Any] | None = None
    i, n = 0, len(t)
    while i < n:
        if t[i] in "{[":
            try:
                val, end = dec.raw_decode(t, i)
            except json.JSONDecodeError:
                i += 1
                continue
            if isinstance(val, (dict, list)) and (best is None or end - i > best[0]):
                best = (end - i, val)
            i = end  # skip everything nested inside a parsed value
            continue
        i += 1
    if best is None:
        raise ValueError("no parsable JSON")
    return best


def extract_json(text: str) -> Any:
    """Parse JSON from a model reply.

    Tolerates code fences, prose around the JSON, trailing commas, and leaked reasoning / tool-call markup
    (Gemma 4 `<|channel>thought…<channel|>`, `<think>…</think>`, stray `<|…|>` tags) before or after it.
    """
    if text is None:
        raise ValueError("empty completion")
    t = strip_reasoning(text.strip())
    m = _FENCE.search(t)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    if "{" not in t and "[" not in t:
        raise ValueError(f"no JSON object in completion: {text[:160]!r}")
    # As written, and with trailing commas removed; the longest value wins (so a list nested in an object that
    # only parses once its trailing comma is gone does not beat the object itself).
    found = []
    for candidate in (t, _TRAILING_COMMA.sub(r"\1", t)):
        try:
            found.append(_decode_candidates(candidate))
        except ValueError:
            continue
    if not found:
        raise ValueError(f"unterminated or invalid JSON in completion: {text[:160]!r}")
    return max(found, key=lambda x: x[0])[1]


def _extra_body() -> dict:
    raw = get_settings().atelier_llm_extra_body.strip()
    if not raw:
        return {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {}
    except ValueError:
        log.warning("ATELIER_LLM_EXTRA_BODY is not valid JSON; ignoring it")
        return {}


def extra_body() -> dict:
    """ATELIER_LLM_EXTRA_BODY as a dict (empty when unset or invalid)."""
    return _extra_body()


def thinking_disabled(body: dict | None = None) -> bool:
    """True when the extra body turns the chat template's thinking off (Gemma 4 / Qwen3:
    {"chat_template_kwargs": {"enable_thinking": false}})."""
    b = extra_body() if body is None else body
    kw = b.get("chat_template_kwargs") if isinstance(b, dict) else None
    return isinstance(kw, dict) and kw.get("enable_thinking") is False


def is_gemma4(model_id: str | None) -> bool:
    """The served model is a Gemma 4 checkpoint (e.g. google/gemma-4-26B-A4B-it)."""
    return bool(model_id) and "gemma-4" in model_id.lower()


def _usage_dict(usage: Any) -> dict | None:
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage
    try:
        return usage.model_dump()
    except Exception:  # noqa: BLE001
        return None


async def _complete(client: AsyncOpenAI, model: str, messages: list[dict], *, max_tokens: int,
                    temperature: float, json_mode: bool, stream: bool,
                    timer: telemetry.Timer) -> tuple[str, dict | None]:
    kwargs: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens,
                              "temperature": temperature}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    extra = _extra_body()
    if extra:
        kwargs["extra_body"] = extra
    if not stream:
        resp = await client.chat.completions.create(**kwargs)  # no TTFT without streaming: left as None
        return resp.choices[0].message.content or "", _usage_dict(resp.usage)
    parts: list[str] = []
    usage = None
    response = await client.chat.completions.create(
        **kwargs, stream=True, stream_options={"include_usage": True})
    async for chunk in response:
        if getattr(chunk, "usage", None):
            usage = _usage_dict(chunk.usage)
        if chunk.choices:
            piece = getattr(chunk.choices[0].delta, "content", None)
            if piece:
                timer.mark_first()
                parts.append(piece)
    return "".join(parts), usage


def no_retry(e: BaseException) -> bool:
    """QA M12: only a bad answer (unparseable / invalid JSON, a rejected request option) is worth a second attempt.
    Timeouts, connection errors and server errors are not: retrying them only doubles the wait."""
    import asyncio

    import httpx
    import openai

    return isinstance(e, (openai.APITimeoutError, openai.APIConnectionError, openai.InternalServerError,
                          httpx.TimeoutException, httpx.TransportError, asyncio.TimeoutError, TimeoutError))


async def chat_json(
    client: AsyncOpenAI,
    model: str,
    messages_for_attempt: Callable[[int], list[dict]],
    validate: Callable[[Any], T],
    *,
    attempts: int = 2,
    max_tokens: int = 1500,
    temperature: float = 0.4,
    service: str = "llm",
    purpose: str = "chat",
    images: int | None = None,
    route: str | None = None,
) -> T:
    """Call chat completions, parse + validate JSON; retry once (attempts=2) then raise.

    Every attempt is recorded in telemetry with measured latency / TTFT and the server's `usage`.
    Attempt 1 asks for JSON mode and streams (each if enabled); the retry is a plain, non-streamed
    request, so a server that rejects either feature still gets a fair second try.
    """
    s = get_settings()
    host = urlparse(str(client.base_url)).netloc
    last: Exception | None = None
    for attempt in range(attempts):
        first = attempt == 0
        timer = telemetry.Timer()
        usage: dict | None = None
        try:
            msgs = messages_for_attempt(attempt)
            content, usage = await hedged(
                lambda: _complete(client, model, msgs, max_tokens=max_tokens,
                                  temperature=temperature if first else 0.1,
                                  json_mode=s.atelier_llm_json_mode and first, stream=s.atelier_llm_stream and first,
                                  timer=timer),
                after=s.atelier_hedge_vision_after if service == "vision" else s.atelier_hedge_brain_after,
                label=f"{service}/{purpose}")
            result = validate(extract_json(content))
        except Exception as e:  # noqa: BLE001 - a bad answer is retried; see no_retry() for what isn't
            last = e
            telemetry.live_llm_call(service=service, purpose=purpose, model=model, host=host, timer=timer,
                                    usage=usage, ok=False, attempt=attempt + 1,
                                    error=f"{e.__class__.__name__}: {e}", images=images, route=route)
            log.warning("%s/%s attempt %d/%d failed after %.0fms: %s", service, purpose, attempt + 1,
                        attempts, timer.ms, e)
            if no_retry(e):  # QA M12: a timeout / dead endpoint fails fast instead of waiting a second time
                break
            continue
        telemetry.live_llm_call(service=service, purpose=purpose, model=model, host=host, timer=timer,
                                usage=usage, ok=True, attempt=attempt + 1, images=images, route=route)
        return result
    assert last is not None
    raise last


