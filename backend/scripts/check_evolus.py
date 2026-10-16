"""One-shot check of every Evolus building block Atelier uses, against the REAL API (backend/.env).

    cd backend && uv run python scripts/check_evolus.py              # everything that is configured
    uv run python scripts/check_evolus.py --no-execute               # no workflow runs, no extractor credits
    uv run python scripts/check_evolus.py --workflows outreach       # only that workflow
    uv run python scripts/check_evolus.py --atelier-url https://<tunnel>   # also hit our quote webhook

Blocks checked (each PASS / FAIL / SKIP when not configured):
  auth        GET /api/v1/ai-tools with X-ApiKey + X-Application-Id
  agents      GET /v1/models - EVOLUS_AGENT_MODEL must be listed
  brain       the agent answers a JSON request through Atelier's adapter (route "evolus-agent → <EVOLUS_AGENT_BACKEND>")
  library     GET /api/v1/memories/{EVOLUS_LIBRARY_ID}/documents - brand book + catalogue indexed
  extractor   POST …/ask-file on a real quote document you pass with --quote-pdf -> unit price / MOQ / lead time
  ai-tool     POST /api/v1/ai-tools/email/run (only with --ai-tool: it uses credits)
  webhook     POST {atelier-url}/api/webhooks/evolus/quote with the shared secret (expects 200 or 404 = no run
              waiting), and without it (expects 401)
  outreach / shopify   run the workflows once with sandbox data (polls to Completed)
  po          run the purchase-order workflow once (only with --test-to)

Workflow runs use sandbox data: RFQ recipients are *.test addresses, which can never be delivered. With
--test-to you@example.com the outreach / po runs send ONE real email, to that inbox only, subject "[Atelier TEST] …"
(use your own address: that is how you see that the Evolus mailer really delivers).
The Shopify workflow WILL create a product in whatever store it is connected to, so use a dev store.
Exit code 0 means every check that ran passed. Uses the app's own adapter (app/services/evolus.py).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.services import evolus, quotes, telemetry  # noqa: E402
from app.services.http import async_client  # noqa: E402

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
if not sys.stdout.isatty():
    GREEN = RED = DIM = RESET = ""

SAMPLE_TECHPACK = {
    "garmentName": "Atelier Check Jacket", "description": "Connectivity test from scripts/check_evolus.py.",
    "billOfMaterials": [{"material": "Selvedge denim", "quantity": "2.4 m", "targetCostPerUnit": 42.0}],
    "measurements": {"chest": "46in"}, "targetSupplierRegion": "check region",
    "targetRetailPrice": 389, "productionQuantity": 300,
}
SAMPLE_EMAILS = [{"supplierName": "Test Mill", "region": "Prato, Italy", "toEmail": "rfq+check@atelier-demo.test",
                  "subject": "RFQ: Atelier Check Jacket - 300 units [ATL-run_check]",
                  "body": "Connectivity test. Please ignore.", "status": "drafted"}]


def test_emails(to: str, kind: str) -> list[dict]:
    """The sandbox RFQ (undeliverable *.test address), or one real test email to `to` (your own inbox)."""
    if not to:
        return SAMPLE_EMAILS
    what = "Purchase order PO-TEST" if kind == "purchase_order" else "RFQ: Atelier Check Jacket - 300 units"
    return [{**SAMPLE_EMAILS[0], "toEmail": to, "kind": kind, "rfqRef": "ATL-run_check",
             "subject": f"[Atelier TEST] {what} [ATL-run_check]",
             "body": "Test email from Atelier's scripts/check_evolus.py, sent through the Evolus workflow.\n"
                     "Nothing to do: it only checks that the Evolus mailer delivers.\n\n"
                     # As long as a real RFQ: Evolus caps a parameter at 500 characters, so this checks that the
                     # drafted emails are split into pieces and joined again by the workflow script.
                     + "\n".join(f"Line {i}: a real RFQ carries the style, quantities, sizes, fabrics and the "
                                  f"deadline for the quote." for i in range(1, 16))}]


def line(ok: bool | None, name: str, msg: str) -> bool:
    tag = f"{GREEN}PASS" if ok else (f"{DIM}SKIP" if ok is None else f"{RED}FAIL")
    print(f"  {tag}{RESET}  {name:<10} {msg}")
    return ok is not False


async def run_workflow(name: str, wf: str, params: dict) -> bool:
    async def on_status(status: str, polls: int) -> None:
        print(f"  {DIM}      {name:<10} poll {polls}: {status}{RESET}")

    t = telemetry.Timer()
    try:
        keys = None if name == "shopify" else evolus.EMAIL_WORKFLOW_PARAMS  # what the app sends
        res = await evolus.execute_workflow(wf, params, purpose=f"check_{name}", on_status=on_status,
                                            param_keys=keys)
    except Exception as e:  # noqa: BLE001
        return line(False, name, f"workflow {wf}: {e} ({t.ms:,.0f}ms)")
    extra = ""
    if name == "shopify":
        p = evolus.parse_shopify(res)
        extra = f" · product {p['productId'] or '(none found in output)'} {p['url'] or ''}"
    elif name in ("outreach", "po"):
        extra = f" · RFQ status -> {evolus.outreach_status(res)}"
    if res["timedOut"]:
        return line(True, name, f"workflow {wf}: accepted, still {res['status']} after "
                                f"{get_settings().evolus_poll_timeout:.0f}s (execution {res['executionId']}){extra}")
    out = str(res.get("execution"))[:160]
    return line(True, name, f"workflow {wf}: {res['status']} in {t.ms:,.0f}ms, {res['polls']} polls "
                            f"(execution {res['executionId']}){extra}\n        {DIM}last status body: {out}{RESET}")


async def check_brain() -> bool:
    def validate(d):
        if not isinstance(d, dict) or "ok" not in d:
            raise ValueError("expected {\"ok\": ...}")
        return d

    msgs = [{"role": "user", "content": 'Health check. Reply with ONLY this JSON: {"ok": true, '
                                        '"brandBookFound": <true if you can read the brand book in your knowledge library>}'}]
    t = telemetry.Timer()
    try:
        value, meta = await evolus.agent_chat_json(messages_for_attempt=lambda a: msgs, validate=validate,
                                                   purpose="check_brain", max_tokens=60)
    except Exception as e:  # noqa: BLE001
        return line(False, "brain", f"{get_settings().evolus_agent_model}: {e}")
    cites = ", ".join(c.source for c in meta.get("citations") or []) or "none returned"
    return line(True, "brain", f"evolus-agent → {get_settings().evolus_agent_backend} answered {json.dumps(value)[:80]} in {t.ms:,.0f}ms · "
                               f"conversation {meta.get('conversationId')} · citations: {cites}")


async def check_library() -> bool:
    try:
        docs = await evolus.library_documents()
    except Exception as e:  # noqa: BLE001
        return line(False, "library", f"{get_settings().evolus_library_id}: {e} "
                                      f"(set EVOLUS_USER_API_KEY if the app key gets 401 on libraries)")
    names = [f"{d.get('title')} (status {d.get('ingestionStatus')}, {d.get('chunkCount', '?')} chunks)" for d in docs]
    ok = len(docs) >= 2
    return line(ok, "library", f"{len(docs)} document(s): {'; '.join(names) or '-'}"
                               + ("" if ok else " - upload the brand book in the Brand workspace (or scripts/provision_evolus.py)"))


async def check_extractor(path: str) -> bool:
    pdf = Path(path).read_bytes()
    t = telemetry.Timer()
    try:
        res = await evolus.run_extractor(pdf, Path(path).name, "application/pdf")
    except Exception as e:  # noqa: BLE001
        return line(False, "extractor", f"{get_settings().evolus_extractor_id}: {e}")
    values, _ = quotes.map_fields(res.get("fields"))
    got = {k: values.get(k) for k in ("supplierName", "unitPrice", "currency", "moq", "leadTime")}
    ok = all(values.get(k) not in (None, "") for k in ("unitPrice", "moq", "leadTime"))
    return line(ok, "extractor", f"{t.ms:,.0f}ms · execution {res.get('extractionId')} · mapped {got}"
                                 + ("" if ok else f"\n        {DIM}raw: {str(res.get('fields'))[:200]}{RESET}"))


async def check_ai_tool() -> bool:
    try:
        out = await evolus.run_ai_tool("email", "Ask the mill for a PDF quote with unit price, MOQ and lead time.",
                                       {"mode": "write", "tone": "commercial"}, purpose="check_ai_tool")
    except Exception as e:  # noqa: BLE001
        return line(False, "ai-tool", f"email: {e}")
    return line(True, "ai-tool", f"email -> {out[:70]!r}…")


async def check_webhook(base: str) -> bool:
    s = get_settings()
    url = f"{base.rstrip('/')}/api/webhooks/evolus/quote"
    body = {"subject": "check_evolus.py webhook test", "extraction": {"supplier_name": "Test Mill"}}
    try:
        async with async_client(10) as c:
            unauth = await c.post(url, json=body)
            auth = await c.post(url, json=body, headers={s.evolus_webhook_header: s.evolus_webhook_secret})
    except Exception as e:  # noqa: BLE001
        return line(False, "webhook", f"{url}: {e}")
    ok = unauth.status_code == 401 and auth.status_code in (200, 404, 422)
    return line(ok, "webhook", f"{url}: without secret {unauth.status_code} (want 401), with secret "
                               f"{auth.status_code} (want 404 = no run waiting, or 200/422)")


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-execute", action="store_true", help="no workflow runs and no extractor call")
    ap.add_argument("--workflows", default="outreach,shopify")
    ap.add_argument("--ai-tool", action="store_true", help="also run the 'email' AI Tool (uses credits)")
    ap.add_argument("--atelier-url", default="", help="public URL of this backend, to test the quote webhook")
    ap.add_argument("--quote-pdf", default="", help="a real supplier quote document to run the extractor on")
    ap.add_argument("--test-to", default="", help="send the outreach / po test email to this inbox (your own)")
    a = ap.parse_args()
    s = get_settings()
    print(f"Atelier Evolus check · {s.evolus_api_base}\n")
    missing = [k for k, v in {"EVOLUS_API_KEY": s.evolus_api_key, "EVOLUS_WORKSPACE_ID": s.evolus_workspace_id}.items()
               if not v]
    if missing:
        print(f"{RED}FAIL{RESET}  config: {', '.join(missing)} not set in backend/.env (see docs/EVOLUS_SETUP.md)")
        return 2
    results = []
    ok, detail, ms = await evolus.probe()
    results.append(line(ok, "auth", f"GET {s.evolus_probe_path} · {ms:,.0f}ms · {detail}"))
    agents: list[str] = []
    try:
        agents = await evolus.list_agents()
        results.append(line(True, "agents", f"GET /v1/models · {len(agents)} agent(s): {', '.join(agents[:4]) or '-'}"))
    except Exception as e:  # noqa: BLE001
        results.append(line(False, "agents", f"GET /v1/models: {e}"))
    model = s.evolus_agent_model.strip()
    if model:
        if agents and model not in agents:
            results.append(line(False, "agents", f"EVOLUS_AGENT_MODEL {model} is not in that list"))
        results.append(await check_brain())
    else:
        line(None, "brain", "EVOLUS_AGENT_MODEL not set - the brain is direct vLLM / fallback")
    if s.evolus_library_id:
        results.append(await check_library())
    else:
        line(None, "library", "EVOLUS_LIBRARY_ID not set")
    if s.evolus_extractor_live and not a.no_execute and a.quote_pdf:
        results.append(await check_extractor(a.quote_pdf))
    else:
        line(None, "extractor", "EVOLUS_EXTRACTOR_AGENT_ID / EVOLUS_EXTRACTOR_ID not set" if not s.evolus_extractor_live
             else "--no-execute" if a.no_execute else "pass --quote-pdf <a real supplier quote PDF> to test it")
    if a.ai_tool:
        results.append(await check_ai_tool())
    else:
        line(None, "ai-tool", "pass --ai-tool to run it (uses credits)")
    if a.atelier_url and s.evolus_webhook_secret:
        results.append(await check_webhook(a.atelier_url))
    else:
        line(None, "webhook", "pass --atelier-url and set EVOLUS_WEBHOOK_SECRET")

    wanted = {w.strip() for w in a.workflows.split(",") if w.strip()}
    if a.no_execute:
        line(None, "workflows", "--no-execute")
    else:
        if "outreach" in wanted:
            if s.evolus_outreach_workflow_id:
                results.append(await run_workflow("outreach", s.evolus_outreach_workflow_id, {
                    "garment_name": SAMPLE_TECHPACK["garmentName"], "production_quantity": 300,
                    "tech_pack": SAMPLE_TECHPACK, "image_url": "https://example.com/atelier-check.png",
                    "rfq_emails": test_emails(a.test_to, "rfq"), "rfq_ref": "ATL-run_check"}))
            else:
                line(None, "outreach", "EVOLUS_OUTREACH_WORKFLOW_ID not set")
        if "po" in wanted:
            if not a.test_to:
                line(None, "po", "pass --test-to <your own inbox> to run the purchase-order workflow")
            elif s.evolus_po_workflow_id:
                results.append(await run_workflow("po", s.evolus_po_workflow_id, {
                    "kind": "purchase_order", "po_number": "PO-TEST", "supplier_name": "Test Mill",
                    "to_email": a.test_to, "quantity": 300, "unit_price": 42.0, "currency": "EUR", "total": 12600.0,
                    "rfq_ref": "ATL-run_check", "quote_number": "", "garment_name": SAMPLE_TECHPACK["garmentName"],
                    "production_quantity": 300, "rfq_emails": test_emails(a.test_to, "purchase_order")}))
            else:
                line(None, "po", "EVOLUS_PO_WORKFLOW_ID not set (POs then go through the outreach workflow)")
        if "shopify" in wanted:
            if s.evolus_shopify_workflow_id:
                results.append(await run_workflow("shopify", s.evolus_shopify_workflow_id, {
                    "title": "Atelier Check Jacket", "description": "Connectivity test - safe to delete.",
                    "price": 389, "image_url": "https://example.com/atelier-check.png",
                    "handle": "atelier-check-jacket", "production_quantity": 300}))
            else:
                line(None, "shopify", "EVOLUS_SHOPIFY_WORKFLOW_ID not set")
    if s.evolus_inbound_workflow_id:
        line(None, "inbound", f"workflow {s.evolus_inbound_workflow_id}: email-triggered, so test it by emailing a "
                              f"supplier's quote PDF to the monitored inbox")
    ok = all(results)
    print(f"\n{GREEN + 'ALL PASS' if ok else RED + 'SOME CHECKS FAILED'}{RESET} ({sum(results)}/{len(results)})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
