"""v4: the brand's guardrails. v5: persisted in the Brand workspace; no defaults - unset rules are not checked."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException

from ..models import Guardrails, GuardrailsPatch
from ..services import decisions, guardrails, workspace
from ..store import store

router = APIRouter(prefix="/api/guardrails", tags=["guardrails"])


@router.get("", response_model=Guardrails, response_model_exclude_none=True)
async def get_guardrails() -> Guardrails:
    return guardrails.current()


def _reevaluate(reason: str, diff: dict | None = None) -> None:
    for run in store.runs.values():
        if run.recommendation is None or (run.demand and run.demand.purchase_order):
            continue
        if diff:
            decisions.audit(run, "human", "guardrails_updated", "Guardrails updated: "
                            + "; ".join(f"{k.replace('_', ' ')} {v}" for k, v in diff.items()), values=diff)
        decisions.reevaluate(run, "guardrails_changed", reason)


@router.put("", response_model=Guardrails, response_model_exclude_none=True)
async def put_guardrails(patch: GuardrailsPatch) -> Guardrails:
    """Partial update; `null` clears a rule (then it is not checked). Saving marks the guardrails reviewed.
    Open hand-offs are re-evaluated: a pick that now passes continues."""
    changes = patch.model_dump(by_alias=False, exclude_unset=True)
    if not changes:
        raise HTTPException(422, "no guardrail fields to update")
    if "certifications_mode" in changes and changes["certifications_mode"] is None:
        changes.pop("certifications_mode")
    if "required_certifications" in changes:
        certs = []
        for c in changes["required_certifications"] or []:
            c = re.sub(r"\s+", " ", str(c)).strip()[:40]
            if c and c.lower() not in (x.lower() for x in certs):
                certs.append(c)
        changes["required_certifications"] = certs
    before = guardrails.current()
    merged = before.model_dump(by_alias=False)
    merged.update(changes)
    g = workspace.save_guardrails(Guardrails.model_validate(merged), by="brand (UI)")
    diff = {k: f"{getattr(before, k)} → {getattr(g, k)}" for k in changes if getattr(before, k) != getattr(g, k)}
    _reevaluate("brand (guardrails edited)", diff)
    return g


@router.post("/review", response_model=Guardrails, response_model_exclude_none=True)
async def review_guardrails() -> Guardrails:
    """The brand reviewed the guardrails as they are (including leaving rules unset)."""
    return workspace.mark_guardrails_reviewed("brand (UI)")


@router.post("/reset", response_model=Guardrails, response_model_exclude_none=True)
async def reset_guardrails() -> Guardrails:
    """v5: clear every rule (nothing is checked until the brand sets limits again)."""
    g = workspace.clear_guardrails("brand (UI, cleared)")
    _reevaluate("brand (guardrails cleared)")
    return g
