"""v3: Customer voice (see CONTRACT.md, "v3 - Customer voice")."""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..models import CustomerEvidence  # noqa: F401  (re-exported in the OpenAPI schema via ApplyResponse)
from ..services import voice as voice_svc
from ..services.errors import ServiceError
from ..services.voice import (ApplyRequest, ApplyResponse, SampleRequest, VoiceError, VoiceInsights, VoiceRecord,
                              VoiceSample)

log = logging.getLogger("atelier.voice")
router = APIRouter(prefix="/api/voice", tags=["voice"])


def _http(e: VoiceError) -> HTTPException:
    return HTTPException(e.status, e.detail)


async def _maybe_phrase(ds: voice_svc.Dataset) -> VoiceInsights:
    """The brain phrases the findings and drafts concrete instructions; without it the deterministic counts,
    quotes and qualitative actions stand on their own and `phrasingError` says why."""
    if ds.insights.recommended_changes:
        try:
            await voice_svc.phrase_live(ds)
        except ServiceError as e:
            ds.insights.phrasing_error = e.message
        except Exception as e:  # noqa: BLE001
            log.warning("voice phrasing failed (%s: %s)", e.__class__.__name__, e)
            ds.insights.phrasing_error = f"{e.__class__.__name__}: {str(e)[:160]}"
    return ds.insights


@router.get("/samples", response_model=list[VoiceSample], response_model_exclude_none=True)
async def samples() -> list[VoiceSample]:
    return voice_svc.list_samples()


@router.post("/upload", response_model=VoiceInsights, response_model_exclude_none=True)
async def upload(file: UploadFile = File(...)) -> VoiceInsights:
    data = await file.read(voice_svc.MAX_UPLOAD_BYTES + 1)
    try:
        ds = voice_svc.ingest_upload(data, file.filename or "upload", file.content_type)
    except VoiceError as e:
        raise _http(e) from e
    return await _maybe_phrase(ds)


@router.post("/sample", response_model=VoiceInsights, response_model_exclude_none=True)
async def sample(req: SampleRequest) -> VoiceInsights:
    try:
        ds = voice_svc.ingest_sample(req.dataset_key)
    except VoiceError as e:
        raise _http(e) from e
    return await _maybe_phrase(ds)


@router.get("/{dataset_id}", response_model=VoiceInsights, response_model_exclude_none=True)
async def get(dataset_id: str) -> VoiceInsights:
    try:
        return voice_svc.get_dataset(dataset_id).insights
    except VoiceError as e:
        raise _http(e) from e


@router.get("/{dataset_id}/records/{record_id}", response_model=VoiceRecord, response_model_exclude_none=True)
async def record(dataset_id: str, record_id: str) -> VoiceRecord:
    try:
        ds = voice_svc.get_dataset(dataset_id)
    except VoiceError as e:
        raise _http(e) from e
    rec = ds.records.get(record_id)
    if rec is None:
        raise HTTPException(404, f"record '{record_id}' not found in {dataset_id}")
    return rec


@router.post("/{dataset_id}/apply", response_model=ApplyResponse, response_model_exclude_none=True)
async def apply(dataset_id: str, req: ApplyRequest) -> ApplyResponse:
    try:
        return voice_svc.apply(dataset_id, req)
    except VoiceError as e:
        raise _http(e) from e
