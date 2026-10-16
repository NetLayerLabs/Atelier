"""v5: real mood boards - openly licensed photos, analysed live by the vision model every time."""

import json

import pytest

from app.data import presets
from app.data.presets import MANIFEST_PATH, MOODBOARDS_DIR, ManifestError, load_manifest
from app.services import http, openai_compat, telemetry
from fake_upstreams import RoutingTransport, create_diffusion_app, create_openai_app

ALLOWED_LICENSES = {"CC0 1.0 (Met Open Access)", "CC BY 2.0", "CC BY 3.0", "CC BY 4.0",
                    "CC BY-SA 2.0", "CC BY-SA 3.0", "CC BY-SA 4.0"}


# --------------------------------------------------------------------------- manifest


def test_manifest_every_image_exists_and_is_attributed():
    boards = load_manifest()
    assert 4 <= len(boards) <= 10
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    attribution = (MOODBOARDS_DIR / "ATTRIBUTION.md").read_text(encoding="utf-8")
    total = 0
    for b, rb in zip(boards, raw["boards"]):
        assert 3 <= len(b.images) <= 4, b.id
        assert set(rb) <= {"id", "title", "images", "aiGenerated"}, "a board is images + a title; no pre-written analysis"
        if b.ai_generated:  # the pilot brand's own AI-generated inspiration: labelled, never passed off as photos
            assert all(im.ai_generated for im in b.images)
            assert b.credit.startswith("AI-generated inspiration · ")
            for im in b.images:
                assert im.path.is_file() and im.path.read_bytes()[:2] == b"\xff\xd8"
                assert "AI-generated" in im.creator and "AI-generated" in im.license
                assert b.id in attribution
                total += im.path.stat().st_size
            continue
        assert b.title and b.credit.startswith("Photos: ")
        for im in b.images:
            assert im.path.is_file() and im.path.read_bytes()[:2] == b"\xff\xd8"
            assert im.source_url.startswith("https://") and im.license_url.startswith("https://")
            assert im.license in ALLOWED_LICENSES and "NC" not in im.license
            assert im.creator and im.title and "Downscaled" in im.modifications
            assert f"`{im.file}`" in attribution and im.source_url in attribution
            total += im.path.stat().st_size
    assert total < 10 * 1024 * 1024


def test_manifest_loader_rejects_unattributed_or_missing_images(tmp_path):
    img = tmp_path / "b" / "01.jpg"
    img.parent.mkdir()
    img.write_bytes(b"\xff\xd8 not really")
    good = {"file": "b/01.jpg", "title": "t", "creator": "c", "sourceUrl": "https://x", "license": "CC BY 2.0",
            "licenseUrl": "https://y", "modifications": "Downscaled"}
    m = tmp_path / "manifest.json"
    m.write_text(json.dumps({"boards": [{"id": "b", "title": "B", "images": [good]}]}))
    assert load_manifest(m)[0].images[0].creator == "c"
    m.write_text(json.dumps({"boards": [{"id": "b", "title": "B", "images": [{**good, "license": ""}]}]}))
    with pytest.raises(ManifestError, match="license"):
        load_manifest(m)
    m.write_text(json.dumps({"boards": [{"id": "b", "title": "B", "images": [{**good, "file": "b/02.jpg"}]}]}))
    with pytest.raises(ManifestError, match="not found"):
        load_manifest(m)
    # an AI-generated image needs no source page, but must still say who made it and under what terms
    ai = {k: v for k, v in good.items() if k not in ("sourceUrl", "licenseUrl")} | {"aiGenerated": True}
    m.write_text(json.dumps({"boards": [{"id": "b", "title": "B", "images": [ai]}]}))
    (board,) = load_manifest(m)
    assert board.ai_generated and board.credit == "AI-generated inspiration · c"
    m.write_text(json.dumps({"boards": [{"id": "b", "title": "B", "images": [{**ai, "creator": ""}]}]}))
    with pytest.raises(ManifestError, match="creator"):
        load_manifest(m)


# --------------------------------------------------------------------------- analyze a board


def test_analyze_preset_sends_the_real_photos_to_the_vision_service(client, fake_vision, monkeypatch):
    from app.services import vision

    seen = []
    inner = vision.analyze_images  # the conftest double

    async def spy(images):
        seen.append(images)
        return await inner(images)

    monkeypatch.setattr(vision, "analyze_images", spy)
    board = presets.find_board("lacoste-fw2010")
    r = client.post("/api/trends/analyze", json={"preset": board.id})
    assert r.status_code == 200, r.text
    t = r.json()
    (images,) = seen
    assert [i.data for i in images] == [im.path.read_bytes() for im in board.images]  # the actual files
    assert all(i.content_type == "image/jpeg" for i in images)
    assert t["sourceImageUrls"] == [f"http://testserver{im.static_path}" for im in board.images]
    assert [s["sourceUrl"] for s in t["sourceImages"]] == [im.source_url for im in board.images]
    assert all(s["license"] and s["creator"] and s["licenseUrl"] for s in t["sourceImages"])
    assert t["analyzedBy"]["model"] == fake_vision.FAKE_MODEL
    assert t["analyzedBy"]["endpointHost"] == fake_vision.FAKE_HOST
    # every analysis is a new model call: no cached / curated answer
    r2 = client.post("/api/trends/analyze", json={"preset": board.id})
    assert r2.json()["id"] != t["id"] and len(seen) == 2


def test_unknown_board_is_404(client):
    r = client.post("/api/trends/analyze", json={"preset": "oversized-asymmetric-denim"})
    assert r.status_code == 404 and "unknown mood board" in r.json()["detail"]


@pytest.mark.real_vision
@pytest.mark.parametrize("kind", ["preset", "upload", "urls"])
def test_not_connected_is_an_honest_503(client, kind):
    if kind == "preset":
        r = client.post("/api/trends/analyze", json={"preset": "max-azria-fw2010"})
    elif kind == "upload":
        r = client.post("/api/trends/analyze", files=[("images", ("a.jpg", b"\xff\xd8x", "image/jpeg"))])
    else:
        r = client.post("/api/trends/analyze", json={"imageUrls": ["https://example.com/a.jpg"]})
    assert r.status_code == 503
    body = r.json()
    assert body["detail"] == "Vision model not connected - see docs/AMD_SETUP.md"
    assert body["service"] == "vision" and body["status"] == "not_configured" and "AMD_VISION_ENDPOINT" in body["hint"]


# --------------------------------------------------------------------------- the real vision path (fake upstream)

VLM = "vlm.fake:8001"


@pytest.fixture
def live_vlm(monkeypatch):
    from app import config

    s = config.get_settings()
    for k, v in {"amd_vision_endpoint": f"http://{VLM}/v1", "amd_vllm_api_key": "k1",
                 "amd_vision_model": "", "atelier_vision_timeout": 5.0}.items():
        monkeypatch.setattr(s, k, v)
    openai_compat._model_cache.clear()
    telemetry.clear()
    yield
    http.set_transport(None)
    openai_compat._model_cache.clear()
    telemetry.clear()


@pytest.mark.real_vision
def test_board_goes_through_the_real_vision_service(client, live_vlm):
    http.set_transport(RoutingTransport({VLM: create_openai_app(api_key="k1", model="Qwen/Qwen3-VL-8B-Instruct")}))
    r = client.post("/api/trends/analyze", json={"preset": "michael-kors-fw2010"})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["trendName"] == "Fake Indigo Utility"  # whatever the model said, nothing curated
    assert t["analyzedBy"]["model"] == "Qwen/Qwen3-VL-8B-Instruct"
    assert t["analyzedBy"]["endpointHost"] == VLM
    calls = [c for c in telemetry.snapshot().calls if c.service == "vision"]
    assert calls and calls[-1].ok and calls[-1].images == 4


@pytest.mark.real_vision
def test_vision_failure_is_an_honest_503_not_a_made_up_trend(client, live_vlm):
    http.set_transport(RoutingTransport({VLM: create_diffusion_app()}))  # wrong server: no chat completions
    r = client.post("/api/trends/analyze", json={"preset": "michael-kors-fw2010"})
    assert r.status_code == 503 and r.json()["detail"].startswith("Vision model call failed")
    assert r.json()["service"] == "vision" and r.json()["status"] == "unreachable"
