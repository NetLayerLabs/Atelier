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
