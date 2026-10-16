"""Small colour / garment helpers shared by prompts and documents (no rendering, no invented data)."""

from __future__ import annotations

_COLOR_NAMES = {
    "ink black": "#141414", "charcoal": "#36454F", "graphite": "#5A5A60", "silver grey": "#A8A9AD",
    "stone grey": "#8C8C91", "warm grey": "#9E978E", "slate": "#5E6670",
    "ivory": "#F3EEE6", "ecru": "#E8E1D3", "sand": "#D8CBB5", "camel": "#B49B7E",
    "taupe": "#7A6A58", "chocolate": "#4A3328", "oxblood": "#6B2737", "aubergine": "#3A1C2E",
    "burgundy": "#7B1E2B", "rust": "#B5541C", "terracotta": "#C8673A", "copper": "#C8873A",
    "mustard": "#E9C46A", "butter yellow": "#F2DC8C", "olive": "#4F6D3A", "moss": "#7A8C4A",
    "sage": "#A3B86C", "forest green": "#2A3B2E", "teal": "#2A6F73", "indigo": "#1F2A44",
    "denim blue": "#3B5B85", "chambray blue": "#A9B8C9", "cobalt": "#1F4FB5", "navy": "#1B2238",
    "blush": "#E8B8B0", "dusty rose": "#C08A8A", "lilac": "#B9A6D0", "champagne": "#C9A27E",
    "white": "#FAFAFA", "black": "#0A0A0A", "red": "#C0272D", "orange": "#E8742A",
}

GARMENT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("dress", ["dress", "gown", "slip", "frock", "jumpsuit"]),
    ("skirt", ["skirt"]),
    ("coat", ["coat", "trench", "parka", "duster", "cape", "puffer", "mac"]),
    ("jacket", ["jacket", "blazer", "bomber", "trucker", "shacket", "outerwear", "vest", "gilet"]),
    ("trousers", ["trouser", "pant", "jean", "cargo", "jogger", "short", "culotte", "chino"]),
    ("top", ["knit", "sweater", "jumper", "cardigan", "pullover", "top", "shirt", "blouse",
             "tee", "hoodie", "turtleneck", "tank", "corset", "bodice", "polo", "crewneck"]),
]


def rgb(h: str) -> tuple[int, int, int]:
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError):
        return (128, 128, 128)


def normalize_hex(c: str) -> str | None:
    c = c.strip()
    if not c.startswith("#"):
        c = "#" + c
    body = c[1:]
    if len(body) == 3:
        body = "".join(ch * 2 for ch in body)
    if len(body) != 6:
        return None
    try:
        int(body, 16)
    except ValueError:
        return None
    return "#" + body.upper()


def color_name(hexcode: str) -> str:
    """A plain-English approximation of a hex colour, for prompts ("indigo (#1F2A44)")."""
    r, g, b = rgb(hexcode)
    best, bestd = "neutral", 1e9
    for name, hx in _COLOR_NAMES.items():
        r2, g2, b2 = rgb(hx)
        d = (r - r2) ** 2 * 0.3 + (g - g2) ** 2 * 0.59 + (b - b2) ** 2 * 0.11
        if d < bestd:
            best, bestd = name, d
    return best


def garment_kind(garment_type: str) -> str:
    g = (garment_type or "").lower()
    for kind, words in GARMENT_KEYWORDS:
        if any(w in g for w in words):
            return kind
    if "denim" in g:
        return "jacket"
    return "top"
