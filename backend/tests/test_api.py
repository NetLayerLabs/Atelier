"""Core API (v5): every model call goes to a real service - here the in-process test doubles - or fails honestly."""

import re

import pytest

from fake_upstreams import tiny_png
from helpers import answer_all_rfqs, approve, wait

from app.services.colors import garment_kind

TREND_KEYS = {"id", "trendName", "summary", "garmentType", "coreSilhouettes", "colorPalette", "keyFabrics",
              "commercialViabilityScore", "sourceImageUrls", "createdAt"}
TREND_V5_KEYS = {"analyzedBy", "sourceImages"}  # v5, additive
DESIGN_KEYS = {"id", "trendId", "imageUrl", "prompt", "garmentType", "seed", "createdAt"}
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _path(url: str) -> str:
    return url.replace("http://testserver", "")


def _no_snake_keys(obj) -> None:
    """Every key in a JSON response must be camelCase (measurement names are free-form data)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert "_" not in k or k in ("measurements",), f"snake_case key leaked: {k}"
            if k != "measurements":
                _no_snake_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            _no_snake_keys(v)


# --------------------------------------------------------------------------- nothing configured


def test_health_without_configuration_is_honest(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and "mode" not in body
    assert body["poweredBy"] == {"amd": False, "evolus": False, "modelConnected": False} and body["fakeUpstreams"] is False
    names = {s["name"] for s in body["services"]}
    assert {"vision", "diffusion", "llm", "evolus_agent", "evolus_extractor", "evolus_outreach", "evolus_po",
            "evolus_shopify", "shopify"} <= names
    for svc in body["services"]:
        assert svc["status"] == "not_configured" and svc["healthy"] is False and svc["hint"]
        assert "mock" not in svc["detail"].lower() and "simulat" not in svc["detail"].lower()


def test_presets(client):
    r = client.get("/api/trends/presets")
    assert r.status_code == 200
    presets = r.json()
    assert 4 <= len(presets) <= 10
    for p in presets:
        ai = p.get("aiGenerated", False)  # the pilot brand's own AI-generated board, flagged and credited as such
        assert set(p) == {"id", "name", "thumbnailUrl", "credit", "images"} | ({"aiGenerated"} if ai else set())
        assert 3 <= len(p["images"]) <= 4
        assert p["thumbnailUrl"] == p["images"][0]["url"]
        assert p["credit"].startswith("AI-generated inspiration · " if ai else "Photos: ")
        for im in p["images"]:
            assert {"url", "title", "creator", "sourceUrl", "license", "licenseUrl", "modifications"} <= set(im)
            assert im["url"].startswith(f"http://testserver/static/moodboards/{p['id']}/")
            if ai:
                assert im["aiGenerated"] and "AI-generated" in im["license"]
            else:
                assert im["sourceUrl"].startswith("https://") and im["licenseUrl"].startswith("https://")
        img = client.get(_path(p["thumbnailUrl"]))
        assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
        assert img.content[:2] == b"\xff\xd8"  # a real JPEG, not a generated SVG


@pytest.mark.real_vision
def test_without_vision_analyze_fails_with_a_hint(client):
    r = client.post("/api/trends/analyze", files=[("images", ("a.png", b"\x89PNG bytes", "image/png"))])
    assert r.status_code == 503
    body = r.json()
    assert body["service"] == "vision" and body["status"] == "not_configured"
    assert "AMD_VISION_ENDPOINT" in body["hint"] and "not connected" in body["detail"].lower()
    r = client.post("/api/trends/analyze", json={"imageUrls": ["https://example.com/a.jpg"]})
    assert r.status_code == 503 and r.json()["service"] == "vision"


def test_without_diffusion_no_concepts_are_made_up(client):
    from app.models import TrendAnalysis
    from app.store import store

    store.trends["trd_x"] = TrendAnalysis(id="trd_x", trend_name="T", summary="s", garment_type="jacket",
                                          core_silhouettes=["boxy"], color_palette=["#111111", "#EEEEEE"],
                                          key_fabrics=["denim"], commercial_viability_score=50)
    r = client.post("/api/designs/generate", json={"trendId": "trd_x"})
    assert r.status_code == 503 and r.json()["service"] == "diffusion" and "AMD_DIFFUSION_ENDPOINT" in r.json()["hint"]
    assert store.designs == {}


def test_telemetry_starts_empty(client):
    t = client.get("/api/telemetry").json()
    assert t["calls"] == [] and t["services"] == [] and "mode" not in t


# --------------------------------------------------------------------------- with the test doubles


def test_health_flags_fake_upstreams_and_never_credits_them(live):
    body = live.get("/api/health").json()
    by = {s["name"]: s for s in body["services"]}
    for name in ("vision", "diffusion", "llm", "evolus_outreach", "evolus_po", "shopify"):
        assert by[name]["status"] == "connected", by[name]
        assert by[name]["fake"] is True and by[name]["detail"].startswith("FAKE UPSTREAM - not real")
    assert body["fakeUpstreams"] is True
    assert body["poweredBy"] == {"amd": False, "evolus": False, "modelConnected": False}  # credits never show for fakes
    assert by["vision"]["model"] == "fake/vlm-model" and by["llm"]["gpu"] == "FAKE-GPU-LABEL"


def test_analyze_upload_with_the_vlm(live, trend):
    assert set(trend) == TREND_KEYS | {"analyzedBy"} and trend["id"].startswith("trd_")
    assert trend["trendName"] == "Fake Indigo Utility"  # the (fake) model's answer, nothing invented
    assert all(HEX.match(c) for c in trend["colorPalette"])
    assert live.get(_path(trend["sourceImageUrls"][0])).status_code == 200
    calls = live.get("/api/telemetry?service=vision").json()["calls"]
    assert calls and calls[0]["purpose"] == "trend_analysis" and calls[0]["fake"] is True


def test_analyze_upload_limits(live):
    files = [("images", (f"{i}.png", b"x", "image/png")) for i in range(7)]
    assert live.post("/api/trends/analyze", files=files).status_code == 422
    r = live.post("/api/trends/analyze", files=[("images", ("a.txt", b"hello", "text/plain"))])
    assert r.status_code == 415 and isinstance(r.json()["detail"], str)
    assert live.post("/api/trends/analyze", json={}).status_code == 422


def test_vlm_failure_is_an_error_not_a_template(client, s, monkeypatch):
    from conftest import go_live, route
    from fake_upstreams import create_openai_app

    go_live(monkeypatch, s)
    route()
    monkeypatch.setattr(s, "amd_vision_endpoint", "http://nowhere.fake:9/v1")
    r = client.post("/api/trends/analyze", files=[("images", ("a.png", tiny_png(), "image/png"))])
    assert r.status_code == 503 and r.json()["status"] == "unreachable" and r.json()["service"] == "vision"
    del create_openai_app


def test_generate_designs_from_diffusion(live, trend):
    r = live.post("/api/designs/generate", json={"trendId": trend["id"]})
    assert r.status_code == 200, r.text
    designs = r.json()["designs"]
    assert len(designs) == 4 and len({d["seed"] for d in designs}) == 4
    for d in designs:
        assert DESIGN_KEYS <= set(d) and d["garmentType"] == trend["garmentType"]
        assert garment_kind(d["garmentType"]) == "jacket"
        assert f"a {trend['garmentType']} featuring" in d["prompt"]
        assert d["imageUrl"].endswith(".png")
    img = live.get(_path(designs[0]["imageUrl"]))
    assert img.status_code == 200 and img.content.startswith(b"\x89PNG")


def test_generate_with_vibe_refine_and_errors(live, trend):
    r = live.post("/api/designs/generate", json={"trendId": trend["id"], "vibe": "make it avant-garde", "count": 2})
    designs = r.json()["designs"]
    assert len(designs) == 2 and all("avant-garde" in d["prompt"] for d in designs)
    kids = live.post(f"/api/designs/{designs[0]['id']}/refine", json={"vibe": "darker"}).json()["designs"]
    assert len(kids) == 4 and all(k["parentDesignId"] == designs[0]["id"] for k in kids)
    assert live.post("/api/designs/generate", json={"trendId": "trd_missing"}).status_code == 404
    assert live.post("/api/designs/generate", json={}).status_code == 422
    assert live.post("/api/designs/dsn_missing/refine", json={"vibe": "x"}).status_code == 404
    assert live.post(f"/api/designs/{designs[0]['id']}/refine", json={"vibe": "   "}).status_code == 422


def test_diffusion_failure_returns_503(client, s, monkeypatch):
    from conftest import go_live, route

    go_live(monkeypatch, s)
    route()
    trend = client.post("/api/trends/analyze", files=[("images", ("a.png", tiny_png(), "image/png"))]).json()
    monkeypatch.setattr(s, "amd_diffusion_endpoint", "http://nowhere.fake:9/generate")
    r = client.post("/api/designs/generate", json={"trendId": trend["id"], "count": 2})
    assert r.status_code == 503 and r.json()["service"] == "diffusion" and r.json()["status"] == "unreachable"


def test_full_run_with_real_quote_documents(live, trend):
    run_id = approve(live, trend, qty=300)
    first = live.get(f"/api/runs/{run_id}").json()
    assert [s["key"] for s in first["steps"]] == ["techpack", "supplier_outreach", "supplier_quotes",
                                                "shopify_preorder", "preorder_demand"]
    run = answer_all_rfqs(live, run_id)
    run = wait(live, run_id, lambda r: (r.get("demand") or {}).get("status") == "collecting")
    _no_snake_keys(run)
    steps = {s["key"]: s for s in run["steps"]}
    assert all("mode" not in s for s in run["steps"])
    assert steps["techpack"]["route"] == "direct vLLM"
    tp = run["techPack"]
    assert tp["garmentName"] == "Fake Test Jacket" and tp["generatedBy"] == "direct vLLM"
    assert tp["constructionNotes"] == ["Canned construction note from the fake model."]
    assert run["styleNumber"] == "ST-00001"
    assert all(e["status"] == "sent" for e in run["supplierEmails"])
    q = run["quotes"][0]
    assert q["unitPrice"] == 101.5 and q["moq"] == 250 and q["leadTimeWeeks"] == 8
    assert q["source"]["engine"] == "amd-llm" and q["source"]["channel"] == "upload"
    assert run["recommendation"]["rationale"].startswith("Canned rationale")
    assert run["shopifyProduct"]["source"] == "shopify" and "simulated" not in run["shopifyProduct"]
    assert run["demand"]["source"] == "shopify" and "visitors" not in run["demand"]


def test_run_without_a_brain_stops_honestly_and_retries(live, trend, s, monkeypatch):
    monkeypatch.setattr(s, "amd_vllm_endpoint", "")
    run_id = approve(live, trend)
    run = wait(live, run_id)
    assert run["status"] == "failed"
    tp = run["steps"][0]
    assert tp["status"] == "error" and tp["service"] == "brain" and tp["retryable"] is True
    assert "No brain connected" in tp["error"] and "AMD_VLLM_ENDPOINT" in tp["hint"]
    assert "techPack" not in run and all(st["status"] == "pending" for st in run["steps"][1:])
    assert live.post(f"/api/runs/{run_id}/retry").status_code == 200  # still not connected -> fails again
    run = wait(live, run_id)
    assert run["status"] == "failed" and run["steps"][0]["status"] == "error"
    monkeypatch.setattr(s, "amd_vllm_endpoint", "http://vllm.fake:8000/v1")  # connect it, retry resumes
    assert live.post(f"/api/runs/{run_id}/retry").status_code == 200
    run = wait(live, run_id, lambda r: (r.get("quoteRound") or {}).get("status") == "awaiting")
    assert run["techPack"]["garmentName"] == "Fake Test Jacket"
    assert live.post(f"/api/runs/{run_id}/retry").status_code == 409  # not failed


def test_outreach_without_evolus_keeps_drafts_and_says_not_sent(live, trend, s, monkeypatch):
    monkeypatch.setattr(s, "evolus_outreach_workflow_id", "")
    run = wait(live, approve(live, trend))
    st = run["steps"][1]
    assert run["status"] == "failed" and st["status"] == "error" and st["service"] == "evolus_outreach"
    assert "not sent" in st["error"] and all(e["status"] == "drafted" for e in run["supplierEmails"])
    monkeypatch.setattr(s, "evolus_outreach_workflow_id", "wf_out")
    live.post(f"/api/runs/{run['id']}/retry")
    run = wait(live, run["id"], lambda r: (r.get("quoteRound") or {}).get("status") == "awaiting")
    assert any("Re-using the" in line for line in run["steps"][1]["log"])
    assert all(e["status"] == "sent" for e in run["supplierEmails"])


def test_404s(client):
    for method, path in [("get", "/api/trends/trd_nope"), ("get", "/api/runs/run_nope"),
                         ("post", "/api/designs/dsn_nope/approve"), ("post", "/api/runs/run_nope/retry")]:
        r = getattr(client, method)(path)
        assert r.status_code == 404 and isinstance(r.json()["detail"], str)


def test_camel_case_everywhere(live, trend):
    _no_snake_keys(live.get("/api/health").json())
    _no_snake_keys(trend)
    _no_snake_keys(live.post("/api/designs/generate", json={"trendId": trend["id"], "count": 1}).json())


def test_cors_preflight(client):
    r = client.options("/api/health", headers={"Origin": "http://localhost:3000",
                                                 "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
