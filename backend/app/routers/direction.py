"""v2: natural-language creative direction + collection mode (see CONTRACT.md, "v2"; v5: live services only)."""

from __future__ import annotations

import random
import zlib

from fastapi import APIRouter, HTTPException

from ..models import (Collection, CollectionLook, CollectionRequest, CreativeDirection, Design, DirectRequest,
                      DirectResponse)
from ..services import collection as collection_svc
from ..services import direction as direction_svc
from ..services.diffusion import render_many
from ..store import new_id, store

router = APIRouter(tags=["direction"])


@router.post("/api/designs/{design_id}/direct", response_model=DirectResponse, response_model_exclude_none=True)
async def direct(design_id: str, req: DirectRequest) -> DirectResponse:
    parent = store.designs.get(design_id)
    if parent is None:
        raise HTTPException(404, f"design '{design_id}' not found")
    trend = store.trends.get(parent.trend_id)
    if trend is None:
        raise HTTPException(404, f"trend '{parent.trend_id}' not found")
    instruction = req.instruction.strip()
    if not instruction:
        raise HTTPException(422, "instruction must not be empty")

    # errors.ServiceError (brain / diffusion) -> 503 with a setup hint (main.py)
    interp = await direction_svc.interpret(instruction, parent, trend)
    d, st = interp.direction, interp.state

    meta = store.design_meta.get(design_id)
    base_seed = meta.base_seed if meta else parent.seed
    vibes = ((meta.vibes if meta else []) + [instruction])[-3:]
    eff = trend.model_copy(update={"color_palette": st.palette or trend.color_palette,
                                   "key_fabrics": st.fabrics or trend.key_fabrics})
    prompt = direction_svc.build_directed_prompt(eff, parent.garment_type, st)
    vh = zlib.crc32(instruction.lower().encode())
    seeds = [(parent.seed * 31 + vh + i * 7919) % 999_000 + 1000 for i in range(req.count)]
    ids = [new_id("dsn") for _ in range(req.count)]
    look_offset = len(store.designs)
    urls = await render_many([
        direction_svc.render_job(design_id=ids[i], trend=eff, garment_type=parent.garment_type, prompt=prompt,
                                 seed=seeds[i], base_seed=base_seed, label=instruction,
                                 look_number=look_offset + i + 1)
        for i in range(req.count)
    ])
    store.directions[d.id] = d
    designs: list[Design] = []
    for i, url in enumerate(urls):
        child = Design(id=ids[i], trend_id=trend.id, parent_design_id=parent.id, image_url=url, prompt=prompt,
                       garment_type=parent.garment_type, vibe=instruction, seed=seeds[i], direction_id=d.id,
                       collection_id=parent.collection_id)
        direction_svc.remember(child, base_seed, vibes, st)
        designs.append(child)
    return DirectResponse(direction=d, designs=designs)


@router.get("/api/directions/{direction_id}", response_model=CreativeDirection, response_model_exclude_none=True)
async def get_direction(direction_id: str) -> CreativeDirection:
    d = store.directions.get(direction_id)
    if d is None:
        raise HTTPException(404, f"direction '{direction_id}' not found")
    return d


@router.post("/api/collections/generate", response_model=Collection, response_model_exclude_none=True)
async def generate_collection(req: CollectionRequest) -> Collection:
    trend = store.trends.get(req.trend_id)
    if trend is None:
        raise HTTPException(404, f"trend '{req.trend_id}' not found")
    plan = await collection_svc.plan_collection(trend, req.size)
    cid = new_id("col")
    rng = random.Random()
    seeds = [rng.randint(1000, 999_999) for _ in plan.pieces]  # diffusion seeds (a model parameter, not data)
    ids = [new_id("dsn") for _ in plan.pieces]
    states = [collection_svc.piece_state(p) for p in plan.pieces]
    effs = [trend.model_copy(update={"color_palette": p.palette, "key_fabrics": p.fabrics}) for p in plan.pieces]
    for st in states:
        st.prompt_additions = [f"part of the '{plan.name}' capsule collection"]
    prompts = [direction_svc.build_directed_prompt(effs[i], p.garment_type, states[i])
               for i, p in enumerate(plan.pieces)]
    urls = await render_many([
        direction_svc.render_job(design_id=ids[i], trend=effs[i], garment_type=p.garment_type, prompt=prompts[i],
                                 seed=seeds[i], base_seed=seeds[i],
                                 label=f"{plan.name} · look {i + 1} of {len(plan.pieces)}", look_number=i + 1)
        for i, p in enumerate(plan.pieces)
    ])
    designs: list[Design] = []
    looks: list[CollectionLook] = []
    for i, (p, url) in enumerate(zip(plan.pieces, urls)):
        d = Design(id=ids[i], trend_id=trend.id, image_url=url, prompt=prompts[i], garment_type=p.garment_type,
                   seed=seeds[i], collection_id=cid)
        direction_svc.remember(d, seeds[i], [], states[i])
        designs.append(d)
        looks.append(CollectionLook(design_id=d.id, title=f"Look {i + 1:02d} - {p.garment_type[0].upper() + p.garment_type[1:]}",
                                    caption=p.note))
    col = Collection(id=cid, trend_id=trend.id, name=plan.name, story=plan.story, designs=designs, looks=looks,
                     generated_by=plan.generated_by or None)
    store.collections[cid] = col
    return col


@router.get("/api/collections/{collection_id}", response_model=Collection, response_model_exclude_none=True)
async def get_collection(collection_id: str) -> Collection:
    col = store.collections.get(collection_id)
    if col is None:
        raise HTTPException(404, f"collection '{collection_id}' not found")
    return col
