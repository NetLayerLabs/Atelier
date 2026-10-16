"""TEST DOUBLE ONLY - canned vision-model answers so the rest of the suite can run without a GPU.

The app itself has no templates: analysing a mood board always calls the live vision model. Tests that don't care
about vision (designs, tech packs, quotes, Shopify…) still need a TrendAnalysis to start from, so conftest swaps
`vision.analyze_images` for `fake_analyze_images` below unless a test is marked `real_vision`. The answers are keyed
by the real board ids so a test can pick a garment type deterministically.
"""

from __future__ import annotations

import hashlib

from app.models import InferenceCall, TrendAnalysis
from app.services import telemetry
from app.store import new_id

FAKE_MODEL = "test-double/vision"
FAKE_HOST = "vision.test-double"

CANNED: dict[str, dict] = {
    "michael-kors-fw2010": {
        "trendName": "Oversized Asymmetric Denim", "summary": "Canned test answer: deconstructed denim workwear.",
        "garmentType": "jacket",
        "coreSilhouettes": ["dropped-shoulder boxy trucker", "asymmetric stepped hem"],
        "colorPalette": ["#1F2A44", "#3B5B85", "#A9B8C9", "#E8E1D3", "#C8873A"],
        "keyFabrics": ["14oz selvedge denim", "raw indigo twill", "organic cotton chambray"],
        "commercialViabilityScore": 87},
    "max-azria-fw2010": {
        "trendName": "Quiet Luxury Knitwear", "summary": "Canned test answer: logo-less tactile knits.",
        "garmentType": "sweater",
        "coreSilhouettes": ["relaxed crew-neck pullover", "elongated ribbed cuffs"],
        "colorPalette": ["#D8CBB5", "#B49B7E", "#7A6A58", "#F3EEE6", "#3E3A36"],
        "keyFabrics": ["Grade-A Mongolian cashmere", "extra-fine merino wool", "baby alpaca blend"],
        "commercialViabilityScore": 91},
    "lacoste-fw2010": {
        "trendName": "Neo-Gothic Tailoring", "summary": "Canned test answer: severe sculpted tailoring.",
        "garmentType": "coat",
        "coreSilhouettes": ["sharp-shouldered longline coat", "peak lapels"],
        "colorPalette": ["#16131A", "#3A1C2E", "#6B2737", "#8C8C91", "#D9D4CF"],
        "keyFabrics": ["wool barathea", "silk-faced satin lapels", "jacquard brocade lining"],
        "commercialViabilityScore": 78},
    "jill-stuart-fw2010": {
        "trendName": "Solarpunk Utility", "summary": "Canned test answer: repairable utility wear.",
        "garmentType": "trousers",
        "coreSilhouettes": ["wide-leg cargo trouser", "articulated knee darts"],
        "colorPalette": ["#4F6D3A", "#A3B86C", "#E9C46A", "#F4EBD0", "#2A3B2E"],
        "keyFabrics": ["recycled nylon ripstop", "organic cotton canvas", "hemp-blend twill"],
        "commercialViabilityScore": 84},
    "met-19c-outerwear": {
        "trendName": "Liquid Satin Minimalism", "summary": "Canned test answer: bias-cut slips.",
        "garmentType": "dress",
        "coreSilhouettes": ["bias-cut slip dress", "soft cowl neckline"],
        "colorPalette": ["#C9A27E", "#8E5B4A", "#EADBC8", "#2B2523", "#B7B1A9"],
        "keyFabrics": ["heavy silk charmeuse", "sand-washed satin", "recycled cupro lining"],
        "commercialViabilityScore": 82},
}
_ORDER = list(CANNED)

calls: list[list[str]] = []  # the public URLs of every image batch the double was asked to analyse


def _answer_for(urls: list[str], digest: str) -> dict:
    for board in _ORDER:
        if any(f"/moodboards/{board}/" in u for u in urls):
            return CANNED[board]
    return CANNED[_ORDER[int(digest, 16) % len(_ORDER)]]


async def fake_analyze_images(images) -> TrendAnalysis:
    urls = [i.public_url for i in images]
    calls.append(urls)
    h = hashlib.sha256()
    for i in images:
        h.update(i.data if i.data is not None else i.public_url.encode())
    a = _answer_for(urls, h.hexdigest())
    telemetry.record(InferenceCall(id=telemetry.new_call_id(), service="vision", purpose="trend_analysis",
                                   mode="live", simulated=False, model=FAKE_MODEL, endpoint_host=FAKE_HOST,
                                   images=min(len(images), 4), latency_ms=1.0))
    return TrendAnalysis(id=new_id("trd"), trend_name=a["trendName"], summary=a["summary"],
                         garment_type=a["garmentType"], core_silhouettes=list(a["coreSilhouettes"]),
                         color_palette=list(a["colorPalette"]), key_fabrics=list(a["keyFabrics"]),
                         commercial_viability_score=a["commercialViabilityScore"], source_image_urls=urls)
