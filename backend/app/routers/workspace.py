"""v5: the Brand workspace API (CONTRACT.md "v5"). One brand per backend; data persisted in SQLite."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response

from .. import security
from ..config import get_settings
from ..models import now_iso
from ..services import files, knowledge, workspace
from ..services import workspace_import as imp
from ..workspace_models import (BrandDocument, BrandProfile, BrandProfileInput, ConfirmSuppliersRequest,
                                ImportPreview, PriceList, SalesHistorySummary, ScoringWeights, ScoringWeightsInput,
                                Supplier, SupplierConfirmation, SupplierInput, Workspace, WorkspaceStatus)

router = APIRouter(prefix="/api/workspace", tags=["workspace"])

MAX_UPLOAD = 25_000_000
TABLE_EXT = (".csv", ".tsv", ".txt", ".xlsx", ".xlsm")


async def _read(file: UploadFile, exts: tuple[str, ...]) -> tuple[str, bytes]:
    name = Path(file.filename or "upload").name
    if not name.lower().endswith(exts):
        raise HTTPException(422, f"unsupported file type '{name}' - use {', '.join(exts)}")
    data = await file.read()
    if not data:
        raise HTTPException(422, "the file is empty")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"file too large (max {MAX_UPLOAD // 1_000_000} MB)")
    return name, data


def _doc_url(doc_id: str) -> str:
    return get_settings().public_url(f"/api/workspace/documents/{doc_id}/file")


# --------------------------------------------------------------------------- whole workspace


@router.get("", response_model=Workspace, response_model_exclude_none=True)
async def get_workspace() -> Workspace:
    return workspace.snapshot()


@router.get("/status", response_model=WorkspaceStatus, response_model_exclude_none=True)
async def get_status() -> WorkspaceStatus:
    return workspace.status()


@router.delete("", response_model=Workspace, response_model_exclude_none=True)
async def delete_workspace(confirm: str = Query("")) -> Workspace:
    """Erase the whole workspace (profile, suppliers, prices, guardrails, documents, sales). `?confirm=DELETE`."""
    if confirm != "DELETE":
        raise HTTPException(422, "pass ?confirm=DELETE to erase the brand workspace")
    workspace.wipe()
    return workspace.snapshot()


# --------------------------------------------------------------------------- brand profile


@router.put("/profile", response_model=BrandProfile, response_model_exclude_none=True)
async def put_profile(body: BrandProfileInput) -> BrandProfile:
    return workspace.save_profile(body)


# --------------------------------------------------------------------------- imports (suppliers, prices, sizes, sales)


async def _import(kind, file: UploadFile, commit: bool, mode: str) -> ImportPreview:
    name, data = await _read(file, TABLE_EXT)
    preview, items = imp.parse_table(kind, name, data)
    preview.mode = "append" if mode == "append" else "replace"  # type: ignore[assignment]
    if commit and items and not imp.has_errors(preview):
        preview.provenance = imp.commit(kind, name, items, append=preview.mode == "append")
        preview.committed = True
    return preview


@router.post("/suppliers/import", response_model=ImportPreview, response_model_exclude_none=True)
async def import_suppliers(file: UploadFile = File(...), commit: bool = Form(False),
                           mode: Literal["replace", "append"] = Form("replace")) -> ImportPreview:
    """CSV/XLSX supplier directory. `commit=false` -> preview with validation issues; `commit=true` stores the rows
    (refused while any row has an error). Storing un-confirms the directory: the brand confirms the contacts again."""
    return await _import("suppliers", file, commit, mode)


@router.post("/prices/import", response_model=ImportPreview, response_model_exclude_none=True)
async def import_prices(file: UploadFile = File(...), commit: bool = Form(False),
                        mode: Literal["replace", "append"] = Form("replace")) -> ImportPreview:
    return await _import("prices", file, commit, mode)


@router.post("/sizes/import", response_model=ImportPreview, response_model_exclude_none=True)
async def import_sizes(file: UploadFile = File(...), commit: bool = Form(False),
                       mode: Literal["replace", "append"] = Form("replace")) -> ImportPreview:
    return await _import("sizes", file, commit, mode)


@router.post("/sales/import", response_model=ImportPreview, response_model_exclude_none=True)
async def import_sales(file: UploadFile = File(...), commit: bool = Form(False),
                       mode: Literal["replace", "append"] = Form("replace")) -> ImportPreview:
    return await _import("sales", file, commit, mode)


@router.get("/templates/{kind}.csv", response_class=Response,
            responses={200: {"content": {"text/csv": {}}, "description": "CSV template (headers only)"}})
async def template(kind: Literal["suppliers", "prices", "sizes", "sales"]) -> Response:
    return Response(content=imp.template_csv(kind), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="atelier-{kind}-template.csv"', "Cache-Control": "no-store"})


# --------------------------------------------------------------------------- suppliers


@router.get("/suppliers", response_model=list[Supplier], response_model_exclude_none=True)
async def list_suppliers() -> list[Supplier]:
    return workspace.suppliers()


@router.post("/suppliers", response_model=Supplier, response_model_exclude_none=True, status_code=201)
async def create_supplier(body: SupplierInput) -> Supplier:
    _check_emails(body)
    return workspace.add_supplier(body)


@router.put("/suppliers/{supplier_id}", response_model=Supplier, response_model_exclude_none=True)
async def put_supplier(supplier_id: str, body: SupplierInput) -> Supplier:
    _check_emails(body)
    try:
        return workspace.update_supplier(supplier_id, body)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@router.delete("/suppliers/{supplier_id}", status_code=204)
async def remove_supplier(supplier_id: str) -> Response:
    try:
        workspace.delete_supplier(supplier_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    return Response(status_code=204)


@router.post("/suppliers/confirm", response_model=SupplierConfirmation, response_model_exclude_none=True)
async def confirm_suppliers(body: ConfirmSuppliersRequest) -> SupplierConfirmation:
    """The brand confirms the directory: "Atelier will email these suppliers when you approve a design"."""
    if not body.confirm:
        raise HTTPException(422, "confirm must be true")
    try:
        return workspace.confirm_suppliers(body.actor)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/suppliers/{supplier_id}/certificates", response_model=Supplier, response_model_exclude_none=True)
async def upload_certificate(supplier_id: str, file: UploadFile = File(...),
                             certification: str = Form(...)) -> Supplier:
    """Attach a certificate document (PDF / image) to one of the supplier's certifications (added if missing)."""
    if workspace.supplier(supplier_id) is None:
        raise HTTPException(404, f"supplier '{supplier_id}' not found")
    if not certification.strip():
        raise HTTPException(422, "certification name is required")
    name, data = await _read(file, (".pdf", ".png", ".jpg", ".jpeg", ".webp"))
    kind = files.sniff(data)  # QA M5: the real type, by content - never the uploader's Content-Type
    if kind is None:
        raise HTTPException(422, f"'{name}' is not a {files.ALLOWED_LABEL} file (checked by its content)")
    name = f"{Path(name).stem[:80] or 'certificate'}.{kind.ext}"
    doc = BrandDocument(id=workspace.new_document_id(), kind="certificate", filename=name,
                        content_type=kind.content_type, size=len(data),
                        uploaded_at=now_iso(), supplier_id=supplier_id, certification=certification.strip()[:80])
    doc.url = _doc_url(doc.id)
    workspace.save_document(doc, data, "")
    return workspace.set_certificate_document(supplier_id, certification, doc.id)


def _check_emails(body: SupplierInput) -> None:
    for e in [*body.emails, *([body.rfq_email_override] if body.rfq_email_override else [])]:
        if "\u2022" in e:  # security.mask_emails: the page was loaded signed out, so it only had the masked address
            raise HTTPException(422, "this email address is masked because the page was loaded before signing in - "
                                     "reload the page, then save again")
        if not imp.EMAIL.match(e.strip()):
            raise HTTPException(422, f"not an email address: {e}")


# --------------------------------------------------------------------------- price list, sales


@router.get("/prices", response_model=PriceList, response_model_exclude_none=True)
async def get_prices() -> PriceList:
    return workspace.price_list()


@router.delete("/prices", response_model=PriceList, response_model_exclude_none=True)
async def delete_prices() -> PriceList:
    workspace.clear_prices()
    return workspace.price_list()


@router.get("/sales", response_model=SalesHistorySummary, response_model_exclude_none=True)
async def get_sales() -> SalesHistorySummary:
    return workspace.sales_summary()


@router.delete("/sales", response_model=SalesHistorySummary, response_model_exclude_none=True)
async def delete_sales() -> SalesHistorySummary:
    workspace.clear_sales()
    return workspace.sales_summary()


# --------------------------------------------------------------------------- scoring weights


@router.get("/scoring", response_model=ScoringWeights, response_model_exclude_none=True)
async def get_scoring() -> ScoringWeights:
    return workspace.scoring_weights()


@router.put("/scoring", response_model=ScoringWeights, response_model_exclude_none=True)
async def put_scoring(body: ScoringWeightsInput) -> ScoringWeights:
    """Any scale (e.g. 50/30/20); normalised to sum to 1."""
    try:
        return workspace.save_scoring_weights(body.price, body.moq, body.lead_time)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/scoring/reset", response_model=ScoringWeights, response_model_exclude_none=True)
async def reset_scoring() -> ScoringWeights:
    return workspace.reset_scoring_weights()


# --------------------------------------------------------------------------- brand book documents


@router.post("/documents", response_model=BrandDocument, response_model_exclude_none=True, status_code=201)
async def upload_document(file: UploadFile = File(...)) -> BrandDocument:
    """Brand book (PDF / DOCX / Markdown): stored, text extracted locally for grounding passages with citations,
    and uploaded to the Evolus knowledge library when one is configured."""
    name, data = await _read(file, tuple(imp.DOC_TYPES))
    ext = "." + name.lower().rsplit(".", 1)[-1]
    # QA M5: the content must match the extension (a PDF is a PDF, a .docx a Word file, Markdown / text is UTF-8)
    if ext == ".pdf" and files.sniff(data, (files.PDF,)) is None:
        raise HTTPException(422, f"'{name}' is not a PDF (checked by its content)")
    if ext == ".docx" and not files.is_docx(data):
        raise HTTPException(422, f"'{name}' is not a Word .docx file (checked by its content)")
    if ext in (".md", ".markdown", ".txt"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise HTTPException(422, f"'{name}' is not UTF-8 text") from e
    try:
        text = imp.extract_text(name, data)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    ctype = imp.DOC_TYPES[ext]
    doc = BrandDocument(id=workspace.new_document_id(), kind="brand_book", filename=name, content_type=ctype,
                        size=len(data), uploaded_at=now_iso(), chars=len(text))
    doc.url = _doc_url(doc.id)
    workspace.save_document(doc, data, text)
    doc.passages = knowledge.passage_count(doc.id)
    doc.evolus = await knowledge.upload_to_library(name, data, ctype)
    workspace.update_document(doc)
    return doc


@router.get("/documents", response_model=list[BrandDocument], response_model_exclude_none=True)
async def list_documents() -> list[BrandDocument]:
    return workspace.documents()


@router.get("/documents/{doc_id}/file", dependencies=[Depends(security.require_private)])
async def document_file(doc_id: str) -> FileResponse:
    """QA M5: private (authorised clients only). PDFs / images whose bytes match are shown inline with their real
    type; anything else (DOCX, Markdown, a file stored before the checks) is an attachment. `nosniff` is always set."""
    d = workspace.document(doc_id)
    p = workspace.document_file(doc_id)
    if d is None or p is None:
        raise HTTPException(404, f"document '{doc_id}' not found")
    with p.open("rb") as fh:
        kind = files.sniff(fh.read(2048))
    if kind is not None:
        return FileResponse(p, media_type=kind.content_type, filename=d.filename, content_disposition_type="inline",
                            headers={"Cache-Control": "private, no-store"})
    ctype = d.content_type if d.content_type in imp.DOC_TYPES.values() else "application/octet-stream"
    return FileResponse(p, media_type=ctype, filename=d.filename, headers={"Cache-Control": "private, no-store"})


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: str) -> Response:
    """Removes the local copy (and its grounding passages). A copy already sent to the Evolus library is removed
    there by hand (the library UI)."""
    try:
        workspace.delete_document(doc_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    return Response(status_code=204)

