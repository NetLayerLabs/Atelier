"""The agent's brain: one chain of REAL models for every generative step (CONTRACT.md v3, v5).

    1. evolus-agent → AMD vLLM   the Evolus agent (EVOLUS_AGENT_MODEL = "<appId>:<agentId>") over Evolus's
                                 OpenAI-compatible endpoint. The agent's model is our AMD vLLM endpoint,
                                 connected in the Evolus workspace, with the knowledge library attached.
    2. direct vLLM               our AMD vLLM endpoint called directly (AMD_VLLM_ENDPOINT)

v5: there is no template fallback. Each path validates the model's JSON against the caller's schema and retries
once; when neither path is configured or both fail, BrainUnavailable (an errors.ServiceError, service "brain") is
raised and the caller shows an honest error with a retry.

Both live paths are grounded in the knowledge library (brand book + supplier catalogue): passages are
retrieved (Evolus library search, or the Brand workspace documents locally) and put in the prompt with numbers, the model
returns "sources": [numbers], and the result carries those passages as Citations.
Every attempt is recorded in telemetry with `route` set, so the Inference panel shows which path ran.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Optional, TypeVar

from ..config import get_settings, host_of
from ..models import Citation
from . import knowledge
from .errors import ServiceError

log = logging.getLogger("atelier.brain")
T = TypeVar("T")

ROUTE_AGENT = f"evolus-agent → {get_settings().evolus_agent_backend}"  # where the agent's model is served
ROUTE_DIRECT = "direct vLLM"

MessagesFn = Callable[[int, str], list[dict]]


class BrainUnavailable(ServiceError):
    """No live path produced a valid answer (or none is configured)."""

    def __init__(self, message: str, *, not_configured: bool = False):
        super().__init__("brain", message, not_configured=not_configured)


@dataclass
class Thought(Generic[T]):
    value: T
    route: str
    model: str
    host: str
    citations: list[Citation] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # failures of earlier paths in the chain

    @property
    def label(self) -> str:
        """For pipeline logs: "Evolus agent app:agent → AMD vLLM (gemma-4…)" / "gemma-4… via direct vLLM @ host"."""
        s = get_settings()
        if self.route == ROUTE_AGENT:
            on = s.evolus_agent_label or s.amd_vllm_model or s.evolus_own_model_name or "the agent's own model"
            return f"Evolus agent {self.model} → {s.evolus_agent_backend} ({on})"
        return f"{self.model} via direct vLLM @ {self.host}"


def plan() -> list[str]:
    """The routes that will be tried, in order (for logs and /api/health)."""
    s = get_settings()
    routes = []
    if s.evolus_agent_live:
        routes.append(ROUTE_AGENT)
    if s.llm_live:
        routes.append(ROUTE_DIRECT)
    return routes


def _pick_citations(data: Any, retrieved: list[Citation]) -> list[Citation]:
    """The passages the model says it used ("sources": [1, 3] or titles); all retrieved if it named none."""
    if not retrieved:
        return []
    refs = data.get("sources") or data.get("citations") if isinstance(data, dict) else None
    chosen: list[Citation] = []
    if isinstance(refs, list):
        for r in refs:
            idx = None
            if isinstance(r, (int, float)) or (isinstance(r, str) and r.strip().strip("[]").isdigit()):
                idx = int(str(r).strip().strip("[]")) - 1
            if idx is not None and 0 <= idx < len(retrieved):
                c = retrieved[idx]
            elif isinstance(r, str):
                c = next((x for x in retrieved if r.lower()[:30] in x.source.lower()), None)
            else:
                c = None
            if c is not None and c not in chosen:
                chosen.append(c)
    return chosen or list(retrieved)



def _why(e: Exception) -> str:
    """A readable reason, also for exceptions without a message (httpx.ReadTimeout() -> "timed out")."""
    text = str(e).strip()
    if not text:
        name = e.__class__.__name__
        text = "timed out (the model took too long to answer)" if "Timeout" in name else name
    return text[:160]

async def think_json(purpose: str, messages: MessagesFn, validate: Callable[[Any], T], *,
                     knowledge_query: Optional[str] = None, max_tokens: int = 1500, temperature: float = 0.4,
                     timeout: Optional[float] = None) -> Thought[T]:
    """Run the chain. Raises BrainUnavailable when neither live path is configured or both failed."""
    s = get_settings()
    retrieved: list[Citation] = []
    if knowledge_query and (s.evolus_agent_live or s.llm_live):
        try:
            retrieved, _where = await knowledge.search(knowledge_query)
        except Exception as e:  # noqa: BLE001
            log.warning("knowledge search failed: %s", e)
    context = knowledge.context_block(retrieved)
    captured: dict[str, Any] = {}

    def checked(data: Any) -> T:
        value = validate(data)  # raises -> retry
        captured["data"] = data
        return value

    errors: list[str] = []
    if s.evolus_agent_live:
        from . import evolus

        try:
            value, meta = await evolus.agent_chat_json(messages_for_attempt=lambda a: messages(a, context),
                                                      validate=checked, purpose=purpose, max_tokens=max_tokens,
                                                      temperature=temperature)
            cites = _pick_citations(captured.get("data"), retrieved)
            for c in meta.get("citations") or []:  # sources the platform itself attached to the reply
                if all(c.source != x.source for x in cites):
                    cites.append(c)
            return Thought(value, ROUTE_AGENT, s.evolus_agent_model, host_of(s.chat_base), cites, errors)
        except Exception as e:  # noqa: BLE001
            log.warning("%s: Evolus agent failed (%s: %s) -> %s", purpose, e.__class__.__name__, e,
                        "direct vLLM" if s.llm_live else "error")
            errors.append(f"Evolus agent: {_why(e)}")
    if s.llm_live:
        from .openai_compat import chat_json, make_client, resolve_model

        try:
            client = make_client(s.amd_vllm_endpoint, s.amd_vllm_api_key, timeout or s.atelier_llm_timeout)
            model = await resolve_model(client, s.amd_vllm_model)
            value = await chat_json(client, model, lambda a: messages(a, context), checked, max_tokens=max_tokens,
                                    temperature=temperature, purpose=purpose, route=ROUTE_DIRECT)
            return Thought(value, ROUTE_DIRECT, model, host_of(s.amd_vllm_endpoint),
                           _pick_citations(captured.get("data"), retrieved), errors)
        except Exception as e:  # noqa: BLE001
            log.warning("%s: direct vLLM failed (%s: %s)", purpose, e.__class__.__name__, e)
            errors.append(f"direct vLLM: {_why(e)}")
    if not errors:
        raise BrainUnavailable("No brain connected - neither the Evolus agent nor AMD vLLM is configured",
                               not_configured=True)
    raise BrainUnavailable("The brain failed: " + "; ".join(errors))
