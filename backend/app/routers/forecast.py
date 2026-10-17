"""v3: explained production forecast ("How many should we make?"). Deterministic maths, no LLM."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services.forecast import Forecast, ForecastRequest, forecast, request_for_run
from ..store import store

router = APIRouter(prefix="/api", tags=["forecast"])


# Plain `def`: FastAPI runs these in its thread pool, so the maths never blocks the event loop (review, 17 Oct).
@router.post("/forecast", response_model=Forecast, response_model_exclude_none=True)
def post_forecast(req: ForecastRequest) -> Forecast:
    """Stateless: orders + economics + window (+ optional assumptions) -> Forecast."""
    try:
        return forecast(req)
    except ValueError as e:  # e.g. an unparseable timestamp
        raise HTTPException(422, str(e)) from e


@router.get("/runs/{run_id}/forecast", response_model=Forecast, response_model_exclude_none=True)
def run_forecast(run_id: str) -> Forecast:
    """Forecast for a pipeline run: selected quote (cost, MOQ, sample cost), retail price and the run's orders."""
    run = store.runs.get(run_id)
    if run is None:
        raise HTTPException(404, f"run '{run_id}' not found")
    try:
        req = request_for_run(run)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    try:
        return forecast(req)
    except ValueError as e:  # e.g. demand beyond the exact table (NegBinom.MAX_TABLE)
        raise HTTPException(422, str(e)) from e
