"""QA H5: sign-in for the optional admin token (ATELIER_ADMIN_TOKEN). See app/security.py."""

from __future__ import annotations

import asyncio
import hmac

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field

from .. import security
from ..config import get_settings
from ..models import CamelModel, SecuritySummary

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(CamelModel):
    token: str = Field(min_length=1, max_length=512)


@router.get("/status", response_model=SecuritySummary)
async def status(request: Request) -> SecuritySummary:
    return SecuritySummary.model_validate(security.summary(request))


@router.post("/login", response_model=SecuritySummary)
async def login(req: LoginRequest, request: Request, response: Response) -> SecuritySummary:
    token = get_settings().atelier_admin_token.strip()
    if not token:
        raise HTTPException(409, "no admin token is configured - this backend only accepts changes from this machine")
    if not hmac.compare_digest(req.token.strip().encode(), token.encode()):
        await asyncio.sleep(0.4)  # slows down guessing
        raise HTTPException(401, "wrong admin token")
    response.set_cookie(security.SESSION_COOKIE, security.session_value(token), max_age=12 * 3600, httponly=True,
                        samesite="lax", secure=request.url.scheme == "https", path="/")
    out = SecuritySummary.model_validate(security.summary(request))
    out.authenticated = True
    return out


@router.post("/logout", response_model=SecuritySummary)
async def logout(request: Request, response: Response) -> SecuritySummary:
    response.delete_cookie(security.SESSION_COOKIE, path="/")
    out = SecuritySummary.model_validate(security.summary(request))
    out.authenticated = False
    return out
