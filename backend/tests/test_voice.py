"""v3: Customer voice - ingest, deterministic taxonomy, citations, apply -> tech pack."""

import csv
import io
import time

import pytest

from app.services import direction, voice
from app.services.voice_taxonomy import THEME_BY_ID, find_mentions, themes_in
from app.store import store


@pytest.fixture(autouse=True)
def _reset_voice():
    voice.reset()
    yield
    voice.reset()


def _csv(rows: list[dict], headers: list[str] | None = None, delimiter: str = ",") -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=headers or list(rows[0]), delimiter=delimiter)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _wait(client, run_id, timeout=20.0):
    """Until the tech pack is written (the rest of the run waits for real quote documents)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if "techPack" in run or run["status"] != "running":
            return run
        time.sleep(0.01)
    raise AssertionError("run did not finish")


# --------------------------------------------------------------------------- column detection


@pytest.mark.parametrize("headers, expected", [
    # Women's E-Commerce Clothing Reviews (the bundled sample)
    (["review_id", "clothing_id", "title", "review_text", "rating", "recommended", "positive_feedback_count",
      "division", "department", "class"],
     {"id": "review_id", "text": "review_text", "title": "title", "rating": "rating", "garment_class": "class",
      "helpful": "positive_feedback_count"}),
    # Judge.me / Shopify product reviews export
    (["title", "body", "rating", "review_date", "source", "curated", "reviewer_name", "reviewer_email",
      "product_id", "product_handle", "reply"],
     {"text": "body", "title": "title", "rating": "rating", "date": "review_date", "product": "product_handle"}),
    # Shopify-style returns export
    (["Order", "Product title", "Variant title", "Return reason", "Customer note", "Created at"],
     {"return_reason": "Return reason", "text": "Customer note", "product": "Product title",
      "size": "Variant title", "date": "Created at", "id": "Order"}),
    # Generic support tickets
    (["Ticket ID", "Subject", "Message", "Customer email", "Category"],
     {"id": "Ticket ID", "title": "Subject", "text": "Message", "garment_class": "Category"}),
    # Fit feedback + size purchased
    (["Comment", "Stars", "Size purchased", "Fit feedback"],
     {"text": "Comment", "rating": "Stars", "size": "Size purchased", "fit_feedback": "Fit feedback"}),
])
def test_detect_columns(headers, expected):
    cols = voice.detect_columns(headers).model_dump(by_alias=False, exclude_none=True)
    assert cols == expected


def test_detect_columns_never_maps_pii_and_falls_back_to_longest_text():
    headers = ["reviewer_email", "col_a", "col_b"]
    rows = [["a@x.test", "5", "The shoulders were far too tight to lift my arms in this coat"],
            ["b@x.test", "3", "Lovely colour but it pills after two washes, really disappointing"]]
    cols = voice.detect_columns(headers, rows)
    assert cols.text == "col_b"
    assert "reviewer_email" not in cols.model_dump(exclude_none=True).values()


def test_parse_csv_semicolon_ratings_and_row_ids():
    data = _csv([{"Comment": "Runs small, size up.", "Rating": "4/5"},
                 {"Comment": "", "Rating": ""},
                 {"Comment": "Itchy wool.", "Rating": "★★"}], delimiter=";")
    records, cols, warnings = voice.parse_csv(data, "x.csv")
    assert cols.text == "Comment" and cols.rating == "Rating"
    assert [r.id for r in records] == ["row-2", "row-4"]  # header is row 1; the blank row 3 is skipped
    assert records[0].rating == 4.0 and records[1].rating == 2.0


def test_parse_csv_rejects_files_without_text():
    with pytest.raises(voice.VoiceError) as e:
        voice.parse_csv(_csv([{"sku": "A1", "qty": "2"}]), "x.csv")
    assert e.value.status == 422


# --------------------------------------------------------------------------- PDF


def _pdf(lines_per_page: list[list[str]]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for lines in lines_per_page:
        y = 800
        for ln in lines:
            c.drawString(40, y, ln)
            y -= 16
        c.showPage()
    c.save()
    return buf.getvalue()


def test_pdf_ingestion_splits_records_and_reads_ratings():
    data = _pdf([
        ["Customer feedback export", "Review #101", "Rating: 2/5", "Tight across the shoulders, I can't lift my arms.",
         "Review #102", "Rating: 5/5", "Not tight at all, true to size and so soft."],
        ["Review #103", "Rating: 1/5", "It pills after one wash."],
    ])
    records, cols, warnings = voice.parse_pdf(data)
    texts = {r.id: r.text for r in records}
    assert any("Review #101" in t and "shoulders" in t for t in texts.values())
    r101 = next(r for r in records if "Review #101" in r.text)
    r103 = next(r for r in records if "Review #103" in r.text)
    assert r101.rating == 2.0 and r103.rating == 1.0
    assert r103.id.startswith("p2-")
    ds = voice.build_dataset(records, cols, voice.VoiceSource(kind="upload", filename="x.pdf"), "x.pdf", warnings,
                             pdf=True)
    by = {t.id: t for t in ds.insights.themes}
    assert by["fit.shoulders_tight"].count == 1  # #102 says "not tight at all" and must not count
    assert by["fabric.pilling"].count == 1


def test_pdf_upload_endpoint(client):
    data = _pdf([["Ticket 1: The zipper broke after a week.", "Ticket 2: The zip is stuck and cheap."]])
    r = client.post("/api/voice/upload", files={"file": ("tickets.pdf", data, "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"]["kind"] == "upload" and body["recordCount"] == 2
    assert any(t["id"] == "construction.zip" and t["count"] == 2 for t in body["themes"])


# --------------------------------------------------------------------------- taxonomy


@pytest.mark.parametrize("text, present, absent", [
    ("Not tight at all in the shoulders.", set(), {"fit.shoulders_tight"}),
    ("The shoulders are not tight.", set(), {"fit.shoulders_tight"}),
    ("Way too tight across the shoulders.", {"fit.shoulders_tight"}, {"fit.runs_small"}),
    ("I have broad shoulders and it fits.", set(), {"fit.shoulders_tight", "fit.shoulders_wide"}),
    ("Runs small, order a size up.", {"fit.runs_small"}, set()),
    ("I did not need to size up.", set(), {"fit.runs_small"}),
    ("No pilling after many washes.", set(), {"fabric.pilling"}),
    ("Pilling is not an issue.", set(), {"fabric.pilling"}),
    ("I was worried it would pill, but it doesn't.", set(), {"fabric.pilling"}),
    ("It started pilling after one wash.", {"fabric.pilling", "care.durability"}, set()),
    ("Not itchy at all.", set(), {"fabric.itchy"}),
    ("It is not warm enough for winter.", {"warmth.not_warm"}, {"warmth.warm"}),
    ("Very warm and cozy.", {"warmth.warm", "comfort.comfortable"}, {"warmth.not_warm"}),
    ("Perfect for warm weather.", set(), {"warmth.warm"}),
    ("Not comfortable for a long day.", {"comfort.uncomfortable"}, {"comfort.comfortable"}),
    ("Not worth the price.", {"value.overpriced"}, {"value.good"}),
    ("The colour is much darker than pictured.", {"colour.vs_photo"}, set()),
    ("The zipper broke within a week.", {"construction.zip"}, set()),
    ("I love the long sleeves.", set(), {"fit.sleeves_long"}),
    ("The sleeves are too long.", {"fit.sleeves_long"}, set()),
    ("Tight at first but it relaxed.", set(), {"fit.runs_small"}),
    ("I can only wear thin tops under it.", set(), {"fabric.thin"}),
])
def test_taxonomy_rules(text, present, absent):
    got = themes_in(text)
    assert present <= got, (text, got)
    assert not (absent & got), (text, got)


def test_negation_flip_keeps_offsets_on_the_text():
    text = "Lovely coat. It is not warm enough though."
    ms = [m for m in find_mentions(text) if m.theme_id == "warmth.not_warm"]
    assert ms and "warm" in text[ms[0].start:ms[0].end]


def test_counts_shares_polarity_and_per_class():
    rows = [
        {"id": "a1", "review": "Tight in the shoulders.", "rating": "2", "class": "Jackets"},
        {"id": "a2", "review": "Tight across the shoulders, can't lift my arms.", "rating": "3", "class": "Jackets"},
        {"id": "a3", "review": "Shoulders are not tight at all. Love it.", "rating": "5", "class": "Jackets"},
        {"id": "a4", "review": "Tight shoulders. Tight shoulders again!", "rating": "2", "class": "Jackets"},
        {"id": "a5", "review": "So soft and comfortable.", "rating": "5", "class": "Knits"},
        {"id": "a6", "review": "Soft. It pills a lot.", "rating": "2", "class": "Knits"},
        {"id": "a7", "review": "", "rating": "4", "class": "Knits"},  # no text: not analysed
        {"id": "a8", "review": "Fine.", "rating": "4", "class": "Knits"},
    ]
    ds = voice.build_dataset(*voice.parse_csv(_csv(rows), "x.csv")[:2], voice.VoiceSource(kind="upload"), "x",
                             [])
    ins = ds.insights
    assert ins.record_count == 8 and ins.analysed_count == 7
    by = {t.id: t for t in ins.themes}
    sh = by["fit.shoulders_tight"]
    assert sh.count == 3  # a1, a2, a4 (a4 counted once); a3 is negated
    assert sh.share == round(100 * 3 / 7, 1)
    assert sh.polarity == "negative" and sh.negative_count == 3
    assert sh.avg_rating == round((2 + 3 + 2) / 3, 2)
    assert [(c.garment_class, c.count, c.total) for c in sh.by_class] == [("Jackets", 3, 4)]
    soft = by["fabric.quality_praised"]
    assert soft.count == 2 and soft.polarity == "positive"
    # the change is scoped to Jackets (all mentions there) and counts against the Jackets base
    chg = next(c for c in ins.recommended_changes if c.theme_id == "fit.shoulders_tight")
    assert (chg.evidence.count, chg.evidence.base, chg.evidence.garment_class) == (3, 4, "Jackets")
    assert "3 of 4 comments for Jackets" in chg.tech_pack_change or "3 of 4 reviews for Jackets" in chg.tech_pack_change
    assert chg.points_of_measure == ["Across shoulder", "Bicep", "Armhole depth"] and "cm" not in chg.action


# --------------------------------------------------------------------------- samples + citation integrity


def test_samples_listed_with_source_and_licence(client):
    r = client.get("/api/voice/samples")
    assert r.status_code == 200
    samples = r.json()
    assert {s["key"] for s in samples} == {"outerwear", "knits", "dresses_pants"}
    for s in samples:
        assert s["records"] == 200
        assert "CC0" in s["source"]["licence"] and s["source"]["url"].startswith("https://")


@pytest.mark.parametrize("key", ["outerwear", "knits", "dresses_pants"])
def test_sample_analysis_citation_integrity(client, key):
    r = client.post("/api/voice/sample", json={"datasetKey": key})
    assert r.status_code == 200, r.text
    ins = r.json()
    ds = voice.get_dataset(ins["id"])
    assert ins["recordCount"] == 200 and ins["themes"] and ins["recommendedChanges"]
    assert ins["source"]["kind"] == "sample" and "CC0" in ins["source"]["licence"]

    def check_quote(q):
        rec = ds.records[q["recordId"]]  # the ref exists
        field = {"text": rec.text, "title": rec.title, "returnReason": rec.return_reason,
                 "fitFeedback": rec.fit_feedback}[q["field"]]
        assert q["text"] in field  # exact excerpt, never paraphrased
        if "matchStart" in q:
            assert 0 <= q["matchStart"] < q["matchEnd"] <= len(q["text"])

    for t in ins["themes"]:
        assert t["count"] == len(set(t["recordIds"])) or t["count"] > 200
        assert all(rid in ds.records for rid in t["recordIds"])
        assert 0 < t["share"] <= 100
        for q in t["quotes"]:
            check_quote(q)
            assert q["recordId"] in t["recordIds"]
    for c in ins["recommendedChanges"]:
        ev = c["evidence"]
        assert ev["count"] >= 3 and ev["count"] <= ev["base"]
        assert all(rid in ds.records for rid in ev["recordIds"])
        for q in ev["quotes"]:
            check_quote(q)
            assert q["recordId"] in ev["recordIds"] and q["recordId"] in c["techPackChange"]
        assert f"{ev['count']} of {ev['base']}" in c["techPackChange"]


def test_sample_counts_are_reproducible(client):
    a = client.post("/api/voice/sample", json={"datasetKey": "outerwear"}).json()
    b = client.post("/api/voice/sample", json={"datasetKey": "outerwear"}).json()
    assert a["id"] != b["id"]
    assert [(t["id"], t["count"]) for t in a["themes"]] == [(t["id"], t["count"]) for t in b["themes"]]


def test_record_endpoint_and_errors(client):
    ins = client.post("/api/voice/sample", json={"datasetKey": "knits"}).json()
    rid = ins["themes"][0]["quotes"][0]["recordId"]
    rec = client.get(f"/api/voice/{ins['id']}/records/{rid}").json()
    assert rec["id"] == rid and ins["themes"][0]["quotes"][0]["text"] in (rec["text"] + (rec.get("title") or ""))
    assert client.get(f"/api/voice/{ins['id']}").json()["id"] == ins["id"]
    assert client.get("/api/voice/voc_nope").status_code == 404
    assert client.post("/api/voice/sample", json={"datasetKey": "nope"}).status_code == 404
    bad = client.post("/api/voice/upload", files={"file": ("x.png", b"\x89PNG....", "image/png")})
    assert bad.status_code == 415
    big = client.post("/api/voice/upload",
                      files={"file": ("x.csv", b"a\n" + b"x" * (voice.MAX_UPLOAD_BYTES + 10), "text/csv")})
    assert big.status_code == 413


# --------------------------------------------------------------------------- apply -> tech pack


def _upload_jacket_reviews(client) -> dict:
    rows = [
        {"Review ID": f"R{i}", "Body": body, "Rating": str(rating), "Product type": "Jackets"}
        for i, (body, rating) in enumerate([
            ("Tight in the shoulders, I can't lift my arms.", 2),
            ("Beautiful, but too tight across the shoulders.", 3),
            ("Shoulders are tight and the zipper broke.", 2),
            ("Snug in the shoulders, sized up.", 3),
            ("Not tight at all, perfect.", 5),
            ("Love it.", 5),
        ], start=1)
    ]
    r = client.post("/api/voice/upload", files={"file": ("reviews.csv", _csv(rows), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


def test_apply_to_design_reaches_techpack_with_citations(client, trend):
    ins = _upload_jacket_reviews(client)
    chg = next(c for c in ins["recommendedChanges"] if c["themeId"] == "fit.shoulders_tight")
    assert chg["evidence"]["count"] == 4 and chg["evidence"]["base"] == 6
    d = client.post("/api/designs/generate", json={"trendId": trend["id"], "count": 1}).json()["designs"][0]

    r = client.post(f"/api/voice/{ins['id']}/apply", json={"changeIds": [chg["id"]], "designId": d["id"]})
    assert r.status_code == 200, r.text
    applied = r.json()
    assert applied["target"] == {"kind": "design", "id": d["id"]}
    assert [a["changeId"] for a in applied["applied"]] == [chg["id"]]

    run_id = client.post(f"/api/designs/{d['id']}/approve", json={}).json()["runId"]
    run = _wait(client, run_id)
    tp = run["techPack"]
    ev = tp["customerEvidence"]
    assert len(ev) == 1 and ev[0]["changeId"] == chg["id"] and ev[0]["count"] == 4
    assert ev[0]["quotes"] and all(q["recordId"] in {"R1", "R2", "R3", "R4"} for q in ev[0]["quotes"])
    # v5: no rule-of-thumb amounts: the change is qualitative + the brain's own instruction from the evidence
    assert "+1.5cm" not in str(tp) and "measurements" not in ev[0] and "bomAdditions" not in ev[0]
    assert ev[0]["instruction"].startswith("Canned instruction") and ev[0]["instructionBy"] == "direct vLLM"
    brief = direction.techpack_brief(store.designs[d["id"]])
    assert any("customer evidence: 4 of 6" in h for h in brief["techPackHints"])
    log = " ".join(run["steps"][0]["log"])
    assert "Customer evidence: 1 change(s)" in log

    # the PDF carries the section too
    pdf = client.get(f"/api/runs/{run_id}/techpack.pdf")
    assert pdf.status_code == 200
    from pypdf import PdfReader

    text = " ".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "CUSTOMER EVIDENCE" in text and "4 of 6" in text


def test_apply_to_trend_is_inherited_and_bom_lines_added(client, trend):
    ins = _upload_jacket_reviews(client)
    zip_chg = next(c for c in ins["recommendedChanges"] if c["themeId"] == "construction.zip") \
        if any(c["themeId"] == "construction.zip" for c in ins["recommendedChanges"]) else None
    shoulder = next(c for c in ins["recommendedChanges"] if c["themeId"] == "fit.shoulders_tight")
    ids = [shoulder["id"]] + ([zip_chg["id"]] if zip_chg else [])
    r = client.post(f"/api/voice/{ins['id']}/apply", json={"changeIds": ids, "trendId": trend["id"]})
    assert r.status_code == 200 and r.json()["target"]["kind"] == "trend"
    d = client.post("/api/designs/generate", json={"trendId": trend["id"], "count": 1}).json()["designs"][0]
    run = _wait(client, client.post(f"/api/designs/{d['id']}/approve", json={}).json()["runId"])
    tp = run["techPack"]
    assert {e["changeId"] for e in tp["customerEvidence"]} == set(ids)
    # re-applying with an empty selection clears it for future approvals
    r = client.post(f"/api/voice/{ins['id']}/apply", json={"changeIds": [], "trendId": trend["id"]})
    assert r.json()["applied"] == []


def test_changes_are_qualitative_without_invented_costs(client):
    rows = [{"Comment": c, "Rating": "2"} for c in
            ["It pills terribly.", "Pilling after one wear.", "Pilled everywhere.", "Awful pilling.", "Fine."]]
    ins = client.post("/api/voice/upload", files={"file": ("r.csv", _csv(rows), "text/csv")}).json()
    chg = next(c for c in ins["recommendedChanges"] if c["themeId"] == "fabric.pilling")
    assert "bomAdditions" not in chg and "measurements" not in chg
    assert not any(ch.isdigit() for ch in chg["action"])  # no rule-of-thumb amounts or grades
    assert chg["evidence"]["count"] == 4  # the deterministic counts stay
    assert "phrasedBy" not in ins and "no brain connected" in ins["phrasingError"].lower()  # no brain here


def test_with_a_brain_each_change_gets_a_drafted_instruction(live):
    rows = [{"Comment": c, "Rating": "2"} for c in
            ["It pills terribly.", "Pilling after one wear.", "Pilled everywhere.", "Awful pilling.", "Fine."]]
    ins = live.post("/api/voice/upload", files={"file": ("r.csv", _csv(rows), "text/csv")}).json()
    assert ins["phrasedBy"] == "direct vLLM" and "phrasingError" not in ins
    chg = next(c for c in ins["recommendedChanges"] if c["themeId"] == "fabric.pilling")
    assert chg["instruction"].startswith("Canned instruction") and chg["instructionBy"] == "direct vLLM"


def test_apply_validation(client, trend):
    ins = _upload_jacket_reviews(client)
    cid = ins["recommendedChanges"][0]["id"]
    assert client.post(f"/api/voice/{ins['id']}/apply", json={"changeIds": [cid]}).status_code == 422
    assert client.post(f"/api/voice/{ins['id']}/apply",
                       json={"changeIds": ["chg_nope"], "trendId": trend["id"]}).status_code == 422
    assert client.post(f"/api/voice/{ins['id']}/apply",
                       json={"changeIds": [cid], "designId": "dsn_nope"}).status_code == 404
    assert client.post("/api/voice/voc_nope/apply", json={"changeIds": [], "trendId": trend["id"]}).status_code == 404


def test_no_voice_means_no_evidence_field(client, trend):
    d = client.post("/api/designs/generate", json={"trendId": trend["id"], "count": 1}).json()["designs"][0]
    run = _wait(client, client.post(f"/api/designs/{d['id']}/approve", json={}).json()["runId"])
    assert "customerEvidence" not in run["techPack"]


def test_themes_have_known_ids(client):
    ins = client.post("/api/voice/sample", json={"datasetKey": "dresses_pants"}).json()
    assert all(t["id"] in THEME_BY_ID for t in ins["themes"])


def test_apply_rejects_contradicting_changes(client, trend):
    rows = [{"Comment": c, "Rating": "3", "Class": "Dresses"} for c in
            ["Runs small.", "Runs small, size up.", "Too small.", "Runs small!", "Runs small sadly.", "Runs small, ugh.", "Runs small again.",
             "Runs large.", "Huge on me.", "Runs large, size down."]]
    ins = client.post("/api/voice/upload", files={"file": ("r.csv", _csv(rows), "text/csv")}).json()
    by = {c["themeId"]: c for c in ins["recommendedChanges"]}
    small, large = by["fit.runs_small"], by["fit.runs_large"]
    assert large["id"] in small["conflictsWith"]
    r = client.post(f"/api/voice/{ins['id']}/apply", json={"changeIds": [small["id"], large["id"]],
                                                             "trendId": trend["id"]})
    assert r.status_code == 422 and "contradicts" in r.json()["detail"]


def test_strong_opposite_sizing_merges_into_size_consistency(client):
    rows = [{"Comment": c, "Rating": "3"} for c in ["Runs small."] * 6 + ["Runs large."] * 5 + ["Lovely."] * 4]
    ins = client.post("/api/voice/upload", files={"file": ("r.csv", _csv(rows), "text/csv")}).json()
    ids = {c["id"] for c in ins["recommendedChanges"]}
    assert "chg_fit_size_consistency" in ids and "chg_fit_runs_small" not in ids
    c = next(c for c in ins["recommendedChanges"] if c["id"] == "chg_fit_size_consistency")
    assert c["evidence"]["count"] == 11 and "6 of 15" in c["evidence"]["summary"]
