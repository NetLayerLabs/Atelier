"""The supplier directory - v5: read from the Brand workspace (the brand's own, real suppliers).

Nothing here is hard-coded: every supplier comes from services/workspace.py (CSV/XLSX import or the form in the
Brand workspace). The public functions keep their pre-v5 signatures and return the same dict shape, so the
pipeline, RFQ drafting, quote matching, guardrails and decisions code is unchanged:

    {"key", "tag", "id", "name", "region", "city", "country", "email", "emails", "language", "specialty",
     "specialty_local", "certifications" (names of certificates that have not expired), "certifications_detail",
     "capabilities", "categories", "match", "maker", "moq", "lead_time_weeks", "payment_terms", "notes",
     "rfq_email_override"}

These are REAL contacts: RFQs only go out after the brand confirmed the directory (workspace.status()), and each
supplier can carry an RFQ override address (e.g. the brand's own sourcing inbox during a pilot) - see inbox_for.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Iterator, overload

from ..services import workspace
from ..workspace_models import Supplier

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"and", "the", "of", "for", "with", "from", "to", "in", "up", "a", "an", "fabric", "fabrics", "blend",
         "blends", "weight", "heavy", "light", "fine", "extra", "grade", "made", "make", "production"}

# Correspondence languages Atelier has RFQ / counter-offer templates for (services/i18n.py). A supplier in any
# other language gets English (its language is still shown in the directory).
LANGUAGE_NAMES = {"en": "English", "it": "Italian", "pt": "Portuguese"}


def _keywords(s: Supplier) -> list[str]:
    words: list[str] = []
    for phrase in [*s.categories, *s.capabilities]:
        for w in _WORD.findall(phrase.lower()):
            if len(w) > 2 and w not in _STOP and not w.isdigit() and w not in words:
                words.append(w)
    return words


def as_dict(s: Supplier) -> dict:
    """A workspace supplier in the dict shape the rest of the backend uses."""
    region = ", ".join(x for x in (s.city, s.country) if x)
    specialty = "; ".join(s.capabilities[:3] or s.categories[:3]) or "supplier"
    return {
        "key": s.id, "tag": s.id, "id": s.id,
        "name": s.name, "region": region, "city": s.city, "country": s.country,
        "email": s.emails[0] if s.emails else "", "emails": list(s.emails),
        "language": s.language, "specialty": specialty,
        "certifications": [c.name for c in s.certifications if not c.expired],
        "certifications_detail": [c.model_dump(by_alias=True) for c in s.certifications],
        "capabilities": list(s.capabilities), "categories": list(s.categories),
        "match": _keywords(s), "maker": s.maker,
        "moq": s.moq, "lead_time_weeks": s.lead_time_weeks, "payment_terms": s.payment_terms, "notes": s.notes,
        "rfq_email_override": s.rfq_email_override,
    }


def all_suppliers() -> list[dict]:
    return [as_dict(s) for s in workspace.suppliers()]


class _LiveDirectory(Sequence):
    """`ALL_SUPPLIERS` stays importable as a list-like, but every access reads the workspace (never stale)."""

    def _items(self) -> list[dict]:
        return all_suppliers()

    @overload
    def __getitem__(self, i: int) -> dict: ...
    @overload
    def __getitem__(self, i: slice) -> list[dict]: ...
    def __getitem__(self, i):  # type: ignore[override]
        return self._items()[i]

    def __len__(self) -> int:
        return len(workspace.suppliers())

    def __iter__(self) -> Iterator[dict]:
        return iter(self._items())

    def __repr__(self) -> str:  # pragma: no cover
        return f"<workspace supplier directory: {len(self)} suppliers>"


ALL_SUPPLIERS: Sequence = _LiveDirectory()


def shortlist(fabrics: list[str], max_mills: int = 2) -> list[dict]:
    """Who gets the RFQ: up to `max_mills` suppliers whose categories/capabilities match the trend fabrics, plus one
    cut-make-trim / full-package maker (category "CMT", "cut-make-trim" or "full package"), preferring a maker in
    the same country as a matched mill. With no capability match, the first supplier(s) in the directory are used.
    """
    sups = all_suppliers()
    if not sups:
        return []
    mills = [s for s in sups if not s["maker"]]
    makers = [s for s in sups if s["maker"]]
    picked: list[dict] = []
    for fabric in fabrics:
        words = set(_WORD.findall(fabric.lower()))
        for s in mills:
            if s in picked:
                continue
            if any(m in words or m in fabric.lower() for m in s["match"]):
                picked.append(s)
                break
        if len(picked) >= max_mills:
            break
    if not picked:
        picked = mills[:1]
    if makers:
        countries = {s["country"].lower() for s in picked if s["country"]}
        maker = next((m for m in makers if m["country"].lower() in countries), makers[0])
        picked.append(maker)
    return picked


def language_of(supplier: dict | None) -> str:
    lang = (supplier or {}).get("language") or "en"
    return lang if lang in LANGUAGE_NAMES else "en"


def specialty_in(supplier: dict, lang: str) -> str:
    return supplier.get("specialty_local") if lang != "en" and supplier.get("specialty_local") else supplier["specialty"]


def inbox_for(supplier: dict) -> str:
    """The address an RFQ / counter-offer to this supplier is really sent to: the supplier's RFQ override address
    (set per supplier in the Brand workspace, e.g. the brand's own sourcing inbox during a pilot) if set, else its
    first contact email."""
    override = (supplier.get("rfq_email_override") or "").strip()
    if override:
        return override
    return (supplier.get("email") or "").strip()


def find_supplier(name: str = "", email: str = "") -> dict | None:
    """Match a reply to a supplier by name (fuzzy), contact / override address, +tag in an address, or city."""
    n = (name or "").strip().lower()
    e = (email or "").strip().lower()
    sups = all_suppliers()
    if n:
        for sup in sups:
            if sup["name"].lower() == n or sup["key"] == n:
                return sup
        for sup in sups:
            words = [w for w in sup["name"].lower().split() if len(w) > 3]
            if sup["name"].lower() in n or (words and sum(w in n for w in words) >= min(2, len(words))):
                return sup
    if e:
        for sup in sups:
            if e in [x.lower() for x in sup["emails"]]:
                return sup
        routed = [sup for sup in sups if e == inbox_for(sup).lower()]
        if len(routed) == 1:  # an override shared by several suppliers (one pilot inbox) can't identify one
            return routed[0]
        for sup in sups:
            tag = sup.get("tag") or ""
            if tag and f"+{tag}@" in e:
                return sup
    if n:
        for sup in sups:
            city = (sup.get("city") or "").lower()
            if city and city in n:
                return sup
    return None
