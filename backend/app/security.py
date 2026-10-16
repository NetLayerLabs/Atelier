"""Request security for the API (QA H5).

Three layers, applied to every state-changing request (POST / PUT / PATCH / DELETE) under /api/ except the
webhooks (/api/webhooks/*, authenticated by Shopify's HMAC / the Evolus shared secret):

1. Origin check (CSRF): a browser always sends `Origin` on a cross-origin POST - even a "simple" multipart one that
   needs no CORS preflight. The request is rejected (403) when its Origin - or, without one, its Referer - is not one
   of CORS_ORIGINS (or the backend's own PUBLIC_BASE_URL). Requests with neither header (curl, scripts) pass this
   layer and are judged by the next one.
2. Admin token: when ATELIER_ADMIN_TOKEN is set, the request needs `Authorization: Bearer <token>` or the session
   cookie set by POST /api/auth/login (the dashboard's small login form). Otherwise 401.
3. Without a token, only clients on this machine may change state: loopback (127.0.0.1 / ::1) or a network listed in
   ATELIER_TRUSTED_NETWORKS (docker-compose adds Docker's bridge range because its published ports are bound to
   127.0.0.1). Anyone else gets 403 with the hint to set ATELIER_ADMIN_TOKEN.

Private files (supplier quote documents, Brand workspace uploads) use the same rule for reads: `require_private`.
Every response also carries `X-Content-Type-Options: nosniff`.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
from typing import Optional
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import get_settings

MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
SESSION_COOKIE = "atelier_session"
EXEMPT_PREFIXES = ("/api/webhooks/",)
LOGIN_PATHS = frozenset({"/api/auth/login", "/api/auth/logout"})
TOKEN_HINT = ("Set ATELIER_ADMIN_TOKEN in backend/.env to allow access from other machines (then sign in with it "
              "in the dashboard, or send `Authorization: Bearer <token>`).")


def _origin(url: str | None) -> Optional[str]:
    if not url:
        return None
    try:
        p = urlparse(url.strip())
    except ValueError:
        return None
    if not p.scheme or not p.netloc:
        return "null" if url.strip().lower() == "null" else None
    return f"{p.scheme.lower()}://{p.netloc.lower()}"


def allowed_origins() -> set[str]:
    s = get_settings()
    out = {o for o in (_origin(x) for x in s.cors_origin_list) if o}
    own = _origin(s.public_base_url)
    if own:
        out.add(own)
    return out


def _networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    nets = []
    for part in get_settings().atelier_trusted_networks.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            continue
    return nets


def client_is_local(host: Optional[str]) -> bool:
    """Loopback, or a network the operator trusts (ATELIER_TRUSTED_NETWORKS)."""
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    if ip.is_loopback or (getattr(ip, "ipv4_mapped", None) is not None and ip.ipv4_mapped.is_loopback):
        return True
    return any(ip in n for n in _networks())


def session_value(token: str) -> str:
    """The cookie holds an HMAC of the token, never the token itself."""
    return hmac.new(token.encode(), b"atelier-session-v1", hashlib.sha256).hexdigest()


def _authenticated(headers: dict[str, str], cookies: dict[str, str]) -> bool:
    token = get_settings().atelier_admin_token.strip()
    if not token:
        return False
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer ") and hmac.compare_digest(auth[7:].strip().encode(), token.encode()):
        return True
    cookie = cookies.get(SESSION_COOKIE, "")
    return bool(cookie) and hmac.compare_digest(cookie.encode(), session_value(token).encode())


def is_authenticated(request: Request) -> bool:
    return _authenticated({k.lower(): v for k, v in request.headers.items()}, dict(request.cookies))


def token_required() -> bool:
    return bool(get_settings().atelier_admin_token.strip())


def authorized(request: Request) -> bool:
    """May this request change state / read private files?"""
    if token_required():
        return is_authenticated(request)
    return client_is_local(request.client.host if request.client else None)


def require_private(request: Request) -> None:
    """FastAPI dependency for private reads (quote documents, workspace files)."""
    if authorized(request):
        return
    if token_required():
        raise HTTPException(401, "sign in with the admin token to open this file")
    raise HTTPException(403, "files are only served to this machine. " + TOKEN_HINT)


def summary(request: Request) -> dict:
    """For GET /api/health and GET /api/auth/status."""
    required = token_required()
    return {"adminTokenRequired": required, "authenticated": is_authenticated(request) if required else False,
            "mutations": "admin-token" if required else "local-only",
            "localClient": client_is_local(request.client.host if request.client else None)}


def _parse_cookies(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in raw.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


class SecurityMiddleware:
    """Pure ASGI middleware (keeps streaming responses and background tasks intact)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        method: str = scope.get("method", "GET").upper()
        if method in MUTATING and path.startswith("/api/") and not path.startswith(EXEMPT_PREFIXES):
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
            rejection = self._check(scope, path, headers)
            if rejection is not None:
                status, detail = rejection
                await self._reject(send, status, detail)
                return

        async def send_nosniff(message: Message) -> None:
            if message["type"] == "http.response.start":
                hdrs = list(message.get("headers", []))
                if not any(k.lower() == b"x-content-type-options" for k, _ in hdrs):
                    hdrs.append((b"x-content-type-options", b"nosniff"))
                message["headers"] = hdrs
            await send(message)

        await self.app(scope, receive, send_nosniff)

    @staticmethod
    def _check(scope: Scope, path: str, headers: dict[str, str]) -> Optional[tuple[int, str]]:
        origin = _origin(headers.get("origin")) or (None if headers.get("origin") else _origin(headers.get("referer")))
        if headers.get("origin") and origin is None:
            origin = "null"
        if origin is not None and origin not in allowed_origins():
            return 403, (f"cross-origin request from {origin} rejected - only the Atelier dashboard "
                         f"(CORS_ORIGINS) may change data")
        if path in LOGIN_PATHS:
            return None
        if token_required():
            if _authenticated(headers, _parse_cookies(headers.get("cookie", ""))):
                return None
            return 401, "admin token required - sign in on the dashboard or send Authorization: Bearer <token>"
        client = scope.get("client")
        if client_is_local(client[0] if client else None):
            return None
        return 403, "changes are only accepted from this machine. " + TOKEN_HINT

    @staticmethod
    async def _reject(send: Send, status: int, detail: str) -> None:
        body = json.dumps({"detail": detail, "auth": "required" if status == 401 else "forbidden"}).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                                (b"x-content-type-options", b"nosniff")]})
        await send({"type": "http.response.body", "body": body})
