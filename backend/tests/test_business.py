"""Business loop (v5): real quote documents -> recommendation -> real pre-orders -> a real PO sent through Evolus.
Everything external is a test double from tests/fake_upstreams.py; nothing in the app is simulated."""

import json
import re

import pytest
from helpers import answer_all_rfqs, approve, collecting, upload_quote, wait

from app.models import SupplierQuote
from app.services import sequences, sourcing
from app.store import store


def _close_windows():
    for meta in store.run_meta.values():
        if meta.get("shopify"):
            meta["shopify"]["launchedMono"] -= 10**9


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    _close_windows()


def _order(fakes, run, n=1, size="M", test=True):
    for _ in range(n):
        fakes["shop.fake"].state.place_order(run["shopifyProduct"]["productId"], 1, size=size, test=test)


def test_full_loop_po_is_numbered_and_sent_through_evolus(live, fakes, trend, s, monkeypatch):
    monkeypatch.setattr(s, "demand_stage_threshold", 2)
    run_id = approve(live, trend, qty=300)
    answer_all_rfqs(live, run_id)
    run = wait(live, run_id, collecting)
    d = run["demand"]
    assert d["thresholdBasis"] == "stage" and d["stageThreshold"] == 2 and d["productionThreshold"] == 300
    _order(fakes, run, 2)
    run = wait(live, run_id)
    assert run["status"] == "completed", run["steps"]
    d = run["demand"]
    assert d["status"] == "unlocked" and d["units"] == 2 and d["testOrders"] == 2 and d["testUnits"] == 2
    po = d["purchaseOrder"]
    assert po["poNumber"] == "PO-00001" and po["status"] == "sent" and po["sentVia"] == "Evolus workflow wf_po"
    assert po["quantity"] == 300 and po["currency"] == "USD" and po["unitPrice"] == 101.5
    assert po["total"] == pytest.approx(300 * 101.5) and po["leadTimeWeeks"] == 8
    assert po["toEmail"] == next(e["toEmail"] for e in run["supplierEmails"] if e["supplierName"] == po["supplierName"])
    assert "issuedAt" not in po and "simulated" not in po
    ex = fakes["evolus.fake"].state.executions
    sent = [x for x in ex.values() if x["workflow"] == "wf_po"]
    # Only the declared email parameters go in `parameters` (Evolus rejects undeclared ones); the rest is in `input`
    assert len(sent) == 1 and {k.split("__")[0] for k in sent[0]["parameters"]} <= {"rfq_emails", "rfq_ref", "kind"}
    assert sent[0]["parameters"]["kind"] == "purchase_order" and '"po_number": "PO-00001"' in sent[0]["input"]
    assert "PO-00001" in json.loads(sent[0]["parameters"]["rfq_emails"])[0]["subject"]
    log = run["steps"][4]["log"]
    assert any("incl. 2 test orders" in line for line in log)
    assert any("PO-00001 sent" in line for line in log)
    assert sequences.peek("po") == 1


def test_po_without_evolus_stays_a_draft_and_can_be_sent_later(live, fakes, trend, s, monkeypatch):
    monkeypatch.setattr(s, "demand_stage_threshold", 1)
    run_id = approve(live, trend)
    answer_all_rfqs(live, run_id)
    run = wait(live, run_id, collecting)
    monkeypatch.setattr(s, "evolus_po_workflow_id", "")
    monkeypatch.setattr(s, "evolus_outreach_workflow_id", "")
    _order(fakes, run)
    run = wait(live, run_id)
    po = run["demand"]["purchaseOrder"]
    assert po["status"] == "draft" and "not been sent" in po["sendError"] and "EVOLUS_PO_WORKFLOW_ID" in po["hint"]
    assert any("draft, not sent" in line for line in run["steps"][4]["log"])
    r = live.post(f"/api/runs/{run_id}/purchase-order/send")
    assert r.status_code == 503 and r.json()["service"] == "evolus_po"
    monkeypatch.setattr(s, "evolus_po_workflow_id", "wf_po")
    r = live.post(f"/api/runs/{run_id}/purchase-order/send")
    assert r.status_code == 200 and r.json()["demand"]["purchaseOrder"]["status"] == "sent"
    assert live.post(f"/api/runs/{run_id}/purchase-order/send").status_code == 409


def test_po_numbers_are_sequential_per_brand(s, monkeypatch):
    assert [sequences.next_code("po") for _ in range(3)] == ["PO-00001", "PO-00002", "PO-00003"]
    assert sequences.next_code("po", brand="other") == "PO-00001"
    assert sequences.next_code("style") == "ST-00001"
    assert sequences.peek("po") == 3


def test_threshold_missed_says_what_really_happens(live, trend, s, monkeypatch):
    monkeypatch.setattr(s, "shopify_demand_window_hours", 0.00002)
    run_id = approve(live, trend)
    answer_all_rfqs(live, run_id)
    run = wait(live, run_id)
    assert run["demand"]["status"] == "expired" and "purchaseOrder" not in run["demand"]
    line = run["steps"][4]["log"][-1]
    assert "does not refund" in line and "refunded" not in line


def test_override_and_techpack_edit_rescore_without_repricing(live, trend):
    run_id = approve(live, trend, qty=400)
    run = wait(live, run_id, lambda r: (r.get("quoteRound") or {}).get("status") == "awaiting")
    a, b = [e["supplierName"] for e in run["supplierEmails"]][:2]
    upload_quote(live, run_id, a, price=100.0, moq=200)
    run = upload_quote(live, run_id, b, price=110.0, moq=800)
    if run["quoteRound"]["status"] == "awaiting":
        live.post(f"/api/runs/{run_id}/quotes/close")
    run = wait(live, run_id, collecting)
    assert run["recommendation"]["supplierName"] == a
    r = live.post(f"/api/runs/{run_id}/supplier", json={"supplierName": b})
    run = r.json()
    assert run["recommendation"]["selectedSupplierName"] == b and run["recommendation"]["overridden"]
    assert run["demand"]["productionThreshold"] == 800
    prices = {q["supplierName"]: q["unitPrice"] for q in run["quotes"]}
    r = live.patch(f"/api/runs/{run_id}/techpack", json={"productionQuantity": 900, "targetRetailPrice": 299})
    run = r.json()
    assert run["techPackRevision"] == 1 and run["shopifyProduct"]["price"] == 299
    assert {q["supplierName"]: q["unitPrice"] for q in run["quotes"]} == prices  # a mill's price is its document's
    assert next(q for q in run["quotes"] if q["supplierName"] == b)["scoreBreakdown"]["moq"] == 100.0
    assert run["recommendation"]["selectedSupplierName"] == b


def test_patch_validation_and_404s(live, trend):
    run_id = approve(live, trend)
    wait(live, run_id, lambda r: "techPack" in r)
    assert live.patch(f"/api/runs/{run_id}/techpack", json={}).status_code == 422
    assert live.patch(f"/api/runs/{run_id}/techpack", json={"targetRetailPrice": 0}).status_code == 422
    assert live.patch(f"/api/runs/{run_id}/techpack", json={"billOfMaterials": []}).status_code == 422
    bad = [{"material": "x", "quantity": "1", "targetCostPerUnit": -1}]
    assert live.patch(f"/api/runs/{run_id}/techpack", json={"billOfMaterials": bad}).status_code == 422
    for method, path, kw in [("patch", "/api/runs/run_nope/techpack", {"json": {"productionQuantity": 3}}),
                             ("get", "/api/runs/run_nope/techpack/alternatives", {}),
                             ("get", "/api/runs/run_nope/techpack.pdf", {}),
                             ("post", "/api/runs/run_nope/supplier", {"json": {"supplierName": "x"}}),
                             ("post", "/api/runs/run_nope/purchase-order/send", {})]:
        assert getattr(live, method)(path, **kw).status_code == 404
    assert live.post(f"/api/runs/{run_id}/demand/speed", json={"speed": 2}).status_code in (404, 405)
    assert live.get(f"/api/runs/{run_id}/quotes/sample/prato.pdf").status_code == 404
    assert live.post(f"/api/runs/{run_id}/purchase-order/send").status_code == 409


def test_alternatives_endpoint(live, trend):
    run_id = approve(live, trend)
    wait(live, run_id, lambda r: "techPack" in r)
    lines = live.get(f"/api/runs/{run_id}/techpack/alternatives").json()["lines"]
    for a in lines:
        assert sum(1 for o in a["options"] if o["original"]) == 1


def _pdf_text(pdf: bytes) -> str:
    import io

    from pypdf import PdfReader

    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)


def test_techpack_pdf_has_only_real_content(live, fakes, trend, s, monkeypatch):
    monkeypatch.setattr(s, "demand_stage_threshold", 2)
    run_id = approve(live, trend)
    answer_all_rfqs(live, run_id, moq=None, lead=None)
    # a lead time the quote doesn't state can't be confirmed inside the guardrail -> a person decides
    run = wait(live, run_id, lambda r: (r.get("decision") or {}).get("status") == "pending")
    assert any(c["actual"] == "not stated" for c in run["decision"]["breaches"])
    assert "negotiate" not in [o["kind"] for o in run["decision"]["options"]]  # nothing to negotiate, only ask
    assert "()" not in run["decision"]["explanation"]
    assert live.post(f"/api/runs/{run_id}/decision/approve", json={"note": "lead time agreed by phone"}).status_code == 200
    run = wait(live, run_id, collecting)
    text = _pdf_text(live.get(f"/api/runs/{run_id}/techpack.pdf").content)
    assert "STYLE ST-00001" in text and "SEASON" not in text and "TCX" not in text
    assert "simulated" not in text.lower() and "AQL" not in text
    assert "Canned construction note from the fake model." in text
    assert "not stated" in text  # MOQ / lead time missing on the quote
    assert "SIZE BREAKDOWN" not in text  # no sized orders yet -> omitted
    _order(fakes, run, 1, size="M")
    _order(fakes, run, 1, size="L")
    wait(live, run_id)
    r = live.get(f"/api/runs/{run_id}/techpack.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    text = _pdf_text(r.content)
    assert "SIZE BREAKDOWN" in text and "from 2 sized pre-orders" in text
    assert "PO-00001" in text and "issued" not in text
    assert len(re.findall(rb"/Type /Page[^s]", r.content)) == 4


def test_pdf_without_construction_notes_omits_the_section(live, trend):
    run_id = approve(live, trend)
    wait(live, run_id, lambda r: "techPack" in r)
    store.runs[run_id].tech_pack.construction_notes = None
    text = _pdf_text(live.get(f"/api/runs/{run_id}/techpack.pdf").content)
    assert "CONSTRUCTION NOTES" not in text


def test_pdf_before_techpack_is_409(client):
    from app.models import PipelineRun, PipelineStep

    store.runs["run_empty"] = PipelineRun(id="run_empty", design_id="dsn_x",
                                          steps=[PipelineStep(key="techpack", label="Tech Pack")])
    assert client.get("/api/runs/run_empty/techpack.pdf").status_code == 409
    assert client.patch("/api/runs/run_empty/techpack", json={"productionQuantity": 3}).status_code == 409
    assert client.post("/api/runs/run_empty/supplier", json={"supplierName": "x"}).status_code == 409


def test_scoring_uses_only_stated_criteria():
    def q(name, price, moq, lead):
        return SupplierQuote(supplier_name=name, region="x", unit_price=price, moq=moq, lead_time_weeks=lead)

    quotes = [q("Cheap but huge MOQ", 80, 1200, 6), q("Balanced", 92, 300, 6), q("Slow", 85, 300, 16),
              q("Silent", 90, None, None)]
    sourcing.score_quotes(quotes, 500)
    by = {x.supplier_name: x for x in quotes}
    assert by["Cheap but huge MOQ"].score_breakdown.price == 100
    assert by["Slow"].score_breakdown.lead_time == 0
    assert by["Silent"].score_breakdown.moq is None and by["Silent"].score_breakdown.lead_time is None
    assert by["Silent"].score == by["Silent"].score_breakdown.price  # only the price is known
    rec = sourcing.recommend(quotes, 500)
    assert rec.rationale is None and rec.rationale_error  # no brain here -> no invented rationale
    unconverted = q("EUR mill", None, 300, 6)
    sourcing.score_quotes([unconverted, by["Balanced"]], 500)
    assert unconverted.score_breakdown.price is None
    assert sourcing.best([unconverted, by["Balanced"]]).supplier_name == "Balanced"
