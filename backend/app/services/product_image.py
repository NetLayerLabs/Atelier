"""The design render as a PNG Shopify accepts.

Shopify product media takes PNG / GIF / JPEG / WEBP / HEIC and can't fetch localhost URLs, so the pipeline uploads
bytes through a staged upload. v5: renders only ever come from the live diffusion server (PNG), so they pass through;
another raster format is converted with Pillow. There is no SVG rasterising any more (no mock renders exist).
"""

from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger("atelier.product_image")

MAX_EDGE = 1600


def is_png(data: bytes) -> bool:
    return data[:8] == b"\x89PNG\r\n\x1a\n"


def to_png(data: bytes) -> bytes:
    """Raster (JPEG/WEBP/…) -> PNG via Pillow unless it already is a PNG."""
    if is_png(data):
        return data
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(data))
    img.thumbnail((MAX_EDGE, MAX_EDGE))
    out = io.BytesIO()
    img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB").save(out, format="PNG")
    return out.getvalue()


def design_png(image_url: str) -> tuple[Optional[bytes], str]:
    """(png bytes or None, a short note for the step log). Blocking: call via asyncio.to_thread."""
    from .techpack_pdf import _load_image_bytes  # same loader the PDF uses (local /static, data:, http)

    loaded = _load_image_bytes(image_url) if image_url else None
    if not loaded:
        return None, "design render could not be loaded - listed without an image"
    data, kind = loaded
    if kind == "svg":
        return None, "the design is not a diffusion render (SVG) - listed without an image"
    try:
        png = to_png(data)
    except Exception as e:  # noqa: BLE001
        log.warning("design render -> PNG failed: %s", e)
        return None, f"could not convert the render to PNG ({e.__class__.__name__})"
    return png, "design image as PNG"
