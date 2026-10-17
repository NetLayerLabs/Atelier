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

Hosted demo (ATELIER_ADMIN_TOKEN set, ATELIER_PUBLIC_DEMO on): visitors WITHOUT the token may still run the steps
that have no outside effect - reading a mood board or a sketch, customer voice on the sample datasets, concepts,
creative direction (PUBLIC_POSTS). They call the models and create in-memory results only: no email is sent, nothing is created
in Shopify and no saved brand data changes. Model-calling steps are rate-limited per visitor and in total (protects
the hosted model's quota), and email addresses in JSON responses are masked for visitors (the supplier directory
holds real inboxes). Everything else keeps the rules above.

Private files (supplier quote documents, Brand workspace uploads) use the same rule for reads: `require_private`.
Every response also carries `X-Content-Type-Options: nosniff`.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import re
import threading
import time
from collections import deque
from typing import Optional
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import get_settings

MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
SESSION_COOKIE = "atelier_session"
EXEMPT_PREFIXES = ("/api/webhooks/",)
LOGIN_PATHS = frozenset({"/api/auth/login", "/api/auth/logout"})
# Hosted demo: POSTs a visitor without the token may make (exact paths; ids are [A-Za-z0-9_-]). Nothing here emails a
# supplier, writes to Shopify or changes saved brand data. `True` = calls a model (rate-limited), `False` = local maths.
_ID = r"[A-Za-z0-9_-]{1,64}"
PUBLIC_POSTS: tuple[tuple[re.Pattern[str], bool], ...] = (
    (re.compile(r"^/api/trends/analyze$"), True),  # read a mood board (vision)
    (re.compile(r"^/api/designs/generate$"), True),  # concepts (diffusion)
    (re.compile(r"^/api/designs/upload$"), True),  # read the designer's sketch (vision)
    (re.compile(rf"^/api/designs/{_ID}/refine$"), True),  # vibe refinement (diffusion)
    (re.compile(rf"^/api/designs/{_ID}/direct$"), True),  # creative direction (brain)
    (re.compile(r"^/api/collections/generate$"), True),  # a collection (brain + diffusion)
    (re.compile(r"^/api/voice/sample$"), True),  # customer voice on the built-in review datasets (brain phrasing)
)
# Not public (review 17 Oct): /api/voice/{id}/apply changes a design an admin may approve, /api/forecast takes up to
# 50,000 orders of maths with no model call to rate-limit; visitors never reach either before Approve anyway.
RATE_WINDOW = 600.0  # seconds
# Public steps that store the visitor's upload on disk (multipart only): paused when the uploads folder is full, so
# visitors can't fill a disk the host shares with other services.
_UPLOAD_POSTS = (re.compile(r"^/api/trends/analyze$"), re.compile(r"^/api/designs/upload$"))
_uploads_size: dict[str, float] = {}  # {"bytes": n, "at": monotonic} - measured at most every 30 s

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


def public_post(method: str, path: str) -> Optional[bool]:
    """None: not a public step. Otherwise whether it calls a model (and so counts towards the rate limit)."""
    if method != "POST":
        return None
    return next((model for pat, model in PUBLIC_POSTS if pat.match(path)), None)


# Where a reverse proxy in front of us can sit (RFC 1918 / unique-local, e.g. Docker's bridge) - an explicit list:
# Python's `is_private` also covers documentation and other special ranges a visitor could come from.
_PROXY_NETS = tuple(ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7"))


def uploads_bytes() -> int:
    """Total size of the uploads folder (cached for 30 s)."""
    from .config import UPLOADS_DIR

    now = time.monotonic()
    if _uploads_size and now - _uploads_size["at"] < 30:
        return int(_uploads_size["bytes"])
    total = 0
    try:
        for entry in os.scandir(UPLOADS_DIR):
            if entry.is_file(follow_symlinks=False):
                total += entry.stat(follow_symlinks=False).st_size
    except FileNotFoundError:
        pass
    _uploads_size.update(bytes=total, at=now)
    return total


def visitor_ip(scope: Scope, headers: dict[str, str]) -> str:
    """The visitor's address. Behind a local reverse proxy (nginx on the host, or Docker's bridge in front of the
    container) the peer is the proxy, so X-Real-IP (set by the proxy from the TCP peer, not by the client) or the
    LAST X-Forwarded-For hop is used. From any other peer the headers are ignored (they could be forged)."""
    client = scope.get("client")
    peer = client[0] if client else ""
    try:
        ip = ipaddress.ip_address(peer.split("%", 1)[0])
        via_proxy = ip.is_loopback or any(ip in n for n in _PROXY_NETS) or any(ip in n for n in _networks())
    except (ValueError, TypeError):
        via_proxy = False
    if via_proxy:
        real = headers.get("x-real-ip", "").strip()
        if real:
            return real
        fwd = [h.strip() for h in headers.get("x-forwarded-for", "").split(",") if h.strip()]
        if fwd:
            return fwd[-1]
    return peer or "unknown"


class RateLimiter:
    """Sliding-window limits for the hosted demo: per visitor and in total."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._per: dict[str, deque[float]] = {}
        self._all: deque[float] = deque()

    def reset(self) -> None:
        with self._lock:
            self._per.clear()
            self._all.clear()

    def refund(self, who: str) -> None:
        """The request never reached a model (rejected first): give the visitor that call back."""
        with self._lock:
            mine = self._per.get(who)
            if mine:
                mine.pop()
            if self._all:
                self._all.pop()

    def hit(self, who: str, per_visitor: int, total: int, now: Optional[float] = None) -> Optional[str]:
        """Count one call; None when allowed, else why not (the call is then not counted)."""
        now = time.monotonic() if now is None else now
        cutoff = now - RATE_WINDOW
        with self._lock:
            while self._all and self._all[0] <= cutoff:
                self._all.popleft()
            mine = self._per.setdefault(who, deque())
            while mine and mine[0] <= cutoff:
                mine.popleft()
            if len(self._per) > 5000:  # forget visitors with no call in the window
                for k in [k for k, v in self._per.items() if not v and k != who]:
                    del self._per[k]
            if per_visitor > 0 and len(mine) >= per_visitor:
                wait = int(mine[0] + RATE_WINDOW - now) // 60 + 1
                return (f"Demo limit: {per_visitor} model calls per visitor every {int(RATE_WINDOW // 60)} minutes. "
                        f"Try again in about {wait} min.")
            if total > 0 and len(self._all) >= total:
                wait = int(self._all[0] + RATE_WINDOW - now) // 60 + 1
                return ("The demo is busy right now (shared model quota). Try again in about "
                        f"{wait} min.")
            mine.append(now)
            self._all.append(now)
            return None


limiter = RateLimiter()

_EMAIL = re.compile(rb"([A-Za-z0-9])[A-Za-z0-9._%+-]*@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")


def mask_emails(body: bytes) -> bytes:
    """jane.doe@gmail.com -> j•••@gmail.com (the domain stays: it says which provider a supplier uses)."""
    return _EMAIL.sub(lambda m: m.group(1) + "•••".encode() + b"@" + m.group(2), body)


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
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        if method in MUTATING and path.startswith("/api/") and not path.startswith(EXEMPT_PREFIXES):
            rejection = self._check(scope, method, path, headers)
            if rejection is not None:
                status, detail = rejection
                await self._reject(send, status, detail)
                return
        # Hosted demo: a visitor without the token never sees a real inbox address in our JSON.
        mask = (path.startswith("/api/") and not path.startswith(EXEMPT_PREFIXES) and token_required()
                and not _authenticated(headers, _parse_cookies(headers.get("cookie", ""))))
        held: dict = {}
        chunks: list[bytes] = []
        counted = scope.pop("atelier.rate_counted", None)  # (visitor, ) when this request used a model-call slot

        async def send_nosniff(message: Message) -> None:
            if message["type"] == "http.response.start":
                if counted and 400 <= message.get("status", 200) < 500:  # rejected before the model ran: not a call
                    limiter.refund(counted)
                hdrs = list(message.get("headers", []))
                if not any(k.lower() == b"x-content-type-options" for k, _ in hdrs):
                    hdrs.append((b"x-content-type-options", b"nosniff"))
                message["headers"] = hdrs
                ctype = next((v for k, v in hdrs if k.lower() == b"content-type"), b"")
                if mask and ctype.lower().startswith(b"application/json"):
                    held["start"] = message  # sent with the rewritten body
                    return
            elif message["type"] == "http.response.body" and "start" in held:
                chunks.append(message.get("body", b""))
                if message.get("more_body"):
                    return
                body = mask_emails(b"".join(chunks))
                start = held.pop("start")
                start["headers"] = [(k, v) for k, v in start["headers"] if k.lower() != b"content-length"] + [
                    (b"content-length", str(len(body)).encode())]
                await send(start)
                await send({"type": "http.response.body", "body": body})
                return
            await send(message)

        await self.app(scope, receive, send_nosniff)

    @staticmethod
    def _check(scope: Scope, method: str, path: str, headers: dict[str, str]) -> Optional[tuple[int, str]]:
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
            s = get_settings()
            model = public_post(method, path) if s.atelier_public_demo else None
            if model is not None:  # hosted demo: a step with no outside effect
                if (headers.get("content-type", "").lower().startswith("multipart/")
                        and any(p.match(path) for p in _UPLOAD_POSTS)
                        and uploads_bytes() >= s.atelier_public_uploads_max_mb * 1024 * 1024):
                    return 503, ("Uploads are paused on the public demo (its storage limit is reached). The preset "
                                 "mood boards still work; sign in to upload.")
                if model:
                    who = visitor_ip(scope, headers)
                    why = limiter.hit(who, s.atelier_public_rate_per_visitor, s.atelier_public_rate_total)
                    if why:
                        return 429, why
                    scope["atelier.rate_counted"] = who
                return None
            return 401, ("admin token required - sign in on the dashboard or send Authorization: Bearer <token>. "
                         "Visitors can try every step up to Approve; approving emails real suppliers and opens a "
                         "real Shopify pre-order")
        client = scope.get("client")
        if client_is_local(client[0] if client else None):
            return None
        return 403, "changes are only accepted from this machine. " + TOKEN_HINT

    @staticmethod
    async def _reject(send: Send, status: int, detail: str) -> None:
        auth = {401: "required", 429: "rate_limited", 503: "paused"}.get(status, "forbidden")
        body = json.dumps({"detail": detail, "auth": auth}).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                                (b"x-content-type-options", b"nosniff")]})
        await send({"type": "http.response.body", "body": body})
