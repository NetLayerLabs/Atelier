"""v4: the garment's size range (for the Shopify "Size" option) and reading a size back out of an order line.

Size range precedence: TechPack.size_range (explicit list) -> a measurements entry whose key mentions "size"
("size range": "XS–XL", "sizes": "S, M, L, XL") -> the brand's default size range (Brand workspace profile)
-> DEFAULT_SIZES.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

DEFAULT_SIZES: list[str] = ["XS", "S", "M", "L", "XL"]
LADDER: list[str] = ["XXXS", "XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "4XL", "5XL"]
_ALIASES = {"2XS": "XXS", "3XS": "XXXS", "2XL": "XXL", "3XL": "XXXL", "XXXXL": "4XL", "XXXXXL": "5XL",
            "SMALL": "S", "MEDIUM": "M", "LARGE": "L", "X-SMALL": "XS", "X-LARGE": "XL", "XX-LARGE": "XXL",
            "EXTRA SMALL": "XS", "EXTRA LARGE": "XL"}
SIZE_OPTION_NAMES = {"size", "sizes", "taglia", "taille", "talla", "größe", "groesse", "grösse", "maat", "storlek",
                     "tamanho", "サイズ"}
_ONE_SIZE = {"ONE SIZE", "OS", "O/S", "ONESIZE"}
MAX_SIZES = 12


def canonical(token: str) -> Optional[str]:
    """'m' -> 'M', '2XL' -> 'XXL', '38' -> '38', 'One size' -> 'One Size'; None if it doesn't look like a size."""
    t = re.sub(r"\s+", " ", str(token or "")).strip()
    if not t:
        return None
    u = t.upper()
    if u in _ONE_SIZE:
        return "One Size"
    u = _ALIASES.get(u, u)
    if u in LADDER:
        return u
    if re.fullmatch(r"\d{1,2}(?:[.,]5)?", t):  # EU / US numeric sizes (0–60), waist sizes
        return t.replace(",", ".")
    if re.fullmatch(r"\d{2}\s*[x/]\s*\d{2}", t):  # waist x inseam, e.g. 32x30
        return re.sub(r"\s*[x/]\s*", "x", t)
    return None


def parse_range(text: str) -> list[str]:
    """'XS – XL (5 sizes)' -> XS..XL; 'S, M, L' -> [S, M, L]; '36-44' -> 36,38,40,42,44 (step 2)."""
    s = re.sub(r"\(.*?\)", "", str(text or "")).strip()
    if not s:
        return []
    m = re.fullmatch(r"\s*([A-Za-z0-9]+)\s*(?:–|\u2014|-|to|…|\.\.)\s*([A-Za-z0-9]+)\s*", s)
    if m:
        a, b = canonical(m.group(1)), canonical(m.group(2))
        if a in LADDER and b in LADDER and LADDER.index(a) <= LADDER.index(b):
            return LADDER[LADDER.index(a):LADDER.index(b) + 1]
        if a and b and a.isdigit() and b.isdigit() and int(a) < int(b) and int(b) - int(a) <= 40:
            step = 2 if (int(b) - int(a)) % 2 == 0 and int(b) - int(a) > 6 else 1
            return [str(x) for x in range(int(a), int(b) + 1, step)][:MAX_SIZES]
    parts = [canonical(p) for p in re.split(r"[,/;|·]|\s+", s) if p.strip()]
    out: list[str] = []
    for p in parts:
        if p and p not in out:
            out.append(p)
    return out[:MAX_SIZES] if parts and all(parts) else []


def _brand_sizes() -> list[str]:
    """The brand's own size range (workspace profile), canonicalised; [] when none is set."""
    from . import workspace

    try:
        prof = workspace.profile()
    except Exception:  # noqa: BLE001 - no workspace (tests, first run): fall through
        return []
    raw = prof.default_size_range if prof else []
    out = [c for c in (canonical(x) or str(x).strip()[:20] for x in raw or []) if c]
    return list(dict.fromkeys(out))[:MAX_SIZES]


def size_range(tp: Any) -> list[str]:
    """The sizes to offer on Shopify for this tech pack (see module docstring)."""
    explicit = getattr(tp, "size_range", None) if tp is not None else None
    if explicit:
        out = [c for c in (canonical(x) or str(x).strip()[:20] for x in explicit) if c]
        if out:
            return list(dict.fromkeys(out))[:MAX_SIZES]
    meas = getattr(tp, "measurements", None) or {}
    for k, v in meas.items():
        if "size" in str(k).lower() and "sample" not in str(k).lower():
            got = parse_range(str(v))
            if got:
                return got
    return _brand_sizes() or list(DEFAULT_SIZES)


def label(sizes: Iterable[str]) -> str:
    xs = list(sizes)
    if not xs:
        return ""
    if len(xs) > 2 and all(x in LADDER for x in xs):
        return f"{xs[0]} – {xs[-1]} ({len(xs)} sizes)"
    return ", ".join(xs) + f" ({len(xs)} size{'s' if len(xs) != 1 else ''})"


def from_selected_options(options: Any) -> Optional[str]:
    """ProductVariant.selectedOptions [{name, value}] -> the Size option's value (canonicalised)."""
    for o in options or []:
        if isinstance(o, dict) and str(o.get("name") or "").strip().lower() in SIZE_OPTION_NAMES:
            v = str(o.get("value") or "").strip()
            if v:
                return canonical(v) or v[:20]
    return None


def from_title(title: Any) -> Optional[str]:
    """A variant title like 'M' or 'M / Indigo' -> 'M'. 'Default Title' / colour-only titles -> None."""
    if not title or not isinstance(title, str) or title.strip().lower() == "default title":
        return None
    for part in title.split(" / "):
        c = canonical(part)
        if c:
            return c
    return None


def from_properties(props: Any) -> Optional[str]:
    """Line-item properties [{name, value}] (pre-order apps sometimes put the size there)."""
    if isinstance(props, dict):
        props = [{"name": k, "value": v} for k, v in props.items()]
    return from_selected_options(props)
