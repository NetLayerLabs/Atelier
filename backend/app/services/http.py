"""One place that builds outbound HTTP clients.

Every upstream call (vLLM, VLM, diffusion, Evolus, Shopify, FX, health probes) goes through `async_client`,
so timeouts are always explicit and tests can route all traffic to in-process fakes with
`set_transport(httpx.ASGITransport(app=fake_app))`.

v5: every response is checked for the fake-upstream marker header (tests/fake_upstreams.py sets it), so a
configured endpoint that is really the local test double is reported as "FAKE UPSTREAM - not real".
"""

from __future__ import annotations

import httpx

_transport: httpx.AsyncBaseTransport | None = None


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Test hook: route every outbound request through `transport` (None restores the network)."""
    global _transport
    _transport = transport


async def _mark_fake(response: httpx.Response) -> None:
    from . import telemetry

    telemetry.note_response(response.request.url.netloc.decode() if isinstance(response.request.url.netloc, bytes)
                            else str(response.request.url.netloc), response.headers)


def async_client(timeout: float, **kwargs) -> httpx.AsyncClient:
    hooks = kwargs.pop("event_hooks", None) or {}
    hooks = {**hooks, "response": [*hooks.get("response", []), _mark_fake]}
    return httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=min(timeout, 10.0)),
                             transport=_transport, event_hooks=hooks, **kwargs)


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"} if key else {}
