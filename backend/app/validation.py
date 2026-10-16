"""Readable 422 messages. Pydantic's own ("instruction: String should have at most 500 characters") is written for
developers; the dashboard shows `detail` to a creative director, so the common cases are put in plain words."""

from __future__ import annotations

from typing import Any

# Field names a person sees in the UI, by the last element of the error location.
LABELS = {
    "instruction": "The direction",
    "vibe": "The vibe",
    "note": "The note",
    "subject": "The subject",
    "body": "The email text",
    "actor": "The name",
    "productionQuantity": "The production quantity",
    "targetRetailPrice": "The retail price",
}


def _label(loc: list[Any]) -> str:
    names = [str(x) for x in loc if x != "body" and not isinstance(x, int)]
    if not names:
        return "The request"
    last = names[-1]
    return LABELS.get(last, last[:1].upper() + last[1:])


def validation_message(err: dict[str, Any]) -> str:
    loc = list(err.get("loc") or [])
    what = _label(loc)
    kind = str(err.get("type") or "")
    ctx = err.get("ctx") or {}
    value = err.get("input")
    if kind == "string_too_long" and "max_length" in ctx:
        n = len(value) if isinstance(value, str) else None
        return (f"{what} is too long - keep it to {ctx['max_length']:,} characters"
                + (f" (this one has {n:,})." if n is not None else "."))
    if kind == "string_too_short":
        return f"{what} can't be empty."
    if kind == "missing":
        return f"{what} is required."
    path = ".".join(str(x) for x in loc if x != "body")
    return f"{path}: {err.get('msg')}" if path else str(err.get("msg"))
