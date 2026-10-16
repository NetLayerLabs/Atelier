"""In-memory store. Single process, single event loop - no locking needed."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Any

from .models import Collection, CreativeDirection, Design, PipelineRun, TrendAnalysis


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(3)}"


@dataclass
class DesignMeta:
    """Backend-only render state (not part of the contract)."""

    base_seed: int  # drives the silhouette "family"; inherited by refinements
    vibes: list[str] = field(default_factory=list)  # accumulated creative directions
    direction: Any = None  # services.direction.DirectionState: lineage of structured directions (v2)


class Store:
    def __init__(self) -> None:
        self.trends: dict[str, TrendAnalysis] = {}
        self.designs: dict[str, Design] = {}
        self.design_meta: dict[str, DesignMeta] = {}
        self.runs: dict[str, PipelineRun] = {}
        self.directions: dict[str, CreativeDirection] = {}
        self.collections: dict[str, Collection] = {}
        self.run_meta: dict[str, dict] = {}  # backend-only per-run state (quote factors, demand speed…)
        self.unmatched_quotes: dict[str, dict] = {}  # inbound quotes that match no run, until a person assigns them
        self.approve_keys: dict[str, str] = {}  # Idempotency-Key (approve) -> run id

    def clear(self) -> None:
        self.trends.clear()
        self.designs.clear()
        self.design_meta.clear()
        self.runs.clear()
        self.directions.clear()
        self.collections.clear()
        self.run_meta.clear()
        self.unmatched_quotes.clear()
        self.approve_keys.clear()
        from .services import guardrails  # v4: the brand guardrails are in-memory state too

        guardrails.reset()


store = Store()
