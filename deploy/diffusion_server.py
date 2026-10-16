"""Minimal diffusion server for the AMD GPU box (PyTorch ROCm + diffusers + FastAPI).

Implements exactly the contract backend/app/services/diffusion.py expects:

    POST /generate  {"prompt", "negative_prompt"?, "seed"?, "width"?, "height"?, "steps"?, "guidance_scale"?}
      -> {"images": ["<base64 png>"], "model", "device", "elapsedMs", "steps", "seed", "width", "height"}
    GET  /health    -> {"status": "ok" | "loading" | "error", "model", "device", "dtype", "torch", "hip"}

"device" is torch.cuda.get_device_name(0) — what the GPU itself reports (e.g. "AMD Instinct MI300X"),
"elapsedMs" is the pipeline call alone (GPU time + scheduler), so the dashboard can show real images/sec.

Env:
    DIFFUSION_MODEL    default black-forest-labs/FLUX.1-schnell (gated "auto": accept on HF + HF_TOKEN)
                       alternatives: stabilityai/stable-diffusion-xl-base-1.0, black-forest-labs/FLUX.2-klein-4B
    DIFFUSION_STEPS    default: 4 for *schnell*/*klein*/*turbo*, else 30
    DIFFUSION_GUIDANCE default: 0.0 for schnell/turbo, else 5.0
    DIFFUSION_DTYPE    bfloat16 (default) | float16
    DIFFUSION_API_KEY  optional; if set, POST /generate requires "Authorization: Bearer <key>"
    DIFFUSION_WARMUP   1 (default) runs one tiny generation at startup so the first stage demo isn't slow

Run (inside a ROCm PyTorch container, see deploy/serve_diffusion.sh):
    pip install -r deploy/requirements-diffusion.txt
    uvicorn diffusion_server:app --host 127.0.0.1 --port 8002 --app-dir deploy
"""

from __future__ import annotations

import base64
import inspect
import io
import logging
import os
import threading
import time
from typing import Any, Optional

import torch
from diffusers import DiffusionPipeline
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

log = logging.getLogger("diffusion_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

MODEL = os.environ.get("DIFFUSION_MODEL", "black-forest-labs/FLUX.1-schnell")
_fast = any(k in MODEL.lower() for k in ("schnell", "klein", "turbo", "lightning"))
STEPS = int(os.environ.get("DIFFUSION_STEPS", "4" if _fast else "30"))
GUIDANCE = float(os.environ.get("DIFFUSION_GUIDANCE", "0.0" if ("schnell" in MODEL.lower() or "turbo" in MODEL.lower()) else "5.0"))
DTYPE = {"float16": torch.float16, "fp16": torch.float16}.get(os.environ.get("DIFFUSION_DTYPE", "").lower(), torch.bfloat16)
API_KEY = os.environ.get("DIFFUSION_API_KEY", "")
WARMUP = os.environ.get("DIFFUSION_WARMUP", "1") == "1"

state: dict[str, Any] = {"status": "loading", "pipe": None, "error": None, "accepts": set()}
_lock = threading.Lock()  # one generation at a time on the GPU; FastAPI runs sync handlers in a threadpool

app = FastAPI(title="Atelier diffusion server")


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    negative_prompt: Optional[str] = None
    seed: Optional[int] = None
    width: int = Field(default=768, ge=256, le=2048)
    height: int = Field(default=1024, ge=256, le=2048)
    steps: Optional[int] = Field(default=None, ge=1, le=100)
    guidance_scale: Optional[float] = None


def _device_name() -> str:
    try:
        return torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    except Exception:  # noqa: BLE001
        return "unknown"


def _load() -> None:
    try:
        t0 = time.perf_counter()
        log.info("loading %s (%s) on %s", MODEL, DTYPE, _device_name())
        pipe = DiffusionPipeline.from_pretrained(MODEL, torch_dtype=DTYPE, token=os.environ.get("HF_TOKEN") or None)
        pipe = pipe.to("cuda" if torch.cuda.is_available() else "cpu")
        pipe.set_progress_bar_config(disable=True)
        state["accepts"] = set(inspect.signature(pipe.__call__).parameters)
        state["pipe"] = pipe
        log.info("loaded in %.1fs", time.perf_counter() - t0)
        if WARMUP:
            _generate(GenerateRequest(prompt="warmup", width=512, height=512, steps=1, seed=0))
            log.info("warmup done")
        state["status"] = "ok"
    except Exception as e:  # noqa: BLE001
        log.exception("failed to load pipeline")
        state["status"], state["error"] = "error", f"{e.__class__.__name__}: {e}"


def _generate(req: GenerateRequest) -> dict[str, Any]:
    pipe = state["pipe"]
    accepts = state["accepts"]
    w, h = req.width // 16 * 16, req.height // 16 * 16  # Flux needs multiples of 16 (SDXL: 8)
    seed = req.seed if req.seed is not None else int(time.time()) % 2**31
    steps = req.steps or STEPS
    kwargs: dict[str, Any] = {"prompt": req.prompt, "width": w, "height": h, "num_inference_steps": steps,
                              "generator": torch.Generator(device="cpu").manual_seed(seed)}
    if "guidance_scale" in accepts:
        kwargs["guidance_scale"] = req.guidance_scale if req.guidance_scale is not None else GUIDANCE
    if req.negative_prompt and "negative_prompt" in accepts and "flux" not in MODEL.lower():
        kwargs["negative_prompt"] = req.negative_prompt  # Flux ignores/needs true CFG for negatives; skip
    if "max_sequence_length" in accepts and "schnell" in MODEL.lower():
        kwargs["max_sequence_length"] = 256
    with _lock:
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        image = pipe(**kwargs).images[0]
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        elapsed = (time.perf_counter() - t0) * 1000.0
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return {"images": [base64.b64encode(buf.getvalue()).decode()], "model": MODEL, "device": _device_name(),
            "elapsedMs": round(elapsed, 1), "steps": steps, "seed": seed, "width": w, "height": h}


@app.on_event("startup")
def _startup() -> None:
    threading.Thread(target=_load, daemon=True).start()


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": state["status"], "model": MODEL, "device": _device_name(), "dtype": str(DTYPE),
            "torch": torch.__version__, "hip": getattr(torch.version, "hip", None), "error": state["error"]}


@app.post("/generate")
def generate(req: GenerateRequest, authorization: Optional[str] = Header(None)) -> dict[str, Any]:
    if API_KEY and authorization != f"Bearer {API_KEY}":
        raise HTTPException(401, "missing or wrong bearer key")
    if state["status"] != "ok":
        raise HTTPException(503, f"model {state['status']}: {state['error'] or 'still loading'}")
    return _generate(req)
