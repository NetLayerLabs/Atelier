"""Atelier backend - FastAPI app (see CONTRACT.md)."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import GENERATED_DIR, STATIC_DIR, UPLOADS_DIR, get_settings
from .data.presets import mood_boards
from .routers import (auth, designs, direction, forecast, guardrails, health, runs, telemetry, trends, voice, webhooks,
                      workspace)
from .security import SecurityMiddleware
from .services.errors import ServiceError
from .validation import validation_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("atelier")

for d in (STATIC_DIR, GENERATED_DIR, UPLOADS_DIR):
    d.mkdir(parents=True, exist_ok=True)


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Atelier API", version="1.0.0",
                  description="Autonomous fashion & merchandising agent - AMD Developer Hackathon ACT III")
    # QA H5: Origin check + admin token / local-only for state changes (app/security.py). Added before CORS so CORS
    # stays the outer layer and the dashboard can read a 401 / 403 body.
    app.add_middleware(SecurityMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Contract: errors are non-2xx with {detail: string}
    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        parts = [validation_message(err) for err in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": "; ".join(parts) or "invalid request"})

    # v5: a real service is missing or failed -> 503 with what, why and how to set it up. Never a made-up result.
    @app.exception_handler(ServiceError)
    async def _service(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": exc.message, "service": exc.service,
                                                      "status": exc.status, "hint": exc.hint})

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return JSONResponse(status_code=exc.status_code, content={"detail": detail}, headers=exc.headers)

    app.include_router(health.router)
    app.include_router(auth.router)  # QA H5: optional admin-token sign-in
    app.include_router(trends.router)
    app.include_router(designs.router)
    app.include_router(runs.router)
    app.include_router(runs.unmatched_router)  # LOW: inbound quotes that matched no run
    app.include_router(direction.router)  # v2: creative direction + collections
    app.include_router(telemetry.router)
    app.include_router(forecast.router)  # v3: explained production forecast
    app.include_router(webhooks.router)  # v3: Shopify orders/create + Evolus inbound quotes
    app.include_router(voice.router)  # v3: customer voice
    app.include_router(guardrails.router)  # v4: brand guardrails + human hand-off
    app.include_router(workspace.router)  # v5: the Brand workspace (the brand's own data, persisted)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    boards = mood_boards()  # validates static/moodboards/manifest.json (every image present and attributed)
    ai = sum(1 for b in boards if b.ai_generated)
    log.info("Mood boards: %d openly licensed photo boards, %d brand AI-generated inspiration boards (%d images)",
             len(boards) - ai, ai, sum(len(b.images) for b in boards))
    log.info("Atelier backend up · configured: llm=%s vision=%s diffusion=%s evolus_agent=%s evolus_outreach=%s "
             "evolus_shopify=%s shopify=%s (unconfigured services report 'not connected')", s.llm_live,
             s.vision_live, s.diffusion_live, s.evolus_agent_live, s.evolus_outreach_live, s.evolus_shopify_live,
             s.shopify_admin_ready)
    log.info("State changes: %s", "admin token required (ATELIER_ADMIN_TOKEN)" if s.atelier_admin_token.strip()
             else "accepted from this machine only (loopback / ATELIER_TRUSTED_NETWORKS); set ATELIER_ADMIN_TOKEN "
                  "to allow remote access")
    return app


app = create_app()
