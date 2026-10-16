"""Per-call inference telemetry: an in-memory ring buffer plus per-pipeline-step collection.

Honesty rules (the Inference panel is shown to judges):
  * live calls record only what was measured (wall-clock latency, time-to-first-token when streamed)
    or reported by the server (OpenAI `usage`, the diffusion server's compute time / device);
    a missing number stays None, it is never estimated.
  * the GPU label comes from AMD_GPU_LABEL (or the device name the diffusion server reports);
    it is never guessed.
  * v5: there are no simulated calls. Calls to an endpoint that identified itself as the local test double
    (tests/fake_upstreams.py) are recorded with fake=True so the UI can say so.
"""

from __future__ import annotations

import secrets
import time
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

from ..config import get_settings
from ..models import InferenceCall, ServiceTelemetry, TelemetryResponse

_buffer: deque[InferenceCall] = deque(maxlen=300)
_collector: ContextVar[Optional[list[InferenceCall]]] = ContextVar("atelier_telemetry", default=None)
# v5: hosts whose responses carried the fake-upstream marker (set by the health probes / clients).
FAKE_HOSTS: set[str] = set()
FAKE_HEADER = "x-atelier-fake-upstream"


def note_response(host: Optional[str], headers) -> None:
    """Remember a host that answered with the fake-upstream marker header."""
    try:
        if host and headers is not None and headers.get(FAKE_HEADER):
            FAKE_HOSTS.add(host)
    except Exception:  # noqa: BLE001
        pass


def _resize() -> None:
    global _buffer
    size = max(10, int(get_settings().atelier_telemetry_size))
    if _buffer.maxlen != size:
        _buffer = deque(_buffer, maxlen=size)


def new_call_id() -> str:
    return f"inf_{secrets.token_hex(4)}"


def gpu_label() -> Optional[str]:
    label = get_settings().amd_gpu_label.strip()
    return label or None


def record(call: InferenceCall) -> InferenceCall:
    if call.endpoint_host and call.endpoint_host in FAKE_HOSTS:
        call.fake = True
    _resize()
    _buffer.append(call)
    bucket = _collector.get()
    if bucket is not None:
        bucket.append(call)
    return call


def clear() -> None:
    _buffer.clear()


@contextmanager
def collect(bucket: list[InferenceCall]) -> Iterator[list[InferenceCall]]:
    """Every call recorded inside this block (including child asyncio tasks) is also appended to `bucket`."""
    token = _collector.set(bucket)
    try:
        yield bucket
    finally:
        _collector.reset(token)


def rate(count: Optional[float], ms: Optional[float]) -> Optional[float]:
    if not count or not ms or ms <= 0:
        return None
    return round(count / (ms / 1000.0), 1)


class Timer:
    def __init__(self) -> None:
        self.t0 = time.perf_counter()
        self.first: Optional[float] = None

    def mark_first(self) -> None:
        if self.first is None:
            self.first = time.perf_counter()

    @property
    def ms(self) -> float:
        return round((time.perf_counter() - self.t0) * 1000.0, 1)

    @property
    def ttft_ms(self) -> Optional[float]:
        return None if self.first is None else round((self.first - self.t0) * 1000.0, 1)


def live_llm_call(*, service: str, purpose: str, model: str, host: str, timer: Timer,
                  usage: Optional[dict], ok: bool, attempt: int, error: Optional[str] = None,
                  images: Optional[int] = None, route: Optional[str] = None,
                  detail: Optional[str] = None) -> InferenceCall:
    latency = timer.ms
    ttft = timer.ttft_ms
    pt = ct = tt = None
    if usage:
        pt, ct, tt = usage.get("prompt_tokens"), usage.get("completion_tokens"), usage.get("total_tokens")
    decode_ms = latency - ttft if ttft is not None and latency > ttft else latency
    return record(InferenceCall(
        id=new_call_id(), service=service, purpose=purpose, ok=ok,
        model=model, endpoint_host=host, gpu=gpu_label(), latency_ms=latency, ttft_ms=ttft,
        prompt_tokens=pt, completion_tokens=ct, total_tokens=tt,
        tokens_per_sec=rate(ct, decode_ms) if ok else None, images=images, attempt=attempt,
        error=(error or None) and error[:300], route=route, detail=detail,
    ))


def failed_live(*, service: str, purpose: str, model: Optional[str], host: Optional[str], timer: Timer,
                error: str, attempt: int = 1, route: Optional[str] = None) -> InferenceCall:
    return record(InferenceCall(
        id=new_call_id(), service=service, purpose=purpose, ok=False,
        model=model, endpoint_host=host, gpu=gpu_label() if service != "evolus" else None,
        latency_ms=timer.ms, attempt=attempt, error=error[:300], route=route,
    ))


# --------------------------------------------------------------------------- aggregates


def _avg(xs: list[float]) -> Optional[float]:
    return round(sum(xs) / len(xs), 1) if xs else None


def _p95(xs: list[float]) -> Optional[float]:
    if not xs:
        return None
    ys = sorted(xs)
    return round(ys[min(len(ys) - 1, int(round(0.95 * (len(ys) - 1))))], 1)


def aggregates(calls: list[InferenceCall]) -> list[ServiceTelemetry]:
    """One row per service (measured calls only)."""
    groups: dict[str, list[InferenceCall]] = {}
    for c in calls:
        groups.setdefault(c.service, []).append(c)
    order = {"llm": 0, "vision": 1, "diffusion": 2, "evolus": 3}
    out: list[ServiceTelemetry] = []
    for service, cs in sorted(groups.items(), key=lambda kv: order.get(kv[0], 9)):
        okc = [c for c in cs if c.ok]
        tps = [c.tokens_per_sec for c in okc if c.tokens_per_sec]
        ips = [c.images_per_sec for c in okc if c.images_per_sec]
        last = cs[-1]
        out.append(ServiceTelemetry(
            service=service, calls=len(cs), errors=sum(1 for c in cs if not c.ok),
            avg_latency_ms=_avg([c.latency_ms for c in okc]), p95_latency_ms=_p95([c.latency_ms for c in okc]),
            avg_ttft_ms=_avg([c.ttft_ms for c in okc if c.ttft_ms is not None]),
            prompt_tokens=sum(c.prompt_tokens or 0 for c in okc),
            completion_tokens=sum(c.completion_tokens or 0 for c in okc),
            avg_tokens_per_sec=_avg(tps), peak_tokens_per_sec=max(tps) if tps else None,
            images=sum(c.images or 0 for c in okc if c.service == "diffusion"),
            avg_images_per_sec=round(sum(ips) / len(ips), 2) if ips else None,
            last_model=last.model, last_endpoint_host=last.endpoint_host,
            gpu=next((c.gpu for c in reversed(cs) if c.gpu), None), last_at=last.started_at,
        ))
    return out


def snapshot(limit: int = 50, service: Optional[str] = None) -> TelemetryResponse:
    calls = list(_buffer)
    if service:
        calls = [c for c in calls if c.service == service]
    return TelemetryResponse(
        gpu_label=gpu_label(),
        calls=list(reversed(calls))[: max(0, limit)],
        services=aggregates(calls),
    )
