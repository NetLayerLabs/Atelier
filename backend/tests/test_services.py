"""Unit tests for parsing / fallback logic that the live paths rely on."""

import asyncio

import pytest

from app.services import evolus, vision
from app.services.openai_compat import extract_json, normalize_base_url
from app.services.colors import garment_kind


def test_extract_json_variants():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here it is: {"a": [1, 2,],} thanks') == {"a": [1, 2]}
    assert extract_json("[1, 2]") == [1, 2]
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_normalize_base_url():
    assert normalize_base_url("http://h:8000") == "http://h:8000/v1"
    assert normalize_base_url("http://h:8000/v1/") == "http://h:8000/v1"
    assert normalize_base_url("http://h:8000/v1/chat/completions") == "http://h:8000/v1"


def test_vision_payload_validation():
    out = vision._validate_trend_payload({
        "trend_name": "Test", "garmentType": "Dress", "colorPalette": ["1f2a44", "#abc", "zzz"],
        "keyFabrics": "silk, satin", "commercialViabilityScore": 0.8,
    })
    assert out["colorPalette"] == ["#1F2A44", "#AABBCC"]
    assert out["keyFabrics"] == ["silk", "satin"]
    assert out["commercialViabilityScore"] == 80
    assert out["garmentType"] == "dress"


def test_vision_never_falls_back(s, monkeypatch):
    from app.services.errors import ServiceError

    with pytest.raises(ServiceError) as e:  # not configured
        asyncio.run(vision.analyze([vision.ImageInput(public_url="http://x/y.jpg")]))
    assert e.value.not_configured and e.value.service == "vision"
    monkeypatch.setattr(s, "amd_vision_endpoint", "http://127.0.0.1:9/v1")  # nothing listens here
    monkeypatch.setattr(s, "atelier_vision_timeout", 1.0)
    with pytest.raises(ServiceError) as e:
        asyncio.run(vision.analyze([vision.ImageInput(public_url="http://x/y.jpg")]))
    assert e.value.status == "unreachable" and not hasattr(vision, "mock_analyze")
    with pytest.raises(ValueError):  # a missing score is a schema failure, never a default
        vision._validate_trend_payload({"trendName": "T", "garmentType": "dress", "colorPalette": ["#111111", "#222222"],
                                        "keyFabrics": ["silk"]})


def test_ecb_rates_parse_and_cross():
    from app.services import fx

    r = fx.parse_ecb("<Cube time='2026-10-12'><Cube currency='USD' rate='1.1181'/>"
                     "<Cube currency='GBP' rate='0.84478'/></Cube>")
    assert r.date == "2026-10-12" and r.per_eur == {"USD": 1.1181, "GBP": 0.84478, "EUR": 1.0}
    fx._cache = r
    import time as _t

    r.fetched = _t.time()
    rate, date = asyncio.run(fx.rate("GBP", "USD"))
    assert rate == pytest.approx(1.1181 / 0.84478) and date == "2026-10-12"
    assert asyncio.run(fx.rate("XYZ", "USD")) is None
    fx.clear_cache()


def test_evolus_lenient_parsing():
    resp = {"execution": {"id": "exe_1", "output": {"product": {"admin_graphql_api_id": "gid://shopify/Product/9",
                                                               "onlineStoreUrl": "https://s.myshopify.com/products/the-coat"}}}}
    p = evolus.parse_shopify(resp)
    assert p["productId"] == "gid://shopify/Product/9"
    assert p["handle"] == "the-coat"
    assert evolus.outreach_status({"status": "completed"}) == "queued"
    assert evolus.outreach_status({"result": {"status": "sent"}}) == "sent"


def test_garment_kind_mapping():
    assert garment_kind("Trench Coat") == "coat"
    assert garment_kind("slip dress") == "dress"
    assert garment_kind("cargo pants") == "trousers"
    assert garment_kind("cashmere sweater") == "top"
    assert garment_kind("denim jacket") == "jacket"


def test_no_concept_renderer_ships():
    import importlib.util

    assert importlib.util.find_spec("app.services.svg_render") is None  # v5: images only from the diffusion model


def test_evolus_prefers_product_id_over_execution_id():
    resp = {"execution": {"id": "exe_2", "output": {"product": {"id": "gid://shopify/Product/777",
                                                               "onlineStoreUrl": "https://shop.test/products/live-coat"}}}}
    p = evolus.parse_shopify(resp)
    assert p["productId"] == "gid://shopify/Product/777" and p["handle"] == "live-coat"


def test_vision_images_are_downscaled_for_the_model():
    """Hosted gateways cap the request size (AMD Token Factory: 5 MB), so large photos are resized before sending."""
    import base64
    import io

    from PIL import Image

    from app.services.vision import ImageInput

    big = io.BytesIO()
    Image.effect_noise((3000, 4000), 80).convert("RGB").save(big, format="PNG")
    url = ImageInput(public_url="x", data=big.getvalue(), content_type="image/png").as_openai_url()
    assert url.startswith("data:image/jpeg;base64,")
    sent = base64.b64decode(url.split(",", 1)[1])
    assert len(sent) < 1_000_000 and max(Image.open(io.BytesIO(sent)).size) == 1280

    small = io.BytesIO()
    Image.new("RGB", (400, 300), "navy").save(small, format="PNG")
    assert ImageInput(public_url="x", data=small.getvalue(), content_type="image/png").as_openai_url().startswith(
        "data:image/png;base64,")


def test_trend_lists_are_flattened_and_cleaned():
    """A model that nests lists or quotes them ("['silk brocade']") must still yield clean fabric names."""
    from app.services import vision

    raw = {"trendName": "T", "summary": "S", "garmentType": "top", "coreSilhouettes": ["tunic", ["kaftan"]],
           "colorPalette": ["#000000", "#B8860B"], "keyFabrics": ["jacquard", "['silk brocade']", "[\"velvet\"]"],
           "commercialViabilityScore": 65}
    parsed = vision._validate_trend_payload(raw)
    assert parsed["keyFabrics"] == ["jacquard", "silk brocade", "velvet"]
    assert parsed["coreSilhouettes"] == ["tunic", "kaftan"]
