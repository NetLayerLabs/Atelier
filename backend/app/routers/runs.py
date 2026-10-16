from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from .. import security

from ..data.materials import alternatives, price_list_label
from ..models import (AlternativesResponse, CounterOfferSendRequest, DecisionApproveRequest, DecisionSwitchRequest,
                      PipelineRun, SelectSupplierRequest, TechPackPatch)
from ..config import get_settings
from ..pipeline import requote, retry, select_supplier, sync_shopify_price
from ..store import store

router = APIRouter(prefix="/api/runs", tags=["runs"])
unmatched_router = APIRouter(prefix="/api/quotes", tags=["runs"])


def _run(run_id: str) -> PipelineRun:
    run = store.runs.get(run_id)
    if run is None:
        raise HTTPException(404, f"run '{run_id}' not found")
    return run


@router.get("/{run_id}", response_model=PipelineRun, response_model_exclude_none=True)
async def get_run(run_id: str, request: Request) -> PipelineRun:
    run = _run(run_id)
    # PII: with an admin token set, customers' first names / cities are only returned to signed-in clients.
    if security.token_required() and not security.is_authenticated(request) and run.demand and run.demand.recent_orders:
        run = run.model_copy(deep=True)
        for o in run.demand.recent_orders:  # type: ignore[union-attr]
            o.first_name, o.city = None, None
    return run


class RetryRequest(BaseModel):
    confirmResend: bool = False


@router.post("/{run_id}/retry", response_model=PipelineRun, response_model_exclude_none=True)
async def retry_run(run_id: str, req: RetryRequest | None = None) -> PipelineRun:
    """v5: resume a failed run from its first errored step (e.g. after connecting the missing service).
    QA M3: when the failed step's Evolus execution may have sent the emails, `{"confirmResend": true}` is required."""
    run = _run(run_id)
    try:
        retry(run, confirm_resend=bool(req and req.confirmResend))
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return run


@router.post("/{run_id}/purchase-order/send", response_model=PipelineRun, response_model_exclude_none=True)
async def send_purchase_order(run_id: str, confirm: str = Query("")) -> PipelineRun:
    """v5: send (or re-send after a failure) the drafted PO to the mill through the Evolus PO workflow.
    QA M3: a PO whose send status is unknown (the workflow started, its outcome couldn't be read) is only re-sent with
    `?confirm=resend`."""
    from ..services import purchase_orders
    from ..services.errors import HINTS, NotConfigured

    run = _run(run_id)
    po = purchase_orders.current(run)
    if po is None:
        raise HTTPException(409, "no purchase order has been drafted yet")
    if po.status in ("sent", "queued", "sending"):
        raise HTTPException(409, f"{po.po_number} is already {po.status}")
    if po.status == "unknown" and confirm != "resend":
        raise HTTPException(409, f"{po.po_number}: send status unknown - Evolus execution {po.execution_id} started; "
                                 f"check it in Evolus first. To send it again anyway, confirm the re-send "
                                 f"(?confirm=resend) - the mill may receive it twice")
    from ..config import get_settings

    if not get_settings().evolus_po_live:
        raise NotConfigured("evolus_po", f"Evolus is not connected - {po.po_number} stays a draft (not sent)",
                            hint=HINTS["evolus_po"])
    step = next((x for x in run.steps if x.key == "preorder_demand"), None)
    await purchase_orders.send(run, po, step.log.append if step else None)
    return run


# --------------------------------------------------------------------------- v2: business loop


@router.patch("/{run_id}/techpack", response_model=PipelineRun, response_model_exclude_none=True)
async def patch_techpack(run_id: str, patch: TechPackPatch) -> PipelineRun:
    """Persist creative-director edits (material swaps, quantity, retail). Open quotes are re-scored and the
    guardrails re-checked against the new costing / retail; the mills' quoted prices never change."""
    run = _run(run_id)
    if run.tech_pack is None:
        raise HTTPException(409, "the tech pack has not been generated yet")
    changes = patch.model_dump(by_alias=False, exclude_unset=True, exclude_none=True)
    if not changes:
        raise HTTPException(422, "no tech pack fields to update")
    for b in patch.bill_of_materials or []:
        if b.target_cost_per_unit < 0 or not b.material.strip():
            raise HTTPException(422, "BOM lines need a material and a non-negative cost")
    merged = run.tech_pack.model_dump(by_alias=False)
    merged.update(changes)
    run.tech_pack = type(run.tech_pack).model_validate(merged)
    run.tech_pack_revision += 1
    if run.original_tech_pack is None:
        run.original_tech_pack = run.tech_pack.model_copy(deep=True)
    if "target_retail_price" in changes and run.shopify_product and not (run.demand and run.demand.purchase_order):
        sync_shopify_price(run)  # v3: the real product's variant price follows (best effort, in the background)
    requote(run)
    return run


@router.get("/{run_id}/techpack/alternatives", response_model=AlternativesResponse, response_model_exclude_none=True)
async def techpack_alternatives(run_id: str) -> AlternativesResponse:
    """Swappable materials per BOM line, costed against the agent's original line."""
    run = _run(run_id)
    base = run.original_tech_pack or run.tech_pack
    if base is None:
        raise HTTPException(409, "the tech pack has not been generated yet")
    dated, source = price_list_label()  # v5: costed from the brand's own price list
    return AlternativesResponse(lines=alternatives(base.bill_of_materials), price_list_dated=dated,
                                price_list_source=source)


@router.get("/{run_id}/techpack.pdf", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}, "description": "Factory tech pack PDF"}})
async def techpack_pdf(run_id: str) -> Response:
    from ..services.techpack_pdf import build_techpack_pdf  # reportlab import kept off the startup path

    run = _run(run_id)
    if run.tech_pack is None:
        raise HTTPException(409, "the tech pack has not been generated yet")
    design = store.designs.get(run.design_id)
    if design is None:
        raise HTTPException(404, f"design '{run.design_id}' not found")
    trend = store.trends.get(design.trend_id)
    pdf = await asyncio.to_thread(build_techpack_pdf, run, run.tech_pack.model_copy(deep=True), design, trend)
    name = re.sub(r"[^A-Za-z0-9]+", "-", run.tech_pack.garment_name).strip("-") or "tech-pack"
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{name}-tech-pack-rev{run.tech_pack_revision:02d}.pdf"',
        "Cache-Control": "no-store",
    })


@router.post("/{run_id}/supplier", response_model=PipelineRun, response_model_exclude_none=True)
async def choose_supplier(run_id: str, req: SelectSupplierRequest) -> PipelineRun:
    """Creative-director override of the agent's supplier pick (until the PO is drafted)."""
    run = _run(run_id)
    try:
        select_supplier(run, req.supplier_name)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return run


@router.get("/{run_id}/storefront-qr.svg", response_class=Response,
            responses={200: {"content": {"image/svg+xml": {}}, "description": "QR code for the product page"}})
async def storefront_qr(run_id: str) -> Response:
    """v3: QR code (SVG, generated locally) that opens the real product page so the audience can pre-order."""
    import io

    import qrcode
    import qrcode.image.svg

    run = _run(run_id)
    product = run.shopify_product
    if product is None or not product.url.startswith(("http://", "https://")):
        raise HTTPException(409, "no storefront product URL yet")
    img = qrcode.make(product.url, image_factory=qrcode.image.svg.SvgPathFillImage, border=2,
                      error_correction=qrcode.constants.ERROR_CORRECT_M)
    buf = io.BytesIO()
    img.save(buf)
    return Response(content=buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


# --------------------------------------------------------------------------- v3: real supplier quotes


@router.post("/{run_id}/quotes", response_model=PipelineRun, response_model_exclude_none=True)
async def upload_quote(run_id: str, file: UploadFile = File(...),
                       supplier_name: str = Form("", alias="supplierName")) -> PipelineRun:
    """A supplier's quote document (PDF or image) -> extractor -> SupplierQuote on the run."""
    from ..services import quotes

    run = _run(run_id)
    data = await file.read(get_settings().atelier_quote_max_bytes + 1)
    try:
        await quotes.ingest_document(run, data, file.filename or "quote.pdf",
                                     file.content_type or "application/octet-stream", channel="upload",
                                     supplier_hint=supplier_name)
    except quotes.DuplicateQuote:
        pass  # QA M9: already received - the run comes back unchanged (the quote's `duplicates` count went up)
    except quotes.QuoteError as e:
        raise HTTPException(422, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return run


@router.get("/{run_id}/quotes/documents/{name}", dependencies=[Depends(security.require_private)],
            response_class=FileResponse)
async def quote_document(run_id: str, name: str) -> FileResponse:
    """QA M5: a stored quote document (private: authorised clients only). PDFs and images only, served inline with
    their real type; `nosniff` is set on every response."""
    from ..services import files, quotes

    path = quotes.document_path(run_id, name)
    if path is None:
        raise HTTPException(404, "document not found")
    with path.open("rb") as fh:
        kind = files.sniff(fh.read(2048))
    if kind is None:
        raise HTTPException(404, "document not found")
    return FileResponse(path, media_type=kind.content_type, filename=name, content_disposition_type="inline",
                        headers={"Cache-Control": "private, no-store"})


class ConfirmQuoteRequest(BaseModel):
    supplierName: str = Field(min_length=1, max_length=200)
    actor: str | None = Field(default=None, max_length=80)


@router.post("/{run_id}/quotes/confirm", response_model=PipelineRun, response_model_exclude_none=True)
async def confirm_quote(run_id: str, req: ConfirmQuoteRequest) -> PipelineRun:
    """QA M10: a person checked the document and confirms the numbers that weren't found in its text."""
    from ..services import quotes

    run = _run(run_id)
    try:
        quotes.confirm_fields(run, req.supplierName, req.actor)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return run


@unmatched_router.get("/unmatched", dependencies=[Depends(security.require_private)])
async def list_unmatched() -> list[dict]:
    """LOW: inbound quotes (email webhook) that matched no run - waiting for a person to assign them."""
    from ..services import quotes

    return [quotes.unmatched_summary(x) for x in reversed(list(store.unmatched_quotes.values()))]


@unmatched_router.post("/unmatched/{item_id}/assign/{run_id}", response_model=PipelineRun,
                       response_model_exclude_none=True)
async def assign_unmatched(item_id: str, run_id: str) -> PipelineRun:
    from ..services import quotes

    item = store.unmatched_quotes.get(item_id)
    if item is None:
        raise HTTPException(404, f"no unmatched quote '{item_id}'")
    run = _run(run_id)
    try:
        await quotes.ingest_extracted(run, item["payload"])
    except quotes.DuplicateQuote:
        pass
    except quotes.QuoteError as e:
        raise HTTPException(422, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    store.unmatched_quotes.pop(item_id, None)
    return run


@router.post("/{run_id}/quotes/close", response_model=PipelineRun, response_model_exclude_none=True)
async def close_quotes(run_id: str) -> PipelineRun:
    """Stop waiting for the remaining mills and recommend from the quotes in hand (at least one)."""
    from ..services import quotes

    run = _run(run_id)
    try:
        quotes.close_round(run)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return run


# --------------------------------------------------------------------------- v4: guardrail hand-off


def _decision_call(run: PipelineRun, fn, *args, **kw):
    from ..services import decisions

    try:
        return fn(run, *args, **kw)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except decisions.DecisionError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/{run_id}/decision/approve", response_model=PipelineRun, response_model_exclude_none=True)
async def decision_approve(run_id: str, req: DecisionApproveRequest) -> PipelineRun:
    """Proceed with the agent's pick despite the guardrail breach; recorded as an override in the audit log."""
    from ..services import decisions

    run = _run(run_id)
    _decision_call(run, decisions.approve, req.note, req.actor)
    return run


@router.post("/{run_id}/decision/switch", response_model=PipelineRun, response_model_exclude_none=True)
async def decision_switch(run_id: str, req: DecisionSwitchRequest) -> PipelineRun:
    """Switch to another mill's quote (ideally one inside the guardrails)."""
    from ..services import decisions

    run = _run(run_id)
    _decision_call(run, decisions.switch, req.supplier_name, req.note, req.actor)
    from ..pipeline import _sync_threshold

    _sync_threshold(run)
    return run


@router.post("/{run_id}/decision/negotiate", response_model=PipelineRun, response_model_exclude_none=True)
async def decision_negotiate(run_id: str) -> PipelineRun:
    """Draft a counter-offer (deterministic target price; wording by the brain - 503 without one)."""
    from ..services import decisions

    run = _run(run_id)
    try:
        await decisions.draft_counter_offer(run)
    except decisions.DecisionError as e:
        raise HTTPException(409, str(e)) from e
    return run


@router.post("/{run_id}/decision/counter-offer/send", response_model=PipelineRun, response_model_exclude_none=True)
async def decision_send(run_id: str, req: CounterOfferSendRequest, confirm: str = Query("")) -> PipelineRun:
    """Send the (optionally edited) counter-offer to the mill via the Evolus workflow (503 without Evolus).
    QA M2: 409 while a send is in flight or once it was sent; QA M3: an unknown outcome needs ?confirm=resend."""
    from ..services import decisions

    run = _run(run_id)
    try:
        await decisions.send_counter_offer(run, req.subject, req.body, req.actor, confirm_resend=confirm == "resend")
    except decisions.DecisionError as e:
        raise HTTPException(409, str(e)) from e
    return run
