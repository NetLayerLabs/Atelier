"""v4: the mills' own languages - formatting, language detection and note translation.

Each mill has a correspondence language (data/suppliers.py). The brain drafts RFQs and counter-offers in that
language with an English version alongside (services/llm.py, services/decisions.py). v5: there are no templates -
without a brain those drafts fail honestly. Supplier notes in another language are translated by the brain; without
one the note stays untranslated and says so (no phrasebook).
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Optional

from ..data.suppliers import LANGUAGE_NAMES, language_of

log = logging.getLogger("atelier.i18n")

LANGS = ("en", "it", "pt")


def name_of(lang: str) -> str:
    return LANGUAGE_NAMES.get(lang, "English")


# --------------------------------------------------------------------------- number formatting


def _group(n: int, sep: str) -> str:
    return f"{n:,}".replace(",", sep)


def fmt_qty(n: int | float, lang: str) -> str:
    n = int(round(n))
    return _group(n, "." if lang in ("it", "pt") else ",")


def fmt_decimal(x: float, lang: str, digits: int = 2) -> str:
    s = f"{x:,.{digits}f}"
    if lang in ("it", "pt"):
        s = s.replace(",", "\u0000").replace(".", ",").replace("\u0000", ".")
    return s


def fmt_money(x: float, currency: str, lang: str, digits: int = 2) -> str:
    """'$227.15' / '€210.31' (en) · '210,31 EUR' (it) · '210,31 EUR' (pt)."""
    currency = (currency or "USD").upper()
    if lang == "en":
        sym = {"USD": "$", "EUR": "€", "GBP": "£"}.get(currency)
        return f"{sym}{fmt_decimal(x, lang, digits)}" if sym else f"{currency} {fmt_decimal(x, lang, digits)}"
    return f"{fmt_decimal(x, lang, digits)} {currency}"


def fmt_pct(x: float, lang: str, digits: int = 1) -> str:
    return f"{fmt_decimal(x, lang, digits)}%" if lang != "pt" else f"{fmt_decimal(x, lang, digits)} %"


def floor_cents(x: float) -> float:
    """Round DOWN to the cent (a target price must never round up past the limit it was computed from)."""
    return math.floor(round(x * 100, 6)) / 100.0


# --------------------------------------------------------------------------- language detection

_STOP = {
    "it": ("il", "lo", "la", "di", "per", "che", "non", "siamo", "possiamo", "capi", "nostro", "nostra",
           "vostro", "grazie", "abbiamo", "sono", "della", "con", "una", "questo", "sotto"),
    "pt": ("o", "os", "de", "para", "não", "peças", "nossa", "nosso", "obrigado", "em", "uma", "com", "esta",
           "isso", "conseguimos", "cor", "das", "pelo", "mantendo"),
    "en": ("the", "and", "we", "our", "for", "is", "can", "your", "pieces", "with", "this", "that", "of", "in"),
}


def detect_language(text: str, default: str = "en") -> str:
    words = re.findall(r"[a-zà-ÿ]+", (text or "").lower())
    if len(words) < 3:
        return default
    scores = {lang: sum(1 for w in words if w in stop) for lang, stop in _STOP.items()}
    if any(ch in (text or "") for ch in "ãõç"):
        scores["pt"] += 3
    best = max(scores, key=lambda k: scores[k])
    ranked = sorted(scores.values(), reverse=True)
    if ranked[0] == 0 or (len(ranked) > 1 and ranked[0] == ranked[1]):
        return default
    return best


def supplier_language(supplier: dict | None) -> str:
    return language_of(supplier)


# --------------------------------------------------------------------------- note translation


async def translate_note(note: str, lang: str) -> tuple[Optional[str], str]:
    """(english, how). how = brain route | "untranslated". English notes return (None, "")."""
    from ..config import get_settings
    from . import brain

    if not note or lang == "en":
        return None, ""
    s = get_settings()
    if s.atelier_translate_notes and s.brain_live:
        def validate(data: Any) -> str:
            text = data.get("english") if isinstance(data, dict) else None
            if not isinstance(text, str) or len(text.strip()) < 3:
                raise ValueError("missing english")
            return text.strip()[:600]

        def messages(attempt: int, context: str) -> list[dict]:
            extra = "" if attempt == 0 else "\nReturn ONLY the JSON object."
            return [
                {"role": "system", "content": "You translate supplier correspondence for a fashion brand's sourcing "
                                              "team. Translate faithfully; keep every number exactly. JSON only."},
                {"role": "user", "content": (f"Translate this note from a mill's quotation from {name_of(lang)} to "
                                             f"English.\n\nNote:\n{note}\n\nReturn {{\"english\": str}}{extra}")},
            ]

        try:
            thought = await brain.think_json("note_translation", messages, validate, max_tokens=300,
                                             timeout=min(s.atelier_llm_timeout, 30.0))
            return thought.value, thought.route
        except Exception as e:  # noqa: BLE001
            log.warning("note translation (%s) failed: %s", lang, e)
    return None, "untranslated"
