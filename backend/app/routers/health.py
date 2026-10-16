"""GET /api/health - what is really connected (CONTRACT.md v5).

Every configured service is probed (short timeout, cached). Each reports `status`:
  connected       configured and answering
  unreachable     configured but the probe failed (detail says why)
  not_configured  its env vars are not set (hint says which)
There is no mock mode. `fake: true` marks an endpoint that is the local test double (tests/fake_upstreams.py):
its detail starts with "FAKE UPSTREAM - not real", and it never counts towards `poweredBy`.
"""

from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Request

from .. import security
from ..config import get_settings
from ..models import HealthResponse, PoweredBy, SecuritySummary, ServiceStatus
from ..services import probe, telemetry
from ..services.errors import HINTS

router = APIRouter(prefix="/api", tags=["health"])

FAKE_PREFIX = "FAKE UPSTREAM - not real · "


def _probed(name: str, r: probe.ProbeResult, hint: str | None = None) -> ServiceStatus:
    detail = (FAKE_PREFIX if r.fake else "") + r.detail
    return ServiceStatus(name=name, status="connected" if r.ok else "unreachable", healthy=r.ok, detail=detail,
                         hint=None if r.ok else hint, fake=r.fake, model=r.model, host=r.host,
                         latency_ms=r.latency_ms)


def _with(st: ServiceStatus, prefix: str) -> str:
    """Prepend `prefix` to the detail, keeping the FAKE UPSTREAM marker first."""
    rest = (st.detail or "").removeprefix(FAKE_PREFIX)
    return (FAKE_PREFIX if st.fake else "") + prefix + rest


def _off(name: str, detail: str, hint: str | None) -> ServiceStatus:
    return ServiceStatus(name=name, status="not_configured", healthy=False, detail=detail, hint=hint)


@router.get("/health", response_model=HealthResponse, response_model_exclude_none=True)
async def health(request: Request) -> HealthResponse:
    s = get_settings()
    gpu = telemetry.gpu_label()

    async def vision() -> ServiceStatus:
        if not s.vision_live:
            return _off("vision", "Not connected - mood boards can't be analysed", HINTS["vision"])
        st = _probed("vision", await probe.probe_openai(s.amd_vision_endpoint, s.amd_vllm_api_key,
                                                                s.amd_vision_model), HINTS["vision"])
        st.gpu = gpu
        return st

    async def llm() -> ServiceStatus:
        if not s.llm_live:
            return _off("llm", "Not connected - AMD vLLM (direct brain path) is not configured", HINTS["llm"])
        st = _probed("llm", await probe.probe_openai(s.amd_vllm_endpoint, s.amd_vllm_api_key,
                                                             s.amd_vllm_model), HINTS["llm"])
        st.gpu = gpu
        return st

    async def diffusion() -> ServiceStatus:
        if not s.diffusion_live:
            return _off("diffusion", "Not connected - concepts can't be rendered", HINTS["diffusion"])
        r = await probe.probe_diffusion(s.amd_diffusion_endpoint)
        st = _probed("diffusion", r, HINTS["diffusion"])
        st.gpu = gpu or r.device
        return st

    async def evolus(name: str, live: bool, workflow: str, off: str, hint: str) -> ServiceStatus:
        if not live:
            return _off(name, off, hint)
        st = _probed(name, await probe.probe_evolus(), hint)
        st.detail = _with(st, f"workflow {workflow} · ")
        return st

    async def shopify() -> ServiceStatus:
        if not s.shopify_admin_ready:
            return _off("shopify", "Not connected - no pre-orders can be opened", HINTS["shopify"])
        return _probed("shopify", await probe.probe_shopify(), HINTS["shopify"])

    async def agent() -> ServiceStatus:  # v3: the brain
        if not s.evolus_agent_live:
            nxt = "the brain runs on AMD vLLM directly" if s.llm_live else "no brain is connected"
            return _off("evolus_agent", f"Evolus agent not configured - {nxt}", HINTS["brain"])
        st = _probed("evolus_agent", await probe.probe_evolus(), HINTS["brain"])
        st.model = s.evolus_agent_model
        st.detail = _with(st, f"agent {s.evolus_agent_model} → {s.evolus_agent_backend}"
                              f"{' (' + s.evolus_agent_label + ')' if s.evolus_agent_label else ''} · ")
        return st

    async def extractor() -> ServiceStatus:  # v3: quote documents
        if not s.evolus_extractor_live:
            eng = "the AMD LLM over the PDF text" if s.llm_live else "the local PDF text parser (text PDFs only)"
            return _off("evolus_extractor", f"Evolus extractor not configured - quote documents are read by {eng}",
                        "Set EVOLUS_EXTRACTOR_AGENT_ID and EVOLUS_EXTRACTOR_ID - docs/EVOLUS_SETUP.md.")
        st = _probed("evolus_extractor", await probe.probe_evolus())
        st.detail = _with(st, f"extractor {s.evolus_extractor_id} · ")
        return st

    services = list(await asyncio.gather(
        vision(), diffusion(), llm(), agent(), extractor(),
        evolus("evolus_outreach", s.evolus_outreach_live, s.evolus_outreach_workflow_id,
               "Not connected - RFQs can be drafted but not sent", HINTS["evolus_outreach"]),
        evolus("evolus_po", s.evolus_po_live, s.po_workflow_id,
               "Not connected - purchase orders stay drafts (not sent)", HINTS["evolus_po"]),
        evolus("evolus_shopify", s.evolus_shopify_live, s.evolus_shopify_workflow_id,
               "Evolus Shopify workflow not configured (Atelier calls the Shopify Admin API directly)",
               "Optional: set EVOLUS_SHOPIFY_WORKFLOW_ID - docs/EVOLUS_SETUP.md."),
        shopify(),
    ))
    _mark_optional(services)
    return HealthResponse(services=services, powered_by=powered_by(services),
                          fake_upstreams=any(x.fake for x in services),
                          security=SecuritySummary.model_validate(security.summary(request)))


def _mark_optional(services: list[ServiceStatus]) -> None:
    """Backups that aren't needed while their alternative is connected are reported as optional, not missing."""
    up = {x.name for x in services if x.status == "connected" and not x.fake}
    for x in services:
        if x.status == "connected":
            continue
        if x.name == "llm" and "evolus_agent" in up:
            x.optional = True
            x.detail = ("Optional - the brain already runs through the Evolus agent. This direct path is a backup "
                        "for our own AMD vLLM droplet.")
        elif x.name == "evolus_shopify" and "shopify" in up:
            x.optional = True
            x.detail = "Optional - Atelier already publishes pre-orders through the Shopify Admin API directly."


_AMD = re.compile(r"\b(amd|instinct|radeon|rocm|mi\d{3}[a-z]*)\b", re.IGNORECASE)


def is_amd_device(label: str | None) -> bool:
    """True when a GPU label names an AMD device ("AMD Instinct MI300X", "MI300X", "ROCm …"). Anything else -
    unset, "cuda:0", a test label - is not verified AMD hardware."""
    return bool(label and _AMD.search(label))


def powered_by(services: list[ServiceStatus]) -> PoweredBy:
    """Which credits may be shown. Only endpoints we probe ourselves count (the Evolus agent's model can't be verified
    from here), never a fake one, and "AMD" needs the hardware verified: AMD_GPU_LABEL naming an AMD device, or the
    diffusion server reporting one. A model that answers on unverified hardware is `model_connected` only."""
    real = [x for x in services if x.status == "connected" and not x.fake]
    models = [x for x in real if x.name in ("vision", "diffusion", "llm")]
    hw = next((x.gpu for x in models if is_amd_device(x.gpu)), None)
    return PoweredBy(amd=hw is not None, evolus=any(x.name.startswith("evolus") for x in real),
                     model_connected=bool(models), hardware=hw)
