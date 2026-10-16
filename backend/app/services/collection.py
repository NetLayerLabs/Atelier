"""Collection mode (v2; v5: brain only): one trend -> a coherent 3–5 piece capsule.

The brain (Evolus agent → AMD vLLM, or direct vLLM; services/brain.py) names the collection, writes the story and
plans the pieces (garment type, lead fabric, one-line note). Different garment types share the trend's palette
(each piece leads with a different colour of it) and fabrics. Every piece is a normal `Design`, so it can be
selected, directed and approved through the existing flow.

v5: there is no template planner. Without a brain the request fails honestly (503 with a setup hint).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from ..models import TrendAnalysis
from .direction import DirectionState

log = logging.getLogger("atelier.collection")


@dataclass
class PiecePlan:
    garment_type: str
    fabrics: list[str]
    palette: list[str]
    note: str


@dataclass
class CollectionPlan:
    name: str
    story: str
    pieces: list[PiecePlan]
    generated_by: str = ""


def _rotate(palette: list[str], i: int) -> list[str]:
    """Piece i leads with the i-th colour of the trend's own palette (no new colours are introduced)."""
    if not palette:
        return palette
    k = i % len(palette)
    return palette[k:] + palette[:k]


async def plan_collection(trend: TrendAnalysis, size: int) -> CollectionPlan:
    """Raises brain.BrainUnavailable when no brain is connected or it failed (schema-validated, one retry)."""
    from . import brain

    brief = trend.model_dump(by_alias=True, exclude={"id", "source_image_urls", "created_at"})
    schema = ('{"name": str (2-3 words, evocative), "story": str (2 sentences, editorial), '
              '"pieces": [{"garmentType": str (a specific garment noun), "fabric": str (one of keyFabrics), '
              '"note": str (one line)}]}')

    def messages(attempt: int, context: str) -> list[dict]:
        extra = "" if attempt == 0 else "\nReturn ONLY the JSON object."
        return [
            {"role": "system", "content": "You are a fashion creative director planning capsule collections. JSON only."},
            {"role": "user", "content": (
                f"Plan a coherent {size}-piece capsule from this trend. Piece 1 MUST be a {trend.garment_type}. "
                f"Use different garment types (e.g. jacket, trousers, top, coat, skirt, dress) that share the palette "
                f"and fabrics.\n\nTrend:\n{json.dumps(brief)}\n\n{context}\n\nSchema:\n{schema}{extra}")},
        ]

    def validate(data: Any) -> CollectionPlan:
        if not isinstance(data, dict):
            raise ValueError("expected object")
        name, story = str(data.get("name") or "").strip(), str(data.get("story") or "").strip()
        raw = data.get("pieces")
        if not name or not story or not isinstance(raw, list) or len(raw) < size:
            raise ValueError("incomplete collection plan")
        pieces: list[PiecePlan] = []
        for i, p in enumerate(raw[:size]):
            if not isinstance(p, dict) or not str(p.get("garmentType") or "").strip():
                raise ValueError("bad piece")
            note = str(p.get("note") or "").strip()
            if not note:
                raise ValueError("piece note missing")
            gtype = trend.garment_type if i == 0 else str(p["garmentType"]).strip().lower()[:40]
            fab = str(p.get("fabric") or "").strip()
            fabrics = ([fab] + [f for f in trend.key_fabrics if f != fab]) if fab else list(trend.key_fabrics)
            pieces.append(PiecePlan(garment_type=gtype, fabrics=fabrics, palette=_rotate(trend.color_palette, i),
                                    note=note[:160]))
        return CollectionPlan(name=name[:60], story=story[:600], pieces=pieces)

    thought = await brain.think_json("collection_plan", messages, validate, max_tokens=900,
                                     knowledge_query=f"collection {trend.trend_name} house signatures price architecture")
    plan = thought.value
    plan.generated_by = thought.route
    return plan


def piece_state(piece: PiecePlan) -> DirectionState:
    return DirectionState(palette=list(piece.palette), fabrics=list(piece.fabrics))
