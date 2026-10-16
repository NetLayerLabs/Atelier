"""Uploaded-file checks (QA M5): the type is decided by the file's magic bytes, never by its name or the
uploader's Content-Type. Only PDF and raster images (PNG, JPEG, WebP) are accepted where documents / images are
uploaded, and they are stored under a name and extension we choose."""

from __future__ import annotations

from typing import NamedTuple, Optional


class Sniffed(NamedTuple):
    ext: str  # "pdf" | "png" | "jpg" | "webp"
    content_type: str


PDF = Sniffed("pdf", "application/pdf")
PNG = Sniffed("png", "image/png")
JPEG = Sniffed("jpg", "image/jpeg")
WEBP = Sniffed("webp", "image/webp")

DOCUMENT_KINDS = (PDF, PNG, JPEG, WEBP)
IMAGE_KINDS = (PNG, JPEG, WEBP)
ALLOWED_LABEL = "PDF, PNG, JPEG or WebP"


def sniff(data: bytes, allowed: tuple[Sniffed, ...] = DOCUMENT_KINDS) -> Optional[Sniffed]:
    """The real type of `data` if it is one of `allowed`, else None."""
    head = data[:16]
    kind: Optional[Sniffed] = None
    if data[:1024].lstrip().startswith(b"%PDF-"):
        kind = PDF
    elif head.startswith(b"\x89PNG\r\n\x1a\n"):
        kind = PNG
    elif head.startswith(b"\xff\xd8\xff"):
        kind = JPEG
    elif head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        kind = WEBP
    return kind if kind in allowed else None


def is_docx(data: bytes) -> bool:
    """A .docx is a ZIP container holding word/document.xml."""
    return data[:4] == b"PK\x03\x04" and b"word/" in data[:200_000]


def inline_ok(content_type: str) -> bool:
    """Only PDFs and raster images may be shown inline; everything else is served as an attachment."""
    return content_type in {k.content_type for k in DOCUMENT_KINDS}
