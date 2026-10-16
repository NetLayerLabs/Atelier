"""Cheap, cached liveness probes for /api/health (so the header reflects reality, not just config).

  * vLLM (LLM / VLM):  GET {base}/v1/models  - reports the served model id
  * diffusion:         GET {origin}/health   - deploy/diffusion_server.py reports model + device
  * Evolus:            GET {EVOLUS_PROBE_PATH} with the REST auth headers (cached longer: 60 req/min limit)

Results are cached for ATELIER_HEALTH_CACHE_SECONDS (Evolus: EVOLUS_PROBE_CACHE_SECONDS), and every probe
uses ATELIER_HEALTH_TIMEOUT, so a dead GPU box can never make the dashboard hang.

v5: a probe that reaches the local test double (its responses carry the X-Atelier-Fake-Upstream header) reports
fake=True, so /api/health says "FAKE UPSTREAM - not real" and the credits line is never shown for it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional
from urllib.parse import urlparse

from ..config import get_settings, host_of
from . import evolus, telemetry
from .http import async_client
from .openai_compat import normalize_base_url


@dataclass
class ProbeResult:
    ok: bool
    detail: str
    latency_ms: Optional[float] = None
    model: Optional[str] = None
    host: Optional[str] = None
    fake: bool = False
    device: Optional[str] = None


def _fake(res: ProbeResult) -> ProbeResult:
    res.fake = bool(res.host and res.host in telemetry.FAKE_HOSTS)
    return res


_cache: dict[str, tuple[float, ProbeResult]] = {}


def clear_cache() -> None:
    _cache.clear()


async def _cached(key: str, ttl: float, fn: Callable[[], Awaitable[ProbeResult]]) -> ProbeResult:
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    res = _fake(await fn())
    _cache[key] = (now + max(0.0, ttl), res)
    return res


async def probe_openai(endpoint: str, api_key: str) -> ProbeResult:
    s = get_settings()

    async def run() -> ProbeResult:
        host = host_of(endpoint)
        url = normalize_base_url(endpoint) + "/models"
        hdrs = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        t = telemetry.Timer()
        try:
            async with async_client(s.atelier_health_timeout) as c:
                r = await c.get(url, headers=hdrs)
        except Exception as e:  # noqa: BLE001
            return ProbeResult(False, f"{host} · unreachable: {e.__class__.__name__}", t.ms, host=host)
        if r.status_code >= 400:
            hint = " - check AMD_VLLM_API_KEY" if r.status_code in (401, 403) else ""
            return ProbeResult(False, f"{host} · HTTP {r.status_code}{hint}", t.ms, host=host)
        try:
            ids = [m.get("id") for m in r.json().get("data", []) if isinstance(m, dict) and m.get("id")]
        except Exception:  # noqa: BLE001
            ids = []
        model = ids[0] if ids else None
        return ProbeResult(True, f"{host} · {', '.join(ids[:2]) or 'reachable'}", t.ms, model=model, host=host)

    return await _cached(f"openai:{endpoint}", s.atelier_health_cache_seconds, run)


def diffusion_health_url(endpoint: str) -> str:
    u = urlparse(endpoint)
    return f"{u.scheme}://{u.netloc}/health"


async def probe_diffusion(endpoint: str) -> ProbeResult:
    s = get_settings()

    async def run() -> ProbeResult:
        host = host_of(endpoint)
        t = telemetry.Timer()
        try:
            async with async_client(s.atelier_health_timeout) as c:
                r = await c.get(diffusion_health_url(endpoint))
        except Exception as e:  # noqa: BLE001
            return ProbeResult(False, f"{host} · unreachable: {e.__class__.__name__}", t.ms, host=host)
        if r.status_code == 404:  # a server without /health: reachable is the best we can say
            return ProbeResult(True, f"{host} · reachable (no /health endpoint)", t.ms, host=host)
        if r.status_code >= 400:
            return ProbeResult(False, f"{host} · HTTP {r.status_code}", t.ms, host=host)
        try:
            body = r.json()
        except Exception:  # noqa: BLE001
            body = {}
        model = body.get("model") if isinstance(body, dict) else None
        device = body.get("device") if isinstance(body, dict) else None
        bits = [b for b in (model, device) if b]
        if isinstance(body, dict) and body.get("status") not in (None, "ok", "ready"):
            return ProbeResult(False, f"{host} · {body.get('status')}", t.ms, model=model, host=host)
        return ProbeResult(True, f"{host} · {' · '.join(bits) or 'ok'}", t.ms, model=model, host=host,
                           device=device if isinstance(device, str) else None)

    return await _cached(f"diffusion:{endpoint}", s.atelier_health_cache_seconds, run)


async def probe_evolus() -> ProbeResult:
    s = get_settings()

    async def run() -> ProbeResult:
        ok, detail, ms = await evolus.probe()
        return ProbeResult(ok, detail, ms, host=host_of(s.evolus_api_base))

    return await _cached(f"evolus:{s.evolus_api_base}:{s.evolus_workspace_id}", s.evolus_probe_cache_seconds, run)


async def probe_shopify() -> ProbeResult:
    """v3: `{ shop { name } currentAppInstallation { accessScopes } }` - cached like Evolus (30s)."""
    from . import shopify

    s = get_settings()

    async def run() -> ProbeResult:
        host = shopify.shop_domain()
        t = telemetry.Timer()
        try:
            async with async_client(s.atelier_health_timeout) as c:
                info = await shopify.shop_info(client=c)
        except Exception as e:  # noqa: BLE001
            return ProbeResult(False, f"{host} · {str(e)[:140]}", t.ms, host=host)
        need = {"write_products", "read_orders"}
        missing = sorted(need - set(info.get("scopes") or []))
        detail = f"{info.get('name') or host} · API {s.shopify_api_version}"
        if missing:
            return ProbeResult(False, f"{detail} · missing scopes: {', '.join(missing)}", t.ms, host=host)
        return ProbeResult(True, detail, t.ms, host=host)

    return await _cached(f"shopify:{s.shopify_base}", s.evolus_probe_cache_seconds, run)
