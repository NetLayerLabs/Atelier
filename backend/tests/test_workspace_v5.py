"""v5: the Brand workspace - importers, persistence, provenance, the stable interfaces that read it, unset
guardrails, the approve gate and the RFQ email override. All data here is synthetic TEST data."""

import io
import sqlite3
import time
import zipfile

import pytest

from app.data import materials, suppliers
from app.models import BomLine, SupplierQuote
from app.services import guardrails, knowledge, sourcing, workspace
from app.services import workspace_import as imp

SUPPLIER_CSV = (
    "Supplier Name,City,Country,Language,Contact Email,Categories,Capabilities,Certifications,Certificate Expiry,"
    "MOQ,Lead time (weeks),Payment terms,Notes,RFQ email override,Unknown column\n"
    "TEST Alpha Knits,Testville,Portugal,Portuguese,a@alpha.test; sales@alpha.test,knitwear;cashmere,"
    "fully-fashioned,GOTS;OEKO-TEX Standard 100,GOTS=2099-01-01,300,7,TEST terms,TEST note,,x\n"
    "TEST Beta CMT,Testville,Portugal,pt,b@beta.test,CMT,,,,150,6,,,pilot@brand.test,x\n"
)


def _post_file(client, path, name, data, **form):
    return client.post(path, files={"file": (name, data, "application/octet-stream")},
                       data={k: str(v).lower() if isinstance(v, bool) else v for k, v in form.items()})


def _xlsx(rows):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _wait(client, run_id, cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        run = client.get(f"/api/runs/{run_id}").json()
        if cond(run):
            return run
        time.sleep(0.02)
    raise AssertionError("condition not reached")


def _design(client):
    """A knitwear trend (wool / cashmere) and one concept from the (fake) diffusion server - needs `live`."""
    from app.models import TrendAnalysis
    from app.store import store

    t = TrendAnalysis(id="trd_knit", trend_name="TEST Knit", summary="s", garment_type="sweater",
                      core_silhouettes=["relaxed"], color_palette=["#D8CBB5", "#4A3328"],
                      key_fabrics=["Grade-A cashmere", "extra-fine merino wool"], commercial_viability_score=60)
    store.trends[t.id] = t
    r = client.post("/api/designs/generate", json={"trendId": t.id, "count": 1})
    assert r.status_code == 200, r.text
    return r.json()["designs"][0]


# --------------------------------------------------------------------------- importers


def test_supplier_csv_preview_then_commit_with_provenance(client):
    workspace.wipe()
    r = _post_file(client, "/api/workspace/suppliers/import", "directory.csv", SUPPLIER_CSV.encode())
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["committed"] is False and p["validRows"] == 2 and not [i for i in p["issues"] if i["level"] == "error"]
    assert "Unknown column" in p["ignoredColumns"] and "contact_emails" in p["columns"]
    assert p["rows"][0]["contactEmails"] == "a@alpha.test; sales@alpha.test"
    assert "GOTS (exp. 2099-01-01)" in p["rows"][0]["certifications"]
    assert workspace.suppliers() == []  # a preview stores nothing

    p = _post_file(client, "/api/workspace/suppliers/import", "directory.csv", SUPPLIER_CSV.encode(),
                   commit=True).json()
    assert p["committed"] is True and p["provenance"]["label"].startswith("Imported from directory.csv on ")
    assert p["provenance"]["rows"] == 2 and p["provenance"]["source"] == "csv"
    sups = client.get("/api/workspace/suppliers").json()
    alpha, beta = sups
    assert alpha["language"] == "pt" and alpha["emails"] == ["a@alpha.test", "sales@alpha.test"]
    assert alpha["certifications"][0] == {"name": "GOTS", "expiresOn": "2099-01-01", "expired": False}
    assert alpha["moq"] == 300 and alpha["leadTimeWeeks"] == 7 and alpha["maker"] is False
    assert beta["maker"] is True and beta["rfqRecipient"] == "pilot@brand.test"
    assert alpha["provenance"]["filename"] == "directory.csv"
    # importing re-opens the contact confirmation
    assert not workspace.supplier_confirmation().confirmed_at


def test_supplier_validation_errors_block_the_commit(client):
    workspace.wipe()
    bad = ("name,contact_emails,moq,language,certifications,certificate_expiry\n"
           "TEST One,not-an-email,10,en,,\n"
           "TEST Two,two@x.test,ten,en,,\n"
           "TEST Three,three@x.test,5,Klingon,,\n"
           "TEST Four,four@x.test,5,en,GOTS,GOTS=31/12/2026\n"
           ",five@x.test,5,en,,\n"
           "TEST Six,six@x.test,5,en,,\n"
           "TEST Six,six2@x.test,5,en,,\n")
    p = _post_file(client, "/api/workspace/suppliers/import", "bad.csv", bad.encode(), commit=True).json()
    errs = {(i["row"], i["field"]) for i in p["issues"] if i["level"] == "error"}
    assert {(1, "contact_emails"), (2, "moq"), (3, "language"), (4, "certificate_expiry"), (5, "name"),
            (7, "name")} <= errs
    assert p["committed"] is False and p["validRows"] == 1 and workspace.suppliers() == []
    assert [r for r in p["rows"] if r.get("_error")]
    missing = _post_file(client, "/api/workspace/suppliers/import", "x.csv", b"city,country\nA,B\n").json()
    assert "missing column(s): name, contact_emails" in missing["issues"][0]["message"]
    assert _post_file(client, "/api/workspace/suppliers/import", "x.pdf", b"%PDF").status_code == 422


def test_xlsx_price_list_import_and_alternatives(client):
    rows = [["Material", "Category", "Unit", "Price", "Currency", "Supplier", "Valid from"],
            ["TEST Wool twill", "TEST wovens", "m", 20, "EUR", "TEST Lanificio Lana", "2026-09-01"],
            ["TEST Recycled wool twill", "TEST wovens", "m", 12.5, "EUR", "Somebody Else", "2026-09-15"],
            ["TEST Bad", "TEST wovens", "m", "free", "EUR", "", "2026-09-01"]]
    p = _post_file(client, "/api/workspace/prices/import", "prices.xlsx", _xlsx(rows), commit=True).json()
    assert p["committed"] is False and any(i["field"] == "price" for i in p["issues"])
    p = _post_file(client, "/api/workspace/prices/import", "prices.xlsx", _xlsx(rows[:3]), commit=True).json()
    assert p["committed"] is True and p["provenance"]["source"] == "xlsx"
    assert any(i["level"] == "warning" and "not in the supplier directory" in i["message"] for i in p["issues"])
    pl = client.get("/api/workspace/prices").json()
    assert pl["dated"] == "2026-09-15" and len(pl["items"]) == 2  # replace mode dropped the TEST fixture list
    alt = materials.alternatives_for(0, BomLine(material="TEST Wool twill - shell", quantity="2 m",
                                                target_cost_per_unit=40.0))
    assert alt is not None and alt.family == "TEST wovens"
    assert alt.options[0].original and "EUR 20.00/m" in alt.options[0].note
    assert alt.options[1].material == "TEST Recycled wool twill - shell" and alt.options[1].target_cost_per_unit == 25.0
    assert materials.alternatives_for(0, BomLine(material="Nothing on the list", quantity="1",
                                                 target_cost_per_unit=5)) is None
    assert materials.price_list_label()[0] == "2026-09-15"


def test_sizes_and_sales_history_import_and_priors(client):
    sizes = "block,point_of_measure,size,value,unit,tolerance\nTEST tops,Chest width,M,52,cm,1\nTEST tops,Length,M,70,cm,\n"
    p = _post_file(client, "/api/workspace/sizes/import", "sizes.csv", sizes.encode(), commit=True).json()
    assert p["committed"] and len(workspace.size_points()) == 2
    assert "size blocks on file: TEST tops" in workspace.brand_prompt("designer")
    sales = ("style;launch_date;week;units;size\nTEST-1;2025-03-01;1;10;S\nTEST-1;2025-03-01;1;30;M\n"
             "TEST-1;2025-03-01;3;20;M\nTEST-2;2025-04-01;2;5;\n")
    p = _post_file(client, "/api/workspace/sales/import", "sales.csv", sales.encode(), commit=True).json()
    assert p["committed"], p["issues"]
    assert workspace.launch_curves() == {"TEST-1": [40, 0, 20], "TEST-2": [0, 5]}
    assert workspace.size_mix() == {"S": 0.1667, "M": 0.8333}
    assert client.get("/api/workspace/sales").json()["styles"] == 2
    bad = "style,launch_date,week,units\nX,2025-01-01,0,5\nY,yesterday,1,5\n"
    p = _post_file(client, "/api/workspace/sales/import", "s.csv", bad.encode()).json()
    assert {i["field"] for i in p["issues"]} == {"week", "launch_date"}


def test_templates_are_headers_only(client):
    for kind in ("suppliers", "prices", "sizes", "sales"):
        r = client.get(f"/api/workspace/templates/{kind}.csv")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
        lines = r.text.strip().splitlines()
        assert len(lines) == 1  # no example rows: nothing invented
    assert client.get("/api/workspace/templates/suppliers.csv").text.startswith("name,city,country,language")


# --------------------------------------------------------------------------- persistence


def test_workspace_persists_in_sqlite_under_the_data_dir(client):
    path = workspace.db_path()
    assert path.is_file() and path.name == "atelier.sqlite3"
    con = sqlite3.connect(path)
    n = con.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0]
    con.close()
    assert n == 9
    workspace._initialised.clear()  # as after a restart: everything is read back from the file
    assert workspace.profile().name == "TEST Brand" and len(workspace.suppliers()) == 9
    assert client.get("/api/workspace").json()["status"]["ready"] is True
    assert client.delete("/api/workspace").status_code == 422
    snap = client.delete("/api/workspace", params={"confirm": "DELETE"}).json()
    assert "profile" not in snap and snap["suppliers"] == [] and snap["status"]["ready"] is False


def test_profile_form_validation_and_provenance(client):
    r = client.put("/api/workspace/profile", json={"name": "TEST Label", "currency": "eur", "targetMarkets": ["EU", "eu"],
                                                   "colours": [{"name": "TEST Ink", "hex": "#101820"}],
                                                   "priceArchitecture": {"mode": "retail_multiple", "value": 4},
                                                   "deliveryPromiseWeeks": 10, "preorderWindowDays": 21})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["currency"] == "EUR" and p["targetMarkets"] == ["EU"] and "code" not in p["colours"][0]
    assert p["provenance"]["source"] == "form" and p["provenance"]["label"].startswith("Entered in the workspace on")
    assert client.get("/api/guardrails").json()["currency"] == "EUR"
    assert client.put("/api/workspace/profile", json={"name": "", "currency": "EUR"}).status_code == 422
    assert client.put("/api/workspace/profile", json={"name": "X", "currency": "EUR",
                                                      "colours": [{"name": "c", "hex": "red"}]}).status_code == 422


# --------------------------------------------------------------------------- stable interfaces read the workspace


def test_supplier_interfaces_read_the_workspace():
    assert len(suppliers.ALL_SUPPLIERS) == 9 and suppliers.ALL_SUPPLIERS[0]["name"] == "TEST Indigo Denim"
    sl = suppliers.shortlist(["Grade-A cashmere", "extra-fine merino wool"])
    assert [s["name"] for s in sl] == ["TEST Malhas Malha", "TEST Lanificio Lana", "TEST Confezioni Europa"]
    sl = suppliers.shortlist(["14oz selvedge denim", "raw indigo twill"])
    assert [s["name"] for s in sl] == ["TEST Indigo Denim", "TEST Organic Cotton", "TEST Garment Asia"]
    assert suppliers.shortlist(["something nobody makes"])[0]["name"] == "TEST Indigo Denim"
    s = suppliers.find_supplier("TEST Tessitura Seta s.r.l.")
    assert s["region"] == "Testville, Italy" and s["language"] == "it" and "SA8000" in s["certifications"]
    assert s["moq"] == 200 and s["lead_time_weeks"] == 7 and s["payment_terms"] == "test terms C"
    assert not hasattr(suppliers, "quote_profile")  # v5: no simulated quotes, so no quote profiles
    # live: a supplier added now is visible through the same imported names
    from app.workspace_models import SupplierInput

    workspace.add_supplier(SupplierInput(name="TEST Late Addition", emails=["late@x.test"], categories=["linen"]))
    assert any(x["name"] == "TEST Late Addition" for x in suppliers.ALL_SUPPLIERS)
    workspace.wipe()
    assert suppliers.shortlist(["denim"]) == [] and len(suppliers.ALL_SUPPLIERS) == 0


def test_sourcing_constants_and_weights_come_from_the_workspace(client):
    assert sourcing.DELIVERY_PROMISE_WEEKS == 12 and sourcing.PREORDER_WINDOW_WEEKS == 2.0
    assert sourcing.LEAD_BUDGET_WEEKS == 10
    w = client.get("/api/workspace/scoring").json()
    assert w == {"price": 0.45, "moq": 0.3, "leadTime": 0.25, "isDefault": True, "label": "default weighting"}
    assert sourcing.WEIGHTS.price == 0.45 and "default weighting" in sourcing.scoring_summary(300)
    w = client.put("/api/workspace/scoring", json={"price": 50, "moq": 25, "leadTime": 25}).json()
    assert w["price"] == 0.5 and w["isDefault"] is False and w["label"] == "set by the brand"
    qs = [SupplierQuote(supplier_name=n, region="", unit_price=p, moq=100, lead_time_weeks=lt, sample_cost=0,
                        payment_terms="", note="") for n, p, lt in (("A", 100, 10), ("B", 120, 4))]
    sourcing.score_quotes(qs, 300)
    assert sourcing.recommend(qs, 300).weights.price == 0.5
    assert client.put("/api/workspace/scoring", json={"price": 0, "moq": 0, "leadTime": 0}).status_code == 422
    assert client.post("/api/workspace/scoring/reset").json()["isDefault"] is True
    # no promise set by the brand -> the lead budget falls back to the max-lead-time guardrail, else relative
    p = workspace.profile()
    workspace.save_profile(p.model_copy(update={"delivery_promise_weeks": None}))
    assert sourcing.DELIVERY_PROMISE_WEEKS is None and sourcing.lead_budget_weeks() == 10.0
    workspace.save_guardrails(guardrails.current().model_copy(update={"max_lead_time_weeks": None}), by="t")
    assert sourcing.lead_budget_weeks() is None and sourcing._lead_score(8, 4) == 50.0


def test_expired_certificates_do_not_count():
    from app.models import Guardrails
    from app.workspace_models import SupplierCertification, SupplierInput

    workspace.add_supplier(SupplierInput(name="TEST Expired Certs", emails=["e@x.test"], certifications=[
        SupplierCertification(name="GOTS", expires_on="2001-01-01"),
        SupplierCertification(name="OEKO-TEX", expires_on="2099-01-01")]))
    sup = workspace.supplier("test-expired-certs")
    assert [c.expired for c in sup.certifications] == [True, False]
    q = SupplierQuote(supplier_name="TEST Expired Certs", region="", unit_price=10, moq=1, lead_time_weeks=1,
                      sample_cost=0, payment_terms="", note="")
    ev = guardrails.evaluate_quote(q, Guardrails(required_certifications=["GOTS", "OEKO-TEX"]), None)
    assert not ev.ok and "missing GOTS" in ev.checks[0].message


def test_prompts_use_the_brand_not_a_fictional_house():
    assert workspace.persona("sourcing manager").startswith("You are TEST Brand's sourcing manager.")
    assert "TEST voice notes." in workspace.persona("x")
    workspace.wipe()
    assert workspace.persona("sourcing manager") == "You are the brand's sourcing manager."


# --------------------------------------------------------------------------- guardrails unset, readiness gate


def test_guardrails_status_lists_unset_rules(client):
    workspace.wipe()
    g = client.get("/api/guardrails").json()
    assert g["unset"] == ["min_margin", "max_unit_cost", "max_lead_time", "max_moq", "certifications"]
    sec = {s["key"]: s for s in client.get("/api/workspace/status").json()["sections"]}
    assert sec["guardrails"]["done"] is False and sec["guardrails"]["detail"] == "0 of 5 rules set · not reviewed"
    g = client.post("/api/guardrails/review").json()
    assert g["reviewedAt"] and len(g["unset"]) == 5
    sec = {s["key"]: s for s in client.get("/api/workspace/status").json()["sections"]}
    assert sec["guardrails"]["done"] is True


def test_approve_is_blocked_until_the_workspace_is_onboarded(live):
    client = live
    from app.workspace_models import SupplierInput

    workspace.wipe()
    d = _design(client)
    r = client.post(f"/api/designs/{d['id']}/approve", json={"productionQuantity": 300})
    assert r.status_code == 409
    msg = r.json()["detail"]
    assert "Brand workspace" in msg and "brand profile" in msg and "at least one supplier" in msg and "guardrails" in msg
    st = client.get("/api/workspace/status").json()
    assert st["ready"] is False and len(st["missing"]) == 3

    client.put("/api/workspace/profile", json={"name": "TEST Label", "currency": "USD"})
    client.post("/api/workspace/suppliers", json=SupplierInput(
        name="TEST Only Mill", emails=["only@x.test"], categories=["cashmere"]).model_dump(by_alias=True))
    msg = client.post(f"/api/designs/{d['id']}/approve", json={}).json()["detail"]
    assert "confirmation of the supplier contacts" in msg and "brand profile" not in msg
    assert client.post("/api/workspace/suppliers/confirm", json={"confirm": False}).status_code == 422
    c = client.post("/api/workspace/suppliers/confirm", json={"confirm": True}).json()
    assert c["confirmedAt"] and c["suppliers"] == 1
    msg = client.post(f"/api/designs/{d['id']}/approve", json={}).json()["detail"]
    assert msg.endswith("a review of the guardrails in Brand workspace before approving a design.")
    client.post("/api/guardrails/review")
    r = client.post(f"/api/designs/{d['id']}/approve", json={"productionQuantity": 300})
    assert r.status_code == 200 and r.json()["runId"]


def test_rfq_email_override_routes_the_rfqs(live):
    client = live
    sup = client.get("/api/workspace/suppliers").json()
    lana = next(s for s in sup if s["name"] == "TEST Lanificio Lana")
    body = {k: v for k, v in lana.items() if k not in ("id", "provenance", "createdAt", "updatedAt", "rfqRecipient",
                                                        "maker")}
    body["rfqEmailOverride"] = "sourcing-pilot@brand.test"
    r = client.put(f"/api/workspace/suppliers/{lana['id']}", json=body)
    assert r.status_code == 200 and r.json()["rfqRecipient"] == "sourcing-pilot@brand.test"
    # who gets emailed changed -> the brand must confirm the directory again before approving
    assert client.get("/api/workspace/status").json()["ready"] is False
    body["rfqEmailOverride"] = "not an email"
    assert client.put(f"/api/workspace/suppliers/{lana['id']}", json=body).status_code == 422
    client.post("/api/workspace/suppliers/confirm", json={"confirm": True})
    d = _design(client)
    run_id = client.post(f"/api/designs/{d['id']}/approve", json={"productionQuantity": 300}).json()["runId"]
    run = _wait(client, run_id, lambda r: (r.get("quoteRound") or {}).get("status") == "awaiting")
    to = {e["supplierName"]: e["toEmail"] for e in run["supplierEmails"]}
    assert to["TEST Lanificio Lana"] == "sourcing-pilot@brand.test"
    assert to["TEST Malhas Malha"] == "test-malhas-malha@supplier.test"


# --------------------------------------------------------------------------- brand book documents


def _docx(paragraphs):
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    def para(style, text):
        ppr = '<w:pPr><w:pStyle w:val="' + style + '"/></w:pPr>' if style else ""
        return f"<w:p>{ppr}<w:r><w:t>{text}</w:t></w:r></w:p>"

    body = "".join(para(style, text) for style, text in paragraphs)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document {ns}><w:body>{body}</w:body></w:document>')
    return buf.getvalue()


def test_brand_book_upload_docx_pdf_md_grounds_citations(client):
    docx = _docx([("Title", "TEST House Rules"), ("Heading1", "TEST Packaging"),
                  ("", "TEST rule: tissue paper is unbleached and recycled.")])
    r = _post_file(client, "/api/workspace/documents", "rules.docx", docx)
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["kind"] == "brand_book" and doc["passages"] >= 1 and doc["chars"] > 20
    assert doc["evolus"]["status"] == "not_configured"
    hits = knowledge.local_search("packaging tissue paper unbleached", 2)
    assert hits and hits[0].source == "TEST House Rules - TEST Packaging" and hits[0].document_id == doc["id"]
    assert client.get(f"/api/workspace/documents/{doc['id']}/file").content == docx

    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, "TEST lining rule: cupro linings only.")
    c.save()
    pdf = _post_file(client, "/api/workspace/documents", "lining.pdf", buf.getvalue()).json()
    assert any(h.document_id == pdf["id"] and "Page 1" in h.source for h in knowledge.local_search("cupro linings", 3))

    assert _post_file(client, "/api/workspace/documents", "x.exe", b"MZ").status_code == 422
    assert client.delete(f"/api/workspace/documents/{doc['id']}").status_code == 204
    assert not any(h.document_id == doc["id"] for h in knowledge.local_search("packaging tissue paper", 5))
    assert client.delete(f"/api/workspace/documents/{doc['id']}").status_code == 404


def test_brand_book_goes_to_the_evolus_library_when_configured(client, monkeypatch):
    from app.config import get_settings
    from app.services import http
    from fake_upstreams import RoutingTransport, create_evolus_app

    s = get_settings()
    for k, v in {"evolus_api_base": "http://evolus.fake", "evolus_api_key": "test-key",
                 "evolus_workspace_id": "app_test", "evolus_library_id": "lib_1"}.items():
        monkeypatch.setattr(s, k, v)
    evo = create_evolus_app()
    http.set_transport(RoutingTransport({"evolus.fake": evo}))
    try:
        doc = _post_file(client, "/api/workspace/documents", "book.md", b"# TEST Book\n\n## Rule\n\nTEST text.").json()
    finally:
        http.set_transport(None)
    assert doc["evolus"]["status"] == "uploaded" and doc["evolus"]["libraryId"] == "lib_1"
    assert any(d["title"] == "book.md" for d in evo.state.documents["lib_1"])


def test_certificate_upload_attaches_to_the_supplier(client):
    sid = "test-indigo-denim"
    r = _post_file(client, f"/api/workspace/suppliers/{sid}/certificates", "gots.pdf", b"%PDF-1.4 test",
                   certification="GOTS (organic cotton)")
    assert r.status_code == 200, r.text
    cert = next(c for c in r.json()["certifications"] if c["name"] == "GOTS (organic cotton)")
    assert cert["documentId"].startswith("doc_")
    assert client.get(f"/api/workspace/documents/{cert['documentId']}/file").content == b"%PDF-1.4 test"
    assert _post_file(client, "/api/workspace/suppliers/nope/certificates", "g.pdf", b"%PDF",
                      certification="GOTS").status_code == 404


@pytest.mark.parametrize("raw,expected", [("1,234.50", 1234.5), ("1.234,50", 1234.5), ("12,5", 12.5),
                                          ("€ 7", 7.0), ("1,200", 1200.0)])
def test_number_parsing(raw, expected):
    assert imp._number(raw) == expected
