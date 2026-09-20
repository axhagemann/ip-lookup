"""Is-it-up checker: layered DNS -> TCP/TLS -> HTTP check for a user-supplied URL.

Mounted into main.py via `app.include_router(router)`.

Security note: this endpoint makes the server fetch user-supplied URLs. Every URL,
including each redirect target, must pass _parse_target() (scheme, credentials, host
form, port) and _resolve_public() (every address public). Each request is then pinned
to the checked address, so DNS rebinding cannot swap in an internal target.
"""

import asyncio
import ipaddress
import re
import socket
import time

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

import geo

router = APIRouter()

_TIMEOUT = 10.0  # seconds per network operation
_MAX_REDIRECTS = 5
_GEO_MAX_IPS = 4  # bound the work when DNS round-robins many A records

_MAX_URL_LENGTH = 2048
_ALLOWED_PORTS = frozenset({80, 443, 8080, 8443})
_WHITESPACE_OR_CONTROL = re.compile(r"[\x00-\x20\x7f]")
_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")

_DNS_TIMEOUT = 5.0  # seconds
_NAT64 = ipaddress.IPv6Network("64:ff9b::/96")
_CHECK_BUDGET = 12.0  # seconds for all DNS lookups and requests; nginx gives up after 15
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})

# Browser-like headers. Many enterprise WAFs reject requests with a bot-shaped
# User-Agent or missing Accept headers before they ever reach the origin.
# This is not evasion — sites that fingerprint TLS will still refuse us, and
# _classify() treats that refusal as "up" because it proves a server answered.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
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

# A connect-level failure is the target's answer, not HEAD's — see _fetch_hop.
_CONNECT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout)


class Rejected(Exception):
    """A URL that will not be fetched; str(exc) is shown to the visitor."""


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _is_acceptable_host(host: str) -> bool:
    if _is_ip(host):
        return True
    name = host.lower().removesuffix(".")
    labels = name.split(".")
    return (
        len(name) <= 253
        and len(labels) >= 2
        and all(_DNS_LABEL.fullmatch(label) for label in labels)
        and not labels[-1].isdigit()
    )


def _parse_target(raw: str) -> httpx.URL:
    raw = raw.strip()
    if not raw:
        raise Rejected("Enter a URL to check")
    if len(raw) > _MAX_URL_LENGTH:
        raise Rejected("URL is too long")
    # Before parsing: urlsplit and httpx disagree on embedded tabs and spaces.
    if _WHITESPACE_OR_CONTROL.search(raw):
        raise Rejected("URL contains spaces or control characters")
    if "://" not in raw:
        raw = "https://" + raw
    try:
        url = httpx.URL(raw)
    except httpx.InvalidURL:
        raise Rejected("Not a valid URL") from None
    if url.scheme not in ("http", "https"):
        raise Rejected("Only http and https URLs can be checked")
    if url.userinfo:
        raise Rejected("URLs with a username or password aren't accepted")
    if not _is_acceptable_host(url.raw_host.decode("ascii")):
        raise Rejected("Not a public hostname or IP address")
    if url.port is not None and url.port not in _ALLOWED_PORTS:
        raise Rejected(f"Port {url.port} isn't allowed — only 80, 443, 8080 and 8443")
    return url.copy_with(fragment=None)


class NotPublic(Exception):
    """The host resolves to at least one address that is not publicly routable."""


class Unresolvable(Exception):
    """The host has no addresses, or DNS did not answer in time."""


def _is_public(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if not addr.is_global:
        return False
    if isinstance(addr, ipaddress.IPv6Address):
        embedded = addr.ipv4_mapped or addr.sixtofour
        if embedded is None and addr in _NAT64:
            embedded = ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)
        if embedded is not None and not embedded.is_global:
            return False
    return True


def _lookup(host: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)]


async def _resolve_public(url: httpx.URL) -> list[str]:
    host = url.raw_host.decode("ascii")
    if _is_ip(host):
        found = [host]
    else:
        loop = asyncio.get_running_loop()
        try:
            # An executor call cannot be cancelled: after the timeout the thread stays in
            # getaddrinfo until the OS resolver gives up. Bounded in practice by the nginx
            # rate limit on /api/up (10/min, burst 3).
            found = await asyncio.wait_for(loop.run_in_executor(None, _lookup, host), _DNS_TIMEOUT)
        except (socket.gaierror, TimeoutError):
            raise Unresolvable from None
    ips = list(dict.fromkeys(found))
    if not ips:
        raise Unresolvable
    if not all(_is_public(ipaddress.ip_address(ip)) for ip in ips):
        raise NotPublic
    return sorted(ips, key=lambda ip: ":" in ip)


def _pinned(url: httpx.URL, ip: str) -> tuple[httpx.URL, dict[str, str], dict[str, str]]:
    host = url.raw_host.decode("ascii")
    if _is_ip(host):
        host_header = f"[{host}]" if ":" in host else host
        extensions = {}
    else:
        host_header = host.removesuffix(".")
        extensions = {"sni_hostname": host_header} if url.scheme == "https" else {}
    if url.port is not None:
        host_header += f":{url.port}"
    return url.copy_with(host=ip), {"Host": host_header}, extensions


async def _fetch_hop(url: httpx.URL, ip: str, transport: httpx.AsyncBaseTransport | None = None) -> httpx.Response:
    """HEAD first (cheap), fall back to GET when HEAD is rejected or blocked.

    Only the HEAD is retried. A connect failure is the target's answer, not HEAD's:
    retrying it would spend a second _TIMEOUT of the check budget and turn
    "Server unreachable" into "Check took too long". A failing GET is final too.
    """
    target, headers, extensions = _pinned(url, ip)
    # Fresh client per hop: httpcore pools by scheme+IP+port, so reuse could skip this hostname's TLS check.
    async with httpx.AsyncClient(
        transport=transport,
        timeout=_TIMEOUT,
        follow_redirects=False,
        trust_env=False,
        headers=_HEADERS,
    ) as client:
        try:
            response = await client.head(target, headers=headers, extensions=extensions)
        except _CONNECT_ERRORS:
            raise
        except httpx.HTTPError:
            return await client.get(target, headers=headers, extensions=extensions)
        if response.status_code in _RETRY_AS_GET:
            response = await client.get(target, headers=headers, extensions=extensions)
        return response


def _geo_for(ips: list[str]) -> list[dict]:
    """Geolocate the resolved target IPs, in the same order as `ips`.

    mmdb reads are memory-mapped and take microseconds, so this stays inline
    rather than going through an executor. IPs with no known location are
    omitted entirely; the list is empty when GeoLite2 has not loaded.
    """
    located = []
    for ip in ips[:_GEO_MAX_IPS]:
        data = geo.lookup(ip)
        if data:
            located.append({"ip": ip, **data})
    return located


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


def _as_clause(message: str) -> str:
    return message if message[:2].isupper() else message[0].lower() + message[1:]


async def _http_check(url: httpx.URL, ips: list[str], transport: httpx.AsyncBaseTransport | None = None) -> dict:
    start = time.monotonic()
    redirects: list[str] = []
    while True:
        response = await _fetch_hop(url, ips[0], transport)
        location = response.headers.get("location")
        if response.status_code not in _REDIRECT_CODES or not location:
            break
        redirects.append(str(url))
        if len(redirects) > _MAX_REDIRECTS:
            return {
                "status": "degraded",
                "stage": "http",
                "detail": f"More than {_MAX_REDIRECTS} redirects",
                "redirects": redirects,
            }
        try:
            url = _parse_target(str(url.join(location)))
            ips = await _resolve_public(url)
        except Rejected as exc:
            detail = f"Redirected to a URL that can't be checked: {_as_clause(str(exc))}"
            return {"status": "blocked", "stage": "redirect", "detail": detail, "redirects": redirects}
        except NotPublic:
            detail = "Redirected to a non-public address"
            return {"status": "blocked", "stage": "redirect", "detail": detail, "redirects": redirects}
        except Unresolvable:
            detail = "Redirect target does not resolve"
            return {"status": "down", "stage": "dns", "detail": detail, "redirects": redirects}

    return {
        "status": _classify(response.status_code),
        "stage": "done",
        "detail": _describe(response.status_code),
        "http_status": response.status_code,
        "response_time_ms": round((time.monotonic() - start) * 1000),
        "final_url": str(url),
        "redirects": redirects,
    }


@router.get("/api/up")
async def check_up(url: str = Query(...)):
    # No max_length here: FastAPI would answer an over-long URL with a 422 validation
    # body the page cannot render. _parse_target enforces _MAX_URL_LENGTH and returns
    # "URL is too long" in the normal response shape.
    return await _run_check(url)


async def _run_check(raw: str, transport: httpx.AsyncBaseTransport | None = None) -> dict:
    try:
        target = _parse_target(raw)
    except Rejected as exc:
        return {"status": "invalid", "stage": "input", "detail": str(exc)}

    # Attached to every outcome below: a site that is down is exactly when
    # "whose address is this?" is most worth answering.
    found: dict = {}
    try:
        async with asyncio.timeout(_CHECK_BUDGET):
            try:
                ips = await _resolve_public(target)
            except NotPublic:
                return {"status": "invalid", "stage": "input", "detail": "Target resolves to a non-public address"}
            except Unresolvable:
                return {"status": "down", "stage": "dns", "detail": "Domain does not resolve"}
            found = {"resolved_ips": ips, "ip_geo": _geo_for(ips)}
            result = await _http_check(target, ips, transport)
    except TimeoutError:
        return {"status": "down", "stage": "http", "detail": "Check took too long", **found}
    except httpx.ConnectError:
        return {"status": "down", "stage": "connect", "detail": "Server unreachable", **found}
    except httpx.ConnectTimeout:
        return {"status": "down", "stage": "connect", "detail": "Connection timed out", **found}
    except httpx.ReadTimeout:
        return {
            "status": "down",
            "stage": "http",
            "detail": "Server accepted the connection but did not respond in time",
            **found,
        }
    except httpx.HTTPError as exc:
        return {"status": "down", "stage": "http", "detail": type(exc).__name__, **found}
    return {**result, **found}


@router.get("/up")
async def up_page():
    return FileResponse("static/up.html")
