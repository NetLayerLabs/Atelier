from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from ..models import TelemetryResponse
from ..services import telemetry

router = APIRouter(prefix="/api", tags=["telemetry"])


@router.get("/telemetry", response_model=TelemetryResponse, response_model_exclude_none=True)
async def get_telemetry(limit: int = Query(50, ge=0, le=500),
                        service: Optional[str] = Query(None, pattern="^(llm|vision|diffusion|evolus)$")
                        ) -> TelemetryResponse:
    """Recent measured inference calls (newest first) + aggregates per service. fake=true marks the test double."""
    return telemetry.snapshot(limit=limit, service=service)
