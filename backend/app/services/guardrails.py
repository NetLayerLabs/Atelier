"""v4: brand guardrails - deterministic checks of every supplier quote (no model involved).

v5: the guardrails are the brand's own, set in the Brand workspace and persisted (services/workspace.py). There are
no invented defaults: every rule starts unset, an unset rule is skipped, and `Guardrails.unset` names them.

    min_margin       gross margin (retail − unit price) / retail ≥ floor
    max_unit_cost    unit price ≤ cap; the cap is absolute, or derived per run from the tech pack costing:
                     costed unit cost × (1 + headroom) - only when the brand set a headroom
    max_lead_time    lead time ≤ N weeks
    max_moq          MOQ ≤ N pieces per colour
    certifications   the supplier holds the required certificates (supplier directory; expired ones don't count)

Prices are compared in the brand currency: quotes in another currency were converted on extraction with the ECB
reference rate (services/fx.py). v5: a value the quote does not state (MOQ, lead time) or a price that could not be
converted is never assumed - the check fails with "not stated" / "can't be checked" and a person decides.
"""

from __future__ import annotations

import re
from typing import Optional

from ..data.suppliers import ALL_SUPPLIERS, find_supplier
from ..models import (Guardrails, GuardrailCheck, GuardrailReport, PipelineRun, QuoteEvaluation, SupplierQuote,
                      TechPack)
from . import i18n, money, sourcing, workspace

EPS = 1e-9


def defaults() -> Guardrails:
    """Nothing set: the brand sets its own limits (no invented defaults)."""
    return Guardrails(updated_by="not set", unset=list(workspace.GUARDRAIL_RULES))


def current() -> Guardrails:
    return workspace.guardrails()


def replace(g: Guardrails) -> Guardrails:
    return workspace.save_guardrails(g, by=g.updated_by or "brand (UI)")


def reset() -> None:
    """Kept for callers (store.clear): the guardrails are persisted brand data now, so nothing is dropped here.
    To clear every rule use workspace.clear_guardrails()."""


# --------------------------------------------------------------------------- evaluation


def margin_pct(retail: float, unit_price: float) -> Optional[float]:
    if retail <= 0:
        return None
    return (retail - unit_price) / retail * 100.0


def unit_cost_cap(g: Guardrails, tp: Optional[TechPack]) -> tuple[Optional[float], bool, Optional[float]]:
    """(cap, derived?, costing). Derived = costed BOM unit cost x (1 + headroom)."""
    costing = sourcing.unit_cost(tp) if tp else None
    if g.max_unit_cost:
        return g.max_unit_cost, False, costing
    if costing and costing > 0 and g.cost_headroom_pct is not None:
        return round(costing * (1 + g.cost_headroom_pct / 100.0), 2), True, costing
    return None, False, costing


def _cert_norm(c: str) -> str:
    return re.sub(r"[^a-z0-9]", "", c.lower())


def certifications_of(supplier_name: str) -> Optional[list[str]]:
    sup = find_supplier(supplier_name)
    if sup is None:
        sup = next((s for s in ALL_SUPPLIERS if s["name"].lower() == supplier_name.lower()), None)
    return list(sup.get("certifications", [])) if sup else None  # expired certificates are already left out


def has_cert(held: list[str], required: str) -> bool:
    r = _cert_norm(required)
    return bool(r) and any(r in _cert_norm(h) for h in held)


def _money(x: float, ccy: Optional[str]) -> str:
    """In the brand currency (the guardrails' currency = the brand profile's)."""
    return money.fmt(x, ccy)


def evaluate_quote(q: SupplierQuote, g: Guardrails, tp: Optional[TechPack]) -> QuoteEvaluation:
    checks: list[GuardrailCheck] = []
    ccy = g.currency
    retail = tp.target_retail_price if tp else 0.0
    m = margin_pct(retail, q.unit_price) if q.unit_price is not None else None
    floor = g.min_gross_margin_pct
    if floor is None:
        pass  # v5: no margin floor set by the brand -> not checked
    elif q.unit_price is None:
        checks.append(GuardrailCheck(
            rule="min_margin", label="Gross margin", ok=False, actual="can't be checked", limit=f"≥ {floor:g}%",
            limit_value=floor,
            message=(f"{q.supplier_name} quoted in {q.currency or 'another currency'} and no FX rate was available, "
                     f"so the margin can't be checked against your {floor:g}% floor.")))
    elif m is None:
        checks.append(GuardrailCheck(rule="min_margin", label="Gross margin", ok=False, actual="n/a",
                                     limit=f"≥ {floor:g}%", limit_value=floor,
                                     message="No retail price on the tech pack, so the margin can't be checked."))
    else:
        ok = m + EPS >= floor
        checks.append(GuardrailCheck(
            rule="min_margin", label="Gross margin", ok=ok, actual=f"{m:.1f}%", limit=f"≥ {floor:g}%",
            actual_value=round(m, 2), limit_value=floor,
            message=(f"{q.supplier_name}'s quote leaves {m:.1f}% gross margin "
                     f"({_money(q.unit_price, ccy)} against {_money(retail, ccy)} retail) - "
                     + (f"at or above your {floor:g}% floor." if ok else f"below your {floor:g}% floor."))))
    cap, derived, costing = unit_cost_cap(g, tp)
    if cap is not None and q.unit_price is not None:
        ok = q.unit_price <= cap + EPS
        how = f" ({_money(costing or 0, ccy)} costing + {g.cost_headroom_pct or 0:g}% headroom)" if derived else ""
        checks.append(GuardrailCheck(
            rule="max_unit_cost", label="Unit cost", ok=ok, actual=_money(q.unit_price, ccy),
            limit=f"≤ {_money(cap, ccy)}", actual_value=q.unit_price, limit_value=cap,
            message=(f"{_money(q.unit_price, ccy)}/unit is " + ("within" if ok else "above")
                     + f" your {_money(cap, ccy)} unit-cost cap{how}.")))
    if g.max_lead_time_weeks and q.lead_time_weeks is None:
        checks.append(GuardrailCheck(
            rule="max_lead_time", label="Lead time", ok=False, actual="not stated",
            limit=f"≤ {g.max_lead_time_weeks} wks", limit_value=g.max_lead_time_weeks,
            message=(f"The quote does not state a lead time, so it can't be confirmed within your "
                     f"{g.max_lead_time_weeks}-week limit.")))
    elif g.max_lead_time_weeks and q.lead_time_weeks is not None:
        ok = q.lead_time_weeks <= g.max_lead_time_weeks
        checks.append(GuardrailCheck(
            rule="max_lead_time", label="Lead time", ok=ok, actual=f"{q.lead_time_weeks} wks",
            limit=f"≤ {g.max_lead_time_weeks} wks", actual_value=q.lead_time_weeks,
            limit_value=g.max_lead_time_weeks,
            message=(f"{q.lead_time_weeks}-week lead time is " + ("within" if ok else "over")
                     + f" your {g.max_lead_time_weeks}-week limit.")))
    if g.max_moq and q.moq is None:
        checks.append(GuardrailCheck(
            rule="max_moq", label="MOQ", ok=False, actual="not stated", limit=f"≤ {g.max_moq:,}",
            limit_value=g.max_moq,
            message=f"The quote does not state an MOQ, so it can't be confirmed within your {g.max_moq:,}-piece limit."))
    elif g.max_moq and q.moq is not None:
        ok = q.moq <= g.max_moq
        checks.append(GuardrailCheck(
            rule="max_moq", label="MOQ", ok=ok, actual=f"{q.moq:,}", limit=f"≤ {g.max_moq:,}",
            actual_value=q.moq, limit_value=g.max_moq,
            message=(f"MOQ {q.moq:,} pieces per colour is " + ("within" if ok else "above")
                     + f" your {g.max_moq:,}-piece limit.")))
    if g.required_certifications:
        held = certifications_of(q.supplier_name)
        need = g.required_certifications
        if held is None:
            ok, missing = False, list(need)
            msg = f"{q.supplier_name} is not in the supplier catalogue, so its certificates are unknown."
        else:
            hits = [c for c in need if has_cert(held, c)]
            missing = [c for c in need if c not in hits]
            ok = bool(hits) if g.certifications_mode == "any" else not missing
            msg = (f"{q.supplier_name} holds " + (", ".join(hits) if hits else "none of")
                   + (f" - missing {', '.join(missing)}." if missing and not ok else
                      f" ({'any' if g.certifications_mode == 'any' else 'all'} of {', '.join(need)} required)."))
        checks.append(GuardrailCheck(
            rule="certifications", label="Certifications", ok=ok,
            actual=", ".join(c for c in need if c not in missing) or "none",
            limit=(" or " if g.certifications_mode == "any" else " + ").join(need), message=msg))
    return QuoteEvaluation(supplier_name=q.supplier_name, ok=all(c.ok for c in checks), unit_price=q.unit_price,
                           margin_pct=round(m, 2) if m is not None else None, checks=checks,
                           quote_number=q.quote_number, revision=q.revision)


def resolved(g: Guardrails, tp: Optional[TechPack]) -> tuple[Guardrails, bool, Optional[float]]:
    """A copy of the guardrails with the derived unit-cost cap filled in (for the report and the UI)."""
    cap, derived, costing = unit_cost_cap(g, tp)
    return g.model_copy(update={"max_unit_cost": cap}), derived, costing


def report(run: PipelineRun, g: Optional[Guardrails] = None) -> Optional[GuardrailReport]:
    if not run.quotes:
        return None
    g = g or current()
    tp = run.tech_pack
    evals = [evaluate_quote(q, g, tp) for q in run.quotes]
    shown, derived, costing = resolved(g, tp)
    sel = sourcing.selected_quote(run.quotes, run.recommendation)
    sel_eval = next((e for e in evals if sel and e.supplier_name == sel.supplier_name), None)
    return GuardrailReport(guardrails=shown, max_unit_cost_derived=derived, costed_unit_cost=costing,
                           retail_price=tp.target_retail_price if tp else None, evaluations=evals,
                           selected_supplier_name=sel.supplier_name if sel else None,
                           selected_ok=sel_eval.ok if sel_eval else None)


def refresh(run: PipelineRun) -> Optional[GuardrailReport]:
    run.guardrail_report = report(run)
    return run.guardrail_report


def evaluation_for(run: PipelineRun, supplier_name: str) -> Optional[QuoteEvaluation]:
    rep = run.guardrail_report or refresh(run)
    if rep is None:
        return None
    return next((e for e in rep.evaluations if e.supplier_name == supplier_name), None)


# --------------------------------------------------------------------------- negotiation target (pure maths)


def negotiation_target(q: SupplierQuote, g: Guardrails, tp: TechPack, fx_to_brand: float | None = None) -> dict:
    """The asks that would bring `q` inside every negotiable guardrail, and the maths behind them.

    Price: target = min(retail × (1 − floor), unit-cost cap) in the BRAND currency, rounded DOWN to the cent; in the
    mill's currency it is target ÷ FX (`fx_to_brand` = brand units per 1 unit of the mill's currency), rounded down
    again, so converting the mill's answer back can never land above the target.
    Returns {"price": {...} | None, "lead": (weeks, quoted) | None, "moq": (moq, quoted) | None, "math": [str],
             "reason": "margin" | "cost" | "lead" | "moq"}.
    """
    retail = tp.target_retail_price
    floor = g.min_gross_margin_pct
    out: dict = {"price": None, "lead": None, "moq": None, "math": [], "reason": ""}
    fx_to_brand = fx_to_brand or q.fx_rate or 1.0
    brand = (g.currency or "").upper()

    def _m(x: float) -> str:
        return _money(x, brand)

    math_lines: list[str] = out["math"]
    candidates: list[tuple[str, float]] = []
    if floor is not None:  # v5: only the rules the brand set
        margin_cap_raw = retail * (1 - floor / 100.0)
        margin_cap = i18n.floor_cents(margin_cap_raw)
        candidates.append(("margin", margin_cap))
        exact = abs(margin_cap_raw - margin_cap) < 0.005
        math_lines.append(f"Margin floor: retail {_m(retail)} × (1 − {floor:g}%) = "
                          + (f"{_m(margin_cap)}" if exact else
                             f"{_m(margin_cap_raw)} → {_m(margin_cap)} (rounded down)")
                          + " - the most we can pay per piece")
    cap, derived, costing = unit_cost_cap(g, tp)
    if cap is not None:
        candidates.append(("cost", i18n.floor_cents(cap)))
        how = (f"costing {_m(costing or 0)} × (1 + {g.cost_headroom_pct or 0:g}%)" if derived
               else "your absolute cap")
        math_lines.append(f"Unit-cost cap: {_m(cap)} ({how})")
    reason, target = min(candidates, key=lambda c: c[1]) if candidates else ("", float("inf"))
    if candidates and q.unit_price is not None and q.unit_price > target + EPS:
        red = (q.unit_price - target) / q.unit_price * 100.0
        local_q = q.unit_price_quoted if q.unit_price_quoted is not None else round(q.unit_price / fx_to_brand, 2)
        cur = (q.currency or brand).upper()
        foreign = bool(brand) and cur != brand
        local_t = i18n.floor_cents(target / fx_to_brand) if foreign else target
        if len(candidates) > 1:
            math_lines.append(f"Target = the lower of the two = {_m(target)}")
        math_lines.append(f"Quoted {_m(q.unit_price)} → ask {_m(q.unit_price - target)} less "
                          f"(−{red:.1f}%)")
        if foreign:
            math_lines.append(f"In the mill's currency: {_m(target)} ÷ {fx_to_brand:.6g} (ECB rate"
                              f"{' ' + q.fx_date if q.fx_date else ''}) = "
                              f"{cur} {local_t:,.2f} (rounded down; quoted {cur} {local_q:,.2f})")
        check_brand = round(local_t * fx_to_brand, 2) if foreign else target
        mm = margin_pct(retail, check_brand)
        if floor is not None and mm is not None:
            math_lines.append(f"Check: at {_m(check_brand)} the margin is {mm:.1f}% (floor {floor:g}%) ✓")
        out["price"] = {"target_brand": target, "brand_currency": brand, "target_local": local_t, "quoted_local": local_q, "currency": cur,
                        "reduction_pct": round(red, 1)}
        out["reason"] = reason
    if g.max_lead_time_weeks and q.lead_time_weeks is not None and q.lead_time_weeks > g.max_lead_time_weeks:
        out["lead"] = (g.max_lead_time_weeks, q.lead_time_weeks)
        math_lines.append(f"Lead time: {q.lead_time_weeks} weeks quoted → ask for {g.max_lead_time_weeks}")
        out["reason"] = out["reason"] or "lead"
    if g.max_moq and q.moq is not None and q.moq > g.max_moq:
        out["moq"] = (g.max_moq, q.moq)
        math_lines.append(f"MOQ: {q.moq:,} quoted → ask for {g.max_moq:,} pieces per colour")
        out["reason"] = out["reason"] or "moq"
    return out
