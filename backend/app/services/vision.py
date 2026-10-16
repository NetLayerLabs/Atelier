"""Trend analysis: the live VLM on AMD via vLLM (OpenAI-compatible). v5: no templates, no mock.

`analyze(images)` is the interface: it returns the model's TrendAnalysis or raises errors.ServiceError
(not configured -> VisionNotConnected / unreachable / invalid output after one retry). Nothing is made up when the
model is missing - the preset mood boards are real photos that go through this same live model.
"""

from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass
from typing import Any

from ..config import get_settings, host_of
from ..models import TrendAnalysis
from ..store import new_id
from .colors import normalize_hex
from .errors import NotConfigured, ServiceError
from .openai_compat import chat_json, make_client, resolve_model

log = logging.getLogger("atelier.vision")


@dataclass
class ImageInput:
    """Image bytes for the model. `public_url` is what we store as sourceImageUrls (never sent to the model)."""

    public_url: str
    data: bytes | None = None
    content_type: str = "image/jpeg"

    def as_openai_url(self) -> str:
        """Always a base64 data: URL. A URL is never handed to the model server (it must not fetch anything - QA M6;
        deploy/ starts vLLM with no allowed media domains): routers fetch remote images via safe_fetch first."""
        if self.data is None:
            raise ValueError("image bytes required - fetch remote images with safe_fetch before analysis")
        data, ctype = _fit_for_model(self.data, self.content_type)
        return f"data:{ctype};base64,{base64.b64encode(data).decode()}"


def _fit_for_model(data: bytes, content_type: str) -> tuple[bytes, str]:
    """Downscale to ATELIER_VISION_MAX_EDGE (long edge) and re-encode as JPEG, so a 4-image board stays well under
    hosted gateways' request limits (AMD Token Factory: 5 MB per request). Reading a trend needs no more detail.
    Images already small enough are sent unchanged; anything Pillow can't read is sent as is."""
    edge = get_settings().atelier_vision_max_edge
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(data))
        if max(im.size) <= edge and len(data) <= 600_000:
            return data, content_type
        im = im.convert("RGB")
        im.thumbnail((edge, edge))
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=85, optimize=True)
        return out.getvalue(), "image/jpeg"
    except Exception:  # noqa: BLE001 - never block analysis on a resize problem
        return data, content_type


NOT_CONNECTED = "Vision model not connected - see docs/AMD_SETUP.md"


class VisionNotConnected(NotConfigured):
    """No vision endpoint is configured (AMD_VISION_ENDPOINT). A 503 with service "vision" and a setup hint."""

    def __init__(self, message: str = NOT_CONNECTED):
        super().__init__("vision", message)


def _trend_from_payload(p: dict, source_urls: list[str]) -> TrendAnalysis:
    """Build a TrendAnalysis from a validated payload (the VLM's answer)."""
    return TrendAnalysis(
        id=new_id("trd"),
        trend_name=p["trendName"],
        summary=p["summary"],
        garment_type=p["garmentType"],
        core_silhouettes=list(p["coreSilhouettes"]),
        color_palette=list(p["colorPalette"]),
        key_fabrics=list(p["keyFabrics"]),
        commercial_viability_score=p["commercialViabilityScore"],
        source_image_urls=source_urls,
    )


# --------------------------------------------------------------------------- live

_SYSTEM = (
    "You are a senior fashion trend forecaster. You analyse mood-board / runway / street-style "
    "images and identify the single strongest emerging micro-trend. Respond with ONLY a JSON object, "
    "no prose, no markdown."
)

_SCHEMA_HINT = """Return exactly this JSON shape:
{
  "trendName": "3-5 word trend name",
  "summary": "1-2 sentence editorial description",
  "garmentType": "one of: jacket, coat, dress, skirt, trousers, sweater, shirt, top",
  "coreSilhouettes": ["3-4 short silhouette descriptors"],
  "colorPalette": ["4-5 hex colours like #1F2A44 taken from the images"],
  "keyFabrics": ["2-4 specific fabrics"],
  "commercialViabilityScore": 1-100 integer
}"""


def _validate_trend_payload(data: Any) -> dict:
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    # accept snake_case too
    def g(camel: str, snake: str, default: Any = None) -> Any:
        return data.get(camel, data.get(snake, default))

    palette = [normalize_hex(str(c)) for c in (g("colorPalette", "color_palette") or [])]
    palette = [p for p in palette if p]
    if len(palette) < 2:
        raise ValueError("colorPalette missing or invalid")

    def strlist(v: Any) -> list[str]:
        """Flat list of clean strings: models sometimes nest lists or return them as "['a', 'b']" strings."""
        out: list[str] = []

        def add(x: Any) -> None:
            if isinstance(x, (list, tuple)):
                for y in x:
                    add(y)
                return
            t = str(x).strip()
            if t.startswith("[") and t.endswith("]"):
                for y in t[1:-1].split(","):
                    add(y)
                return
            t = t.strip().strip("'\"").strip()
            if t and t not in out:
                out.append(t)

        add([s for s in v.split(",")] if isinstance(v, str) and not v.strip().startswith("[") else v or [])
        return out

    score_raw = g("commercialViabilityScore", "commercial_viability_score")
    try:  # no default: a missing score is a schema failure (retried once), never a made-up number
        score_f = float(str(score_raw).rstrip("%"))
    except (TypeError, ValueError) as e:
        raise ValueError("commercialViabilityScore missing or not a number") from e
    if 0 < score_f < 1:  # model returned a 0-1 scale
        score_f *= 100
    elif 1 <= score_f <= 10 and "." in str(score_raw):  # e.g. 8.5 on a 0-10 scale
        score_f *= 10
    score = int(round(score_f))
    out = {
        "trendName": str(g("trendName", "trend_name") or "").strip(),
        "summary": str(g("summary", "summary") or "").strip(),
        "garmentType": str(g("garmentType", "garment_type") or "").strip().lower(),
        "coreSilhouettes": strlist(g("coreSilhouettes", "core_silhouettes")),
        "colorPalette": palette[:6],
        "keyFabrics": strlist(g("keyFabrics", "key_fabrics")),
        "commercialViabilityScore": max(1, min(100, score)),
    }
    if not out["trendName"] or not out["garmentType"]:
        raise ValueError("trendName/garmentType missing")
    if not out["keyFabrics"]:
        raise ValueError("keyFabrics missing")
    if not out["summary"]:
        out["summary"] = f"{out['trendName']} - identified from the submitted mood board."
    if not out["coreSilhouettes"]:
        out["coreSilhouettes"] = [out["garmentType"]]
    return out


def images_for_prompt(images: list[ImageInput]) -> list[ImageInput]:
    """The images that go into the one vision prompt: at most ATELIER_VISION_MAX_IMAGES (default 4, the vLLM
    server's --limit-mm-per-prompt image budget). Mood boards have 3-4 photos; an upload of 5-6 is analysed from
    its first N, and AnalyzedBy.imagesAnalyzed / imagesSubmitted say so in the UI."""
    cap = max(1, get_settings().atelier_vision_max_images)
    if len(images) > cap:
        log.info("vision: %d images submitted, the model reads the first %d (max per prompt)", len(images), cap)
    return images[:cap]


def vision_messages(images: list[ImageInput], attempt: int) -> list[dict]:
    """OpenAI chat format with `image_url` parts (data: URLs for bytes), images BEFORE the text - the order the
    Gemma 4 model card recommends."""
    text = _SCHEMA_HINT if attempt == 0 else (
        _SCHEMA_HINT + "\nYour previous answer was not valid JSON. Output the JSON object only.")
    content: list[dict] = [{"type": "image_url", "image_url": {"url": i.as_openai_url()}} for i in images]
    content.append({"type": "text", "text": text})
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": content}]


async def live_analyze(images: list[ImageInput]) -> TrendAnalysis:
    s = get_settings()
    client = make_client(s.amd_vision_endpoint, s.amd_vllm_api_key, s.atelier_vision_timeout)
    model = await resolve_model(client, s.amd_vision_model)
    sent = images_for_prompt(images)

    # The retry sends the same images (a smaller set would change what the analysis is based on).
    payload = await chat_json(client, model, lambda attempt: vision_messages(sent, attempt), _validate_trend_payload,
                              max_tokens=700, service="vision", purpose="trend_analysis", images=len(sent))
    return _trend_from_payload(payload, [i.public_url for i in images])


async def analyze(images: list[ImageInput]) -> TrendAnalysis:
    """The live VLM's trend analysis. Raises errors.ServiceError (service "vision") - never a made-up trend."""
    s = get_settings()
    if not s.vision_live:
        raise VisionNotConnected()
    try:
        return await live_analyze(images)
    except ServiceError:
        raise
    except Exception as e:  # noqa: BLE001
        log.warning("vision analysis failed at %s: %s: %s", host_of(s.amd_vision_endpoint), e.__class__.__name__, e)
        raise ServiceError("vision", f"Vision model call failed at {host_of(s.amd_vision_endpoint)}: "
                                     f"{e.__class__.__name__}: {str(e)[:160]}") from e


async def analyze_images(images: list[ImageInput]) -> TrendAnalysis:
    """The trends router's entry point (tests swap it for a canned double). Raises like `analyze`."""
    return await analyze(images)
