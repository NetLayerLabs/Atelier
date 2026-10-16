"""v5: persisted per-brand sequences (PO numbers, style numbers). Never random, never seed-based.

Stored as JSON in ATELIER_DATA_DIR/sequences.json: {"<brand>": {"po": 12, "style": 7}}. Single process, so a
module lock plus an atomic replace is enough.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Optional

from ..config import get_settings

_lock = threading.Lock()
PREFIX = {"po": "PO", "style": "ST"}


def _path():
    return get_settings().data_dir / "sequences.json"


def _load() -> dict:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def peek(kind: str, brand: Optional[str] = None) -> int:
    brand = brand or get_settings().atelier_brand_id
    return int(_load().get(brand, {}).get(kind, 0))


def next_number(kind: str, brand: Optional[str] = None) -> int:
    brand = brand or get_settings().atelier_brand_id
    with _lock:
        data = _load()
        n = int(data.setdefault(brand, {}).get(kind, 0)) + 1
        data[brand][kind] = n
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, p)
    return n


def next_code(kind: str, brand: Optional[str] = None) -> str:
    """'PO-00001', 'ST-00001', … for the brand."""
    return f"{PREFIX.get(kind, kind.upper())}-{next_number(kind, brand):05d}"
