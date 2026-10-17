from __future__ import annotations

import json
import secrets

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from ..config import UPLOADS_DIR, get_settings
from ..data.presets import MoodBoard, find_board, mood_boards
from ..models import AnalyzedBy, AnalyzeJsonRequest, InferenceCall, PresetSummary, SourceImage, TrendAnalysis
from ..services import files as filetypes
from ..services import safe_fetch, telemetry, vision
from ..services.vision import ImageInput
from ..store import store

router = APIRouter(prefix="/api/trends", tags=["trends"])

MAX_IMAGES = 6
MAX_IMAGE_BYTES = 12 * 1024 * 1024

def _board_images(board: MoodBoard) -> list[SourceImage]:
    s = get_settings()
    return [SourceImage(url=s.public_url(i.static_path), title=i.title, creator=i.creator, source_url=i.source_url,
                        license=i.license, license_url=i.license_url, modifications=i.modifications,
                        ai_generated=i.ai_generated or None)
            for i in board.images]


@router.get("/presets", response_model=list[PresetSummary], response_model_exclude_none=True)
async def list_presets() -> list[PresetSummary]:
    """The preset mood boards: real, openly licensed photos with per-image attribution, plus the pilot brand's own
    AI-generated inspiration boards (flagged `aiGenerated`)."""
    out = []
    for b in mood_boards():
        images = _board_images(b)
        out.append(PresetSummary(id=b.id, name=b.title, thumbnail_url=images[0].url, credit=b.credit, images=images,
                                 ai_generated=b.ai_generated or None))
    return out


def _vision_ready() -> bool:
    return get_settings().vision_live


async def _analyze_live(images: list[ImageInput]) -> TrendAnalysis:
    """Send the images to the live vision model. No templates, no artificial delay, no fallback: a missing or
    failing model is an errors.ServiceError -> 503 {detail, service: "vision", status, hint} (main.py)."""
    if not _vision_ready():
        raise vision.VisionNotConnected()
    calls: list[InferenceCall] = []
    with telemetry.collect(calls):
        trend = await vision.analyze_images(images)
    live = [c for c in calls if c.service == "vision" and c.ok]
    if live:
        c = live[-1]
        trend.analyzed_by = AnalyzedBy(model=c.model, endpoint_host=c.endpoint_host, gpu=c.gpu,
                                       latency_ms=c.latency_ms, call_id=c.id,
                                       images_analyzed=c.images, images_submitted=len(images))
    return trend


_ANALYZE_DOC = {
    "requestBody": {
        "content": {
            "application/json": {"schema": {"type": "object", "properties": {
                "imageUrls": {"type": "array", "items": {"type": "string"}},
                "preset": {"type": "string"}}}},
            "multipart/form-data": {"schema": {"type": "object", "properties": {
                "images": {"type": "array", "items": {"type": "string", "format": "binary"}}}}},
        }
    }
}


@router.post("/analyze", response_model=TrendAnalysis, response_model_exclude_none=True, openapi_extra=_ANALYZE_DOC)
async def analyze(request: Request) -> TrendAnalysis:
    s = get_settings()
    ctype = request.headers.get("content-type", "").lower()
    if not _vision_ready():  # say what's missing before fetching / checking any image
        raise vision.VisionNotConnected()

    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        files = [f for f in form.getlist("images") if isinstance(f, UploadFile)]
        if not files:
            raise HTTPException(422, "multipart body must include 1-6 files in the 'images' field")
        if len(files) > MAX_IMAGES:
            raise HTTPException(422, f"too many images: {len(files)} (max {MAX_IMAGES})")
        images: list[ImageInput] = []
        for f in files:
            data = await f.read()
            if not data:
                raise HTTPException(422, f"image '{f.filename}' is empty")
            if len(data) > MAX_IMAGE_BYTES:
                raise HTTPException(413, f"image '{f.filename}' exceeds 12MB")
            kind = filetypes.sniff(data, filetypes.IMAGE_KINDS)  # QA M5: by content, not by name / declared type
            if kind is None:
                raise HTTPException(415, f"'{f.filename}' is not a PNG, JPEG or WebP image")
            if filetypes.too_many_pixels(data):  # decoding it could exhaust memory (decompression bomb)
                raise HTTPException(413, f"'{f.filename}' is larger than {filetypes.MAX_IMAGE_PIXELS // 1_000_000} "
                                         "megapixels")
            images.append(ImageInput(public_url="", data=data, content_type=kind.content_type))
        trend = await _analyze_live(images)
        # Stored only after a successful analysis, under our own name and the real extension (served as an image).
        urls = []
        for im in images:
            ext = next(k.ext for k in filetypes.IMAGE_KINDS if k.content_type == im.content_type)
            name = f"upl_{secrets.token_hex(6)}.{ext}"
            (UPLOADS_DIR / name).write_bytes(im.data or b"")
            urls.append(s.public_url(f"/static/uploads/{name}"))
        trend.source_image_urls = urls
        store.trends[trend.id] = trend
        return trend

    # JSON body
    try:
        raw = await request.body()
        payload = json.loads(raw or b"{}")
        body = AnalyzeJsonRequest.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as e:
        raise HTTPException(422, f"invalid JSON body: {str(e).splitlines()[0]}") from e

    if body.preset:
        board = find_board(body.preset)
        if board is None:
            raise HTTPException(404, f"unknown mood board '{body.preset}'")
        # The board's real photos go to the model as bytes (the vision server can't reach our localhost URLs),
        # exactly like an upload. At most MAX_IMAGES; the vision service decides how many it sends per prompt.
        images = [ImageInput(public_url=s.public_url(i.static_path), data=i.path.read_bytes(),
                             content_type=i.content_type) for i in board.images[:MAX_IMAGES]]
        trend = await _analyze_live(images)
        trend.source_images = _board_images(board)[:MAX_IMAGES]
        store.trends[trend.id] = trend
        return trend

    urls = [u.strip() for u in (body.image_urls or []) if u and u.strip()]
    if not urls:
        raise HTTPException(422, "provide multipart 'images', or JSON {imageUrls: string[]} or {preset: string}")
    if len(urls) > MAX_IMAGES:
        raise HTTPException(422, f"too many images: {len(urls)} (max {MAX_IMAGES})")
    # QA M6: the backend fetches each URL itself (https, public addresses only, size / time / type limits) and sends
    # the bytes to the vision model - a user URL is never handed to vLLM.
    images = []
    for u in urls:
        try:
            data, kind = await safe_fetch.fetch_image(u, max_bytes=MAX_IMAGE_BYTES)
        except safe_fetch.FetchError as e:
            raise HTTPException(422, f"image URL rejected: {e}") from e
        if filetypes.too_many_pixels(data):
            raise HTTPException(413, f"image URL rejected: larger than {filetypes.MAX_IMAGE_PIXELS // 1_000_000} "
                                     "megapixels")
        images.append(ImageInput(public_url=u, data=data, content_type=kind.content_type))
    trend = await _analyze_live(images)
    store.trends[trend.id] = trend
    return trend


@router.get("/{trend_id}", response_model=TrendAnalysis, response_model_exclude_none=True)
async def get_trend(trend_id: str) -> TrendAnalysis:
    trend = store.trends.get(trend_id)
    if trend is None:
        raise HTTPException(404, f"trend '{trend_id}' not found")
    return trend
