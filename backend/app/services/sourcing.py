"""Supplier quotes, weighted scoring and the agent's recommendation.

Quotes are REAL documents (services/quotes.py: upload or inbound email -> extractor). Scoring is deterministic and
uses only what the documents state: a criterion a quote does not state (MOQ, lead time) - or a price that could not
be converted to the brand currency - is left out of that quote's score (weighted mean over the known criteria) and
shown as "not stated". The agent's brain (Evolus agent -> AMD vLLM, or direct vLLM) drafts the rationale; v5: there
is no template rationale - without a brain the recommendation carries `rationaleError` instead.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from ..config import get_settings
from ..models import Citation, ScoreBreakdown, SupplierQuote, SupplierRecommendation, TechPack
from . import workspace

log = logging.getLogger("atelier.sourcing")

# v5: the delivery promise and pre-order window are the brand's (Brand workspace profile); the scoring weights are
# an editable workspace setting, shown as "default weighting" until the brand changes them. The old module
# constants stay readable (sourcing.WEIGHTS, DELIVERY_PROMISE_WEEKS, PREORDER_WINDOW_WEEKS, LEAD_BUDGET_WEEKS) via
# the module __getattr__ below, but always reflect the workspace.


def weights() -> ScoreBreakdown:
    w = workspace.scoring_weights()
    return ScoreBreakdown(price=w.price, moq=w.moq, lead_time=w.lead_time)


def delivery_promise_weeks() -> int | None:
    """What the pre-order page promises customers, from launch (brand profile; None = not set)."""
    return workspace.delivery_promise_weeks()


def preorder_window_weeks() -> float | None:
    days = workspace.preorder_window_days()
    return round(days / 7.0, 2) if days else None


def lead_budget_weeks() -> float | None:
    """Production must fit in promise - window. Not set -> the brand's max-lead-time guardrail, else None."""
    promise, window = delivery_promise_weeks(), preorder_window_weeks()
    if promise:
        return max(1.0, promise - (window or 0))
    g = workspace.guardrails()
    return float(g.max_lead_time_weeks) if g.max_lead_time_weeks else None


def scoring_summary(quantity: int) -> str:
    w = weights()
    lead = (f"lead time vs {delivery_promise_weeks()}-week promise" if delivery_promise_weeks()
            else "lead time (fastest first)")
    tag = f" ({workspace.DEFAULT_WEIGHTS_LABEL})" if workspace.scoring_weights().is_default else ""
    return (f"Scoring{tag}: price {w.price:.0%} · MOQ fit vs {quantity:,}-unit run {w.moq:.0%} · "
            f"{lead} {w.lead_time:.0%} (criteria a quote does not state are left out of its score)")


def __getattr__(name: str):  # PEP 562: the old constants, now live workspace values
    if name == "WEIGHTS":
        return weights()
    if name == "DELIVERY_PROMISE_WEEKS":
        return delivery_promise_weeks()
    if name == "PREORDER_WINDOW_WEEKS":
        return preorder_window_weeks()
    if name == "LEAD_BUDGET_WEEKS":
        b = lead_budget_weeks()
        return int(round(b)) if b else 0
    raise AttributeError(name)


def unit_cost(tp: TechPack) -> float:
    return round(sum(b.target_cost_per_unit for b in tp.bill_of_materials), 2)


def _lead_score(weeks: int, fastest: int | None = None) -> float:
    budget = lead_budget_weeks()
    if not budget:  # v5: no promise / lead-time limit set by the brand -> relative to the fastest quote
        return round(100.0 * max(fastest or weeks, 1) / max(weeks, 1), 1)
    if weeks <= budget:
        return 100.0 - (weeks / budget) * 35.0  # faster is better, 65 at the edge of the budget
    return max(0.0, 65.0 - (weeks - budget) * 20.0)


def _moq_score(moq: int, quantity: int) -> float:
    if moq <= quantity:
        return 100.0
    return 100.0 * (quantity / moq) ** 2  # excess inventory risk grows fast


def score_quotes(quotes: list[SupplierQuote], quantity: int) -> None:
    """Score in place (0-100) with the workspace weights: price · MOQ fit vs production quantity · lead time,
    renormalised over the criteria the quote actually states."""
    if not quotes:
        return
    # QA M10: a number the document text doesn't show (until a person confirms it) is not scored.
    price = {id(q): q.unit_price if "unitPrice" not in q.unverified_fields else None for q in quotes}
    moq = {id(q): q.moq if "moq" not in q.unverified_fields else None for q in quotes}
    lead = {id(q): q.lead_time_weeks if "leadTime" not in q.unverified_fields else None for q in quotes}
    priced = [v for v in price.values() if v]
    cheapest = min(priced) if priced else None
    leads = [v for v in lead.values() if v]
    fastest = min(leads) if leads else None
    w = weights()
    for q in quotes:
        p, m, lt = price[id(q)], moq[id(q)], lead[id(q)]
        b = ScoreBreakdown(
            price=round(100.0 * cheapest / max(p, 0.01), 1) if (p and cheapest) else None,
            moq=round(_moq_score(m, quantity), 1) if m else None,
            lead_time=round(_lead_score(lt, fastest), 1) if lt else None,
        )
        q.score_breakdown = b
        parts = [(v, wt) for v, wt in ((b.price, w.price), (b.moq, w.moq), (b.lead_time, w.lead_time))
                 if v is not None]
        wsum = sum(wt for _, wt in parts)
        q.score = round(sum(v * wt for v, wt in parts) / wsum, 1) if wsum else 0.0


def best(quotes: list[SupplierQuote]) -> SupplierQuote:
    """Highest score among quotes with a comparable price (any quote when none has one).
    QA M10: a price that is not printed in its document (unverified, not confirmed) is never picked automatically
    while another quote has a verified price."""
    pool = ([q for q in quotes if q.unit_price and "unitPrice" not in q.unverified_fields]
            or [q for q in quotes if q.unit_price] or quotes)
    return max(pool, key=lambda q: (q.score, -(q.unit_price or 0)))


def recommend(quotes: list[SupplierQuote], quantity: int, *, previous: SupplierRecommendation | None = None,
              rationale: str | None = None, rationale_error: str | None = None,
              citations: list[Citation] | None = None, generated_by: str | None = None) -> SupplierRecommendation:
    """Agent pick; keeps a user override (if that supplier still quoted). A previous rationale is kept when the
    pick is unchanged (it explains the same choice); otherwise it is dropped rather than left stale."""
    pick = best(quotes)
    if rationale is None and previous is not None and previous.supplier_name == pick.supplier_name:
        rationale, citations, generated_by = previous.rationale, previous.citations, previous.generated_by
        rationale_error = rationale_error or previous.rationale_error
    rec = SupplierRecommendation(
        supplier_name=pick.supplier_name,
        rationale=rationale,
        rationale_error=None if rationale else (rationale_error or "No rationale drafted yet"),
        score=pick.score,
        weights=weights(),
        selected_supplier_name=pick.supplier_name,
        citations=citations or None,
        generated_by=generated_by if rationale else None,
    )
    if previous and previous.overridden and any(q.supplier_name == previous.selected_supplier_name for q in quotes):
        rec.selected_supplier_name = previous.selected_supplier_name
        rec.overridden = previous.selected_supplier_name != pick.supplier_name
    return rec


def selected_quote(quotes: list[SupplierQuote] | None, rec: SupplierRecommendation | None) -> SupplierQuote | None:
    if not quotes:
        return None
    name = rec.selected_supplier_name if rec else None
    return next((q for q in quotes if q.supplier_name == name), None) or best(quotes)


def _window_and_promise() -> str:
    days, promise = workspace.preorder_window_days(), delivery_promise_weeks()
    return ((f"{days}-day pre-order" if days else "pre-order")
            + (f" with a {promise}-week delivery promise" if promise else ""))


def _weights_text() -> str:
    w = weights()
    return f"price {w.price:.0%}, MOQ fit {w.moq:.0%}, lead time {w.lead_time:.0%}"


def _stated(v: Optional[Any]) -> Any:
    return v if v not in (None, "") else "not stated"


async def live_rationale(tp: TechPack, quotes: list[SupplierQuote], pick: SupplierQuote):
    """The brain drafts a 2-3 sentence rationale for the (already chosen) supplier, citing the brand book and
    supplier catalogue. Returns a brain.Thought[str]. Raises brain.BrainUnavailable."""
    from . import brain

    table = [{"supplier": q.supplier_name, "region": q.region, "unitPrice": _stated(q.unit_price),
              "currencyQuoted": q.currency, "unitPriceQuoted": q.unit_price_quoted, "moq": _stated(q.moq),
              "leadTimeWeeks": _stated(q.lead_time_weeks), "paymentTerms": _stated(q.payment_terms),
              "score": q.score, "source": (q.source.engine if q.source else "unknown")} for q in quotes]

    def validate(data: Any) -> str:
        text = data.get("rationale") if isinstance(data, dict) else None
        if not isinstance(text, str) or len(text.strip()) < 20:
            raise ValueError("missing rationale")
        return text.strip()[:700]

    def messages(attempt: int, context: str) -> list[dict]:
        extra = "" if attempt == 0 else "\nReturn ONLY the JSON object."
        return [
            {"role": "system", "content": workspace.persona("sourcing manager") + " Be concrete and brief. Use only "
                                          "numbers from the quotes; a value marked 'not stated' is unknown. "
                                          "Output JSON only."},
            {"role": "user", "content": (
                f"We are producing {tp.production_quantity} units of {tp.garment_name} for a "
                f"{_window_and_promise()}. Weighted scoring ({_weights_text()}, over the criteria each quote states) "
                f"picked {pick.supplier_name}. Explain why in 2-3 sentences, citing numbers, the runner-up trade-off and "
                f"anything in the supplier catalogue or brand book (certifications, payment-term preference) that "
                f"supports or qualifies the pick.\n\nQuotes (from the mills' own documents):\n{json.dumps(table)}\n\n"
                f"{context}\n\nReturn {{\"rationale\": str, \"sources\": [passage numbers you used]}}{extra}")},
        ]

    query = f"supplier {pick.supplier_name} certifications payment terms lead time MOQ price architecture"
    return await brain.think_json("supplier_rationale", messages, validate, knowledge_query=query,
                                  max_tokens=400, timeout=min(get_settings().atelier_llm_timeout, 45.0))
