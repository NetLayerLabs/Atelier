"""v4: the human hand-off. When the agent's pick breaks a brand guardrail, the agent stops and asks.

State machine (PipelineRun.decision):

    (quotes scored, pick breaks a guardrail)
        -> pending ──approve(note)──────────────────────────────> resolved (approved: override in the audit log)
           pending ──switch(mill)───────────────────────────────> resolved (switched)
           pending ──draft counter-offer─> pending (draft) ──send──> negotiating
           negotiating ──revised quote inside the guardrails────> resolved (revised)
           negotiating ──revised quote still outside────────────> pending (ask again; approve / switch / negotiate)
           pending|negotiating ──guardrails or retail edited so the pick passes──> resolved (*_changed)

The pipeline (pipeline._step_quotes -> `gate`) waits while the decision is pending or negotiating, so nothing reaches
Shopify until a person has decided. Every step lands in run.audit (who, what, when, which guardrail, the numbers).
The counter-offer price is computed deterministically (guardrails.negotiation_target); the brain chain writes the
wording, in the mill's language with an English version. v5: there is no template - without a brain the draft fails
(409 with the reason and a setup hint), and without Evolus the counter-offer can't be sent (it stays a draft).
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Optional

from ..config import get_settings
from ..data.suppliers import find_supplier, inbox_for, language_of
from ..models import (AuditEntry, CounterOffer, Decision, DecisionOption, PipelineRun, PipelineStep, SupplierQuote,
                      now_iso)
from ..store import new_id
from . import brain, guardrails, i18n, money, sourcing, workspace
from .errors import NotConfigured, ServiceError

log = logging.getLogger("atelier.decisions")

NEGOTIABLE = {"min_margin", "max_unit_cost", "max_lead_time", "max_moq"}
OPEN = ("pending", "negotiating")
HUMAN = "creative director"


class DecisionError(ValueError):
    """Not allowed in the current state (-> 409). `hint` = how to fix it when a service is missing."""

    def __init__(self, message: str, hint: Optional[str] = None):
        super().__init__(message)
        self.hint = hint


def is_open(run: PipelineRun) -> bool:
    return run.decision is not None and run.decision.status in OPEN


def audit(run: PipelineRun, actor: str, action: str, summary: str, **kw: Any) -> AuditEntry:
    values = {k: str(v) for k, v in (kw.pop("values", None) or {}).items()}
    entry = AuditEntry(actor=actor, action=action, summary=summary, values=values, **kw)  # type: ignore[arg-type]
    run.audit = [*run.audit, entry]
    return entry


def _step(run: PipelineRun) -> Optional[PipelineStep]:
    return next((s for s in run.steps if s.key == "supplier_quotes"), None)


def _say(run: PipelineRun, line: str) -> None:
    st = _step(run)
    if st is not None:
        st.log.append(line)


def _brand() -> str:
    """The brand currency (the guardrails carry the brand profile's)."""
    return guardrails.current().currency


def _price(q: SupplierQuote) -> str:
    if q.unit_price is not None:
        return money.fmt(q.unit_price, _brand())
    return f"{q.currency or ''} {q.unit_price_quoted or 0:,.2f} (not converted)".strip()


def _quote(run: PipelineRun, name: str) -> Optional[SupplierQuote]:
    return next((q for q in run.quotes or [] if q.supplier_name.lower() == name.strip().lower()), None)


def _fx(q: SupplierQuote) -> Optional[float]:
    """Brand-currency units per 1 unit of the quote's currency (ECB rate recorded on the quote), else None."""
    return q.fx_rate


# --------------------------------------------------------------------------- opening the hand-off


def _alt_detail(run: PipelineRun, q: SupplierQuote, margin: Optional[float]) -> str:
    qty = run.tech_pack.production_quantity if run.tech_pack else 0
    bits = [f"{margin:.0f}% margin" if margin is not None else "",
            f"{q.lead_time_weeks} wks" if q.lead_time_weeks else "lead time not stated",
            f"MOQ {q.moq:,}" if q.moq else "MOQ not stated"]
    if qty and q.moq and q.moq > qty:
        bits.append(f"pre-order threshold rises to {q.moq:,}")
    return " · ".join(b for b in bits if b)


def _compose(run: PipelineRun) -> Decision:
    """Build (or rebuild) the decision for the currently selected quote from the guardrail report."""
    rep = guardrails.refresh(run)
    assert rep is not None and run.tech_pack is not None
    sel = sourcing.selected_quote(run.quotes, run.recommendation)
    assert sel is not None
    ev = next(e for e in rep.evaluations if e.supplier_name == sel.supplier_name)
    breaches = ev.breaches
    by_name = {q.supplier_name: q for q in run.quotes or []}
    passing = sorted((e for e in rep.evaluations if e.ok and e.supplier_name != sel.supplier_name),
                     key=lambda e: -by_name[e.supplier_name].score)
    all_breach = not any(e.ok for e in rep.evaluations)
    options = [DecisionOption(kind="approve", label="Approve anyway",
                              detail="Proceed with " + sel.supplier_name + "; recorded as an override of "
                                     + ", ".join(c.label.lower() for c in breaches))]
    negotiable = [c for c in breaches if c.rule in NEGOTIABLE]
    target_txt = ""
    if negotiable:
        tgt = guardrails.negotiation_target(sel, guardrails.current(), run.tech_pack, _fx(sel))
        lang = sel.language or language_of(find_supplier(sel.supplier_name))
        if tgt["price"]:
            p = tgt["price"]
            target_txt = (f"counter-offer at {money.fmt(p['target_brand'], p['brand_currency'])}, "
                          f"−{p['reduction_pct']:.1f}%")
        elif tgt["lead"]:
            target_txt = f"ask for {tgt['lead'][0]} weeks"
        elif tgt["moq"]:
            target_txt = f"ask for MOQ {tgt['moq'][0]:,}"
        else:  # e.g. only an unstated lead time / MOQ: there is no number to negotiate, only to ask for
            negotiable = []
    if negotiable:
        options.append(DecisionOption(kind="negotiate", label=f"Negotiate with {sel.supplier_name}",
                                      detail=f"{target_txt}, drafted in {i18n.name_of(lang)}"
                                             + (" with English alongside" if lang != "en" else ""),
                                      supplier_name=sel.supplier_name))
    for e in passing[:2]:
        q = by_name[e.supplier_name]
        options.append(DecisionOption(kind="switch", label=f"Switch to {q.supplier_name}",
                                      detail=_alt_detail(run, q, e.margin_pct), supplier_name=q.supplier_name))
    what = "breaks a guardrail" if len(breaches) == 1 else f"breaks {len(breaches)} guardrails"
    revised = f" (revised quote {sel.quote_number})" if sel.revision and sel.quote_number else ""
    lines = [c.message for c in breaches]
    opts = ["approve anyway"]
    if negotiable:
        opts.append(f"negotiate ({target_txt})")
    if passing:
        q0 = by_name[passing[0].supplier_name]
        opts.append(f"switch to {q0.supplier_name} ({_alt_detail(run, q0, passing[0].margin_pct)})")
    explanation = " ".join(lines) + " Options: " + (", ".join(opts[:-1]) + ", or " + opts[-1] if len(opts) > 1
                                                       else opts[0]) + "."
    if all_breach and len(rep.evaluations) > 1:
        explanation += f" All {len(rep.evaluations)} quotes break at least one guardrail, so there is no compliant " \
                       f"mill to switch to."
    prev = run.decision
    return Decision(
        id=prev.id if prev and prev.status in OPEN else new_id("dec"),
        supplier_name=sel.supplier_name,
        headline=f"{sel.supplier_name}'s quote{revised} {what} - your call",
        explanation=explanation, breaches=breaches, all_quotes_breach=all_breach, options=options,
        counter_offer=prev.counter_offer if prev and prev.status in OPEN else None,
        negotiation_rounds=prev.negotiation_rounds if prev and prev.status in OPEN else 0,
        created_at=prev.created_at if prev and prev.status in OPEN else now_iso(),
    )


def open_if_needed(run: PipelineRun) -> Optional[Decision]:
    """After the recommendation: check the pick; open a hand-off if it breaks a guardrail. Returns it (or None)."""
    rep = guardrails.refresh(run)
    if rep is None or rep.selected_ok is not False:
        return None
    d = _compose(run)
    run.decision = d
    for c in d.breaches:
        audit(run, "agent", "guardrail_breach", c.message, supplier_name=d.supplier_name, guardrail=c.rule,
              values={"actual": c.actual, "limit": c.limit})
    audit(run, "agent", "handoff", f"Stopped before the pre-order and asked a person: {d.headline}",
          supplier_name=d.supplier_name, guardrail=",".join(c.rule for c in d.breaches),
          values={"options": " / ".join(o.label for o in d.options)})
    return d


async def gate(run: PipelineRun, step: PipelineStep) -> None:
    """Pipeline hook: block until a person resolves the hand-off (real time; we are waiting on people)."""
    rep = guardrails.refresh(run)
    if rep is None:
        return
    g = rep.guardrails
    limits = [f"margin ≥ {g.min_gross_margin_pct:g}%"] if g.min_gross_margin_pct is not None else []
    if g.max_unit_cost:
        limits.append(f"unit ≤ {money.fmt(g.max_unit_cost, g.currency)}"
                      + (" (derived)" if rep.max_unit_cost_derived else ""))
    if g.max_lead_time_weeks:
        limits.append(f"lead ≤ {g.max_lead_time_weeks} wks")
    if g.max_moq:
        limits.append(f"MOQ ≤ {g.max_moq:,}")
    if g.required_certifications:
        limits.append("certs: " + ", ".join(g.required_certifications))
    if g.unset:  # v5: rules the brand left empty are not checked
        limits.append("not set (not checked): " + ", ".join(r.replace("_", " ") for r in g.unset))
    step.log.append("Guardrails: " + " · ".join(limits))
    d = open_if_needed(run)
    if d is None:
        ok = sum(1 for e in rep.evaluations if e.ok)
        step.log.append(f"Guardrails ✓ {rep.selected_supplier_name} is inside every limit "
                        f"({ok} of {len(rep.evaluations)} quotes pass)")
        audit(run, "agent", "guardrails_passed", f"{rep.selected_supplier_name} is inside every guardrail",
              supplier_name=rep.selected_supplier_name)
        return
    step.log.append(f"✋ Hand-off: {d.explanation}")
    step.log.append("Waiting for a person to decide - nothing goes to Shopify until then")
    while is_open(run):
        await asyncio.sleep(0.1)
    d = run.decision
    assert d is not None
    step.log.append(f"Decision: {d.outcome} → {d.resolved_supplier_name} ({d.resolved_by})"
                    + (f" · note: {d.note}" if d.note else ""))


def _resolve(run: PipelineRun, outcome: str, supplier: str, by: str, note: Optional[str] = None) -> None:
    d = run.decision
    assert d is not None
    d.status = "resolved"
    d.outcome = outcome  # type: ignore[assignment]
    d.resolved_supplier_name = supplier
    d.resolved_by = by
    d.resolved_at = now_iso()
    d.note = note or None


# --------------------------------------------------------------------------- the human's options


def approve(run: PipelineRun, note: Optional[str] = None, actor: Optional[str] = None) -> Decision:
    if not is_open(run):
        raise DecisionError("no decision is waiting")
    d = run.decision
    assert d is not None
    who = actor or HUMAN
    q = _quote(run, d.supplier_name)
    audit(run, "human", "approved_override",
          f"{who} approved {d.supplier_name} despite " + "; ".join(f"{c.label.lower()} {c.actual} (limit {c.limit})"
                                                                   for c in d.breaches),
          supplier_name=d.supplier_name, guardrail=",".join(c.rule for c in d.breaches),
          values={**{c.rule: f"{c.actual} vs {c.limit}" for c in d.breaches},
                  **({"unitPrice": _price(q)} if q else {})}, note=note or None)
    _resolve(run, "approved", d.supplier_name, who, note)
    _say(run, f"Override recorded: {who} approved {d.supplier_name} outside the guardrails")
    return d


def switch(run: PipelineRun, supplier_name: str, note: Optional[str] = None, actor: Optional[str] = None) -> Decision:
    if not is_open(run):
        raise DecisionError("no decision is waiting")
    q = _quote(run, supplier_name)
    if q is None:
        raise LookupError(f"no quote from '{supplier_name}'")
    d = run.decision
    assert d is not None and run.recommendation is not None
    who = actor or HUMAN
    run.recommendation.selected_supplier_name = q.supplier_name
    run.recommendation.overridden = q.supplier_name != run.recommendation.supplier_name
    rep = guardrails.refresh(run)
    ev = next((e for e in rep.evaluations if e.supplier_name == q.supplier_name), None) if rep else None
    breaches = ev.breaches if ev else []
    audit(run, "human", "switched", f"{who} switched from {d.supplier_name} to {q.supplier_name}"
          + (" - inside every guardrail" if not breaches else
             " - which also breaks " + ", ".join(f"{c.label.lower()} ({c.actual}, limit {c.limit})" for c in breaches)),
          supplier_name=q.supplier_name, guardrail=",".join(c.rule for c in breaches) or None,
          values={"from": d.supplier_name, "to": q.supplier_name, "unitPrice": _price(q),
                  **({"margin": f"{ev.margin_pct:.1f}%"} if ev and ev.margin_pct is not None else {})},
          note=note or None)
    if breaches:
        audit(run, "human", "approved_override", f"{who} accepted {q.supplier_name} outside the guardrails",
              supplier_name=q.supplier_name, guardrail=",".join(c.rule for c in breaches),
              values={c.rule: f"{c.actual} vs {c.limit}" for c in breaches}, note=note or None)
    _resolve(run, "switched", q.supplier_name, who, note)
    _say(run, f"Switched to {q.supplier_name} by {who}")
    return d


async def draft_counter_offer(run: PipelineRun, actor: Optional[str] = None) -> CounterOffer:
    if not is_open(run):
        raise DecisionError("no decision is waiting")
    d = run.decision
    assert d is not None and run.tech_pack is not None
    q = _quote(run, d.supplier_name)
    if q is None:
        raise DecisionError("the quote under review is gone")
    tgt = guardrails.negotiation_target(q, guardrails.current(), run.tech_pack, _fx(q))
    if not (tgt["price"] or tgt["lead"] or tgt["moq"]):
        raise DecisionError("nothing to negotiate: only certifications are missing, and a mill can't negotiate those")
    sup = find_supplier(q.supplier_name) or {"name": q.supplier_name, "region": q.region, "key": "", "email": ""}
    lang = language_of(sup) if sup.get("key") else (q.language or "en")
    ref = run.quote_round.rfq_ref if run.quote_round else f"ATL-{run.id}"
    asks_local: dict[str, Any] = {}
    asks_en: dict[str, Any] = {}
    if tgt["price"]:
        p = tgt["price"]
        asks_local["price"] = (p["target_local"], p["quoted_local"], p["currency"], p["reduction_pct"])
        asks_en["price"] = asks_local["price"]
    if tgt["lead"]:
        asks_local["lead"] = asks_en["lead"] = tgt["lead"]
    if tgt["moq"]:
        asks_local["moq"] = asks_en["moq"] = tgt["moq"]
    common = dict(supplier_name=q.supplier_name, garment=run.tech_pack.garment_name,
                  quantity=run.tech_pack.production_quantity, rfq_ref=ref, quote_number=q.quote_number,
                  reason=tgt["reason"])
    try:
        thought = await _live_counter_offer(run, q, lang, tgt, ref, common, asks_local)
    except ServiceError as e:
        log.warning("counter_offer: brain unavailable (%s)", e)
        _say(run, f"✗ Counter-offer not drafted: {e.message}")
        raise
    subject, body, subject_en, body_en = thought.value
    route = thought.route
    p = tgt["price"] or {}
    co = CounterOffer(
        supplier_name=q.supplier_name, region=q.region, to_email=inbox_for(sup) if sup.get("key") else
        (sup.get("email") or ""), language=lang, language_name=i18n.name_of(lang), subject=subject, body=body,
        subject_english=subject_en, body_english=body_en, rfq_ref=ref, quote_number=q.quote_number,
        currency=p.get("currency") or q.currency or _brand(), brand_currency=_brand(),
        quoted_unit_price=q.unit_price,
        quoted_unit_price_local=p.get("quoted_local"), target_unit_price=p.get("target_brand"),
        target_unit_price_local=p.get("target_local"), reduction_pct=p.get("reduction_pct", 0.0), math=tgt["math"],
        generated_by=route,
    )
    d.counter_offer = co
    audit(run, "agent", "counter_offer_drafted",
          f"Drafted a counter-offer to {q.supplier_name} in {co.language_name}"
          + (f": {money.fmt(co.target_unit_price, co.brand_currency)}/unit (−{co.reduction_pct:.1f}%)" if p else ""),
          supplier_name=q.supplier_name, guardrail=",".join(c.rule for c in d.breaches),
          values={"quoted": _price(q), **({"target": money.fmt(co.target_unit_price, co.brand_currency),
                                           "targetLocal": money.fmt(co.target_unit_price_local, co.currency)}
                                          if p else {}),
                  "wording": route},
          note=f"requested by {actor}" if actor else None)
    _say(run, f"Counter-offer drafted for {q.supplier_name} in {co.language_name}"
              + (f" · target {money.fmt(co.target_unit_price, co.brand_currency)} (−{co.reduction_pct:.1f}%)"
                 if p else "")
              + f" · {route}")
    return co


_NUM = re.compile(r"\d[\d.,\u00a0\u202f' ]*\d|\d")


def _as_number(tok: str) -> Optional[float]:
    """'1.250,00' / '1,250.00' / '250' / "1'250.50" -> float (the last . or , followed by 1-2 digits is decimal)."""
    t = re.sub(r"[\u00a0\u202f' ]", "", tok)
    m = re.match(r"^(.*?)([.,](\d{1,2}))?$", t)
    if not m:
        return None
    whole = re.sub(r"[.,]", "", m.group(1))
    try:
        return float(f"{whole}.{m.group(3)}" if m.group(3) else whole)
    except ValueError:
        return None


def states_amount(text: str, value: float) -> bool:
    """True when `text` writes `value` in any common form: 250, 250.00, 250,00, €250, 1.250,00 …"""
    return any(abs((_as_number(t) or -1) - value) < 0.005 for t in _NUM.findall(text))


async def _live_counter_offer(run: PipelineRun, q: SupplierQuote, lang: str, tgt: dict, ref: str,
                              common: dict, asks: dict):
    p = tgt["price"]
    must = []  # facts the draft has to carry verbatim
    amount = float(p["target_local"]) if p else None  # the target price: any written form of the same number
    if q.quote_number:
        must.append((q.quote_number, q.quote_number))
    must.append((ref, ref))

    def validate(data: Any) -> tuple[str, str, str, str]:
        if not isinstance(data, dict):
            raise ValueError("expected an object")
        subject, body = str(data.get("subject") or "").strip(), str(data.get("body") or "").strip()
        subject_en = str(data.get("subjectEnglish") or "").strip() or subject
        body_en = str(data.get("bodyEnglish") or "").strip() or (body if lang == "en" else "")
        if len(body) < 80 or not body_en:
            raise ValueError("draft or English version missing")
        blob, blob_en = f"{subject}\n{body}", f"{subject_en}\n{body_en}"
        if amount is not None:
            if not states_amount(blob, amount):
                raise ValueError(f"the draft must state the target price {i18n.fmt_decimal(amount, lang)}")
            if not states_amount(blob_en, amount):
                raise ValueError(f"the English version must state the target price {i18n.fmt_decimal(amount, 'en')}")
        for local, en in must:
            if local not in blob and en not in blob:
                raise ValueError(f"the draft must state {local}")
            if local not in blob_en and en not in blob_en:
                raise ValueError(f"the English version must state {en}")
        if lang != "en" and i18n.detect_language(body, default=lang) != lang:
            raise ValueError(f"the draft is not in {i18n.name_of(lang)}")
        if ref not in subject:
            subject = f"{subject} [{ref}]"
        if ref not in subject_en:
            subject_en = f"{subject_en} [{ref}]"
        return subject, body, subject_en, body_en

    facts = {"mill": q.supplier_name, "language": i18n.name_of(lang), "quoteNumber": q.quote_number,
             "rfqReference": ref, "garment": run.tech_pack.garment_name if run.tech_pack else "",
             "quantity": run.tech_pack.production_quantity if run.tech_pack else None,
             "asks": {k: v for k, v in (("price", p), ("leadTimeWeeks", tgt["lead"]), ("moq", tgt["moq"])) if v}}

    def messages(attempt: int, context: str) -> list[dict]:
        extra = "" if attempt == 0 else "\nReturn ONLY the JSON object, and state the target price exactly."
        return [
            {"role": "system", "content": workspace.persona("sourcing manager") + " You write polite, specific, "
                                          "warm counter-offers to partner mills. Never reveal the brand's margin "
                                          "floor. Output JSON only."},
            {"role": "user", "content": (
                f"Write a counter-offer email to {q.supplier_name} in {i18n.name_of(lang)} (formal business register), "
                f"and a faithful English version. Thank them for quote {q.quote_number or ''}, reference our RFQ "
                f"{ref} in the subject, state the ask exactly as given (numbers verbatim, in the mill's currency "
                f"{(p or {}).get('currency', '')}), keep quantity and specification, offer to discuss alternatives, "
                f"and ask for a revised PDF quote. Sign as 'Atelier Sourcing Agent'.\n\nFacts:\n{facts}\n\n"
                f"Exact figures to state (in the mill's currency): {asks}\n\n{context}\n\n"
                f'Return {{"subject": str, "body": str, "subjectEnglish": str, "bodyEnglish": str}}{extra}')},
        ]

    return await brain.think_json("counter_offer", messages, validate,
                                  knowledge_query="RFQ tone of voice payment terms supplier negotiation "
                                                  + q.supplier_name, max_tokens=900,
                                  timeout=min(get_settings().atelier_llm_timeout, 60.0))


async def send_counter_offer(run: PipelineRun, subject: Optional[str] = None, body: Optional[str] = None,
                             actor: Optional[str] = None, *, confirm_resend: bool = False) -> CounterOffer:
    """Send the (possibly edited) counter-offer through the Evolus outreach / negotiation workflow to the mill's
    address from the supplier directory. v5: without Evolus nothing is sent - DecisionError with a setup hint, and
    the draft is kept."""
    from . import evolus

    if not is_open(run):
        raise DecisionError("no decision is waiting")
    d = run.decision
    assert d is not None
    co = d.counter_offer
    if co is None:
        raise DecisionError("draft a counter-offer first")
    # QA M2: one send per counter-offer - a double click or a concurrent request must not e-mail the mill twice
    if co.status == "sending":
        raise DecisionError(f"the counter-offer to {co.supplier_name} is being sent right now")
    if co.status in ("queued", "sent"):
        raise DecisionError(f"the counter-offer to {co.supplier_name} was already {co.status}")
    if co.status == "unknown" and not confirm_resend:  # QA M3
        raise DecisionError(f"send status unknown - Evolus execution {co.execution_id} started; check it in Evolus "
                            f"first. To send it again anyway, confirm the re-send (?confirm=resend)")
    who = actor or HUMAN
    if subject and subject.strip() != co.subject:
        co.subject, co.edited = subject.strip(), True
    if body and body.strip() != co.body:
        co.body, co.edited = body.strip(), True
    if co.rfq_ref not in co.subject:
        co.subject = f"{co.subject} [{co.rfq_ref}]"
    sup = find_supplier(co.supplier_name)
    co.to_email = inbox_for(sup) if sup else co.to_email  # recipients only ever come from the supplier directory
    s = get_settings()
    if not s.evolus_negotiation_live:
        co.send_error = "Evolus is not connected - the counter-offer was not sent"
        raise NotConfigured("evolus_negotiation", co.send_error)
    email = {"supplierName": co.supplier_name, "region": co.region, "toEmail": co.to_email, "subject": co.subject,
             "body": co.body, "status": "drafted", "rfqRef": co.rfq_ref, "language": co.language,
             "kind": "counter_offer"}
    wf = s.negotiation_workflow_id
    _say(run, f"POST Evolus workflow {wf} (counter-offer to {co.supplier_name})…")
    co.status = "sending"  # in flight: a concurrent send gets 409 (QA M2)
    try:
        resp = await evolus.execute_workflow(wf, {
            "garment_name": run.tech_pack.garment_name if run.tech_pack else "",
            "production_quantity": run.tech_pack.production_quantity if run.tech_pack else 0,
            "rfq_emails": [email],  # same flat shape as the outreach workflow, one email
            "rfq_ref": co.rfq_ref,
            "kind": "counter_offer",
            "quote_number": co.quote_number or "",
            "target_unit_price": co.target_unit_price_local or co.target_unit_price,
            "currency": co.currency,
        }, purpose="counter_offer", param_keys=evolus.EMAIL_WORKFLOW_PARAMS)
        co.status = evolus.outreach_status(resp)  # type: ignore[assignment]
        co.execution_id = resp.get("executionId")
        co.sent_via = f"Evolus workflow {wf}"
        co.send_error = None
    except evolus.EvolusStatusUnknown as e:  # QA M3: started - it may have reached the mill
        log.warning("counter-offer: Evolus execution %s status unknown: %s", e.execution_id, e)
        co.status, co.execution_id, co.sent_via = "unknown", e.execution_id, f"Evolus workflow {wf}"
        co.send_error = (f"send status unknown - Evolus execution {e.execution_id} started; check Evolus before "
                         f"sending again")
        _say(run, f"⚠ Counter-offer to {co.supplier_name}: {co.send_error}")
        raise ServiceError("evolus_negotiation", co.send_error,
                           hint="Check the execution in Evolus; re-sending needs an explicit confirmation.") from e
    except BaseException as e:  # noqa: BLE001
        co.status = "draft"
        log.warning("counter-offer via Evolus failed: %s", e)
        co.send_error = f"Evolus workflow failed: {str(e)[:160]}"
        if not isinstance(e, Exception):
            raise
        raise ServiceError("evolus_negotiation", f"{co.send_error} - the draft is kept, try again") from e
    co.sent_at = now_iso()
    d.status = "negotiating"
    d.negotiation_rounds += 1
    audit(run, "human", "counter_offer_sent",
          f"{who} sent the counter-offer to {co.supplier_name} ({co.language_name})"
          + (" after editing it" if co.edited else "") + f" via {co.sent_via}",
          supplier_name=co.supplier_name, values={"to": co.to_email, "subject": co.subject,
                                                  **({"target": money.fmt(co.target_unit_price,
                                                                          co.brand_currency)}
                                                     if co.target_unit_price is not None else {}),
                                                  **({"executionId": co.execution_id} if co.execution_id else {})})
    _say(run, f"Counter-offer {co.status} to {co.supplier_name} → {co.to_email} · waiting for a revised quote "
              f"(upload it, or it arrives by email with ref {co.rfq_ref})")
    return co


# --------------------------------------------------------------------------- re-evaluation


def on_quote(run: PipelineRun, quote: SupplierQuote) -> None:
    """quotes.add_quote hook: a (revised) quote arrived while a decision is open - re-evaluate it."""
    if not is_open(run):
        if run.recommendation is not None:
            guardrails.refresh(run)
        return
    d = run.decision
    assert d is not None
    rep = guardrails.refresh(run)
    ev = next((e for e in rep.evaluations if e.supplier_name == quote.supplier_name), None) if rep else None
    if ev is not None:
        label = f"revised quote {quote.quote_number}" if quote.revision else f"quote {quote.quote_number or ''}".strip()
        audit(run, "system", "revised_quote" if quote.revision else "quote_received",
              f"{quote.supplier_name} sent {label}: {_price(quote)}/unit"
              + (f", {ev.margin_pct:.1f}% margin" if ev.margin_pct is not None else "")
              + (" - inside every guardrail" if ev.ok else " - still outside: "
                 + ", ".join(f"{c.label.lower()} {c.actual}" for c in ev.breaches)),
              supplier_name=quote.supplier_name, guardrail=",".join(c.rule for c in ev.breaches) or None,
              values={"unitPrice": _price(quote),
                      **({"margin": f"{ev.margin_pct:.1f}%"} if ev.margin_pct is not None else {}),
                      **({"revises": quote.revises} if quote.revises else {})})
    _reconsider(run, "revised", "agent (re-evaluated the new quote)")


def reevaluate(run: PipelineRun, cause: str, actor: str) -> None:
    """Guardrails or the tech pack changed: refresh the report; an open hand-off may now be clear."""
    if run.recommendation is None or not run.quotes:
        return
    guardrails.refresh(run)
    if is_open(run):
        _reconsider(run, cause, actor)


def _reconsider(run: PipelineRun, outcome: str, by: str) -> None:
    rep = run.guardrail_report
    d = run.decision
    assert d is not None
    if rep is not None and rep.selected_ok:
        audit(run, "agent", "resolved",
              f"{rep.selected_supplier_name} is now inside every guardrail - continuing to the pre-order",
              supplier_name=rep.selected_supplier_name, values={"cause": outcome})
        _resolve(run, outcome, rep.selected_supplier_name or d.supplier_name, by)
        _say(run, f"Guardrails ✓ {rep.selected_supplier_name} now passes ({outcome.replace('_', ' ')})")
        return
    rebuilt = _compose(run)
    rebuilt.status = "pending"  # a person decides again (approve / switch / negotiate another round)
    run.decision = rebuilt
    _say(run, f"✋ Still outside the guardrails: {rebuilt.explanation}")


def note_supplier_override(run: PipelineRun, supplier_name: str, actor: Optional[str] = None) -> None:
    """POST /supplier outside a hand-off: record it (and any guardrail it breaks) in the audit log."""
    rep = guardrails.refresh(run)
    ev = next((e for e in rep.evaluations if e.supplier_name == supplier_name), None) if rep else None
    who = actor or HUMAN
    breaches = ev.breaches if ev else []
    audit(run, "human", "supplier_override", f"{who} chose {supplier_name}"
          + ("" if not breaches else " - outside " + ", ".join(f"{c.label.lower()} ({c.actual}, limit {c.limit})"
                                                               for c in breaches)),
          supplier_name=supplier_name, guardrail=",".join(c.rule for c in breaches) or None,
          values={c.rule: f"{c.actual} vs {c.limit}" for c in breaches})
