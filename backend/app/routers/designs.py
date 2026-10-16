from __future__ import annotations

import random
import zlib

import secrets

from fastapi import APIRouter, Body, File, Form, Header, HTTPException, UploadFile

from ..models import (ApproveRequest, ApproveResponse, Design, DesignsResponse, GenerateRequest,
                      RefineRequest, TrendAnalysis)
from ..config import UPLOADS_DIR, get_settings
from ..pipeline import create_run, start_run
from ..services import files as filetypes
from ..services import vision, workspace
from ..services.diffusion import build_prompt, render_many
from ..store import DesignMeta, new_id, store

router = APIRouter(prefix="/api/designs", tags=["designs"])

DEFAULT_PRODUCTION_QTY = 500


async def _make_designs(trend: TrendAnalysis, *, garment_type: str, count: int, seeds: list[int],
                        base_seeds: list[int], vibes: list[str], latest_vibe: str | None,
                        parent_id: str | None) -> list[Design]:
    prompt = build_prompt(trend, garment_type, vibes)
    ids = [new_id("dsn") for _ in range(count)]
    look_offset = len(store.designs)
    # v5: the live diffusion server only; errors.ServiceError -> 503 with a setup hint (main.py).
    urls = await render_many([dict(design_id=ids[i], trend=trend, garment_type=garment_type, prompt=prompt,
                                   seed=seeds[i], base_seed=base_seeds[i], vibes=vibes,
                                   look_number=look_offset + i + 1) for i in range(count)])
    designs: list[Design] = []
    for i, url in enumerate(urls):
        d = Design(id=ids[i], trend_id=trend.id, parent_design_id=parent_id, image_url=url, prompt=prompt,
                   garment_type=garment_type, vibe=latest_vibe, seed=seeds[i])
        store.designs[d.id] = d
        store.design_meta[d.id] = DesignMeta(base_seed=base_seeds[i], vibes=list(vibes))
        designs.append(d)
    return designs


@router.post("/generate", response_model=DesignsResponse, response_model_exclude_none=True)
async def generate(req: GenerateRequest) -> DesignsResponse:
    trend = store.trends.get(req.trend_id)
    if trend is None:
        raise HTTPException(404, f"trend '{req.trend_id}' not found")
    vibe = (req.vibe or "").strip() or None
    rng = random.Random()
    seeds = [rng.randint(1000, 999_999) for _ in range(req.count)]
    designs = await _make_designs(trend, garment_type=trend.garment_type, count=req.count, seeds=seeds,
                                  base_seeds=seeds, vibes=[vibe] if vibe else [], latest_vibe=vibe,
                                  parent_id=None)
    return DesignsResponse(designs=designs)


MAX_SKETCH_BYTES = 12 * 1024 * 1024


@router.post("/upload", response_model=DesignsResponse, response_model_exclude_none=True)
async def upload_design(file: UploadFile = File(...), trend_id: str = Form(..., alias="trendId", max_length=64),
                        note: str = Form("", max_length=600)) -> DesignsResponse:
    """The designer's own sketch, drawing or photo as the concept (no diffusion render). The vision model reads it
    (garment type, silhouette, visible details) and that reading goes into the tech-pack brief, so the factory gets
    what the designer drew. Raises 503 when the vision model isn't connected - never a made-up reading."""
    trend = store.trends.get(trend_id)
    if trend is None:
        raise HTTPException(404, f"trend '{trend_id}' not found")
    data = await file.read(MAX_SKETCH_BYTES + 1)
    if not data:
        raise HTTPException(422, "the file is empty")
    if len(data) > MAX_SKETCH_BYTES:
        raise HTTPException(413, "sketch exceeds 12MB")
    kind = filetypes.sniff(data, filetypes.IMAGE_KINDS)  # by content, not by name
    if kind is None:
        raise HTTPException(415, f"'{file.filename}' is not a PNG, JPEG or WebP image")
    reading = await vision.read_sketch(vision.ImageInput(public_url="", data=data, content_type=kind.content_type))
    name = f"sketch_{secrets.token_hex(6)}.{kind.ext}"
    (UPLOADS_DIR / name).write_bytes(data)
    note = note.strip()
    prompt = (f"The designer's own sketch (uploaded, not generated). {reading['description']}"
              + (f" Details: {'; '.join(reading['details'])}." if reading["details"] else "")
              + (f" Designer's note: {note}" if note else ""))
    d = Design(id=new_id("dsn"), trend_id=trend.id, image_url=get_settings().public_url(f"/static/uploads/{name}"),
               prompt=prompt, garment_type=reading["garmentType"] or trend.garment_type, vibe=note or None, seed=0,
               source="designer_upload", sketch_reading=reading)
    store.designs[d.id] = d
    store.design_meta[d.id] = DesignMeta(base_seed=0, vibes=[note] if note else [])
    return DesignsResponse(designs=[d])


@router.post("/{design_id}/refine", response_model=DesignsResponse, response_model_exclude_none=True)
async def refine(design_id: str, req: RefineRequest) -> DesignsResponse:
    parent = store.designs.get(design_id)
    if parent is None:
        raise HTTPException(404, f"design '{design_id}' not found")
    trend = store.trends.get(parent.trend_id)
    if trend is None:
        raise HTTPException(404, f"trend '{parent.trend_id}' not found")
    vibe = req.vibe.strip()
    if not vibe:
        raise HTTPException(422, "vibe must not be empty")
    meta = store.design_meta.get(design_id) or DesignMeta(base_seed=parent.seed)
    vibes = (meta.vibes + [vibe])[-3:]  # keep the last few directions
    # Same silhouette family (base seed) as the parent, new detail seeds folded with the vibe.
    vh = zlib.crc32(vibe.lower().encode())
    seeds = [(parent.seed * 31 + vh + i * 7919) % 999_000 + 1000 for i in range(req.count)]
    designs = await _make_designs(trend, garment_type=parent.garment_type, count=req.count, seeds=seeds,
                                  base_seeds=[meta.base_seed] * req.count, vibes=vibes, latest_vibe=vibe,
                                  parent_id=parent.id)
    return DesignsResponse(designs=designs)


@router.get("/{design_id}/rfq-recipients")
async def rfq_recipients(design_id: str) -> dict:
    """Who approving this design would email: the same shortlist the outreach step uses, with the address each RFQ
    really goes to (the supplier's RFQ override inbox if the brand set one). Read-only - nothing is sent."""
    from ..config import get_settings
    from ..data.suppliers import inbox_for, shortlist

    design = store.designs.get(design_id)
    if design is None:
        raise HTTPException(404, f"design '{design_id}' not found")
    trend = store.trends.get(design.trend_id)
    if trend is None:
        raise HTTPException(404, f"trend '{design.trend_id}' not found")
    out = [{"supplierName": x["name"], "region": x["region"], "toEmail": inbox_for(x),
            "override": bool((x.get("rfq_email_override") or "").strip()), "language": x.get("language") or "en"}
           for x in shortlist(trend.key_fabrics)]
    return {"recipients": out, "sends": get_settings().evolus_outreach_live}


@router.post("/{design_id}/approve", response_model=ApproveResponse)
async def approve(design_id: str, req: ApproveRequest | None = Body(default=None),
                  idempotency_key: str | None = Header(default=None, alias="Idempotency-Key",
                                                       max_length=200)) -> ApproveResponse:
    """Start the pipeline for a design. QA M2: idempotent - while a run for this design is active (running, or
    failed and waiting for a retry) a second approve returns that run (`existing: true`) instead of starting another
    one that would e-mail the suppliers again; the same `Idempotency-Key` header always returns the same run."""
    design = store.designs.get(design_id)
    if design is None:
        raise HTTPException(404, f"design '{design_id}' not found")
    if idempotency_key:
        prev = store.approve_keys.get(f"{design_id}:{idempotency_key}")
        if prev and prev in store.runs:
            return ApproveResponse(run_id=prev, existing=True)
    active = [r for r in store.runs.values() if r.design_id == design_id and r.status in ("running", "failed")]
    if active:
        return ApproveResponse(run_id=active[-1].id, existing=True)
    trend = store.trends.get(design.trend_id)
    if trend is None:
        raise HTTPException(404, f"trend '{design.trend_id}' not found")
    try:  # v5: RFQs go to the brand's real suppliers, so the workspace must be set up (and confirmed) first
        workspace.require_ready()
    except workspace.NotReady as e:
        raise HTTPException(409, str(e)) from e
    qty = (req.production_quantity if req and req.production_quantity else None) or DEFAULT_PRODUCTION_QTY
    run = create_run(design)
    if idempotency_key:
        store.approve_keys[f"{design_id}:{idempotency_key}"] = run.id
    start_run(run, design, trend, qty)
    return ApproveResponse(run_id=run.id)
