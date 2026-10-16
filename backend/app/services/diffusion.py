"""Design image generation on the live diffusion server (AMD). v5: no SVG mock renders - a concept image only ever
comes from the diffusion model; without it the request fails with errors.ServiceError("diffusion")."""

from __future__ import annotations

import base64
import logging

from ..config import GENERATED_DIR, get_settings, host_of
from ..models import InferenceCall, TrendAnalysis
from . import telemetry
from .colors import color_name
from .errors import NotConfigured, ServiceError
from .http import async_client, bearer

log = logging.getLogger("atelier.diffusion")

NEGATIVE_PROMPT = (
    "blurry, low quality, deformed, extra limbs, text, watermark, logo, cropped garment, "
    "busy background, mannequin seams, jpeg artifacts"
)


def build_prompt(trend: TrendAnalysis, garment_type: str, vibes: list[str]) -> str:
    """Diffusion prompt. The garment noun ALWAYS comes from the trend/design - never hardcoded."""
    sil = ", ".join(trend.core_silhouettes[:3]) or garment_type
    colors = ", ".join(f"{color_name(c)} ({c})" for c in trend.color_palette[:4])
    fabrics = ", ".join(trend.key_fabrics[:3])
    prompt = (
        f"High fashion editorial photography, isolated on a seamless off-white studio background, "
        f"a {garment_type} featuring {sil}, colored in {colors}, made of {fabrics}, "
        f"embodying the '{trend.trend_name}' trend"
    )
    vibes = [v.strip() for v in vibes if v and v.strip()]
    if vibes:
        prompt += ". Creative direction: " + "; ".join(vibes)
    prompt += ". Full garment visible, soft key light, highly detailed fabric texture, sharp focus, 8k"
    return prompt


# --------------------------------------------------------------------------- live adapter


async def _call_diffusion_endpoint(prompt: str, negative_prompt: str, seed: int,
                                   width: int, height: int) -> bytes:
    """THE ONLY FUNCTION THAT KNOWS THE DIFFUSION SERVER'S WIRE FORMAT.

    Assumed contract (adapt here for Automatic1111 `/sdapi/v1/txt2img`, ComfyUI, a custom
    diffusers/FastAPI wrapper on the MI300X, etc.):

        POST {AMD_DIFFUSION_ENDPOINT}
        {"prompt", "negative_prompt", "seed", "width", "height"}
        -> {"images": ["<base64 png>", ...]}

    Optional response fields (sent by deploy/diffusion_server.py) feed the Inference panel:
    "model", "device" (torch.cuda.get_device_name), "elapsedMs" (GPU compute time), "steps".
    """
    s = get_settings()
    host = host_of(s.amd_diffusion_endpoint)
    timer = telemetry.Timer()
    try:
        async with async_client(s.atelier_diffusion_timeout) as client:
            r = await client.post(
                s.amd_diffusion_endpoint,
                json={"prompt": prompt, "negative_prompt": negative_prompt, "seed": seed,
                      "width": width, "height": height},
                headers=bearer(s.amd_diffusion_api_key),
            )
            r.raise_for_status()
            data = r.json()
        images = data.get("images") if isinstance(data, dict) else None
        if not images:
            raise ValueError(f"diffusion response has no images: {str(data)[:200]}")
        b64 = images[0]
        if isinstance(b64, dict):  # some wrappers return [{"b64_json": ...}]
            b64 = b64.get("b64_json") or b64.get("image") or ""
        if "," in b64[:100] and b64.startswith("data:"):
            b64 = b64.split(",", 1)[1]
        png = base64.b64decode(b64)
    except Exception as e:  # noqa: BLE001
        telemetry.failed_live(service="diffusion", purpose="design_render", model=None, host=host, timer=timer,
                              error=f"{e.__class__.__name__}: {e}")
        raise
    latency = timer.ms
    server_ms = data.get("elapsedMs") if isinstance(data.get("elapsedMs"), (int, float)) else None
    device = data.get("device") if isinstance(data.get("device"), str) else None
    telemetry.record(InferenceCall(
        id=telemetry.new_call_id(), service="diffusion", purpose="design_render",
        model=str(data.get("model") or "") or None, endpoint_host=host,
        gpu=telemetry.gpu_label() or device,  # configured label, else the device the server itself reports
        latency_ms=latency, server_ms=server_ms, images=1,
        images_per_sec=telemetry.rate(1, server_ms or latency),
        detail=f"{width}x{height}" + (f" · {data['steps']} steps" if data.get("steps") else ""),
    ))
    return png


# --------------------------------------------------------------------------- public API


async def render_design(*, design_id: str, trend: TrendAnalysis, garment_type: str, prompt: str,
                        seed: int, base_seed: int, vibes: list[str], look_number: int) -> tuple[str, str]:
    """Returns (absolute PNG URL, "live"). Raises errors.ServiceError when the diffusion server is missing or fails."""
    s = get_settings()
    if not s.diffusion_live:
        raise NotConfigured("diffusion", "Diffusion model not connected - no concepts can be rendered")
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    try:
        png = await _call_diffusion_endpoint(prompt, NEGATIVE_PROMPT, seed,
                                             s.atelier_diffusion_width, s.atelier_diffusion_height)
    except Exception as e:  # noqa: BLE001
        log.warning("diffusion render %s failed at %s: %s: %s", design_id, host_of(s.amd_diffusion_endpoint),
                    e.__class__.__name__, e)
        raise ServiceError("diffusion", f"The diffusion server at {host_of(s.amd_diffusion_endpoint)} failed: "
                                        f"{e.__class__.__name__}: {str(e)[:160]}") from e
    (GENERATED_DIR / f"{design_id}.png").write_bytes(png)
    return s.public_url(f"/static/generated/{design_id}.png"), "live"


async def render_many(jobs: list[dict]) -> list[str]:
    """Render several designs concurrently. Returns URLs for every job, or raises the first ServiceError when
    any render failed (a partial set is not returned: the caller retries the whole request)."""
    import asyncio

    results = await asyncio.gather(*[render_design(**j) for j in jobs], return_exceptions=True)
    errs = [r for r in results if isinstance(r, BaseException)]
    if errs:
        e = errs[0]
        if isinstance(e, ServiceError):
            raise e
        raise ServiceError("diffusion", f"render failed: {e.__class__.__name__}: {str(e)[:160]}") from e
    return [url for url, _ in results]  # type: ignore[misc]
