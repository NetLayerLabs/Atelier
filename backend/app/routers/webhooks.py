"""v3: inbound webhooks.

POST /api/webhooks/shopify/orders-create - Shopify orders/create (for when Atelier is hosted at a public URL;
localhost uses polling). Shopify signs the raw body: X-Shopify-Hmac-Sha256 = base64(HMAC-SHA256(app client
secret, raw body)). Unsigned / mis-signed requests get 401 and are never parsed.

POST /api/webhooks/evolus/quote - the email-triggered Evolus workflow ("When an email arrives" on the
supplier inbox -> "Call a data extractor" on the attachment -> "Call an endpoint (API)") posts the extracted
quote JSON here.

Auth: Evolus webhook/endpoint steps send a static header you choose (no signature), so the workflow sends
`X-Atelier-Webhook-Secret: <EVOLUS_WEBHOOK_SECRET>` (header name: EVOLUS_WEBHOOK_HEADER). For callers that can
sign, `X-Atelier-Signature: sha256=<hex HMAC-SHA256(secret, raw body)>` is accepted too. Comparisons are
constant-time. With no secret configured the endpoint is disabled (503): it never accepts unauthenticated data.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from ..config import get_settings
from ..services import preorders, shopify
from ..store import store

log = logging.getLogger("atelier.webhooks")
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


# --- Shopify orders/create ------------------------------------------------------------------------------

@router.post("/shopify/orders-create")
async def shopify_orders_create(request: Request) -> dict:
    secret = get_settings().shopify_webhook_key
    if not secret:
        raise HTTPException(503, "webhooks not configured: set SHOPIFY_WEBHOOK_SECRET (the app's client secret)")
    raw = await request.body()
    if not shopify.verify_webhook(raw, request.headers.get("X-Shopify-Hmac-Sha256"), secret):
        raise HTTPException(401, "invalid webhook signature")
    topic = request.headers.get("X-Shopify-Topic", "orders/create")
    if topic != "orders/create":
        return {"ok": True, "ignored": topic}
    try:
        payload = json.loads(raw)
        order = shopify.order_from_webhook(payload)
    except (ValueError, TypeError, AttributeError) as e:
        raise HTTPException(400, f"unreadable order payload: {e.__class__.__name__}") from e
    matched = []
    for line in order.lines:
        for run in preorders.runs_for_product(line.product_id):
            if run.id not in matched and preorders.record_order(run, order, "webhook"):
                matched.append(run.id)
    log.info("orders/create %s (%s) -> %s", order.name, request.headers.get("X-Shopify-Webhook-Id"),
             matched or "no tracked product")
    return {"ok": True, "order": order.name, "runs": matched}


# --- Evolus inbound quote -------------------------------------------------------------------------------

def verify(secret: str, raw: bytes, headers: dict[str, str], header_name: str) -> bool:
    if not secret:
        return False
    lower = {k.lower(): v for k, v in headers.items()}
    shared = lower.get(header_name.lower(), "")
    if shared and hmac.compare_digest(shared.strip().encode(), secret.encode()):
        return True
    sig = lower.get("x-atelier-signature", "").strip()
    if sig:
        expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig.encode(), expected.encode())
    return False


@router.post("/evolus/quote")
async def evolus_quote(request: Request) -> dict:
    from ..services import quotes

    s = get_settings()
    if not s.evolus_webhook_secret:
        raise HTTPException(503, "quote webhook disabled: set EVOLUS_WEBHOOK_SECRET")
    raw = await request.body()
    if not verify(s.evolus_webhook_secret, raw, dict(request.headers), s.evolus_webhook_header):
        log.warning("rejected quote webhook: bad or missing secret/signature")
        raise HTTPException(401, "invalid webhook secret or signature")
    try:
        payload = json.loads(raw or b"{}")
    except ValueError as e:
        raise HTTPException(400, "body must be JSON") from e
    if isinstance(payload, str):  # a workflow may send the extractor output as a JSON string
        try:
            payload = json.loads(payload)
        except ValueError as e:
            raise HTTPException(400, "body must be a JSON object") from e
    if not isinstance(payload, dict):
        payload = {"fields": payload}
    run = quotes.find_run_for(payload, store.runs)
    if run is None:  # LOW: no RFQ ref, unknown sender, several open runs: a person assigns it (never guessed)
        item = quotes.park_unmatched(payload, "no RFQ reference and no single open run from this sender")
        log.info("inbound quote parked as unmatched: %s", item["id"])
        return JSONResponse(status_code=202, content={"ok": True, "parked": True, "unmatchedId": item["id"],
                                                      "detail": "no matching run - parked for a person to assign"})
    try:
        q = await quotes.ingest_extracted(run, payload)
    except quotes.DuplicateQuote as d:  # QA M9: a replayed / repeated delivery
        q = d.quote
        return {"ok": True, "duplicate": True, "runId": run.id, "supplierName": q.supplier_name,
                "quoteNumber": q.quote_number, "unitPrice": q.unit_price}
    except quotes.QuoteError as e:
        raise HTTPException(422, str(e)) from e
    except ValueError as e:  # incl. QA H3 QuoteLocked: the PO is already drafted
        raise HTTPException(409, str(e)) from e
    return {"ok": True, "runId": run.id, "supplierName": q.supplier_name, "unitPrice": q.unit_price,
            "received": run.quote_round.received if run.quote_round else len(run.quotes or []),
            "expected": run.quote_round.expected if run.quote_round else None}
