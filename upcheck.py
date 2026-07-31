"""Is-it-up checker: layered DNS -> TCP/TLS -> HTTP check for a user-supplied URL.

Mounted into main.py via `app.include_router(router)`.

Security note: this endpoint makes the server fetch user-supplied URLs.
_guard_ssrf() rejects private, loopback, link-local and reserved targets so the
tool cannot be used to probe the host's internal network. There is a small
TOCTOU window (DNS rebinding) between the guard resolution and the actual
request; acceptable for a personal tool behind nginx rate limiting.
"""

import asyncio
import ipaddress
import socket
import time
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

router = APIRouter()

_TIMEOUT = 10.0  # seconds per network operation
_MAX_REDIRECTS = 5

# Browser-like headers. Many enterprise WAFs reject requests with a bot-shaped
# User-Agent or missing Accept headers before they ever reach the origin.
# This is not evasion — sites that fingerprint TLS will still refuse us, and
# _classify() treats that refusal as "up" because it proves a server answered.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Codes meaning "a server answered and is healthy, it just refused this client".
# The site is up; only our specific request was rejected.
_REFUSED_CODES = {401, 403, 429}

# Codes where a HEAD request is worth retrying as GET: some servers reject HEAD
# outright (405/501), and some WAFs block HEAD as a scanner signature (403).
_RETRY_AS_GET = {403, 405, 501}


def _normalize_url(raw: str) -> str | None:
    """Return a normalized http(s) URL, or None if the input is unusable."""
    raw = raw.strip()
    if not raw or len(raw) > 2048:
        return None
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    return raw


def _guard_ssrf(host: str) -> tuple[list[str], str | None]:
    """Resolve host and reject non-public targets.

    Returns (resolved_ips, error). error is None when the target is allowed.
    """
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return [], "dns"
    ips = sorted({info[4][0] for info in infos})
    for ip in ips:
        addr = ipaddress.ip_address(ip)
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
            addr = addr.ipv4_mapped
        if not addr.is_global:
            return ips, "blocked"
    return ips, None


def _classify(status_code: int) -> str:
    if status_code < 400:
        return "up"
    if status_code in _REFUSED_CODES:
        # The server responded quickly and correctly — it is reachable and
        # healthy. It simply declined to serve this particular client.
        return "up"
    if status_code < 500:
        return "degraded"
    return "down"


def _describe(status_code: int) -> str:
    if status_code in _REFUSED_CODES:
        return (
            f"Site is up, but refused this check ({status_code}) — most likely "
            "bot protection. A human browser will probably reach it fine."
        )
    if status_code < 400:
        return "Site responded normally"
    if status_code < 500:
        return f"Server responded with a client error ({status_code})"
    return f"Server responded with an error ({status_code})"


async def _http_check(url: str) -> dict:
    """HEAD first (cheap), fall back to GET when HEAD is rejected or blocked."""
    async with httpx.AsyncClient(
        timeout=_TIMEOUT,
        follow_redirects=True,
        max_redirects=_MAX_REDIRECTS,
        headers=_HEADERS,
    ) as client:
        start = time.monotonic()
        try:
            response = await client.head(url)
            if response.status_code in _RETRY_AS_GET:
                response = await client.get(url)
        except httpx.HTTPError:
            response = await client.get(url)
        elapsed_ms = round((time.monotonic() - start) * 1000)

    redirects = [str(r.url) for r in response.history]
    return {
        "status": _classify(response.status_code),
        "detail": _describe(response.status_code),
        "http_status": response.status_code,
        "response_time_ms": elapsed_ms,
        "final_url": str(response.url),
        "redirects": redirects,
    }


@router.get("/api/up")
async def check_up(url: str = Query(..., max_length=2048)):
    normalized = _normalize_url(url)
    if normalized is None:
        return {"status": "invalid", "stage": "input", "detail": "Not a valid http(s) URL"}

    host = urlsplit(normalized).hostname or ""
    loop = asyncio.get_running_loop()
    ips, guard_error = await loop.run_in_executor(None, _guard_ssrf, host)

    if guard_error == "dns":
        return {"status": "down", "stage": "dns", "detail": "Domain does not resolve"}
    if guard_error == "blocked":
        return {"status": "invalid", "stage": "input", "detail": "Target resolves to a non-public address"}

    try:
        result = await _http_check(normalized)
    except httpx.ConnectError:
        return {"status": "down", "stage": "connect", "detail": "Server unreachable", "resolved_ips": ips}
    except httpx.ConnectTimeout:
        return {"status": "down", "stage": "connect", "detail": "Connection timed out", "resolved_ips": ips}
    except httpx.ReadTimeout:
        return {"status": "down", "stage": "http", "detail": "Server accepted the connection but did not respond in time", "resolved_ips": ips}
    except httpx.TooManyRedirects:
        return {"status": "degraded", "stage": "http", "detail": f"More than {_MAX_REDIRECTS} redirects", "resolved_ips": ips}
    except httpx.HTTPError as exc:
        return {"status": "down", "stage": "http", "detail": type(exc).__name__, "resolved_ips": ips}

    result["stage"] = "done"
    result["resolved_ips"] = ips
    return result


@router.get("/up")
async def up_page():
    return FileResponse("static/up.html")