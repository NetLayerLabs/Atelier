"""The designer's own sketch as the concept: the vision model reads it, the reading reaches the tech-pack brief."""

import pytest
from fake_upstreams import tiny_png

from app.services import vision
from app.store import store

# A TEST double of the vision model's reading (the live path is app.services.vision.read_sketch).
READING = {"garmentType": "shirt", "garmentName": "TEST Isiagu Shirt",
           "description": "TEST Short-sleeved shirt with a mandarin collar and a concealed placket.",
           "details": ["mandarin collar", "concealed placket"], "colors": ["#000000"],
           "fabricsSuggested": ["cotton"], "model": "TEST-vision"}


@pytest.fixture
def reads_sketch(monkeypatch):
    seen = []

    async def fake(image):
        seen.append(image)
        return dict(READING)

    monkeypatch.setattr(vision, "read_sketch", fake)
    return seen


def test_upload_makes_a_design_from_the_sketch(live, trend, reads_sketch):
    r = live.post("/api/designs/upload", data={"trendId": trend["id"], "note": "Shorter sleeves"},
                  files={"file": ("sketch.png", tiny_png(), "image/png")})
    assert r.status_code == 200, r.text
    (d,) = r.json()["designs"]
    assert d["source"] == "designer_upload" and d["garmentType"] == "shirt"
    assert d["sketchReading"]["garmentName"] == "TEST Isiagu Shirt"
    assert d["imageUrl"].startswith("http://testserver/static/uploads/sketch_") and d["imageUrl"].endswith(".png")
    assert "designer's own sketch" in d["prompt"] and "mandarin collar" in d["prompt"]
    assert "Shorter sleeves" in d["prompt"] and d["vibe"] == "Shorter sleeves"
    assert reads_sketch[0].data == tiny_png() and reads_sketch[0].content_type == "image/png"
    assert store.designs[d["id"]].sketch_reading["model"] == "TEST-vision"
    assert live.get(d["imageUrl"].removeprefix("http://testserver")).content == tiny_png()


def test_upload_rejects_non_images_and_unknown_trends(live, trend, reads_sketch):
    r = live.post("/api/designs/upload", data={"trendId": trend["id"]},
                  files={"file": ("sketch.png", b"%PDF-1.4 not an image", "image/png")})
    assert r.status_code == 415
    r = live.post("/api/designs/upload", data={"trendId": "trd_nope"},
                  files={"file": ("sketch.png", tiny_png(), "image/png")})
    assert r.status_code == 404
    assert not reads_sketch  # the model is never called for a rejected upload


def test_sketch_reading_is_validated_not_invented():
    ok = vision._validate_sketch({"garmentType": "A tailored Jacket", "description": "Single-breasted.",
                                  "details": "notch lapel", "colors": ["#1f2a44", "navy"]})
    assert ok["garmentType"] == "jacket" and ok["details"] == ["notch lapel"] and ok["colors"] == ["#1F2A44"]
    with pytest.raises(ValueError):
        vision._validate_sketch({"garmentType": "hat", "description": ""})


def test_direction_on_a_sketch_needs_no_diffusion(live, trend, reads_sketch, monkeypatch):
    """Creative direction on the designer's own sketch: the brain interprets it and one directed child keeps the
    sketch image (there is nothing to re-render), so the tech pack gets the direction."""
    from app import config

    monkeypatch.setattr(config.get_settings(), "amd_diffusion_endpoint", "")  # no diffusion server
    r = live.post("/api/designs/upload", data={"trendId": trend["id"]},
                  files={"file": ("sketch.png", tiny_png(), "image/png")})
    sketch = r.json()["designs"][0]
    d = live.post(f"/api/designs/{sketch['id']}/direct", json={"instruction": "three-quarter sleeves"})
    assert d.status_code == 200, d.text
    body = d.json()
    assert body["direction"]["instruction"] == "three-quarter sleeves" and body["direction"]["interpretation"]
    (child,) = body["designs"]
    assert child["parentDesignId"] == sketch["id"] and child["imageUrl"] == sketch["imageUrl"]
    assert child["source"] == "designer_upload" and child["sketchReading"] == sketch["sketchReading"]
    assert child["directionId"] == body["direction"]["id"] and "three-quarter sleeves" in child["prompt"]
    # the direction reaches the tech-pack brief
    from app.services import direction as direction_svc
    from app.store import store

    brief = direction_svc.techpack_brief(store.designs[child["id"]])
    assert brief and brief["directions"] == ["three-quarter sleeves"]
