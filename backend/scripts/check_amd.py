"""One-shot check of the AMD inference endpoints configured in backend/.env (or the environment).

    cd backend && uv run python scripts/check_amd.py            # all configured endpoints
    uv run python scripts/check_amd.py --only llm,vision

For each configured endpoint it pings it, runs tiny real requests and prints the model, latency, tokens/sec (from
the server's `usage`) or images/sec, and PASS/FAIL:

  llm        GET /v1/models - WARN unless the served id contains "gemma-4" (the Google "Gemma on AMD" prize
             depends on it) · a strict-JSON completion with thinking off (ATELIER_LLM_EXTRA_BODY, the same client
             code as the app: streaming, JSON mode) · a tool-call round trip (tool call -> tool result -> answer;
             needs --enable-auto-tool-choice and the right --tool-call-parser, `gemma4` for Gemma 4)
  vision     one image (data: URL, OpenAI `image_url` part) -> JSON
  diffusion  /health + one 512x512 render

Exit code 0 means every configured endpoint passed (a WARN does not fail the run).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings, host_of  # noqa: E402
from app.services import openai_compat, telemetry  # noqa: E402
from app.services.http import async_client, bearer  # noqa: E402
from app.services.probe import diffusion_health_url  # noqa: E402

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
if not sys.stdout.isatty():
    GREEN = RED = YELLOW = DIM = RESET = ""

FABRIC_TOOL = {
    "type": "function",
    "function": {
        "name": "get_fabric_price",
        "description": "Current mill price of a fabric, in USD per metre.",
        "parameters": {"type": "object", "properties": {"fabric": {"type": "string", "description": "fabric name"}},
                       "required": ["fabric"]},
    },
}


def swatch_png(size: int = 96) -> bytes:
    """A small two-colour test image (indigo top, camel bottom) for the vision check."""
    rows = []
    for y in range(size):
        rgb = (31, 42, 68) if y < size // 2 else (201, 183, 156)
        rows.append(b"\x00" + bytes(rgb) * size)

    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))


def _json_object(d: object) -> dict:
    if not isinstance(d, dict):
        raise ValueError("reply is not a JSON object")
    return d


def line(ok: bool, name: str, msg: str) -> bool:
    print(f"  {GREEN + 'PASS' if ok else RED + 'FAIL'}{RESET}  {name:<10} {msg}")
    return ok


def warn(name: str, msg: str) -> None:
    print(f"  {YELLOW}WARN{RESET}  {name:<10} {msg}")


def stats_of(c) -> str:
    """'1,234ms · TTFT 210ms · 40+120 tok · 95.3 tok/s' from a telemetry record."""
    stats = [f"{c.latency_ms:,.0f}ms"]
    if c.ttft_ms is not None:
        stats.append(f"TTFT {c.ttft_ms:,.0f}ms")
    if c.prompt_tokens is not None:
        stats.append(f"{c.prompt_tokens}+{c.completion_tokens} tok")
    stats.append(f"{c.tokens_per_sec:,.1f} tok/s" if c.tokens_per_sec else "tok/s n/a (server sent no usage)")
    if c.attempt > 1:
        stats.append(f"needed retry #{c.attempt}")
    return " · ".join(stats)


def gemma_verdict(model: str, fake: bool = False) -> tuple[bool, str]:
    """(is Gemma 4, message) for the served model id. A test double never counts for anything."""
    if fake:
        return False, f"{model} is the local TEST DOUBLE (FAKE UPSTREAM - not real); it proves nothing about Gemma"
    if openai_compat.is_gemma4(model):
        return True, f"{model} is Gemma 4 (Google, open) - counts for the Gemma-on-AMD prize"
    return False, (f"served model {model!r} is not Gemma 4 - the Google prize needs a gemma-4 model "
                   "(default plan: google/gemma-4-26B-A4B-it, see docs/AMD_SETUP.md)")


async def check_tools(client, model: str) -> bool:
    """Tool-call round trip: the model must call get_fabric_price, then answer from the tool's result."""
    extra = openai_compat.extra_body()
    kw = {"extra_body": extra} if extra else {}
    messages: list[dict] = [{"role": "user", "content": "What does 14oz selvedge denim cost per metre right now? "
                                                        "Use the get_fabric_price tool."}]
    t1 = telemetry.Timer()
    try:
        r1 = await client.chat.completions.create(model=model, messages=messages, tools=[FABRIC_TOOL],
                                                  tool_choice="auto", max_tokens=200, temperature=0, **kw)
    except Exception as e:  # noqa: BLE001
        return line(False, "tools", f"request failed after {t1.ms:.0f}ms: {e.__class__.__name__}: {str(e)[:160]} "
                                    "(was vLLM started with --enable-auto-tool-choice --tool-call-parser …?)")
    msg = r1.choices[0].message
    calls = msg.tool_calls or []
    if not calls:
        leaked = " - tool markup leaked into content: check --tool-call-parser" if "tool_call" in (msg.content or "") \
            else ""
        return line(False, "tools", f"no tool call in the reply ({(msg.content or '')[:80]!r}){leaked}")
    call = calls[0]
    try:
        args = json.loads(call.function.arguments or "{}")
    except ValueError:
        return line(False, "tools", f"tool call arguments are not JSON: {call.function.arguments!r}")
    if call.function.name != "get_fabric_price":
        return line(False, "tools", f"called an unknown tool {call.function.name!r}")
    first_ms = t1.ms
    messages.append({"role": "assistant", "content": msg.content or "",
                     "tool_calls": [{"id": call.id, "type": "function",
                                     "function": {"name": call.function.name, "arguments": call.function.arguments}}]})
    messages.append({"role": "tool", "tool_call_id": call.id,
                     "content": json.dumps({"fabric": args.get("fabric", "selvedge denim"), "usdPerMetre": 14.5})})
    t2 = telemetry.Timer()
    try:
        r2 = await client.chat.completions.create(model=model, messages=messages, tools=[FABRIC_TOOL],
                                                  max_tokens=200, temperature=0, **kw)
    except Exception as e:  # noqa: BLE001
        return line(False, "tools", f"tool-result turn failed after {t2.ms:.0f}ms: {e.__class__.__name__}: "
                                    f"{str(e)[:160]}")
    answer = openai_compat.strip_reasoning(r2.choices[0].message.content or "")
    if not answer:
        return line(False, "tools", "empty answer after the tool result")
    total_ms = first_ms + t2.ms
    usages = [openai_compat._usage_dict(r.usage) or {} for r in (r1, r2)]
    ct = sum(int(u.get("completion_tokens") or 0) for u in usages)
    rate = telemetry.rate(ct, total_ms) if ct else None
    tps = f"{rate:,.1f} tok/s" if rate else "tok/s n/a"
    return line(True, "tools", f"{model} · get_fabric_price({json.dumps(args)}) -> answer · {total_ms:,.0f}ms "
                               f"(2 turns) · {ct} completion tok · {tps} · {answer[:70]!r}")


async def check_chat(name: str, endpoint: str, model_cfg: str, api_key: str, *, image: bool,
                     tools: bool = False) -> bool:
    s = get_settings()
    print(f"{name}: {endpoint}")
    client = openai_compat.make_client(endpoint, api_key, s.atelier_vision_timeout if image else s.atelier_llm_timeout)
    t = telemetry.Timer()
    try:
        models = await client.models.list()
        ids = [m.id for m in models.data]
    except Exception as e:  # noqa: BLE001
        return line(False, "models", f"GET /v1/models failed after {t.ms:.0f}ms: {e.__class__.__name__}: {e}")
    line(True, "models", f"{t.ms:.0f}ms · serving {', '.join(ids) or '(none)'}")
    model = model_cfg or (ids[0] if ids else "")
    if model_cfg and model_cfg not in ids:
        print(f"  {DIM}note: configured model {model_cfg!r} is not in the served list{RESET}")
    fake = host_of(endpoint) in telemetry.FAKE_HOSTS  # the test double marks every response
    gemma, verdict = gemma_verdict(model, fake)
    if gemma:
        line(True, "gemma-4", verdict)
    else:
        warn("gemma-4", verdict)
    if not image:
        if openai_compat.thinking_disabled():
            print(f"  {DIM}thinking: off (ATELIER_LLM_EXTRA_BODY chat_template_kwargs.enable_thinking=false){RESET}")
        else:
            warn("thinking", "ATELIER_LLM_EXTRA_BODY does not set chat_template_kwargs.enable_thinking=false; "
                             "JSON calls may spend tokens thinking (see backend/.env.example)")
    if image:
        url = "data:image/png;base64," + base64.b64encode(swatch_png()).decode()
        prompt = ('Look at the image. Reply with ONLY a JSON object: {"colors": ["#RRGGBB", ...], '
                  '"description": "<5 words>"}')
        # image before text (Gemma 4 model card)
        content: object = [{"type": "image_url", "image_url": {"url": url}}, {"type": "text", "text": prompt}]
    else:
        content = ('Reply with ONLY a JSON object describing a denim jacket: {"garment": str, '
                   '"fabrics": [str, str], "retailPriceUsd": number}')
    telemetry.clear()
    try:
        out = await openai_compat.chat_json(client, model, lambda a: [{"role": "user", "content": content}],
                                            _json_object,
                                            max_tokens=200, service="vision" if image else "llm", purpose="check",
                                            images=1 if image else None)
    except Exception as e:  # noqa: BLE001
        last = telemetry.snapshot().calls[:1]
        took = f" after {last[0].latency_ms:.0f}ms" if last else ""
        return line(False, "image" if image else "json", f"{model}: {e.__class__.__name__}: {str(e)[:160]}{took}")
    c = telemetry.snapshot().calls[0]
    ok = line(True, "image" if image else "json", f"{model} · {stats_of(c)} · {str(out)[:90]}")
    if tools:
        ok = await check_tools(client, model) and ok
    return ok


async def check_diffusion(endpoint: str, out_dir: Path) -> bool:
    s = get_settings()
    print(f"diffusion: {endpoint}")
    t = telemetry.Timer()
    try:
        async with async_client(s.atelier_health_timeout * 2) as c:
            r = await c.get(diffusion_health_url(endpoint))
        info = r.json() if r.status_code == 200 else {}
        line(r.status_code < 500, "health", f"{t.ms:.0f}ms · HTTP {r.status_code} · "
                                            f"{info.get('model', '?')} · {info.get('device', '?')}")
    except Exception as e:  # noqa: BLE001
        return line(False, "health", f"unreachable: {e.__class__.__name__}: {e}")
    t = telemetry.Timer()
    try:
        async with async_client(s.atelier_diffusion_timeout) as c:
            r = await c.post(endpoint, json={"prompt": "a camel wool coat on a white background, studio photo",
                                             "negative_prompt": "text, watermark", "seed": 7,
                                             "width": 512, "height": 512},
                             headers=bearer(s.amd_diffusion_api_key))
        r.raise_for_status()
        data = r.json()
        png = base64.b64decode(data["images"][0].split(",", 1)[-1])
    except Exception as e:  # noqa: BLE001
        return line(False, "generate", f"{e.__class__.__name__}: {str(e)[:160]} after {t.ms:.0f}ms")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "check_amd_diffusion.png"
    path.write_bytes(png)
    server = data.get("elapsedMs")
    ips = telemetry.rate(1, server or t.ms)
    return line(True, "generate", f"{data.get('model', '?')} · {t.ms:,.0f}ms wall"
                + (f" · {server:,.0f}ms GPU" if server else "") + f" · {ips} img/s · 512x512 · "
                f"{len(png):,} bytes -> {path}")


async def run(only: set[str], out_dir: Path) -> int:
    s = get_settings()
    gpu = s.amd_gpu_label or "(AMD_GPU_LABEL not set)"
    print(f"Atelier AMD check · GPU label: {gpu}\n")
    results: list[bool] = []
    ran = 0
    if "llm" in only:
        if s.amd_vllm_endpoint:
            ran += 1
            results.append(await check_chat("llm", s.amd_vllm_endpoint, s.amd_vllm_model, s.amd_vllm_api_key,
                                            image=False, tools=True))
        else:
            print(f"llm: {DIM}skipped (AMD_VLLM_ENDPOINT not set){RESET}")
    if "vision" in only:
        if s.amd_vision_endpoint:
            ran += 1
            same = openai_compat.normalize_base_url(s.amd_vision_endpoint) == \
                openai_compat.normalize_base_url(s.amd_vllm_endpoint or "-")
            if same:
                print(f"{DIM}(vision uses the same server as the LLM - the default one-model plan){RESET}")
            results.append(await check_chat("vision", s.amd_vision_endpoint, s.amd_vision_model,
                                            s.amd_vllm_api_key, image=True))
        else:
            print(f"vision: {DIM}skipped (AMD_VISION_ENDPOINT not set){RESET}")
    if "diffusion" in only:
        if s.amd_diffusion_endpoint:
            ran += 1
            results.append(await check_diffusion(s.amd_diffusion_endpoint, out_dir))
        else:
            print(f"diffusion: {DIM}skipped (AMD_DIFFUSION_ENDPOINT not set){RESET}")
    print()
    if ran == 0:
        print(f"{RED}NOTHING CHECKED{RESET} - set AMD_* endpoints in backend/.env (see docs/AMD_SETUP.md)")
        return 2
    ok = all(results)
    print(f"{GREEN + 'ALL PASS' if ok else RED + 'SOME CHECKS FAILED'}{RESET} ({sum(results)}/{len(results)} endpoints)"
          f" · hosts: {', '.join(sorted({host_of(e) for e in (s.amd_vllm_endpoint, s.amd_vision_endpoint, s.amd_diffusion_endpoint) if e}))}")
    return 0 if ok else 1


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="llm,vision,diffusion")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "static" / "generated"))
    a = ap.parse_args()
    return await run({x.strip() for x in a.only.split(",")}, Path(a.out))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
