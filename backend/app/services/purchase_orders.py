"""v5: real purchase orders.

When real pre-orders clear the threshold, a PO is drafted for the selected mill:
  * number   - the brand's persisted PO sequence (services/sequences.py): PO-00001, PO-00002, … never random
  * to       - the mill's address from the supplier directory (data/suppliers.inbox_for)
  * terms    - the quantity and the mill's own quoted unit price, in the currency it quoted; lead time only if the
               quote stated one
It is then sent through an Evolus workflow (EVOLUS_PO_WORKFLOW_ID, else the outreach workflow) and the send result is
recorded. Without Evolus the PO stays "draft - not sent" with a send action; it is never shown as issued.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..config import get_settings
from ..data.suppliers import find_supplier, inbox_for
from ..models import PipelineRun, PurchaseOrder, now_iso
from . import money, sequences, sourcing
from .errors import HINTS

log = logging.getLogger("atelier.po")


class POError(ValueError):
    """Not allowed in the current state (-> 409)."""


def create_draft(run: PipelineRun, quantity: int) -> PurchaseOrder:
    q = sourcing.selected_quote(run.quotes, run.recommendation)
    if q is None:
        raise POError("no supplier quote selected")
    sup = find_supplier(q.supplier_name)
    brand = money.brand_currency()
    currency = (q.currency or brand or "").upper()
    if not currency:
        raise POError(f"{q.supplier_name}'s quote states no currency and the brand profile has none")
    unit_local = q.unit_price_quoted if q.unit_price_quoted is not None else q.unit_price
    if unit_local is None:
        raise POError(f"{q.supplier_name}'s quote has no unit price")
    unit_brand = q.unit_price
    po = PurchaseOrder(
        po_number=sequences.next_code("po"),
        supplier_name=q.supplier_name, region=q.region, to_email=inbox_for(sup) if sup else None,
        quantity=quantity, currency=currency, unit_price=round(unit_local, 2),
        total=round(quantity * unit_local, 2),
        unit_price_brand=unit_brand, brand_currency=brand, total_brand=round(quantity * unit_brand, 2) if unit_brand is not None else None,
        lead_time_weeks=q.lead_time_weeks, quote_number=q.quote_number,
        rfq_ref=run.quote_round.rfq_ref if run.quote_round else f"ATL-{run.id}",
    )
    if not po.to_email:
        po.send_error = f"{q.supplier_name} is not in the supplier directory, so there is no address to send the PO to"
    if not get_settings().evolus_po_live:
        po.send_error = po.send_error or "Evolus is not connected - the PO has not been sent"
        po.hint = HINTS["evolus_po"]
    return po


def _body(run: PipelineRun, po: PurchaseOrder) -> str:
    tp = run.tech_pack
    lines = [
        f"Purchase order {po.po_number}",
        f"To: {po.supplier_name} ({po.region})",
        f"Style: {tp.garment_name if tp else ''}" + (f" · style no. {run.style_number}" if run.style_number else ""),
        f"Quantity: {po.quantity:,} pieces",
        f"Unit price: {po.currency} {po.unit_price:,.2f} (as quoted"
        + (f", quote {po.quote_number}" if po.quote_number else "") + ")",
        f"Total: {po.currency} {po.total:,.2f}",
    ]
    if po.lead_time_weeks:
        lines.append(f"Lead time: {po.lead_time_weeks} weeks, as quoted")
    lines.append(f"Reference: {po.rfq_ref}")
    # Nothing is attached: the specification went out in the RFQ email for this reference. Say so plainly.
    lines.append(f"Specification: as sent with our RFQ {po.rfq_ref} (materials, measurements, quantities). Reply to "
                 "this email if you need the full tech pack document. Please confirm receipt and the ex-factory date.")
    return "\n".join(lines)


async def send(run: PipelineRun, po: PurchaseOrder, log_line=None) -> PurchaseOrder:
    """Send the PO through the Evolus workflow. Records the result on `po` (never raises for send failures)."""
    from . import evolus

    s = get_settings()
    say = log_line or (lambda _m: None)
    if po.status in ("sent", "queued", "sending"):
        raise POError(f"{po.po_number} has already been sent" if po.status != "sending"
                      else f"{po.po_number} is being sent")
    if not s.evolus_po_live:
        po.status, po.send_error, po.hint = "draft", "Evolus is not connected - the PO has not been sent", HINTS["evolus_po"]
        say(f"{po.po_number} drafted for {po.supplier_name} - draft, not sent (Evolus not connected)")
        return po
    if not po.to_email:
        po.status = "draft"
        say(f"{po.po_number} not sent: {po.send_error}")
        return po
    wf = s.po_workflow_id
    po.status = "sending"
    say(f"POST Evolus workflow {wf} (purchase order {po.po_number} → {po.to_email})…")
    email = {"supplierName": po.supplier_name, "region": po.region, "toEmail": po.to_email,
             "subject": f"Purchase order {po.po_number} [{po.rfq_ref}]", "body": _body(run, po),
             "status": "drafted", "rfqRef": po.rfq_ref, "kind": "purchase_order"}
    try:
        resp = await evolus.execute_workflow(wf, {
            "kind": "purchase_order", "po_number": po.po_number, "supplier_name": po.supplier_name,
            "to_email": po.to_email, "quantity": po.quantity, "unit_price": po.unit_price, "currency": po.currency,
            "total": po.total, "rfq_ref": po.rfq_ref, "quote_number": po.quote_number or "",
            "garment_name": run.tech_pack.garment_name if run.tech_pack else "",
            "production_quantity": po.quantity,
            "rfq_emails": [email],  # same flat shape as the outreach workflow, so it can be reused
        }, purpose="purchase_order", param_keys=evolus.EMAIL_WORKFLOW_PARAMS)
    except evolus.EvolusStatusUnknown as e:  # QA M3: started - it may have reached the mill
        log.warning("PO %s via Evolus: execution %s status unknown: %s", po.po_number, e.execution_id, e)
        po.status, po.execution_id, po.sent_via = "unknown", e.execution_id, f"Evolus workflow {wf}"
        po.send_error = (f"send status unknown - Evolus execution {e.execution_id} started; check Evolus before "
                         f"sending again")
        say(f"⚠ {po.po_number}: {po.send_error}")
        return po
    except Exception as e:  # noqa: BLE001
        log.warning("PO %s via Evolus failed: %s", po.po_number, e)
        po.status, po.send_error = "failed", f"Evolus workflow failed: {str(e)[:200]}"
        say(f"✗ {po.po_number} not sent - {po.send_error}")
        return po
    po.status = evolus.outreach_status(resp)  # type: ignore[assignment]  # "sent" | "queued"
    po.execution_id = resp.get("executionId")
    po.sent_via, po.sent_at, po.send_error, po.hint = f"Evolus workflow {wf}", now_iso(), None, None
    say(f"{po.po_number} {po.status} to {po.supplier_name} → {po.to_email} via Evolus workflow {wf} · execution "
        f"{po.execution_id or '(no id returned)'}")
    return po


def current(run: PipelineRun) -> Optional[PurchaseOrder]:
    return run.demand.purchase_order if run.demand else None
