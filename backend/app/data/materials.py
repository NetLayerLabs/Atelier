"""Material alternatives per BOM line, for live costing in the tech pack editor - v5: from the brand's own
material price list (Brand workspace, CSV/XLSX import). Nothing is hard-coded.

A BOM line is matched to the price-list entry whose material name best overlaps the line's material (the line's
"current" material); the alternatives are the other entries in the same category, in the same currency and unit.
An alternative costs `line_cost × alt.price / current.price`, so quantities and wastage already baked into the line
carry over. A line that matches nothing on the price list gets no alternatives.

Public functions unchanged: family_for(material), alternatives_for(index, line), alternatives(bom).
"""

from __future__ import annotations

import re
from typing import Optional

from ..models import BomAlternatives, BomLine, MaterialOption
from ..services import workspace
from ..workspace_models import MaterialPrice

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"and", "the", "of", "with", "for", "per", "a", "an", "in", "to", "shell", "body", "main", "colour", "color"}

# Lines that are never swapped for a cloth/trim alternative (generic garment-making vocabulary, not brand data).
_NOT_SWAPPABLE = ("cut-make-trim", "label", "thread", "interlining", "interfacing", "zip", "cord", "buckle", "strap")


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1}


def _head_and_tail(material: str) -> tuple[str, str]:
    """'Grade-A cashmere - shell, colour X' -> ('Grade-A cashmere', ' - shell, colour X')."""
    m = re.search(r"\s+[-–\u2014]\s+", material)
    if m and m.start() > 0:
        return material[: m.start()], material[m.start():]
    return material, ""


def _match(material: str, items: list[MaterialPrice]) -> Optional[MaterialPrice]:
    head = _head_and_tail(material)[0]
    if any(w in head.lower() for w in _NOT_SWAPPABLE):
        return None
    want = _tokens(head)
    if not want:
        return None
    best, best_score = None, 0.0
    for it in items:
        have = _tokens(it.material)
        overlap = len(want & have)
        if not overlap:
            continue
        score = overlap / len(have) + 0.25 * len(want & _tokens(it.category))
        if score > best_score:
            best, best_score = it, score
    return best if best_score >= 0.34 else None


def family_for(material: str) -> dict | None:
    """{"family": category, "current": MaterialPrice, "options": [MaterialPrice]} or None."""
    items = workspace.price_list().items
    cur = _match(material, items)
    if cur is None:
        return None
    options = [i for i in items if i.category.lower() == cur.category.lower()
               and i.currency == cur.currency and i.unit.lower() == cur.unit.lower()]
    return {"family": cur.category, "current": cur, "options": options}


def _note(p: MaterialPrice) -> str:
    bits = [f"{p.currency} {p.price:,.2f}/{p.unit}"]
    if p.supplier:
        bits.append(p.supplier)
    bits.append(f"from {p.valid_from}")
    return " · ".join(bits)


def alternatives_for(index: int, line: BomLine) -> BomAlternatives | None:
    if line.target_cost_per_unit <= 0:
        return None
    fam = family_for(line.material)
    if fam is None:
        return None
    cur: MaterialPrice = fam["current"]
    _, tail = _head_and_tail(line.material)
    options: list[MaterialOption] = [
        MaterialOption(material=line.material, target_cost_per_unit=line.target_cost_per_unit, note=_note(cur),
                       original=True)
    ]
    for o in fam["options"]:
        if o is cur or (o.material == cur.material and o.supplier == cur.supplier):
            continue
        cost = round(line.target_cost_per_unit * o.price / cur.price, 2)
        options.append(MaterialOption(material=f"{o.material}{tail}", target_cost_per_unit=cost, note=_note(o)))
    if len(options) < 2:
        return None
    return BomAlternatives(index=index, family=fam["family"], options=options)


def alternatives(bom: list[BomLine]) -> list[BomAlternatives]:
    out = []
    for i, line in enumerate(bom):
        alt = alternatives_for(i, line)
        if alt is not None:
            out.append(alt)
    return out


def price_list_label() -> tuple[Optional[str], Optional[str]]:
    """(dated, provenance label) of the brand's price list, for "price list dated …"."""
    pl = workspace.price_list()
    return pl.dated, (pl.provenance.label if pl.provenance else None)
