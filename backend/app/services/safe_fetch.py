"""QA M6: fetch a user-supplied image URL without SSRF.

The URLs a client sends (POST /api/trends/analyze {imageUrls}) are never passed to the vision server (vLLM runs with
host networking: it could reach the cloud metadata service or local ports). The backend fetches the bytes itself:

* https only (no http, file:, data:, javascript:, ftp: …), no credentials in the URL, port 443 only;
* the host name is resolved and EVERY address must be public (not private, loopback, link-local - 169.254.169.254 -,
  multicast, reserved, unspecified, shared CGNAT, or an IPv4-mapped / 6to4 / Teredo form of one);
* the connection goes to the address that was checked (pinned: no DNS rebinding between check and connect), with the
  original host name for TLS (SNI + certificate verification) and the Host header;
* redirects are followed by hand (at most 3), each target checked the same way;
* a total time limit, a byte limit while streaming, and the body must be a PNG / JPEG / WebP by its magic bytes.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Awaitable, Callable, Optional
from urllib.parse import urljoin, urlsplit

import httpx

from . import files
from .http import async_client

MAX_BYTES = 12 * 1024 * 1024
TIMEOUT_S = 10.0
MAX_REDIRECTS = 3
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


class FetchError(ValueError):
    """The URL is not allowed or the image could not be fetched (-> 422)."""


Resolver = Callable[[str, int], Awaitable[list[str]]]


async def _system_resolve(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(i[4][0] for i in infos))


resolve: Resolver = _system_resolve  # tests replace this (no real DNS in the test suite)


def ip_is_public(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        for inner in (ip.ipv4_mapped, ip.sixtofour, (ip.teredo or (None, None))[1]):
            if inner is not None and not ip_is_public(str(inner)):
                return False
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved \
            or ip.is_unspecified or (isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT):
        return False
    return ip.is_global


def check_url(url: str) -> tuple[str, int]:
    """Syntax checks; returns (host, port). Raises FetchError."""
    try:
        parts = urlsplit(url.strip())
    except ValueError as e:
        raise FetchError("not a valid URL") from e
    if parts.scheme.lower() != "https":
        raise FetchError("only https:// image URLs are accepted")
    if parts.username or parts.password:
        raise FetchError("URLs with credentials are not accepted")
    host = (parts.hostname or "").strip(".").lower()
    if not host:
        raise FetchError("the URL has no host")
    try:
        port = parts.port or 443
    except ValueError as e:
        raise FetchError("invalid port") from e
    if port != 443:
        raise FetchError("only the standard https port (443) is accepted")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise FetchError("local host names are not accepted")
    return host, port


async def _public_address(host: str, port: int) -> str:
    try:
        literal = ipaddress.ip_address(host)
        addrs = [str(literal)]
    except ValueError:
        try:
            addrs = await resolve(host, port)
        except (OSError, UnicodeError) as e:
            raise FetchError(f"could not resolve {host}") from e
    if not addrs:
        raise FetchError(f"could not resolve {host}")
    bad = [a for a in addrs if not ip_is_public(a)]
    if bad:
        raise FetchError(f"{host} resolves to a private or reserved address - not fetched")
    return addrs[0]


async def fetch_image(url: str, *, max_bytes: int = MAX_BYTES, timeout: float = TIMEOUT_S) -> tuple[bytes, files.Sniffed]:
    """Returns (bytes, Sniffed). Raises FetchError."""
    try:
        return await asyncio.wait_for(_fetch(url, max_bytes, timeout), timeout=timeout)
    except asyncio.TimeoutError as e:
        raise FetchError(f"timed out after {timeout:g}s") from e


async def _fetch(url: str, max_bytes: int, timeout: float) -> tuple[bytes, files.Sniffed]:
    current = url.strip()
    async with async_client(timeout, follow_redirects=False) as client:
        for _hop in range(MAX_REDIRECTS + 1):
            host, port = check_url(current)
            addr = await _public_address(host, port)
            parts = urlsplit(current)
            ip_host = f"[{addr}]" if ":" in addr else addr
            pinned = parts._replace(netloc=ip_host).geturl()
            req = client.build_request("GET", pinned, headers={"Host": host, "Accept": "image/png,image/jpeg,image/webp"},
                                       extensions={"sni_hostname": host})
            try:
                resp = await client.send(req, stream=True)
            except httpx.HTTPError as e:
                raise FetchError(f"could not fetch the image ({e.__class__.__name__})") from e
            try:
                if resp.status_code in (301, 302, 303, 307, 308):
                    loc = resp.headers.get("location")
                    if not loc:
                        raise FetchError("redirect without a location")
                    current = urljoin(current, loc)
                    continue
                if resp.status_code != 200:
                    raise FetchError(f"the image URL answered HTTP {resp.status_code}")
                ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                if ctype and not ctype.startswith("image/") and ctype != "application/octet-stream":
                    raise FetchError(f"not an image ({ctype})")
                declared: Optional[str] = resp.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise FetchError(f"image larger than {max_bytes // (1024 * 1024)} MB")
                buf = bytearray()
                async for chunk in resp.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > max_bytes:
                        raise FetchError(f"image larger than {max_bytes // (1024 * 1024)} MB")
            finally:
                await resp.aclose()
            kind = files.sniff(bytes(buf), files.IMAGE_KINDS)
            if kind is None:
                raise FetchError("the URL did not return a PNG, JPEG or WebP image")
            return bytes(buf), kind
    raise FetchError("too many redirects")
