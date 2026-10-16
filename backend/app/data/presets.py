"""Preset mood boards: real, openly licensed photographs, plus the pilot brand's own AI-generated inspiration boards
(clearly marked `aiGenerated`; see static/moodboards/ATTRIBUTION.md).

A board is only images + a factual title + per-image attribution, loaded from static/moodboards/manifest.json.
Nothing about a board's trend is written here: analysing a board sends its images to the live vision model,
exactly like an upload. Rebuild the assets with `backend/scripts/build_moodboards.py`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..config import STATIC_DIR

MOODBOARDS_DIR = STATIC_DIR / "moodboards"
MANIFEST_PATH = MOODBOARDS_DIR / "manifest.json"
REQUIRED_IMAGE_FIELDS = ("file", "title", "creator", "sourceUrl", "license", "licenseUrl", "modifications")
# A brand's own AI-generated inspiration has no public source page or licence deed, but must say what it is.
REQUIRED_AI_IMAGE_FIELDS = ("file", "title", "creator", "license", "modifications")


@dataclass(frozen=True)
class BoardImage:
    file: str  # relative to static/moodboards/, e.g. "lacoste-fw2010/01.jpg"
    title: str
    creator: str
    source_url: str
    license: str
    license_url: str
    modifications: str
    original_source_url: str | None = None
    repository: str | None = None
    ai_generated: bool = False  # the brand's own AI-generated inspiration, never a photograph

    @property
    def path(self) -> Path:
        return MOODBOARDS_DIR / self.file

    @property
    def static_path(self) -> str:
        return f"/static/moodboards/{self.file}"

    @property
    def content_type(self) -> str:
        ext = self.file.rsplit(".", 1)[-1].lower()
        return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(
            ext, "image/jpeg")


@dataclass(frozen=True)
class MoodBoard:
    id: str
    title: str
    images: tuple[BoardImage, ...]

    @property
    def ai_generated(self) -> bool:
        return any(i.ai_generated for i in self.images)

    @property
    def credit(self) -> str:
        """One-line credit, e.g. "Photos: Masaki-H · CC BY 2.0 · via Wikimedia Commons", or, for a brand's own
        AI-generated board, "AI-generated inspiration · UGO SARTORIA (AI-generated with ChatGPT)"."""
        if self.ai_generated:
            return "AI-generated inspiration · " + ", ".join(sorted({i.creator for i in self.images}))
        creators = sorted({i.creator for i in self.images})
        licenses = sorted({i.license for i in self.images})
        repos = sorted({i.repository for i in self.images if i.repository})
        line = f"Photos: {', '.join(creators)} · {', '.join(licenses)}"
        repos = [r for r in repos if not any(c in r for c in creators)]  # "The Met" needn't be named twice
        return f"{line} · via {', '.join(repos)}" if repos else line


class ManifestError(ValueError):
    pass


def load_manifest(path: Path = MANIFEST_PATH) -> list[MoodBoard]:
    """Parse and validate the manifest. Every image must exist on disk and carry a licence + source URL."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ManifestError(f"cannot read mood-board manifest {path}: {e}") from e
    boards: list[MoodBoard] = []
    seen: set[str] = set()
    base = path.parent
    for b in raw.get("boards", []):
        bid, title = str(b.get("id", "")).strip(), str(b.get("title", "")).strip()
        if not bid or not title:
            raise ManifestError("every board needs an id and a title")
        if bid in seen:
            raise ManifestError(f"duplicate board id '{bid}'")
        seen.add(bid)
        images: list[BoardImage] = []
        for im in b.get("images", []):
            ai = bool(im.get("aiGenerated") or b.get("aiGenerated"))
            missing = [k for k in (REQUIRED_AI_IMAGE_FIELDS if ai else REQUIRED_IMAGE_FIELDS)
                       if not str(im.get(k, "")).strip()]
            if missing:
                raise ManifestError(f"board '{bid}' image {im.get('file')!r} is missing {', '.join(missing)}")
            if not (base / im["file"]).is_file():
                raise ManifestError(f"board '{bid}' image file not found: {im['file']}")
            images.append(BoardImage(
                file=im["file"], title=im["title"], creator=im["creator"], source_url=im.get("sourceUrl", ""),
                license=im["license"], license_url=im.get("licenseUrl", ""), modifications=im["modifications"],
                original_source_url=im.get("originalSourceUrl"), repository=im.get("repository"), ai_generated=ai))
        if not images:
            raise ManifestError(f"board '{bid}' has no images")
        boards.append(MoodBoard(id=bid, title=title, images=tuple(images)))
    return boards


@lru_cache
def mood_boards() -> tuple[MoodBoard, ...]:
    return tuple(load_manifest())


def find_board(key: str) -> MoodBoard | None:
    """Match by id or (case-insensitive) title."""
    k = key.strip().lower()
    for b in mood_boards():
        if b.id == k or b.title.lower() == k:
            return b
    return None
