"""v3: Evolus as the brain (agent -> AMD vLLM, else direct vLLM; v5: no template fallback), knowledge citations,
real supplier quotes (upload -> extractor, inbound-email webhook), the quote round and FX.

Every Evolus / vLLM call goes in-process to the test doubles in tests/fake_upstreams.py (no sockets).
"""

import hashlib
import hmac
import json
import time

import pytest
import conftest
from helpers import quote_pdf

from app.services import evolus, fx, knowledge, quotes, telemetry
from app.store import store
from fake_upstreams import create_ecb_app, create_evolus_app

VLLM = conftest.VLLM
EVO = conftest.EVO
SECRET = "s3cret-hook"


@pytest.fixture(autouse=True)
def s(s, monkeypatch):
    """Every service on the test doubles (the brain = direct vLLM); tests switch on the agent with `live()`."""
    evolus._doc_titles.clear()
    conftest.go_live(monkeypatch, s)
    conftest.route()
    yield s
    evolus._doc_titles.clear()


def live(monkeypatch, st, *, agent=True, vllm=True, extractor=False, **over):
    vals = {
        "amd_vllm_endpoint": f"http://{VLLM}/v1" if vllm else "",
        "evolus_agent_model": "app_test:agent_sourcing" if agent else "", "evolus_library_id": "lib_1",
        "evolus_extractor_agent_id": "agent_x" if extractor else "", "evolus_extractor_id": "ext_quote" if extractor else "",
        "evolus_agent_label": "Qwen3.6-35B-A3B",
    }
    vals.update(over)
    conftest.go_live(monkeypatch, st, **vals)


def route(evolus_app=None, vllm_app=None, **extra):
    if vllm_app is not None:
        extra[VLLM] = vllm_app
    return conftest.route(evolus_app=evolus_app, **extra)


def _wait(client, run_id, cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        run = client.get(f"/api/runs/{run_id}").json()
        if cond(run):
            return run
        time.sleep(0.02)
    raise AssertionError(f"condition not reached: {client.get(f'/api/runs/{run_id}').json().get('steps')}")


def _awaiting(run):
    return (run.get("quoteRound") or {}).get("status") == "awaiting"


def _approve(client, qty=500):
    from fake_upstreams import tiny_png

    t = client.post("/api/trends/analyze", files=[("images", ("b.png", tiny_png(), "image/png"))]).json()
    d = client.post("/api/designs/generate", json={"trendId": t["id"], "count": 1}).json()["designs"][0]
    return client.post(f"/api/designs/{d['id']}/approve", json={"productionQuantity": qty}).json()["runId"]


def _doc(run_id, name, **kw):
    return quote_pdf(name, ref=f"ATL-{run_id}", **kw)


def _names(run):
    return [e["supplierName"] for e in run["supplierEmails"]]


# --------------------------------------------------------------------------- the brain


def test_agent_is_the_brain_with_citations(client, s, monkeypatch):
    live(monkeypatch, s)
    apps = route()
    run_id = _approve(client)
    run = _wait(client, run_id, _awaiting)
    tp_step = run["steps"][0]
    assert tp_step["route"] == "evolus-agent → AMD vLLM"
    assert any("Evolus agent app_test:agent_sourcing → AMD vLLM (Qwen3.6-35B-A3B)" in line for line in tp_step["log"])
    calls = [c for c in tp_step["telemetry"] if c["purpose"] == "techpack"]
    assert calls[-1]["route"] == "evolus-agent → AMD vLLM" and calls[-1]["ok"] and calls[-1]["fake"] is True
    assert calls[-1]["endpointHost"] == EVO and calls[-1]["model"] == "app_test:agent_sourcing"
    tp = run["techPack"]
    assert tp["generatedBy"] == "evolus-agent → AMD vLLM"
    assert tp["citations"] and all(c["library"] == "local" for c in tp["citations"])
    assert any("Brand Book" in c["source"] for c in tp["citations"])
    # the agent really got the knowledge passages and plain-text content
    body = apps[EVO].state.chat_calls[0]
    assert body["model"] == "app_test:agent_sourcing"
    assert "Knowledge library passages" in body["messages"][-1]["content"]
    # RFQs too, with the RFQ reference in every subject
    assert run["steps"][1]["route"] == "evolus-agent → AMD vLLM"
    assert all(f"ATL-{run_id}" in e["subject"] for e in run["supplierEmails"])


def test_agent_down_falls_back_to_direct_vllm(client, s, monkeypatch):
    live(monkeypatch, s)
    route(evolus_app=create_evolus_app(agent_down=True))
    run = _wait(client, _approve(client), _awaiting)
    step = run["steps"][0]
    assert step["route"] == "direct vLLM"
    assert any("Evolus agent" in line and "next in the chain" in line for line in step["log"])
    routes = [(c["route"], c["ok"]) for c in step["telemetry"] if c["purpose"] == "techpack"]
    assert ("evolus-agent → AMD vLLM", False) in routes and routes[-1] == ("direct vLLM", True)
    assert run["techPack"]["generatedBy"] == "direct vLLM"


def test_everything_down_is_an_honest_error_with_retry(client, s, monkeypatch):
    live(monkeypatch, s, amd_vllm_endpoint="http://nobody.fake:9/v1", atelier_llm_timeout=1.0)
    route(evolus_app=create_evolus_app(agent_down=True))
    run = _wait(client, _approve(client), lambda r: r["status"] != "running")
    step = run["steps"][0]
    assert run["status"] == "failed" and step["status"] == "error" and step["service"] == "brain"
    assert step["error"].startswith("The brain failed: Evolus agent") and "direct vLLM" in step["error"]
    assert step["retryable"] and "techPack" not in run
    assert not any(c.get("simulated") for c in step["telemetry"])  # only real (failed) calls were recorded
    assert all(c["ok"] is False for c in step["telemetry"])


def test_rest_transport_returns_evolus_citations(s, monkeypatch):
    live(monkeypatch, s, evolus_agent_transport="rest")
    route()
    from app.services import brain

    async def go():
        return await brain.think_json("techpack", lambda a, ctx: [{"role": "user", "content": "tech pack " + ctx}],
                                      lambda d: d, knowledge_query="jacket fit block")

    import asyncio

    t = asyncio.run(go())
    assert t.route == brain.ROUTE_AGENT
    evo = [c for c in t.citations if c.library == "evolus"]
    assert evo and evo[0].source == "Fake library - Brand Book" and evo[0].document_id == "doc_brand"


def test_creative_direction_through_agent(client, s, monkeypatch, trend):
    live(monkeypatch, s)
    route()
    d = client.post("/api/designs/generate", json={"trendId": trend["id"], "count": 1}).json()["designs"][0]
    body = client.post(f"/api/designs/{d['id']}/direct", json={"instruction": "darker and cropped", "count": 1}).json()
    dr = body["direction"]
    assert "mode" not in dr and dr["generatedBy"] == "evolus-agent → AMD vLLM"
    assert dr["interpretation"].startswith("I'll deepen")


def test_local_knowledge_search_finds_brand_rules():
    """v5: passages come from the Brand workspace (the TEST brand book + the catalogue generated from the TEST
    supplier directory)."""
    hits = knowledge.local_search("jacket fit block chest shoulder", 3)
    assert hits and "Fit blocks" in hits[0].source and hits[0].document_id.startswith("doc_")
    cat = knowledge.local_search("TEST Indigo Denim selvedge certifications MOQ", 3)
    assert any("TEST Indigo Denim" in c.source for c in cat)
    assert all("@" not in (c.snippet or "") for c in cat)  # contact addresses never go into the catalogue


# --------------------------------------------------------------------------- real quotes: upload


def test_quote_round_waits_for_real_documents(client, s, monkeypatch):
    monkeypatch.setattr(s, "shopify_store_domain", "")
    run_id = _approve(client)
    run = _wait(client, run_id, _awaiting)
    rnd = run["quoteRound"]
    assert rnd["expected"] == len(run["supplierEmails"]) == len(rnd["awaiting"]) and rnd["received"] == 0
    assert rnd["rfqRef"] == f"ATL-{run_id}" and "simulated" not in rnd
    step = next(x for x in run["steps"] if x["key"] == "supplier_quotes")
    assert step["status"] == "running"
    assert any(f"Awaiting replies - 0 of {rnd['expected']} received" in line for line in step["log"])
    assert not run.get("quotes")  # nothing simulated, nothing invented
    time.sleep(0.3)
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "running"  # still waiting

    keys = _names(run)
    r = client.post(f"/api/runs/{run_id}/quotes", files={"file": ("q1.pdf", _doc(run_id, keys[0]),
                                                                  "application/pdf")})
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["quoteRound"]["received"] == 1 and run["quoteRound"]["status"] == "awaiting"
    q = run["quotes"][0]
    assert "simulated" not in q and q["source"]["channel"] == "upload"
    assert q["source"]["engine"] == "amd-llm"  # no Evolus extractor configured -> the AMD LLM read the text
    # QA M5: private, served by an authorised route with its real type (not from /static)
    assert q["source"]["documentUrl"].startswith(f"http://testserver/api/runs/{run_id}/quotes/documents/")
    doc = client.get(q["source"]["documentUrl"].removeprefix("http://testserver"))
    assert doc.status_code == 200 and doc.headers["content-type"] == "application/pdf"
    assert doc.headers["x-content-type-options"] == "nosniff"
    assert q["quoteNumber"].startswith("Q-") and q["unitPrice"] > 0 and q["moq"] > 0
    assert {f["name"] for f in q["source"]["fields"]} >= {"unitPrice", "moq", "leadTime", "quoteNumber"}
    assert client.get(q["source"]["documentUrl"].replace("http://testserver", "")).status_code == 200
    step = next(x for x in run["steps"] if x["key"] == "supplier_quotes")
    assert any(f"Awaiting replies - 1 of {run['quoteRound']['expected']} received" in line for line in step["log"])

    for k in keys[1:]:
        assert client.post(f"/api/runs/{run_id}/quotes", files={"file": (f"{k[:6]}.pdf", _doc(run_id, k),
                                                                         "application/pdf")}).status_code == 200
    run = _wait(client, run_id, lambda r: r.get("recommendation"))
    assert run["quoteRound"]["status"] == "complete" and run["quoteRound"]["awaiting"] == []
    assert run["recommendation"]["supplierName"] in {x["supplierName"] for x in run["quotes"]}
    assert run["recommendation"]["generatedBy"] == "direct vLLM"
    run = _wait(client, run_id, lambda r: r["status"] != "running", timeout=20)
    steps = {x["key"]: x for x in run["steps"]}
    assert steps["supplier_quotes"]["status"] == "done"
    # No Shopify store: the pipeline stops honestly at the pre-order (tests/test_shopify.py covers the real store)
    assert run["status"] == "failed" and "Shopify not connected" in steps["shopify_preorder"]["error"]


def test_eur_quote_is_converted_with_the_ecb_rate(client, s):
    run_id = _approve(client)
    run = _wait(client, run_id, _awaiting)
    name = _names(run)[0]
    pdf = _doc(run_id, "Some Mill", currency="EUR", price=220.0, sample=100.0)
    r = client.post(f"/api/runs/{run_id}/quotes", files={"file": ("eur.pdf", pdf, "application/pdf")},
                    data={"supplierName": name})
    assert r.status_code == 200, r.text
    q = r.json()["quotes"][0]
    assert q["supplierName"] == name and q["currency"] == "EUR" and q["unitPriceQuoted"] == 220.0
    assert q["unitPrice"] == pytest.approx(242.0) and q["fxRate"] == pytest.approx(1.1)  # fake ECB: 1 EUR = 1.10 USD
    assert q["fxSource"] == fx.SOURCE and q["fxDate"] == "2026-10-12" and q["sampleCost"] == pytest.approx(110.0)
    assert any("ECB reference rate of 2026-10-12" in w for w in q["source"]["warnings"])


def test_without_fx_rates_the_quote_stays_in_its_currency(client, s):
    route(**{conftest.ECB: create_ecb_app(down=True)})
    run_id = _approve(client)
    run = _wait(client, run_id, _awaiting)
    name = _names(run)[0]
    r = client.post(f"/api/runs/{run_id}/quotes", files={"file": ("eur.pdf", _doc(run_id, name, currency="EUR",
                                                                               price=220.0), "application/pdf")},
                    data={"supplierName": name})
    q = r.json()["quotes"][0]
    assert q.get("unitPrice") is None and q["currency"] == "EUR" and q["unitPriceQuoted"] == 220.0
    assert "fxRate" not in q and any("not converted" in w for w in q["source"]["warnings"])
    assert q["scoreBreakdown"].get("price") is None


def test_missing_fields_are_not_stated_never_assumed(client, s):
    run_id = _approve(client)
    run = _wait(client, run_id, _awaiting)
    name = _names(run)[0]
    pdf = _doc(run_id, name, moq=None, lead=None, sample=None, terms=None, note=None)
    q = client.post(f"/api/runs/{run_id}/quotes", files={"file": ("q.pdf", pdf, "application/pdf")},
                    data={"supplierName": name}).json()["quotes"][0]
    for k in ("moq", "leadTimeWeeks", "sampleCost", "paymentTerms"):
        assert k not in q, k
    assert {"MOQ not stated", "lead time not stated"} <= set(q["source"]["warnings"])


def test_upload_rejects_documents_without_a_price(client, s):
    run_id = _approve(client)
    _wait(client, run_id, _awaiting)
    from reportlab.pdfgen import canvas
    import io

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, "TEST Indigo Denim - thank you, we will come back next week.")
    c.save()
    r = client.post(f"/api/runs/{run_id}/quotes", files={"file": ("letter.pdf", buf.getvalue(), "application/pdf")})
    assert r.status_code == 422 and "unit price" in r.json()["detail"]
    r = client.post(f"/api/runs/{run_id}/quotes", files={"file": ("x.png", b"\x89PNG....", "image/png")})
    assert r.status_code == 422


def test_close_round_needs_a_quote_then_recommends(client, s):
    run_id = _approve(client)
    run = _wait(client, run_id, _awaiting)
    assert client.post(f"/api/runs/{run_id}/quotes/close").status_code == 409
    k = _names(run)[0]
    client.post(f"/api/runs/{run_id}/quotes", files={"file": ("a.pdf", _doc(run_id, k), "application/pdf")})
    r = client.post(f"/api/runs/{run_id}/quotes/close")
    assert r.status_code == 200 and r.json()["quoteRound"]["status"] == "closed"
    run = _wait(client, run_id, lambda x: x.get("recommendation"))
    step = next(x for x in run["steps"] if x["key"] == "supplier_quotes")
    assert any("Round closed by the creative director with 1 of" in line for line in step["log"])


def test_upload_through_evolus_extractor(client, s, monkeypatch):
    live(monkeypatch, s, extractor=True)
    apps = route()
    run_id = _approve(client)
    run = _wait(client, run_id, _awaiting)
    k = _names(run)[0]
    r = client.post(f"/api/runs/{run_id}/quotes", files={"file": ("mill.pdf", _doc(run_id, k),
                                                                  "application/pdf")})
    assert r.status_code == 200, r.text
    q = r.json()["quotes"][0]
    assert q["source"]["engine"] == "evolus-extractor" and q["source"]["engineLabel"] == "Evolus document extractor"
    assert q["source"]["extractionId"].startswith("askx_")
    assert q["quoteNumber"] and q["leadTimeWeeks"] > 0 and q["paymentTerms"]
    assert apps[EVO].state.extractions == [{"agentId": "agent_x", "extractorId": "ext_quote", "filename": "mill.pdf"}]
    ext = [c for c in telemetry.snapshot(50).calls if c.purpose == "quote_extraction"]
    assert ext and ext[0].route == "evolus-extractor" and ext[0].ok


def test_extractor_down_falls_back_to_amd_llm(client, s, monkeypatch):
    live(monkeypatch, s, extractor=True, agent=False, evolus_extractor_id="ext_missing",
         evolus_extract_path="/nope/{agent_id}/{extractor_id}")
    route()
    run_id = _approve(client)
    run = _wait(client, run_id, _awaiting)
    r = client.post(f"/api/runs/{run_id}/quotes", files={"file": ("m.pdf", _doc(run_id, _names(run)[0]),
                                                                  "application/pdf")})
    assert r.status_code == 200, r.text
    q = r.json()["quotes"][0]
    assert q["source"]["engine"] == "amd-llm" and q["unitPrice"] == 101.5  # what the (fake) model read
    assert any("fell back: Evolus extractor" in w for w in q["source"]["warnings"])


# --------------------------------------------------------------------------- real quotes: inbound email webhook


def _payload(run_id, supplier="TEST Indigo Denim"):
    return {"from": "Sales <team+test-indigo-denim@example.com>", "subject": f"Re: RFQ Verso Jacket [ATL-{run_id}]",
            "filename": "Q-OKA-2610.pdf",
            "extraction": {"supplier_name": supplier, "quote_number": "Q-OKA-2610-512", "currency": "USD",
                           "unit_price": {"value": "142.80", "confidence": 0.93}, "moq": {"value": "300", "confidence": 0.88},
                           "lead_time": "9 weeks after PP approval", "sample_cost": "240",
                           "payment_terms": "30% deposit · 70% against B/L", "valid_until": "2026-11-12"}}


def test_webhook_requires_the_shared_secret(client, s, monkeypatch):
    run_id = _approve(client)
    _wait(client, run_id, _awaiting)
    body = json.dumps(_payload(run_id))
    assert client.post("/api/webhooks/evolus/quote", content=body).status_code == 503  # no secret configured
    monkeypatch.setattr(s, "evolus_webhook_secret", SECRET)
    assert client.post("/api/webhooks/evolus/quote", content=body).status_code == 401
    assert client.post("/api/webhooks/evolus/quote", content=body,
                       headers={"X-Atelier-Webhook-Secret": "wrong"}).status_code == 401
    bad_sig = "sha256=" + hmac.new(b"other", body.encode(), hashlib.sha256).hexdigest()
    assert client.post("/api/webhooks/evolus/quote", content=body,
                       headers={"X-Atelier-Signature": bad_sig}).status_code == 401
    assert not client.get(f"/api/runs/{run_id}").json().get("quotes")


def test_webhook_maps_extracted_json_to_a_quote(client, s, monkeypatch):
    monkeypatch.setattr(s, "evolus_webhook_secret", SECRET)
    run_id = _approve(client)
    _wait(client, run_id, _awaiting)
    r = client.post("/api/webhooks/evolus/quote", json=_payload(run_id), headers={"X-Atelier-Webhook-Secret": SECRET})
    assert r.status_code == 200, r.text
    assert r.json()["runId"] == run_id and r.json()["supplierName"] == "TEST Indigo Denim"
    q = client.get(f"/api/runs/{run_id}").json()["quotes"][0]
    assert q["unitPrice"] == 142.8 and q["moq"] == 300 and q["leadTimeWeeks"] == 9 and q["sampleCost"] == 240
    assert q["source"]["channel"] == "email" and q["source"]["engine"] == "evolus-extractor"
    assert q["source"]["sender"] == "team+test-indigo-denim@example.com"
    assert q["source"]["confidence"] == pytest.approx((0.93 + 0.88) / 2, abs=0.001)
    assert next(f for f in q["source"]["fields"] if f["name"] == "unitPrice")["confidence"] == 0.93


def test_webhook_hmac_signature_and_run_matching_by_supplier(client, s, monkeypatch):
    monkeypatch.setattr(s, "evolus_webhook_secret", SECRET)
    run_id = _approve(client)
    run = _wait(client, run_id, _awaiting)
    name = run["supplierEmails"][-1]["supplierName"]
    payload = _payload("nothing")  # no usable run reference: matched by the awaiting supplier
    payload["subject"] = "Re: your RFQ"
    payload["extraction"]["supplier_name"] = name
    raw = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    r = client.post("/api/webhooks/evolus/quote", content=raw, headers={"X-Atelier-Signature": sig})
    assert r.status_code == 200, r.text
    assert r.json()["runId"] == run_id and r.json()["supplierName"] == name


def test_webhook_parks_the_quote_when_no_run_matches(client, s, monkeypatch):
    """LOW: a quote that matches no run is never attached to a guessed run; it waits for a person (202, parked)."""
    monkeypatch.setattr(s, "evolus_webhook_secret", SECRET)
    store.clear()
    r = client.post("/api/webhooks/evolus/quote", json=_payload("run_000000"),
                    headers={"X-Atelier-Webhook-Secret": SECRET})
    assert r.status_code == 202 and r.json()["parked"] is True
    items = client.get("/api/quotes/unmatched").json()
    assert [x["id"] for x in items] == [r.json()["unmatchedId"]] and "payload" not in items[0]


# --------------------------------------------------------------------------- mapping + helpers


def test_map_fields_handles_many_shapes():
    v, c = quotes.map_fields({"data": {"Unit Price": "$1,234.50", "MOQ": 600, "Lead-Time": "45 days"}})
    assert v["unitPrice"] == "$1,234.50" and v["moq"] == 600 and v["leadTime"] == "45 days"
    v, c = quotes.map_fields([{"name": "unit_price", "value": "98,40", "confidence": 87}])
    assert v["unitPrice"] == "98,40" and c["unitPrice"] == 0.87
    v, _ = quotes.map_fields({"output": json.dumps({"price_per_unit": 12})})
    assert v["unitPrice"] == 12
    assert quotes.parse_number("€ 1.234,50") == 1234.5 and quotes.parse_number("USD 98.40") == 98.4
    assert quotes.parse_number("98,4") == 98.4 and quotes.parse_number("1,200") == 1200
    assert quotes.parse_weeks("45 days") == 7 and quotes.parse_weeks("8-9 weeks") == 9 and quotes.parse_weeks(6) == 6
    assert quotes.parse_currency("€120") == "EUR"


def test_inboxes_come_from_the_directory_with_rfq_override(s, monkeypatch):
    """v5: an RFQ goes to the supplier's own contact, or to its RFQ override address when the brand set one."""
    from app.data.suppliers import ALL_SUPPLIERS, find_supplier, inbox_for
    from app.services import workspace
    from app.workspace_models import SupplierInput

    lana = next(x for x in ALL_SUPPLIERS if x["tag"] == "test-lanificio-lana")
    assert inbox_for(lana) == "test-lanificio-lana@supplier.test"
    sup = workspace.supplier("test-lanificio-lana")
    inp = SupplierInput.model_validate({**sup.model_dump(by_alias=False), "rfq_email_override": "sourcing@brand.test"})
    workspace.update_supplier(sup.id, inp)
    lana = next(x for x in ALL_SUPPLIERS if x["tag"] == "test-lanificio-lana")
    assert inbox_for(lana) == "sourcing@brand.test"
    assert find_supplier(email="someone+test-indigo-denim@brand.test")["tag"] == "test-indigo-denim"
    assert find_supplier(email="test-lanificio-lana@supplier.test")["tag"] == "test-lanificio-lana"
    assert find_supplier("TEST LANIFICIO LANA S.p.A.")["tag"] == "test-lanificio-lana"


def test_ai_tool_polishes_rfqs_when_enabled(client, s, monkeypatch):
    live(monkeypatch, s, agent=False, evolus_rfq_ai_tool=True)
    route()
    run = _wait(client, _approve(client), _awaiting)
    assert all("(polished by the fake AI Tool)" in e["body"] for e in run["supplierEmails"])
    tools = [c for c in run["steps"][1]["telemetry"] if c.get("route") == "evolus-ai-tool"]
    assert tools and all(c["ok"] and c["model"] == "ai-tool email" for c in tools)


# --------------------------------------------------------------------------- scripts against the fake


def test_check_evolus_passes_every_block_on_the_fake(s, monkeypatch, capsys, tmp_path):
    import asyncio
    import sys

    from scripts import check_evolus

    live(monkeypatch, s, extractor=True, evolus_outreach_workflow_id="wf_out", evolus_shopify_workflow_id="wf_shop")
    route()
    pdf = tmp_path / "quote.pdf"
    pdf.write_bytes(quote_pdf("Lanificio Bisenzio"))  # a throwaway document, made for this test only
    monkeypatch.setattr(sys, "argv", ["check_evolus.py", "--ai-tool", "--quote-pdf", str(pdf)])
    assert asyncio.run(check_evolus.main()) == 0
    out = capsys.readouterr().out
    for block in ("auth", "agents", "brain", "library", "extractor", "ai-tool", "outreach", "shopify"):
        assert f"PASS  {block}" in out, (block, out)


def test_provision_creates_library_agent_extractor_webhook(s, monkeypatch, capsys):
    import asyncio
    import sys

    from scripts import provision_evolus

    live(monkeypatch, s, evolus_library_id="", evolus_own_model_name="Qwen3.6-35B-A3B",
         evolus_webhook_secret=SECRET)
    apps = route()
    monkeypatch.setattr(sys, "argv", ["provision_evolus.py", "--all", "--webhook-url",
                                      "https://tunnel.example/api/webhooks/evolus/quote"])
    assert asyncio.run(provision_evolus.main()) == 0
    out = capsys.readouterr().out
    created = apps[EVO].state.created
    assert [k for k, _ in created] == ["memory", "agent", "attach", "agent", "extractor", "webhook"]
    agent = created[1][1]
    assert agent["modelKey"] == "own/Qwen3.6-35B-A3B" and "knowledge library" in agent["prompt"]
    assert json.loads(created[4][1]["structure"])["properties"]["unit_price"]["type"] == "number"
    hook = created[5][1]
    assert hook["apiKeyName"] == "X-Atelier-Webhook-Secret" and hook["apiKeyValue"] == SECRET
    lib = next(k for k in apps[EVO].state.documents if k != "lib_1")
    docs = apps[EVO].state.documents[lib]
    # v5: the brand's own brand-book file + the catalogue / profile generated from the workspace
    assert {d["title"] for d in docs} >= {"test-brand-book.md", "supplier-catalogue.pdf", "brand-profile.pdf"}
    assert "TEST Brand" in agent["prompt"]
    assert all(d["language"] == "en" for d in docs)
    for key in ("EVOLUS_LIBRARY_ID=", "EVOLUS_AGENT_MODEL=app_test:agent_", "EVOLUS_EXTRACTOR_AGENT_ID=",
                "EVOLUS_EXTRACTOR_ID=ext_"):
        assert key in out
