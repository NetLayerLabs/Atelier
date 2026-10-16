"""Natural-language creative direction (v2; v5: brain only).

The creative director types or says something like "make it darker, cropped, more Margiela". The brain (Evolus
agent → AMD vLLM, or direct vLLM; services/brain.py) turns that into a structured `CreativeDirection` - what the agent
"heard", prompt additions/removals, a re-coloured palette, fabric swaps, silhouette changes and concrete tech-pack
hints. It is folded into the design lineage as a `DirectionState`, the new variations are rendered on the live
diffusion server, and at approval the accumulated hints go into the tech-pack brief.

v5: there is no keyword interpreter and no fixed cm / cost effects. Without a brain the request fails honestly
(503 with a setup hint); without the diffusion server likewise.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, replace
from typing import Any

from ..models import CreativeDirection, Design, PaletteShift, TrendAnalysis
from ..store import DesignMeta, new_id, store
from . import workspace
from .colors import color_name, normalize_hex

log = logging.getLogger("atelier.direction")


# --------------------------------------------------------------------------- lineage state


@dataclass
class DirectionState:
    """Everything a design inherited from the directions in its lineage (backend-only)."""

    palette: list[str] | None = None  # effective palette, when a direction (or collection) set one
    fabrics: list[str] | None = None  # effective fabrics, shell first
    hints: list[str] = field(default_factory=list)  # tech-pack hints (brain-written, or customer evidence), in order
    prompt_additions: list[str] = field(default_factory=list)
    direction_ids: list[str] = field(default_factory=list)

    def copy(self) -> "DirectionState":
        return replace(self, palette=list(self.palette) if self.palette else None,
                       fabrics=list(self.fabrics) if self.fabrics else None, hints=list(self.hints),
                       prompt_additions=list(self.prompt_additions), direction_ids=list(self.direction_ids))


def state_for(design_id: str) -> DirectionState | None:
    meta = store.design_meta.get(design_id)
    st = getattr(meta, "direction", None) if meta else None
    return st if isinstance(st, DirectionState) else None


def effective_trend(trend: TrendAnalysis, design: Design) -> TrendAnalysis:
    """The trend as this design sees it: palette and fabrics overridden by its lineage."""
    st = state_for(design.id)
    if st is None or (st.palette is None and st.fabrics is None):
        return trend
    return trend.model_copy(update={"color_palette": st.palette or trend.color_palette,
                                    "key_fabrics": st.fabrics or trend.key_fabrics})


@dataclass
class Interpretation:
    direction: CreativeDirection
    state: DirectionState  # the child's lineage state (parent state + this direction)


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for x in items:
        k = x.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(x.strip())
    return out


_HEX = re.compile(r"^#?[0-9A-Fa-f]{6}$")


def _str_list(v: Any, limit: int = 8) -> list[str]:
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if str(x).strip()][:limit]


async def interpret(instruction: str, design: Design, trend: TrendAnalysis) -> Interpretation:
    """The brain interprets the instruction. Raises brain.BrainUnavailable (-> 503) - never a keyword guess."""
    from . import brain

    parent = state_for(design.id)
    st = parent.copy() if parent else DirectionState()
    eff_palette = list(st.palette or trend.color_palette)
    eff_fabrics = list(st.fabrics or trend.key_fabrics)
    brief = {
        "garmentType": design.garment_type, "trendName": trend.trend_name,
        "silhouettes": trend.core_silhouettes[:4], "palette": eff_palette, "fabrics": eff_fabrics,
        "previousDirections": [store.directions[i].instruction for i in st.direction_ids
                               if i in store.directions][-3:],
    }
    schema = ('{"interpretation": str (ONE sentence, first person, what you will change), '
              '"promptAdditions": [str], "promptRemovals": [str], '
              '"paletteAfter": [hex] (same length as the current palette, or [] to keep it), '
              '"fabricsAfter": [str] (the fabrics after any swap, shell first, or [] to keep them), '
              '"silhouetteChanges": [str], "techPackHints": [str] (concrete factory instructions, '
              'e.g. "shorten body length 6cm", "swap to black-dyed denim"), '
              '"references": [str] (designer / era references detected, "Name - what it means here")}')

    def messages(attempt: int, context: str) -> list[dict]:
        extra = "" if attempt == 0 else "\nReturn ONLY the JSON object."
        return [
            {"role": "system", "content": (workspace.brand_prompt("design agent's creative-direction interpreter")
                                           + " Stay inside the brand book (approved colours, signatures, "
                                           "sustainability). Translate a creative director's words into precise "
                                           "design and production changes. Respond with ONLY a JSON object.")},
            {"role": "user", "content": (f"Current design brief:\n{json.dumps(brief)}\n\n"
                                         f"Creative director says: “{instruction.strip()}”\n\n{context}\n\n"
                                         f"Schema:\n{schema} plus \"sources\": [passage numbers used]{extra}")},
        ]

    def validate(data: Any) -> dict:
        if not isinstance(data, dict):
            raise ValueError("expected object")
        interp = str(data.get("interpretation") or "").strip()
        if not interp:
            raise ValueError("missing interpretation")
        after = [normalize_hex(c) for c in _str_list(data.get("paletteAfter"), 8) if _HEX.match(c.strip())]
        return {"interpretation": interp[:400],
                "promptAdditions": _str_list(data.get("promptAdditions")),
                "promptRemovals": _str_list(data.get("promptRemovals")),
                "paletteAfter": [c for c in after if c],
                "fabricsAfter": _str_list(data.get("fabricsAfter"), 6),
                "silhouetteChanges": _str_list(data.get("silhouetteChanges")),
                "techPackHints": _str_list(data.get("techPackHints")),
                "references": _str_list(data.get("references"), 5)}

    thought = await brain.think_json("creative_direction", messages, validate, max_tokens=900,
                                     knowledge_query=f"{instruction} approved colour standards house signatures")
    out = thought.value
    palette_shift = None
    if len(out["paletteAfter"]) >= 2:
        palette_shift = PaletteShift(before=eff_palette, after=out["paletteAfter"], note="re-coloured by the model")
        st.palette = out["paletteAfter"]
    fabrics_after = None
    if out["fabricsAfter"] and [f.lower() for f in out["fabricsAfter"]] != [f.lower() for f in eff_fabrics]:
        fabrics_after = out["fabricsAfter"]
        st.fabrics = fabrics_after
    rm = {r.lower() for r in out["promptRemovals"]}
    st.prompt_additions = _dedupe([a for a in st.prompt_additions if a.lower() not in rm]
                                  + (out["promptAdditions"] or [instruction.strip()]))[-8:]
    st.hints = _dedupe(st.hints + out["techPackHints"])
    d = CreativeDirection(
        id=new_id("dir"), design_id=design.id, instruction=instruction.strip(), interpretation=out["interpretation"],
        prompt_additions=out["promptAdditions"], prompt_removals=out["promptRemovals"], palette_shift=palette_shift,
        silhouette_changes=out["silhouetteChanges"], tech_pack_hints=out["techPackHints"],
        references=out["references"], fabrics_after=fabrics_after, generated_by=thought.route,
        citations=thought.citations or None,
    )
    st.direction_ids = st.direction_ids + [d.id]
    return Interpretation(direction=d, state=st)


# --------------------------------------------------------------------------- rendering


def build_directed_prompt(trend: TrendAnalysis, garment_type: str, st: DirectionState) -> str:
    from .diffusion import build_prompt  # local import keeps diffusion's import graph unchanged

    return build_prompt(trend, garment_type, st.prompt_additions[-6:])


def render_job(*, design_id: str, trend: TrendAnalysis, garment_type: str, prompt: str, seed: int, base_seed: int,
               label: str | None, look_number: int) -> dict:
    """Keyword arguments for diffusion.render_design / render_many (the live diffusion server only)."""
    return dict(design_id=design_id, trend=trend, garment_type=garment_type, prompt=prompt, seed=seed,
                base_seed=base_seed, vibes=[label] if label else [], look_number=look_number)


def remember(design: Design, base_seed: int, vibes: list[str], st: DirectionState) -> None:
    store.designs[design.id] = design
    store.design_meta[design.id] = DesignMeta(base_seed=base_seed, vibes=list(vibes), direction=st)


# --------------------------------------------------------------------------- tech pack


def techpack_brief(design: Design) -> dict | None:
    """Extra brief for the tech-pack prompt (hints the brain must apply)."""
    st = state_for(design.id)
    if st is None or not st.direction_ids:
        return None
    return {
        "techPackHints": st.hints,
        "palette": st.palette,
        "fabrics": st.fabrics,
        "directions": [store.directions[i].instruction for i in st.direction_ids if i in store.directions],
    }


def color_story(palette: list[str], n: int = 3) -> str:
    return " / ".join(color_name(c) for c in palette[:n])
