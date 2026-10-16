"""Provision Atelier's Evolus building blocks through the REST API (best effort, then prints .env lines).

    cd backend
    uv run python scripts/build_knowledge.py                 # supplier catalogue + brand profile PDFs (workspace)
    uv run python scripts/provision_evolus.py --dry-run      # show what it would create
    uv run python scripts/provision_evolus.py --all --webhook-url https://<tunnel>/api/webhooks/evolus/quote

What it creates (skip any step with its flag off; existing ids in backend/.env are reused, not duplicated):
  --library    knowledge library "<brand> knowledge" + uploads the Brand workspace's brand-book files and the
               generated supplier catalogue / brand profile PDFs (language=en)
  --agent      agent "Atelier Sourcing & Tech Design" on our AMD model (modelKey "own/<EVOLUS_OWN_MODEL_NAME>"),
               with the library attached
  --extractor  an extractor agent + JSON extractor "Supplier quote" with the field schema from
               app/services/quotes.py (EXTRACTOR_SCHEMA)
  --webhook    outbound webhook -> Atelier's /api/webhooks/evolus/quote with the X-Atelier-Webhook-Secret header
Workflows (outreach email, inbound email -> extractor -> webhook) are set up in the UI, as docs/EVOLUS_SETUP.md
describes: their step types are numeric and only listed by the in-workspace step catalog, which this script prints.

The endpoint shapes come from the Evolus web app's API client and the public docs (docs/EVOLUS_API_NOTES.md):
creation endpoints are NOT in the public docs, so a 4xx here means "do it in the UI". Requires
EVOLUS_API_KEY and EVOLUS_WORKSPACE_ID (+ EVOLUS_USER_API_KEY if library calls get 401 with the app key).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.services import evolus  # noqa: E402
from app.services.http import async_client  # noqa: E402
from app.services import workspace  # noqa: E402
from app.services.quotes import EXTRACTOR_PROMPT, EXTRACTOR_SCHEMA  # noqa: E402

AGENT_PROMPT_TEMPLATE = """You are Atelier, {brand}'s product-development agent.
You write factory-ready tech packs, supplier RFQ emails, creative-direction interpretations and supplier
recommendations. Always follow the attached knowledge library: the brand's own brand book (fit blocks, fabric
standards, sustainability rules, price architecture, approved colours, tone of voice), its brand profile and its
Supplier Catalogue (suppliers, MOQs, lead times, certifications). When the caller asks for JSON, answer
with ONLY the JSON object, no prose and no markdown fences, and include "sources" naming the passages you used.
Never invent supplier prices: real prices come from the suppliers' quote documents."""


def agent_prompt() -> str:
    return AGENT_PROMPT_TEMPLATE.format(brand=workspace.brand_name() or "the brand")


def library_files() -> list[tuple[str, bytes, str]]:
    """(filename, bytes, content type): the brand's uploaded brand-book files + the generated PDFs."""
    from scripts.build_knowledge import build

    out = []
    for d in workspace.documents("brand_book"):
        p = workspace.document_file(d.id)
        if p is not None:
            out.append((d.filename, p.read_bytes(), d.content_type))
    for pdf in build():
        out.append((pdf.name, pdf.read_bytes(), "application/pdf"))
    return out


def _ok(msg: str) -> None:
    print(f"  ok    {msg}")


def _fail(msg: str) -> None:
    print(f"  FAIL  {msg}")


async def _post(c: httpx.AsyncClient, path: str, *, dry: bool, lib: bool = False, **kw: Any) -> dict | None:
    hdr = evolus.library_headers() if lib else evolus.headers()
    if dry:
        body = kw.get("json")
        print(f"  dry   POST {path} {json.dumps(body)[:160] if body else '(multipart)'}")
        return {"id": f"<{path.split('/')[-1]}-id>", "agentId": "<agent-id>"}
    r = await c.post(evolus._url(path), headers=hdr, **kw)
    if r.status_code >= 400:
        _fail(f"POST {path}: {evolus._explain(r)}")
        return None
    try:
        return r.json()
    except ValueError:
        return {}


def _id(obj: dict | None, *keys: str) -> str | None:
    if not obj:
        return None
    v = evolus.find_key(obj, *keys)
    return str(v) if v is not None else None


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--library", action="store_true")
    ap.add_argument("--agent", action="store_true")
    ap.add_argument("--extractor", action="store_true")
    ap.add_argument("--webhook", action="store_true")
    ap.add_argument("--webhook-url", default="", help="public URL of POST /api/webhooks/evolus/quote")
    ap.add_argument("--model-key", default="", help='agent modelKey, default "own/$EVOLUS_OWN_MODEL_NAME"')
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    s = get_settings()
    want = {k for k in ("library", "agent", "extractor", "webhook") if getattr(a, k) or a.all}
    if not want:
        want = {"library", "agent", "extractor", "webhook"} if a.dry_run else set()
    if not want:
        ap.print_help()
        return 2
    if not a.dry_run and not (s.evolus_api_key and s.evolus_workspace_id):
        print("EVOLUS_API_KEY and EVOLUS_WORKSPACE_ID must be set in backend/.env (see docs/EVOLUS_SETUP.md)")
        return 2
    env: dict[str, str] = {}
    failures = 0
    print(f"Provisioning on {s.evolus_api_base} · space {s.evolus_workspace_id or '(unset)'}"
          f"{' · DRY RUN' if a.dry_run else ''}\n")
    async with async_client(60.0) as c:
        lib_id = s.evolus_library_id
        if "library" in want:
            print("Knowledge library")
            if not lib_id:
                res = await _post(c, "/api/v1/memories/simple", dry=a.dry_run, lib=True,
                                  json={"name": f"{workspace.brand_name() or 'Brand'} knowledge"})
                lib_id = _id(res, "id", "memoryId") or ""
                if lib_id:
                    _ok(f"created library {lib_id}")
                else:
                    failures += 1
            else:
                _ok(f"reusing EVOLUS_LIBRARY_ID={lib_id}")
            files = library_files()
            if not files:
                _fail("the Brand workspace has no brand book, profile or suppliers yet - set it up first")
                failures += 1
            for name, data, ctype in files if lib_id else []:
                res = await _post(c, f"/api/v1/memories/{lib_id}/documents?language=en", dry=a.dry_run, lib=True,
                                  files={"file": (name, data, ctype)})
                if res is not None:
                    _ok(f"uploaded {name} -> document {_id(res, 'id') or '?'} (indexing in the background)")
                else:
                    failures += 1
            if lib_id:
                env["EVOLUS_LIBRARY_ID"] = lib_id

        if "agent" in want:
            print("Agent (the brain)")
            model_key = a.model_key or (f"own/{s.evolus_own_model_name}" if s.evolus_own_model_name else "")
            if not model_key:
                _fail("set EVOLUS_OWN_MODEL_NAME (the name you gave the AMD vLLM model on the Models page) "
                      "or pass --model-key own/<name>")
                failures += 1
            else:
                res = await _post(c, "/api/v1/agents", dry=a.dry_run, json={
                    "name": "Atelier Sourcing & Tech Design", "prompt": agent_prompt(), "language": "en",
                    "modelKey": model_key, "isChatVisible": True,
                    "description": "Tech packs, RFQs, creative direction and supplier picks for "
                                   f"{workspace.brand_name() or 'the brand'}"})
                agent_id = _id(res, "agentId", "id")
                if agent_id:
                    _ok(f"created agent {agent_id} on {model_key}")
                    env["EVOLUS_AGENT_MODEL"] = f"{s.evolus_workspace_id or '<spaceId>'}:{agent_id}"
                    if lib_id:
                        if await _post(c, f"/api/v1/agents/{agent_id}/memories", dry=a.dry_run,
                                       json={"memoryId": lib_id}) is not None:
                            _ok(f"attached library {lib_id}")
                        else:
                            failures += 1
                else:
                    failures += 1

        if "extractor" in want:
            print("Document extractor (supplier quotes)")
            model_key = a.model_key or (f"own/{s.evolus_own_model_name}" if s.evolus_own_model_name else "")
            res = await _post(c, "/api/v1/agents", dry=a.dry_run, json={
                "name": "Atelier Quote Reader", "prompt": EXTRACTOR_PROMPT, "language": "en", "isExtractor": True,
                **({"modelKey": model_key} if model_key else {})})
            ex_agent = _id(res, "agentId", "id")
            if ex_agent:
                res = await _post(c, f"/api/v1/agents/{ex_agent}/json", dry=a.dry_run, json={
                    "title": "Supplier quote", "structure": json.dumps(EXTRACTOR_SCHEMA),
                    "userPrompt": EXTRACTOR_PROMPT, "canUseOCR": True})
                ex_id = _id(res, "id", "outputStructureId")
                if ex_id:
                    _ok(f"created extractor {ex_id} on agent {ex_agent}")
                    env["EVOLUS_EXTRACTOR_AGENT_ID"] = ex_agent
                    env["EVOLUS_EXTRACTOR_ID"] = ex_id
                else:
                    failures += 1
            else:
                failures += 1

        if "webhook" in want:
            print("Webhook (inbound quotes -> Atelier)")
            if not a.webhook_url or not s.evolus_webhook_secret:
                _fail("needs --webhook-url (public https URL of /api/webhooks/evolus/quote) and EVOLUS_WEBHOOK_SECRET")
                failures += 1
            else:
                res = await _post(c, "/api/v1/webhooks", dry=a.dry_run, json={
                    "name": "Atelier quote intake", "url": a.webhook_url, "contentType": "application/json",
                    "apiKeyName": s.evolus_webhook_header, "apiKeyValue": s.evolus_webhook_secret})
                wid = _id(res, "id", "webhookId")
                if wid:
                    _ok(f"created webhook {wid} -> {a.webhook_url}")
                else:
                    failures += 1

        if not a.dry_run:
            try:
                r = await c.get(evolus._url("/api/v1/workflows/step-catalog"), headers=evolus.headers())
                if r.status_code < 400:
                    steps = evolus.find_key(r.json(), "steps") or []
                    print("\nWorkflow step catalog (for the UI / API): "
                          + ", ".join(f"{x.get('title')}={x.get('type')}" for x in steps if isinstance(x, dict)))
            except Exception as e:  # noqa: BLE001
                print(f"\n(step catalog unavailable: {e})")

    if env:
        print("\nAdd to backend/.env:\n")
        for k, v in env.items():
            print(f"{k}={v}")
    print(f"\n{'done' if not failures else f'{failures} step(s) failed - finish those in the UI (docs/EVOLUS_SETUP.md)'}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
