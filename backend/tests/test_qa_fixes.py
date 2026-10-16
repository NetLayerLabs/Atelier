"""QA fixes: the brand currency end to end (EUR and USD brands), supplier-safe RFQs and POs, the early-window
forecast safeguards, honest AMD credits, readable 422s and the RFQ recipient preview.

Everything external is a test double (tests/fake_upstreams.py): the fake ECB publishes 1 EUR = 1.10 USD and the fake
Shopify store sells in USD, so an EUR brand exercises the store-currency ≠ brand-currency path.
"""

from __future__ import annotations

import asyncio
import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from helpers import approve, awaiting, collecting, upload_quote, wait

from app.models import BomLine, Design, ServiceStatus, TechPack, TrendAnalysis
from app.routers import health
from app.services import forecast as fc
from app.services import brain, llm, money, purchase_orders, supplier_view, workspace
from app.store import store
from app.workspace_models import BrandProfileInput


def _set_currency(ccy: str) -> None:
    data = workspace.profile().model_dump(by_alias=False)
    workspace.save_profile(BrandProfileInput.model_validate(
        {**{k: data[k] for k in BrandProfileInput.model_fields}, "currency": ccy}))


def _close_windows():
    for meta in store.run_meta.values():
        if meta.get("shopify"):
            meta["shopify"]["launchedMono"] -= 10**9


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    _close_windows()


def _pdf_text(pdf: bytes) -> str:
    from pypdf import PdfReader

    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)


def _tp(**kw) -> TechPack:
    base = dict(garment_name="Test Jacket", description="A test jacket.",
                bill_of_materials=[BomLine(material="Wool shell", quantity="2 m", target_cost_per_unit=41.5),
                                   BomLine(material="CMT", quantity="1", target_cost_per_unit=38.0)],
                measurements={"chest": "46in", "length": "28in"}, target_supplier_region="Italy",
                target_retail_price=389.0, production_quantity=300, currency="EUR",
                construction_notes=["Bound seams."])
    base.update(kw)
    return TechPack(**base)


# --------------------------------------------------------------------------- the money formatter


def test_money_formatter_uses_the_given_currency_never_a_default_dollar():
    assert money.fmt(170, "EUR") == "€170.00"
    assert money.fmt(170, "usd") == "$170.00"
    assert money.fmt(1234.5, "GBP", 0) == "£1,234"
    assert money.fmt(170, "CHF") == "CHF 170.00"
    assert money.fmt(-38, "EUR") == "-€38.00"
    assert money.fmt(170, None) == "170.00"  # no currency known -> no guessed symbol
    _set_currency("EUR")
    assert money.brand_currency() == "EUR" and money.brand(389, 0) == "€389"
    workspace.wipe()
    assert money.brand_currency() is None


# --------------------------------------------------------------------------- H2: EUR brand end to end


def test_eur_brand_end_to_end_quotes_guardrails_shopify_po_forecast_pdf(live, fakes, trend, s, monkeypatch):
    _set_currency("EUR")
    monkeypatch.setattr(s, "demand_stage_threshold", 1)
    run_id = approve(live, trend, qty=300)
    run = wait(live, run_id, awaiting)
    assert run["techPack"]["currency"] == "EUR"
    tlog = run["steps"][0]["log"]
    assert any("Target cost €" in line and "target retail €389" in line for line in tlog)
    assert not any("$" in line for line in tlog)

    emails = run["supplierEmails"]
    first = emails[0]["supplierName"]
    upload_quote(live, run_id, first, currency="USD", price=110.0)  # = €100.00 at 1 EUR = 1.10 USD
    for e in emails[1:]:
        upload_quote(live, run_id, e["supplierName"], currency="EUR", price=120.0)
    run = wait(live, run_id, collecting)
    q = next(x for x in run["quotes"] if x["supplierName"] == first)
    assert q["currency"] == "USD" and q["unitPrice"] == pytest.approx(100.0)  # converted to the BRAND currency
    ev = next(e for e in run["guardrailReport"]["evaluations"] if e["supplierName"] == first)
    margin = next(c for c in ev["checks"] if c["rule"] == "min_margin")
    assert "€100.00 against €389.00 retail" in margin["message"] and "$" not in margin["message"]
    cap = next(c for c in ev["checks"] if c["rule"] == "max_unit_cost")
    assert cap["actual"] == "€100.00" and cap["limit"].startswith("≤ €")

    # The store sells in USD: both prices are kept, converted at the ECB rate - never a silent mix.
    sp = run["shopifyProduct"]
    assert sp["currency"] == "USD" and sp["brandCurrency"] == "EUR" and sp["priceBrand"] == 389
    assert sp["fxRate"] == pytest.approx(1.1) and sp["price"] == pytest.approx(427.9)
    shop_log = run["steps"][3]["log"]
    assert any("Store currency USD ≠ brand currency EUR: retail €389.00 listed at $427.90" in x for x in shop_log)
    assert fakes["shop.fake"].state.products[sp["productId"]]["variants"][0]["price"] in ("427.90", 427.9)

    fakes["shop.fake"].state.place_order(sp["productId"], 1, size="M", test=True)
    run = wait(live, run_id)
    po = run["demand"]["purchaseOrder"]
    assert po["currency"] == "USD" and po["unitPrice"] == 110.0  # placed in the mill's quoted currency
    assert po["brandCurrency"] == "EUR" and po["totalBrand"] == pytest.approx(300 * 100.0)

    f = live.get(f"/api/runs/{run_id}/forecast").json()
    assert f["currency"] == "EUR" and f["retailPrice"] == 389 and f["unitCost"] == pytest.approx(100.0)
    assert "$" not in f["explanation"]["summary"] and "€" in f["explanation"]["summary"]

    text = _pdf_text(live.get(f"/api/runs/{run_id}/techpack.pdf").content)
    assert "COSTING SUMMARY (EUR)" in text and "€389.00" in text and "$389" not in text
    assert "$110.00 ≈ €100.00" in text  # the mill's own quote, with the brand-currency equivalent


def test_usd_brand_keeps_one_price_when_the_store_currency_matches(live, fakes, trend, s, monkeypatch):
    monkeypatch.setattr(s, "demand_stage_threshold", 1)
    run_id = approve(live, trend, qty=300)
    run = wait(live, run_id, awaiting)
    assert run["techPack"]["currency"] == "USD"
    for e in run["supplierEmails"]:
        upload_quote(live, run_id, e["supplierName"], currency="USD", price=101.5)
    run = wait(live, run_id, collecting)
    sp = run["shopifyProduct"]
    assert sp["currency"] == "USD" == sp["brandCurrency"] and sp["price"] == sp["priceBrand"] == 389
    assert "fxRate" not in sp
    assert any("Store currency USD = brand currency · listed at $389.00" in x for x in run["steps"][3]["log"])
    text = _pdf_text(live.get(f"/api/runs/{run_id}/techpack.pdf").content)
    assert "COSTING SUMMARY (USD)" in text and "$389.00" in text and "€" not in text


def test_store_currency_differs_and_no_fx_rate_stops_before_listing(live, fakes, trend, s, monkeypatch):
    _set_currency("EUR")
    monkeypatch.setattr(s, "atelier_fx_url", "http://ecb.fake/missing.xml")  # 404 -> no published rate
    run_id = approve(live, trend, qty=300)
    run = wait(live, run_id, awaiting)
    for e in run["supplierEmails"]:
        upload_quote(live, run_id, e["supplierName"], currency="EUR", price=101.5)
    run = wait(live, run_id)
    step = run["steps"][3]
    assert run["status"] == "failed" and step["status"] == "error" and step["service"] == "shopify"
    assert "sells in USD but the brand prices in EUR" in step["error"] and "nothing was listed" in step["error"]
    assert not fakes["shop.fake"].state.products


def test_retail_edit_reconverts_the_listing_price(live, fakes, trend, s, monkeypatch):
    _set_currency("EUR")
    run_id = approve(live, trend, qty=300)
    run = wait(live, run_id, awaiting)
    for e in run["supplierEmails"]:
        upload_quote(live, run_id, e["supplierName"], currency="EUR", price=101.5)
    run = wait(live, run_id, collecting)
    r = live.patch(f"/api/runs/{run_id}/techpack", json={"targetRetailPrice": 400})
    assert r.status_code == 200, r.text
    run = wait(live, run_id, lambda x: x["shopifyProduct"]["price"] == pytest.approx(440.0))
    sp = run["shopifyProduct"]
    assert sp["priceBrand"] == 400 and sp["currency"] == "USD"
    assert any("Price updated on Shopify: $440.00 (€400.00 brand retail)" in x for x in run["steps"][3]["log"])


def test_techpack_and_rfq_prompts_name_the_brand_currency(monkeypatch):
    _set_currency("EUR")
    seen: list[list[dict]] = []

    async def capture(purpose, messages, validate, **kw):
        seen.append(messages(0, ""))
        raise RuntimeError("captured")

    monkeypatch.setattr(brain, "think_json", capture)
    trend = TrendAnalysis(id="trd_x", trend_name="T", summary="s", garment_type="jacket", core_silhouettes=["boxy"],
                          color_palette=["#111111"], key_fabrics=["wool"], commercial_viability_score=50)
    design = Design(id="dsn_x", trend_id="trd_x", image_url="http://localhost:8787/static/generated/dsn_x.png",
                    prompt="p", garment_type="jacket", seed=1)
    with pytest.raises(RuntimeError):
        asyncio.run(llm.live_techpack(trend, design, 300))
    tp_prompt = json.dumps(seen[-1])
    assert "EUR per finished garment" in tp_prompt and '\\"targetRetailPrice\\": number (EUR)' in tp_prompt
    assert "USD" not in tp_prompt

    sup = [{"name": "TEST Mill", "region": "Testville, Italy", "specialty": "wool", "language": "it",
            "certifications": [], "email": "mill@supplier.test", "key": "x"}]
    with pytest.raises(RuntimeError):
        asyncio.run(llm.live_supplier_emails(_tp(), sup, design, trend, rfq_ref="ATL-run_x"))
    rfq = seen[-1][1]["content"]
    assert "quoted in EUR" in rfq and "USD" not in rfq
    # M11: the supplier-safe view - no target cost, no retail price, no margin; no dead localhost link
    assert "targetCostPerUnit" not in rfq and "targetRetailPrice" not in rfq and "389" not in rfq
    assert "41.5" not in rfq and "localhost" not in rfq and "Do not include any link" in rfq
    assert "Wool shell" in rfq and "chest" in rfq and "requiredLeadTimeWeeks" in rfq

    public = design.model_copy(update={"image_url": "https://atelier.example.com/static/generated/dsn_x.png"})
    with pytest.raises(RuntimeError):
        asyncio.run(llm.live_supplier_emails(_tp(), sup, public, trend, rfq_ref="ATL-run_x"))
    assert "Include the design link https://atelier.example.com/static/generated/dsn_x.png" in seen[-1][1]["content"]


# --------------------------------------------------------------------------- M11: what reaches a mill


def test_supplier_view_has_no_brand_economics():
    view = supplier_view.techpack(_tp())
    blob = json.dumps(view)
    assert not any(k in blob for k in supplier_view.PRIVATE_FIELDS)
    assert "389" not in blob and "41.5" not in blob
    assert view["billOfMaterials"] == [{"material": "Wool shell", "quantity": "2 m"}, {"material": "CMT", "quantity": "1"}]
    assert view["productionQuantity"] == 300 and view["measurements"]["chest"] == "46in"


@pytest.mark.parametrize("url,ok", [
    ("https://atelier.example.com/static/x.png", True),
    ("http://atelier.example.com/static/x.png", False),
    ("http://localhost:8787/static/x.png", False),
    ("https://localhost/static/x.png", False),
    ("https://127.0.0.1/x.png", False),
    ("https://10.1.2.3/x.png", False),
    ("https://atelier.test/x.png", False),
    ("", False),
])
def test_only_public_https_links_reach_a_supplier(url, ok):
    assert (supplier_view.public_link(url) == url) is ok


def test_outreach_workflow_gets_the_supplier_safe_view_and_no_dead_link(live, fakes, trend):
    run_id = approve(live, trend, qty=300)
    wait(live, run_id, awaiting)
    out = [x for x in fakes["evolus.fake"].state.executions.values() if x["workflow"] == "wf_out"]
    # The tech pack and image link travel in the `input` payload (only the email fields are workflow parameters)
    params = json.loads(out[0]["input"].split("\n", 1)[1])
    tech = params["tech_pack"]
    assert "targetRetailPrice" not in tech and all("targetCostPerUnit" not in b for b in tech["billOfMaterials"])
    assert params["image_url"] == ""  # PUBLIC_BASE_URL is http://testserver: not reachable by a mill


def test_po_email_does_not_claim_an_attachment():
    from app.models import PipelineRun, PurchaseOrder

    run = PipelineRun(id="run_x", design_id="d", steps=[], tech_pack=_tp(), style_number="ST-00001")
    po = PurchaseOrder(po_number="PO-00001", supplier_name="TEST Mill", region="Italy", quantity=300,
                       currency="EUR", unit_price=100.0, total=30000.0, rfq_ref="ATL-run_x")
    body = purchase_orders._body(run, po)
    assert "attached" not in body.lower()
    assert "as sent with our RFQ ATL-run_x" in body and "full tech pack document" in body


# --------------------------------------------------------------------------- hand-off wording


def test_english_mill_negotiate_option_does_not_mention_translation(live, fakes):
    # A denim trend: the TEST shortlist is TEST Indigo Denim, TEST Organic Cotton and TEST Garment Asia (all English).
    t = TrendAnalysis(id="trd_denim", trend_name="Denim", summary="s", garment_type="jacket", core_silhouettes=["x"],
                      color_palette=["#223344"], key_fabrics=["selvedge denim", "organic cotton"],
                      commercial_viability_score=60)
    store.trends[t.id] = t
    run_id = approve(live, t.model_dump(by_alias=True), qty=300)
    run = wait(live, run_id, awaiting)
    assert {e["language"] for e in run["supplierEmails"]} == {"en"}
    for e in run["supplierEmails"]:  # every quote breaks the 65% margin floor (389 retail)
        upload_quote(live, run_id, e["supplierName"], currency="USD", price=160.0)
    run = wait(live, run_id, lambda r: (r.get("decision") or {}).get("status") == "pending")
    neg = next(o for o in run["decision"]["options"] if o["kind"] == "negotiate")
    assert "drafted in English" in neg["detail"] and "alongside" not in neg["detail"]
    assert "counter-offer at $136.15" in neg["detail"]  # 389 × (1 − 65%), in the brand currency


# --------------------------------------------------------------------------- M7: early-window forecast

L = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _req(orders, as_of_h, planned=300, **assumptions):
    a = fc._plan_anchored_assumptions(planned)
    for k, v in assumptions.items():
        setattr(a, k, v)
    return fc.ForecastRequest(
        orders=[fc.OrderEvent(timestamp=(L + timedelta(hours=h)).isoformat(), quantity=1, size="M",
                              order_id=f"o{i}") for i, h in enumerate(orders)],
        launch_at=L.isoformat(), as_of=(L + timedelta(hours=as_of_h)).isoformat(), window_hours=336,
        economics=fc.Economics(unit_cost=100.0, retail_price=389.0, currency="EUR"), assumptions=a,
        planned_quantity=planned)


def test_two_early_orders_do_not_trigger_a_production_call():
    f = fc.forecast(_req([0.5, 1.0], as_of_h=2))
    assert f.recommendation_status == "too_early" and not f.evidence.ready
    assert f.recommended_quantity == 300  # the plan stands
    assert f.evidence.orders == 2 and f.evidence.min_orders == 5 and f.evidence.min_window_share_elapsed == 0.10
    assert f.explanation.summary.startswith("Too early to recommend - collecting orders (2 so far)")
    assert any("Too early to recommend" in n for n in f.explanation.notes)
    assert any(s.title == "Enough evidence to recommend?" for s in f.explanation.steps)
    keys = {a.key for a in f.explanation.assumptions}
    assert {"minExposure", "minWindowShareElapsed", "minOrders"} <= keys
    assert f.currency == "EUR" and "€" in f.explanation.summary and "$" not in f.explanation.summary


def test_exposure_floor_stops_early_orders_exploding():
    floored = fc.forecast(_req([0.5, 1.0], as_of_h=2))
    raw = fc.forecast(_req([0.5, 1.0], as_of_h=2, min_exposure=0.0))
    prior_season = 300  # m₀ × M = planned quantity
    assert raw.season.mean > 1.5 * prior_season  # the bug: ~3× the plan on two orders
    assert floored.season.mean < raw.season.mean and floored.season.mean < 1.5 * prior_season
    assert floored.newsvendor_quantity < raw.newsvendor_quantity
    step = next(s for s in floored.explanation.steps if s.title.startswith("Update with the orders"))
    assert "exposure floor" in step.substituted and "g_min = 0.05" in step.substituted
    assert any("exposure floor" in n for n in floored.explanation.notes)


def test_floor_with_no_orders_is_exactly_the_prior():
    f = fc.forecast(_req([], as_of_h=0))
    assert f.posterior.alpha == f.posterior.prior_alpha and f.posterior.beta == f.posterior.prior_beta
    assert f.season.mean == pytest.approx(300, rel=1e-3)


def test_recommends_once_the_evidence_threshold_is_met():
    hours = [3 * i + 1 for i in range(12)]  # 12 orders over the first ~36 h
    f = fc.forecast(_req(hours, as_of_h=40))  # 40 / 336 = 11.9% of the window
    assert f.recommendation_status == "recommended" and f.evidence.ready
    assert f.recommended_quantity == f.newsvendor_quantity
    assert f.explanation.summary.startswith("Make ")
    # enough orders but too little of the window: still too early
    g = fc.forecast(_req([0.1 * i for i in range(1, 9)], as_of_h=1))
    assert g.recommendation_status == "too_early" and "of the window to pass" in g.evidence.note


# --------------------------------------------------------------------------- honest AMD credit


def _svc(name, gpu=None, fake=False, status="connected"):
    return ServiceStatus(name=name, status=status, healthy=status == "connected", fake=fake, gpu=gpu)


def test_amd_credit_needs_verified_amd_hardware():
    unknown = health.powered_by([_svc("llm")])
    assert not unknown.amd and unknown.model_connected and unknown.hardware is None
    nvidia = health.powered_by([_svc("diffusion", gpu="cuda:0 NVIDIA A100")])
    assert not nvidia.amd and nvidia.model_connected
    amd = health.powered_by([_svc("llm", gpu="AMD Instinct MI300X (192 GB)")])
    assert amd.amd and amd.hardware == "AMD Instinct MI300X (192 GB)"
    assert health.powered_by([_svc("diffusion", gpu="MI300X")]).amd
    fake = health.powered_by([_svc("llm", gpu="AMD Instinct MI300X", fake=True)])
    assert not fake.amd and not fake.model_connected  # a test double never earns a credit
    down = health.powered_by([_svc("llm", gpu="AMD Instinct MI300X", status="unreachable")])
    assert not down.amd and not down.model_connected


# --------------------------------------------------------------------------- readable validation errors


def test_too_long_direction_gets_a_plain_message(client):
    r = client.post("/api/designs/dsn_any/direct", json={"instruction": "x" * 501})
    assert r.status_code == 422
    assert r.json()["detail"] == "The direction is too long - keep it to 500 characters (this one has 501)."


# --------------------------------------------------------------------------- H6: who approving would email


def test_rfq_recipient_preview_names_every_address(live, fakes, trend):
    d = live.post("/api/designs/generate", json={"trendId": trend["id"], "count": 1}).json()["designs"][0]
    sup = next(x for x in workspace.suppliers() if x.name == "TEST Indigo Denim")
    inp = workspace.SupplierInput.model_validate(
        {**sup.model_dump(by_alias=False, include=set(workspace.SupplierInput.model_fields)),
         "rfq_email_override": "pilot-inbox@brand.test"})
    workspace.update_supplier(sup.id, inp)
    r = live.get(f"/api/designs/{d['id']}/rfq-recipients")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sends"] is True and body["recipients"]
    by = {x["supplierName"]: x for x in body["recipients"]}
    assert by["TEST Indigo Denim"]["toEmail"] == "pilot-inbox@brand.test" and by["TEST Indigo Denim"]["override"]
    assert not store.runs  # read-only: nothing was approved or sent
    assert live.get("/api/designs/dsn_missing/rfq-recipients").status_code == 404
