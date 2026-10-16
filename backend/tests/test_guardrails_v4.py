"""v4: brand guardrails, the human hand-off (decision state machine), counter-offers and multilingual sourcing.

Deterministic throughout: guardrail checks and target prices are pure maths. v5: the hand-off is reproduced with
throwaway quote documents generated in each test (never stored); the brain (counter-offers, RFQs, translations) and
Evolus are the in-process test doubles. Without a brain or Evolus the hand-off actions fail honestly (503).
"""

import asyncio
import json
import time

import pytest
import conftest
from helpers import quote_pdf

from app.data.suppliers import ALL_SUPPLIERS, language_of
from app.models import BomLine, Guardrails, SupplierQuote, TechPack, TrendAnalysis
from app.services import evolus, guardrails, i18n, telemetry
from app.services.quotes import parse_quantity, parse_weeks, rules_extract
from app.store import store

EVO = conftest.EVO
SECRET = "s3cret-hook"
EUR = 1.1  # the fake ECB rate (tests/fake_upstreams.py)


# --------------------------------------------------------------------------- helpers


def _tp(retail=600.0, cost=150.0, qty=300) -> TechPack:
    return TechPack(garment_name="Test Sweater", description="d",
                    bill_of_materials=[BomLine(material="Cashmere shell", quantity="1.5 m", target_cost_per_unit=cost)],
                    measurements={"chest": "44in"}, target_supplier_region="Testville, Portugal", target_retail_price=retail,
                    production_quantity=qty)


def _q(name="TEST Lanificio Lana", price=200.0, moq=250, lead=8, currency="USD", local=None) -> SupplierQuote:
    return SupplierQuote(supplier_name=name, region="", unit_price=price, moq=moq, lead_time_weeks=lead,
                         sample_cost=0, payment_terms="", note="", currency=currency, unit_price_quoted=local)


def _check(ev, rule):
    return next(c for c in ev.checks if c.rule == rule)


def _wait(client, run_id, cond, timeout=10.0):
    end = time.time() + timeout
    run = None
    while time.time() < end:
        run = client.get(f"/api/runs/{run_id}").json()
        if cond(run):
            return run
        time.sleep(0.02)
    logs = [(x["key"], x["status"], x["log"][-6:], x.get("error")) for x in (run or {}).get("steps", [])]
    raise AssertionError(f"condition not reached: {logs}")


@pytest.fixture(autouse=True)
def s(s, monkeypatch):
    """Every service on the test doubles; the brain = direct vLLM (the agent where a test asks for it)."""
    evolus._doc_titles.clear()
    guardrails.reset()
    conftest.go_live(monkeypatch, s, shopify_store_domain="")  # stop at Shopify: these tests are about quotes
    conftest.route()
    yield s
    guardrails.reset()


def _approve(client, qty=300):
    """A wool/cashmere trend: the shortlist (TEST workspace) is TEST Lanificio Lana (Italian), TEST Malhas Malha
    (Portuguese) and the European CMT unit."""
    t = TrendAnalysis(id="trd_wool", trend_name="Quiet Wool", summary="s", garment_type="sweater",
                      core_silhouettes=["relaxed"], color_palette=["#D8CBB5", "#4A3328"],
                      key_fabrics=["wool barathea", "cashmere"], commercial_viability_score=60)
    store.trends[t.id] = t
    d = client.post("/api/designs/generate", json={"trendId": t.id, "count": 1}).json()["designs"][0]
    return client.post(f"/api/designs/{d['id']}/approve", json={"productionQuantity": qty}).json()["runId"]


def _upload(client, run_id, name, **kw):
    pdf = quote_pdf(name, ref=f"ATL-{run_id}", **kw)
    r = client.post(f"/api/runs/{run_id}/quotes", files={"file": (f"{name[:6]}.pdf", pdf, "application/pdf")},
                    data={"supplierName": name})
    assert r.status_code == 200, r.text
    return r.json()


BIS = "TEST Lanificio Lana"


def _handoff(client):
    """TEST Lanificio Lana quotes EUR 140 (= USD 154 at the fake ECB rate: 60.4% margin on the fake tech pack's 389 retail) but
    is the agent's pick on MOQ and lead time; the other mills pass every guardrail."""
    run_id = _approve(client)
    run = _wait(client, run_id, lambda r: (r.get("quoteRound") or {}).get("status") == "awaiting")
    for e in run["supplierEmails"]:
        if e["supplierName"] == BIS:
            _upload(client, run_id, BIS, currency="EUR", price=140.0, moq=200, lead="3 weeks", number="Q-PRA-1")
        else:
            _upload(client, run_id, e["supplierName"], price=101.5, moq=900, lead="10 weeks")
    return run_id, _wait(client, run_id, lambda r: (r.get("decision") or {}).get("status") == "pending")


# --------------------------------------------------------------------------- guardrail rules


def test_no_invented_defaults_and_unset_rules_are_skipped(s):
    """v5: the guardrails start empty (nothing invented); unset rules are listed and not checked."""
    from app.services import workspace

    workspace.wipe()
    g = guardrails.current()
    assert g.min_gross_margin_pct is None and g.max_unit_cost is None and g.cost_headroom_pct is None
    assert g.max_lead_time_weeks is None and g.max_moq is None and g.required_certifications == []
    assert g.unset == ["min_margin", "max_unit_cost", "max_lead_time", "max_moq", "certifications"]
    assert g.reviewed_at is None and guardrails.defaults().unset == g.unset
    ev = guardrails.evaluate_quote(_q(price=10_000, lead=99, moq=99_999), g, _tp())
    assert ev.ok and ev.checks == []  # nothing set -> nothing checked
    # a partially set brand: only the set rules are checked, and they persist
    workspace.save_guardrails(g.model_copy(update={"max_moq": 400}), by="test")
    g = guardrails.current()
    assert g.max_moq == 400 and "max_moq" not in g.unset and "min_margin" in g.unset and g.reviewed_at
    ev = guardrails.evaluate_quote(_q(price=10_000, moq=500), g, _tp())
    assert [c.rule for c in ev.checks] == ["max_moq"] and not ev.ok
    t = guardrails.negotiation_target(_q(price=10_000, moq=500), g, _tp())
    assert t["price"] is None and t["moq"] == (400, 500)  # no margin / cost rule -> no price ask


def test_margin_floor_pass_fail_and_exact_edge():
    g, tp = Guardrails(min_gross_margin_pct=65), _tp(retail=600)
    assert _check(guardrails.evaluate_quote(_q(price=200), g, tp), "min_margin").ok  # 66.7%
    edge = guardrails.evaluate_quote(_q(price=210), g, tp)  # exactly 65.0% (float 64.999…)
    assert _check(edge, "min_margin").ok and edge.margin_pct == pytest.approx(65.0)
    bad = guardrails.evaluate_quote(_q(price=210.01), g, tp)
    c = _check(bad, "min_margin")
    assert not c.ok and not bad.ok and c.actual == "65.0%" and c.limit == "≥ 65%"
    assert "below your 65% floor" in c.message and "TEST Lanificio Lana's quote leaves" in c.message
    over = guardrails.evaluate_quote(_q(price=700), g, tp)  # price above retail: negative margin
    assert _check(over, "min_margin").actual_value < 0
    none = guardrails.evaluate_quote(_q(price=10), g, _tp(retail=0.0001).model_copy(update={"target_retail_price": 0}))
    assert not _check(none, "min_margin").ok and "can't be checked" in _check(none, "min_margin").message


def test_unit_cost_cap_absolute_and_derived():
    tp = _tp(retail=10_000, cost=100)
    derived = Guardrails(cost_headroom_pct=75)
    cap, is_derived, costing = guardrails.unit_cost_cap(derived, tp)
    assert (cap, is_derived, costing) == (175.0, True, 100.0)
    assert _check(guardrails.evaluate_quote(_q(price=175), derived, tp), "max_unit_cost").ok
    c = _check(guardrails.evaluate_quote(_q(price=175.01), derived, tp), "max_unit_cost")
    assert not c.ok and "costing" in c.message and c.limit == "≤ $175.00"
    absolute = Guardrails(max_unit_cost=110)
    assert not _check(guardrails.evaluate_quote(_q(price=110.5), absolute, tp), "max_unit_cost").ok
    assert _check(guardrails.evaluate_quote(_q(price=110), absolute, tp), "max_unit_cost").ok
    rep_g, d, _ = guardrails.resolved(derived, tp)
    assert rep_g.max_unit_cost == 175.0 and d


def test_lead_time_and_moq_limits_including_off():
    tp = _tp()
    g = Guardrails(max_lead_time_weeks=10, max_moq=500)
    ok = guardrails.evaluate_quote(_q(lead=10, moq=500), g, tp)
    assert _check(ok, "max_lead_time").ok and _check(ok, "max_moq").ok
    bad = guardrails.evaluate_quote(_q(lead=11, moq=501), g, tp)
    assert not _check(bad, "max_lead_time").ok and not _check(bad, "max_moq").ok
    off = guardrails.evaluate_quote(_q(lead=30, moq=5000), Guardrails(max_lead_time_weeks=None, max_moq=None), tp)
    assert off.checks == [] and off.ok  # v5: unset rules are not checked
    on = guardrails.evaluate_quote(_q(lead=30, moq=5000), Guardrails(min_gross_margin_pct=65, cost_headroom_pct=75), tp)
    assert {c.rule for c in on.checks} == {"min_margin", "max_unit_cost"}


def test_certifications_all_any_unknown_and_normalised():
    tp = _tp()
    g = Guardrails(required_certifications=["GOTS", "OEKO-TEX"])
    okayama = guardrails.evaluate_quote(_q(name="TEST Indigo Denim", price=100), g, tp)  # holds both
    assert _check(okayama, "certifications").ok
    prato = _check(guardrails.evaluate_quote(_q(name="TEST Lanificio Lana", price=100), g, tp), "certifications")
    assert not prato.ok and "missing GOTS, OEKO-TEX" in prato.message
    como = _check(guardrails.evaluate_quote(_q(name="TEST Tessitura Seta", price=100), g, tp), "certifications")
    assert not como.ok and "missing GOTS" in como.message  # has OEKO-TEX Standard 100 only
    anyg = Guardrails(required_certifications=["GOTS", "OEKO-TEX"], certifications_mode="any")
    assert _check(guardrails.evaluate_quote(_q(name="TEST Tessitura Seta", price=100), anyg, tp), "certifications").ok
    unknown = _check(guardrails.evaluate_quote(_q(name="Some Other Mill", price=100), g, tp), "certifications")
    assert not unknown.ok and "not in the supplier catalogue" in unknown.message
    assert guardrails.has_cert(["OEKO-TEX Standard 100"], "oeko tex") and not guardrails.has_cert(["GRS"], "")


# --------------------------------------------------------------------------- counter-offer maths


def test_target_price_hits_the_margin_floor_and_rounds_down():
    tp, g = _tp(retail=649), Guardrails(min_gross_margin_pct=65, cost_headroom_pct=500)
    t = guardrails.negotiation_target(_q(price=246.62), g, tp)
    p = t["price"]
    assert p["target_brand"] == 227.15  # 649 x 0.35 (float 227.1499999…) is exactly 227.15, not 227.14
    assert t["reason"] == "margin" and p["reduction_pct"] == pytest.approx((246.62 - 227.15) / 246.62 * 100, abs=0.05)
    assert guardrails.margin_pct(649, p["target_brand"]) >= 65
    assert any("649.00 × (1 − 65%)" in line for line in t["math"])
    assert any(line.startswith("Check:") and "✓" in line for line in t["math"])


def test_target_in_the_mills_currency_never_reconverts_above_target():
    tp, g = _tp(retail=619), Guardrails(min_gross_margin_pct=65, cost_headroom_pct=500)
    q = _q(price=235.21, currency="EUR", local=217.79)
    p = guardrails.negotiation_target(q, g, tp, fx_to_brand=1.08)["price"]
    assert p["currency"] == "EUR" and p["quoted_local"] == 217.79
    assert p["target_local"] == 200.60  # 216.65 / 1.08 = 200.6018… rounded down
    assert round(p["target_local"] * 1.08, 2) <= p["target_brand"]
    assert guardrails.margin_pct(619, round(p["target_local"] * 1.08, 2)) >= 65


def test_cost_cap_wins_when_lower_and_lead_moq_asks():
    tp = _tp(retail=1000, cost=100)
    g = Guardrails(min_gross_margin_pct=50, cost_headroom_pct=20, max_lead_time_weeks=8, max_moq=300)
    t = guardrails.negotiation_target(_q(price=150, lead=12, moq=600), g, tp)
    assert t["reason"] == "cost" and t["price"]["target_brand"] == 120.0  # min(500, 120)
    assert t["lead"] == (8, 12) and t["moq"] == (300, 600)
    ok = guardrails.negotiation_target(_q(price=100, lead=8, moq=300), g, tp)
    assert ok["price"] is None and ok["lead"] is None and ok["moq"] is None


def test_unconvertible_price_and_unstated_terms_are_never_assumed():
    tp, g = _tp(), Guardrails(min_gross_margin_pct=65, max_lead_time_weeks=10, max_moq=500)
    q = _q(price=None, currency="EUR", local=180.0, lead=None, moq=None)
    ev = guardrails.evaluate_quote(q, g, tp)
    assert not ev.ok and ev.unit_price is None
    assert _check(ev, "min_margin").actual == "can't be checked" and "no FX rate" in _check(ev, "min_margin").message
    assert _check(ev, "max_lead_time").actual == "not stated" and _check(ev, "max_moq").actual == "not stated"
    assert not any(c.rule == "max_unit_cost" for c in ev.checks)
    t = guardrails.negotiation_target(q, g, tp)
    assert t["price"] is None and t["lead"] is None and t["moq"] is None


# --------------------------------------------------------------------------- languages


def test_each_mill_has_a_language():
    langs = {s["tag"]: language_of(s) for s in ALL_SUPPLIERS}
    assert langs == {"test-indigo-denim": "en", "test-lanificio-lana": "it", "test-tessitura-seta": "it",
                     "test-malhas-malha": "pt", "test-ripstop-technical": "en", "test-conceria-pelle": "it",
                     "test-organic-cotton": "en", "test-garment-asia": "en", "test-confezioni-europa": "it"}
    # a language Atelier has no RFQ templates for falls back to English
    assert language_of({"language": "ja"}) == "en"


def test_number_formats_and_parsing():
    assert i18n.fmt_money(1234.5, "EUR", "it") == "1.234,50 EUR" and i18n.fmt_money(1234.5, "USD", "en") == "$1,234.50"
    assert i18n.floor_cents(227.14999999999998) == 227.15 and i18n.floor_cents(216.6599) == 216.65
    assert parse_quantity("1.000 capi per colore") == 1000 and parse_quantity("250 capi") == 250
    assert parse_quantity("1,200 pcs") == 1200
    assert parse_weeks("8 settimane dall'approvazione") == 8 and parse_weeks("56 giorni") == 8
    assert parse_weeks("7 semanas") == 7 and parse_weeks("45 dias") == 7 and parse_weeks("2 mesi") == 9


def test_rules_parser_reads_italian_and_portuguese_labels():
    it = rules_extract("TEST Lanificio Lana\nOfferta n. Q-PRA-9\nValuta: EUR\nPrezzo unitario: EUR 243,99\n"
                       "Minimo d'ordine (MOQ): 1.000 capi\nTempi di consegna: 8 settimane\n")
    assert it["unitPrice"].endswith("243,99") and it["leadTime"].startswith("8 settimane") and it["currency"] == "EUR"
    pt = rules_extract("TEST Malhas Malha\nPreço unitário: EUR 99,50\nPrazo de entrega: 45 dias\n")
    assert pt["unitPrice"].endswith("99,50") and parse_weeks(pt["leadTime"]) == 7


def test_translate_note_without_a_brain_says_untranslated(s, monkeypatch):
    monkeypatch.setattr(s, "amd_vllm_endpoint", "")
    en, how = asyncio.run(i18n.translate_note("Una nota qualsiasi che non conosciamo affatto.", "it"))
    assert en is None and how == "untranslated"
    assert asyncio.run(i18n.translate_note("Hello", "en")) == (None, "")
    monkeypatch.setattr(s, "amd_vllm_endpoint", f"http://{conftest.VLLM}/v1")
    en, how = asyncio.run(i18n.translate_note("Una nota qualsiasi che non conosciamo affatto.", "it"))
    assert how == "direct vLLM" and "fake model" in en


def test_rfqs_go_out_in_the_mills_language_drafted_by_the_brain(client):
    run_id = _approve(client)
    run = _wait(client, run_id, lambda r: r.get("quoteRound"))
    by = {e["supplierName"]: e for e in run["supplierEmails"]}
    assert by[BIS]["language"] == "it" and by[BIS]["languageName"] == "Italian"
    assert by[BIS]["body"].startswith("Gentile team") and by[BIS]["bodyEnglish"].startswith("Dear")
    assert by["TEST Malhas Malha"]["language"] == "pt" and by["TEST Malhas Malha"]["body"].startswith("Caros colegas")
    assert all(e["rfqRef"] in e["subject"] for e in by.values())
    assert run["steps"][1]["route"] == "direct vLLM"


# --------------------------------------------------------------------------- the decision state machine


def test_handoff_blocks_the_pipeline_until_a_person_decides(client):
    run_id, run = _handoff(client)
    d = run["decision"]
    assert d["supplierName"] == BIS and [b["rule"] for b in d["breaches"]] == ["min_margin"]
    assert "60.4% gross margin" in d["explanation"] and "below your 65% floor" in d["explanation"]
    assert "Options: approve anyway, negotiate" in d["explanation"] and "switch to" in d["explanation"]
    assert [o["kind"] for o in d["options"]][:2] == ["approve", "negotiate"]
    assert any(o["kind"] == "switch" for o in d["options"]) and not d["allQuotesBreach"]
    rep = run["guardrailReport"]
    assert rep["selectedOk"] is False and rep["maxUnitCostDerived"] is True
    assert sum(1 for e in rep["evaluations"] if e["ok"]) == 2
    assert [a["action"] for a in run["audit"]] == ["guardrail_breach", "handoff"]
    time.sleep(0.3)  # nothing moves on its own
    run = client.get(f"/api/runs/{run_id}").json()
    steps = {x["key"]: x for x in run["steps"]}
    assert run["status"] == "running" and steps["supplier_quotes"]["status"] == "running"
    assert steps["shopify_preorder"]["status"] == "pending" and "shopifyProduct" not in run
    assert any(line.startswith("✋ Hand-off") for line in steps["supplier_quotes"]["log"])


def test_approve_records_an_override_and_the_pipeline_continues(client):
    run_id, _ = _handoff(client)
    r = client.post(f"/api/runs/{run_id}/decision/approve", json={"note": "Hero piece, margin accepted"})
    assert r.status_code == 200
    run = _wait(client, run_id, lambda x: x["status"] != "running")
    d = run["decision"]
    assert d["status"] == "resolved" and d["outcome"] == "approved" and d["resolvedSupplierName"] == BIS
    ov = next(a for a in run["audit"] if a["action"] == "approved_override")
    assert ov["actor"] == "human" and ov["guardrail"] == "min_margin" and "60.4%" in ov["values"]["min_margin"]
    steps = {x["key"]: x for x in run["steps"]}
    assert steps["supplier_quotes"]["status"] == "done"
    assert steps["shopify_preorder"]["error"].startswith("Shopify not connected")  # it went on to Shopify
    assert client.post(f"/api/runs/{run_id}/decision/approve", json={}).status_code == 409


def test_switch_to_a_compliant_mill(client):
    run_id, run = _handoff(client)
    alt = next(o["supplierName"] for o in run["decision"]["options"] if o["kind"] == "switch")
    assert client.post(f"/api/runs/{run_id}/decision/switch", json={"supplierName": "Nobody Mills"}).status_code == 404
    r = client.post(f"/api/runs/{run_id}/decision/switch", json={"supplierName": alt, "note": "MOQ is fine"})
    assert r.status_code == 200
    run = _wait(client, run_id, lambda x: x["status"] != "running")
    assert run["recommendation"]["selectedSupplierName"] == alt and run["recommendation"]["overridden"]
    assert run["decision"]["outcome"] == "switched" and run["decision"]["resolvedSupplierName"] == alt
    sw = next(a for a in run["audit"] if a["action"] == "switched")
    assert sw["values"]["from"] == BIS and sw["values"]["to"] == alt and "inside every guardrail" in sw["summary"]


def test_legacy_supplier_override_counts_as_switch_during_a_handoff(client):
    run_id, _ = _handoff(client)
    r = client.post(f"/api/runs/{run_id}/supplier", json={"supplierName": "TEST Confezioni Europa"})
    assert r.status_code == 200 and r.json()["decision"]["outcome"] == "switched"


def test_negotiate_send_revised_quote_and_proceed(client):
    run_id, run = _handoff(client)
    assert client.post(f"/api/runs/{run_id}/decision/counter-offer/send", json={}).status_code == 409  # no draft
    r = client.post(f"/api/runs/{run_id}/decision/negotiate")
    assert r.status_code == 200, r.text
    co = r.json()["decision"]["counterOffer"]
    assert co["language"] == "it" and co["generatedBy"] == "direct vLLM" and "template" not in co
    assert co["status"] == "draft" and co["toEmail"] == "test-lanificio-lana@supplier.test"
    assert "Q-PRA-1" in co["subject"] or "Q-PRA-1" in co["body"]
    assert co["rfqRef"] in co["subject"] and co["body"].startswith("Gentile team")
    assert co["targetUnitPrice"] == i18n.floor_cents(389 * 0.35) and co["currency"] == "EUR"
    assert co["targetUnitPriceLocal"] == i18n.floor_cents(co["targetUnitPrice"] / EUR)
    assert f"{co['targetUnitPriceLocal']:.2f}" in co["body"] and co["math"][-1].startswith("Check:")
    assert any("ECB rate 2026-10-12" in line for line in co["math"])
    edited = co["body"] + " Un caro saluto."
    r = client.post(f"/api/runs/{run_id}/decision/counter-offer/send", json={"body": edited})
    assert r.status_code == 200, r.text
    d = r.json()["decision"]
    assert d["status"] == "negotiating" and d["negotiationRounds"] == 1
    assert d["counterOffer"]["edited"] and d["counterOffer"]["status"] == "sent"
    assert d["counterOffer"]["sentVia"] == "Evolus workflow wf_out"
    time.sleep(0.2)
    assert client.get(f"/api/runs/{run_id}").json()["steps"][3]["status"] == "pending"  # still blocked
    run = _upload(client, run_id, BIS, currency="EUR", price=co["targetUnitPriceLocal"], moq=200, lead="3 weeks",
                  number="Q-PRA-1-R1")
    rev = next(q for q in run["quotes"] if q["supplierName"] == BIS)
    assert rev["revision"] == 1 and rev["revises"] == "Q-PRA-1" and rev["unitPrice"] <= co["targetUnitPrice"]
    run = _wait(client, run_id, lambda x: x["status"] != "running")
    assert run["decision"]["outcome"] == "revised" and run["guardrailReport"]["selectedOk"] is True
    assert [a["action"] for a in run["audit"]] == ["guardrail_breach", "handoff", "counter_offer_drafted",
                                                   "counter_offer_sent", "revised_quote", "resolved"]
    assert run["steps"][2]["status"] == "done" and run["steps"][3]["status"] == "error"  # on to Shopify


def test_negotiation_without_brain_or_evolus_is_an_honest_error(client, s, monkeypatch):
    run_id, _ = _handoff(client)
    monkeypatch.setattr(s, "amd_vllm_endpoint", "")
    r = client.post(f"/api/runs/{run_id}/decision/negotiate")
    assert r.status_code == 503 and r.json()["service"] == "brain" and r.json()["hint"]
    assert client.get(f"/api/runs/{run_id}").json()["decision"].get("counterOffer") is None  # nothing invented
    monkeypatch.setattr(s, "amd_vllm_endpoint", f"http://{conftest.VLLM}/v1")
    assert client.post(f"/api/runs/{run_id}/decision/negotiate").status_code == 200
    monkeypatch.setattr(s, "evolus_api_key", "")
    r = client.post(f"/api/runs/{run_id}/decision/counter-offer/send", json={})
    assert r.status_code == 503 and r.json()["service"] == "evolus_negotiation"
    d = client.get(f"/api/runs/{run_id}").json()["decision"]
    assert d["status"] == "pending" and d["counterOffer"]["status"] == "draft" and d["counterOffer"]["sendError"]


def test_a_revised_quote_still_outside_asks_again(client):
    run_id, _ = _handoff(client)
    client.post(f"/api/runs/{run_id}/decision/negotiate")
    client.post(f"/api/runs/{run_id}/decision/counter-offer/send", json={})
    _upload(client, run_id, BIS, currency="EUR", price=140.0, moq=200, lead="3 weeks", number="Q-PRA-2")
    run = client.get(f"/api/runs/{run_id}").json()
    d = run["decision"]
    assert d["status"] == "pending" and d["negotiationRounds"] == 1 and "revised quote" in d["headline"]
    assert run["audit"][-1]["action"] == "revised_quote" and "still outside" in run["audit"][-1]["summary"]
    assert client.post(f"/api/runs/{run_id}/decision/approve", json={}).status_code == 200


def test_editing_guardrails_or_retail_can_clear_a_handoff(client):
    run_id, _ = _handoff(client)
    r = client.put("/api/guardrails", json={"minGrossMarginPct": 60})
    assert r.status_code == 200 and r.json()["minGrossMarginPct"] == 60 and r.json()["updatedBy"].endswith("(UI)")
    run = _wait(client, run_id, lambda x: x["status"] != "running")
    assert run["decision"]["outcome"] == "guardrails_changed"
    assert any(a["action"] == "guardrails_updated" for a in run["audit"])
    assert client.get("/api/guardrails").json()["minGrossMarginPct"] == 60
    cleared = client.post("/api/guardrails/reset").json()  # v5: reset clears every rule (no defaults)
    assert "minGrossMarginPct" not in cleared and "min_margin" in cleared["unset"] and cleared["reviewedAt"]
    client.put("/api/guardrails", json={"minGrossMarginPct": 65, "costHeadroomPct": 75, "maxLeadTimeWeeks": 10})
    run_id, run = _handoff(client)
    retail = run["techPack"]["targetRetailPrice"]
    assert client.patch(f"/api/runs/{run_id}/techpack", json={"targetRetailPrice": retail * 1.2}).status_code == 200
    run = _wait(client, run_id, lambda x: x["status"] != "running")
    assert run["decision"]["outcome"] == "techpack_changed"


def test_guardrails_api_validation_and_clearing(client):
    assert client.put("/api/guardrails", json={}).status_code == 422
    assert client.put("/api/guardrails", json={"minGrossMarginPct": 120}).status_code == 422
    g = client.put("/api/guardrails", json={"minGrossMarginPct": None}).json()  # v5: clearing = not checked
    assert "minGrossMarginPct" not in g and "min_margin" in g["unset"]
    g = client.put("/api/guardrails", json={"maxUnitCost": 110, "maxMoq": 400,
                                            "requiredCertifications": [" GOTS ", "gots", "OEKO-TEX"]}).json()
    assert g["maxUnitCost"] == 110 and g["maxMoq"] == 400 and g["requiredCertifications"] == ["GOTS", "OEKO-TEX"]
    g = client.put("/api/guardrails", json={"maxUnitCost": None, "maxMoq": None, "maxLeadTimeWeeks": None}).json()
    assert "maxUnitCost" not in g and "maxMoq" not in g and "maxLeadTimeWeeks" not in g


def test_certification_only_breach_cannot_be_negotiated(client):
    client.put("/api/guardrails", json={"requiredCertifications": ["bluesign"]})
    run_id, run = _handoff(client)
    d = run["decision"]
    assert d["allQuotesBreach"] and not any(o["kind"] == "switch" for o in d["options"])
    assert "no compliant mill" in d["explanation"]
    assert client.post(f"/api/runs/{run_id}/decision/negotiate").status_code == 200  # margin is negotiable
    client.put("/api/guardrails", json={"minGrossMarginPct": 1})  # now only the certificate is missing
    run = client.get(f"/api/runs/{run_id}").json()
    assert [b["rule"] for b in run["decision"]["breaches"]] == ["certifications"]
    assert client.post(f"/api/runs/{run_id}/decision/negotiate").status_code == 409


def test_revised_quote_by_email_webhook_is_matched_and_re_evaluated(client, s, monkeypatch):
    monkeypatch.setattr(s, "evolus_webhook_secret", SECRET)
    run_id, run = _handoff(client)
    client.post(f"/api/runs/{run_id}/decision/negotiate")
    co = client.post(f"/api/runs/{run_id}/decision/counter-offer/send", json={}).json()["decision"]["counterOffer"]
    payload = {"from": "TEST Lanificio Lana <test-lanificio-lana@supplier.test>", "subject": "Re: controproposta",
               "extraction": {"supplier_name": BIS, "quote_number": "Q-PRA-REV-1", "currency": "EUR",
                              "unit_price": i18n.fmt_decimal(co["targetUnitPriceLocal"], "it"), "moq": "200",
                              "lead_time": "3 settimane",
                              "notes": "Grazie per la vostra controproposta, possiamo accettare il prezzo."}}
    assert client.post("/api/webhooks/evolus/quote", json=payload).status_code == 401
    r = client.post("/api/webhooks/evolus/quote", json=payload, headers={"X-Atelier-Webhook-Secret": SECRET})
    assert r.status_code == 200 and r.json()["runId"] == run_id, r.text  # matched by the open negotiation
    run = _wait(client, run_id, lambda x: x["status"] != "running")
    q = next(x for x in run["quotes"] if x["supplierName"] == BIS)
    assert q["source"]["channel"] == "email" and q["revision"] == 1 and q["language"] == "it"
    assert q["noteTranslation"] == "direct vLLM" and "fake model" in q["noteEnglish"]
    assert run["decision"]["outcome"] == "revised"


def test_agent_drafts_and_evolus_sends_the_counter_offer(client, s, monkeypatch):
    conftest.go_live(monkeypatch, s, shopify_store_domain="", evolus_agent_model="app_test:agent_sourcing",
                     evolus_library_id="lib_1", evolus_negotiation_workflow_id="wf_negotiation")
    apps = conftest.route()
    run_id, _ = _handoff(client)
    co = client.post(f"/api/runs/{run_id}/decision/negotiate").json()["decision"]["counterOffer"]
    assert co["generatedBy"] == "evolus-agent → AMD vLLM"
    d = client.post(f"/api/runs/{run_id}/decision/counter-offer/send", json={}).json()["decision"]
    assert d["counterOffer"]["sentVia"] == "Evolus workflow wf_negotiation" and d["counterOffer"]["executionId"]
    sent = [x for x in apps[EVO].state.executions.values() if x["workflow"] == "wf_negotiation"]
    assert len(sent) == 1 and sent[0]["parameters"]["kind"] == "counter_offer"
    emails = json.loads(sent[0]["parameters"]["rfq_emails"])  # flat params: nested values travel as JSON strings
    assert emails[0]["toEmail"] == "test-lanificio-lana@supplier.test" and emails[0]["language"] == "it"
    assert "counter_offer" in [c.purpose for c in telemetry.snapshot(limit=200).calls]


def test_a_draft_that_drops_the_target_price_is_rejected_not_replaced(client, monkeypatch):
    import fake_upstreams as fake

    real = fake._reply_for

    def lying(messages):
        out = real(messages)
        if "write a counter-offer email" in json.dumps(messages).lower():
            data = json.loads(out)
            data["body"] = "Gentile team, vorremmo un piccolo sconto sul prezzo. Grazie per la vostra offerta, " \
                           "restiamo in attesa di una risposta dal vostro ufficio commerciale."
            return json.dumps(data)
        return out

    monkeypatch.setattr(fake, "_reply_for", lying)
    run_id, _ = _handoff(client)
    r = client.post(f"/api/runs/{run_id}/decision/negotiate")
    assert r.status_code == 503 and r.json()["service"] == "brain" and "must state" in r.json()["detail"]
    assert client.get(f"/api/runs/{run_id}").json()["decision"].get("counterOffer") is None
