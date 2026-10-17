"""Regression tests for the pre-pitch audit of 17 Oct 2026 (each defect was reproduced by an auditor first)."""

from __future__ import annotations

import json

import httpx
import pytest
from conftest import go_live, route
from fake_upstreams import create_evolus_app, tiny_png
from helpers import answer_all_rfqs, awaiting, collecting, upload_quote, wait

from app.services import http, shopify
from app.services.errors import HINTS, NotConfigured, ServiceError
from app.store import store  # noqa: F401

SHOP = "shop.fake"  # conftest.route()'s fake Shopify store


class Flaky(httpx.AsyncBaseTransport):
    """`fail(request)` -> a status code to answer (or None to pass through)."""

    def __init__(self, inner, fail):
        self.inner, self.fail, self.hits = inner, fail, 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        what = self.fail(request)
        if what is not None:
            self.hits += 1
            return httpx.Response(what, json={"error": "fake outage"}, request=request)
        return await self.inner.handle_async_request(request)


def _approve(client, qty: int = 300) -> str:
    t = client.post("/api/trends/analyze", files=[("images", ("b.png", tiny_png(), "image/png"))]).json()
    d = client.post("/api/designs/generate", json={"trendId": t["id"], "count": 1}).json()["designs"][0]
    r = client.post(f"/api/designs/{d['id']}/approve", json={"productionQuantity": qty})
    assert r.status_code == 200, r.text
    return r.json()["runId"]


# 1. A configured service that fails gets no "set X" setup hint; a missing one still does.
def test_setup_hint_only_for_a_service_that_is_not_configured():
    assert NotConfigured("vision", "not connected").hint == HINTS["vision"]
    assert ServiceError("vision", "Vision model call failed at host: timed out").hint is None
    assert ServiceError("evolus_outreach", "Evolus HTTP 402").hint is None
    assert ServiceError("vision", "x", hint="custom").hint == "custom"


# 2. One failed status poll is retried; only a run of failures becomes "status unknown".
def test_one_failed_status_poll_does_not_become_status_unknown(client, s, monkeypatch):
    go_live(monkeypatch, s, shopify_store_domain="")
    evo = create_evolus_app()
    route(evolus_app=evo)
    hits = {"n": 0}

    def fail(req):
        if "/executions/" in req.url.path and hits["n"] < 2:  # the first two polls blip
            hits["n"] += 1
            return 502
        return None

    http.set_transport(Flaky(http._transport, fail))
    run_id = _approve(client)
    run = wait(client, run_id, awaiting)
    step = run["steps"][1]
    assert step["status"] == "done" and "unknownExecutionId" not in step, step
    assert hits["n"] == 2 and len(evo.state.executions) == 1  # recovered on the next poll, nothing re-sent


def test_a_run_of_failed_polls_is_still_status_unknown(client, s, monkeypatch):
    go_live(monkeypatch, s, shopify_store_domain="")
    evo = create_evolus_app()
    route(evolus_app=evo)
    http.set_transport(Flaky(http._transport, lambda req: 500 if "/executions/" in req.url.path else None))
    run_id = _approve(client)
    run = wait(client, run_id)
    assert run["status"] == "failed" and "status unknown" in run["steps"][1]["error"]


# 3. A "partial" workflow result names who was not emailed and keeps that RFQ as a draft.
def test_partial_send_names_the_unsent_recipient(client, s, monkeypatch):
    go_live(monkeypatch, s, shopify_store_domain="")
    evo = create_evolus_app()
    route(evolus_app=evo)
    orig = evo.state.executions  # the fake's store; patch its status handler's output through the transport

    class Partial(httpx.AsyncBaseTransport):
        def __init__(self, inner):
            self.inner = inner

        async def handle_async_request(self, request):
            resp = await self.inner.handle_async_request(request)
            if "/executions/" in request.url.path and resp.status_code == 200:
                body = json.loads(await resp.aread())
                if body.get("status") == "Completed" and "emailStatus" in (body.get("output") or ""):
                    eid = body["executionId"]
                    emails = json.loads(orig[eid]["parameters"]["rfq_emails"])
                    out = {"emailStatus": "partial", "sentCount": len(emails) - 1, "notSentCount": 1,
                           "emails": [{"toEmail": e["toEmail"], "result": "sent"} for e in emails[:-1]]
                           + [{"toEmail": emails[-1]["toEmail"], "result": "not sent",
                               "error": "no email step for this address"}]}
                    body["output"] = json.dumps(out)
                    return httpx.Response(200, json=body, request=request)
            return resp

    http.set_transport(Partial(http._transport))
    run_id = _approve(client)
    run = wait(client, run_id, awaiting)
    emails = run["supplierEmails"]
    assert [e["status"] for e in emails[:-1]] == ["queued"] * (len(emails) - 1) and emails[-1]["status"] == "drafted"
    log = "\n".join(run["steps"][1]["log"])
    assert f"{len(emails) - 1} of {len(emails)} RFQs" in log
    assert "Not sent" in log and emails[-1]["supplierName"] in log and "provision_evolus_workflows" in log


# 4. The PO carries the production plan as it stands when the gate opens, not when the window opened.
def test_po_quantity_follows_a_tech_pack_edit_during_the_window(client, s, monkeypatch):
    from fake_upstreams import create_shopify_app

    shop = create_shopify_app()
    go_live(monkeypatch, s, shopify_store_domain=SHOP, shopify_admin_token="shpat_fake", demand_stage_threshold=1)
    route(shopify_app=shop, **{SHOP: shop})
    run_id = _approve(client, qty=500)
    answer_all_rfqs(client, run_id, moq=250)
    run = wait(client, run_id, collecting)
    assert run["demand"]["productionThreshold"] == 500
    r = client.patch(f"/api/runs/{run_id}/techpack", json={"productionQuantity": 300})
    assert r.status_code == 200 and r.json()["demand"]["productionThreshold"] == 300
    shop.state.place_order(run["shopifyProduct"]["productId"], 1, first_name="Ana", city="Porto", size="M")
    run = wait(client, run_id, lambda r: r["status"] != "running")
    po = run["demand"]["purchaseOrder"]
    assert po["quantity"] == 300 and run["demand"]["productionThreshold"] == 300


# 5. A late quote after the gate passed never re-selects a mill that breaks a guardrail on its own.
def test_late_quote_that_breaks_a_guardrail_does_not_take_over(client, s, monkeypatch):
    go_live(monkeypatch, s, shopify_store_domain="")  # stop before Shopify
    route()
    # max lead time 10 weeks; the two first quotes pass, a later cheaper one at 11 weeks scores higher but breaks it
    assert client.put("/api/guardrails", json={"maxLeadTimeWeeks": 10, "minGrossMarginPct": 50}).status_code == 200
    run_id = _approve(client)
    run = wait(client, run_id, awaiting)
    names = [e["supplierName"] for e in run["supplierEmails"]]
    for n in names[:-1]:
        upload_quote(client, run_id, n, price=101.5, lead="8 weeks")
    assert client.post(f"/api/runs/{run_id}/quotes/close").status_code == 200
    run = wait(client, run_id, lambda r: r["steps"][2]["status"] == "done" or r["status"] != "running")
    before = run["recommendation"]["selectedSupplierName"]
    assert run["guardrailReport"]["selectedOk"] is True and before in names[:-1]
    run = upload_quote(client, run_id, names[-1], price=80.0, lead="11 weeks")  # late, cheaper, too slow
    assert run["recommendation"]["selectedSupplierName"] == before
    held = [a for a in run["audit"] if a["action"] == "late_quote_held"]
    assert held and names[-1] in held[0]["summary"] and before in held[0]["summary"]


# 6. The Shopify description states the brand's own delivery promise, never a padded guess.
def test_preorder_description_uses_the_brands_delivery_promise():
    html = shopify.preorder_description_html("Tailored garment.", lead_weeks=6, materials=["Wool"],
                                             delivery_promise_weeks=6)
    assert "Delivery: about 6 weeks after the pre-order window closes." in html and "8 weeks" not in html
    html = shopify.preorder_description_html("Tailored garment.", lead_weeks=6, materials=["Wool"])
    assert "quoted production lead time is 6 weeks" in html and "8 weeks" not in html
    html = shopify.preorder_description_html("Tailored garment.")
    assert "weeks" not in html and "Pre-order." in html


# 7. Hosted demo: a request rejected before the model (bad input) does not use one of the visitor's model calls.
def test_rejected_input_does_not_use_a_model_call():
    from app.security import RateLimiter

    lim = RateLimiter()
    for _ in range(15):
        assert lim.hit("203.0.113.9", 15, 120) is None
        lim.refund("203.0.113.9")
    assert lim.hit("203.0.113.9", 15, 120) is None  # 15 refunded rejections later, still within the limit
