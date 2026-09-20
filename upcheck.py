"""Is-it-up checker: layered DNS -> TCP/TLS -> HTTP check for a user-supplied URL.

Mounted into main.py via `app.include_router(router)`.

Security note: this endpoint makes the server fetch user-supplied URLs. Every URL,
including each redirect target, must pass _parse_target() (scheme, credentials, host
form, port) and _resolve_public() (every address public). Each request is then pinned
to the checked address, so DNS rebinding cannot swap in an internal target.
"""

import asyncio
import ipaddress
import os
import re
import socket
import time
import zlib
from typing import NamedTuple

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

import geo

try:  # Optional, and only imported when UPCHECK_IMPERSONATE=1 is set — see _impersonated_status.
    from curl_cffi import CurlOpt
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover - exercised by deployments without the extra installed
    CurlOpt = None
    curl_requests = None

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

# Signals that a refusal is an anti-bot interstitial rather than the site's own
# "no". Cloudflare sets cf-mitigated on every challenge it serves; its older
# challenge pages only carry the interstitial title. Both are definitive —
# unlike `server: cloudflare`, which a site's genuine 403 carries too.
_CHALLENGE_TITLE = b"<title>just a moment"
_CHALLENGE_SNIFF = 1024  # decoded bytes of body worth looking at for the title
_SNIFF_RAW = 32 * 1024  # encoded bytes to pull before giving up on the sniff

# Off by default. When on, a detected challenge is retried once with a browser TLS
# fingerprint (curl_cffi), because some sites answer that when they challenge httpx.
# Measured against allianz.de it succeeds roughly half the time and only on the
# newest profile, so it can add information but is never trusted to remove any:
# a failed or challenged retry leaves the honest "challenged" result untouched.
_IMPERSONATE = os.environ.get("UPCHECK_IMPERSONATE") == "1"
_IMPERSONATE_PROFILE = os.environ.get("UPCHECK_IMPERSONATE_PROFILE", "chrome")
_IMPERSONATE_TIMEOUT = 5.0  # seconds; deliberately below _TIMEOUT, this is a bonus check

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


def _to_origin(url: httpx.URL) -> tuple[httpx.URL, str | None]:
    """Reduce the visitor's URL to its origin, and report what that dropped.

    Checking a deep link would report a site as "erroring" over a single missing
    page, and would make this server fetch whatever path a visitor pasted. Only
    the entered URL is reduced — redirect targets keep their paths, or a site
    that sends "/" to "/en/" would bounce back to "/" until the hop limit.
    """
    dropped = url.raw_path.decode("ascii")
    return url.copy_with(raw_path=b"/"), dropped if dropped != "/" else None


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


class _Hop(NamedTuple):
    """A response plus the only part of its body we ever read.

    They travel together because the body is no longer on the response: it is
    read under a cap and the response is closed, so `.content` would raise.
    """

    response: httpx.Response
    body: bytes


def _inflate(raw: bytes, encoding: str) -> bytes:
    """Decode at most _CHALLENGE_SNIFF bytes out of `raw`, or b"" if we can't.

    The output cap is the whole point: a target picks its own compression ratio,
    so decoding a body in full lets 199 KB on the wire become 200 MB in memory.
    Encodings the standard library cannot bound (br, zstd) return b"", and
    _is_challenge() then relies on the cf-mitigated header alone.
    """
    encoding = encoding.lower().strip()
    if encoding in ("", "identity"):
        return raw[:_CHALLENGE_SNIFF]
    if encoding in ("gzip", "x-gzip"):
        wbits = (31,)
    elif encoding == "deflate":
        wbits = (15, -15)  # zlib-wrapped or bare; servers send both
    else:
        return b""
    for bits in wbits:
        try:
            return zlib.decompressobj(bits).decompress(raw, _CHALLENGE_SNIFF)
        except zlib.error:
            continue
    return b""


async def _sniff_body(response: httpx.Response) -> bytes:
    """The opening bytes of a body, read without trusting the sender's size.

    Reads raw (still-encoded) bytes and stops at _SNIFF_RAW. aiter_bytes() would
    not do: it decodes a whole 64 KB wire chunk before yielding, which is 32 MB
    at a 1000:1 ratio. Nothing here needs more than the first _CHALLENGE_SNIFF
    bytes anyway — the body is only ever checked for a challenge interstitial.
    """
    if response.is_stream_consumed:
        # A transport that answered from memory rather than a socket, which is
        # what MockTransport does in the tests. Nothing was read off a network.
        raw = response.content[:_SNIFF_RAW]
    else:
        raw = b""
        async for chunk in response.aiter_raw():
            raw += chunk
            if len(raw) >= _SNIFF_RAW:
                break
        raw = raw[:_SNIFF_RAW]
    return _inflate(raw, response.headers.get("content-encoding", ""))


async def _send(client: httpx.AsyncClient, method: str, target: httpx.URL, headers, extensions) -> _Hop:
    """One request, reading only as much of the body as _sniff_body wants."""
    request = client.build_request(method, target, headers=headers, extensions=extensions)
    response = await client.send(request, stream=True)
    try:
        body = await _sniff_body(response)
    finally:
        await response.aclose()
    return _Hop(response, body)


async def _fetch_hop(url: httpx.URL, ip: str, transport: httpx.AsyncBaseTransport | None = None) -> _Hop:
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
            hop = await _send(client, "HEAD", target, headers, extensions)
        except _CONNECT_ERRORS:
            raise
        except httpx.HTTPError:
            return await _send(client, "GET", target, headers, extensions)
        if hop.response.status_code in _RETRY_AS_GET:
            return await _send(client, "GET", target, headers, extensions)
        return hop


def _impersonated_get(url: httpx.URL, ip: str) -> tuple[int, bool]:
    """One blocking, IP-pinned request carrying a browser TLS fingerprint.

    Returns its status code and whether it was challenged too. curl_cffi's
    Session takes no `resolve=` argument, so the pin is set on the handle
    directly. That is also why this is the sync Session and not AsyncSession:
    the async one draws a handle from a pool per request, leaving nothing to
    pin. Redirects are not followed — a redirect target has not been through
    _parse_target()/_resolve_public(), and this must not become the path that
    skips them.

    Streamed, and only the first chunk is read: libcurl decodes in 16 KB writes,
    so this stays bounded however the target chose to compress its body.
    """
    host = url.raw_host.decode("ascii").removesuffix(".")
    port = url.port or (443 if url.scheme == "https" else 80)
    with curl_requests.Session() as session:
        session.curl.setopt(CurlOpt.RESOLVE, [f"{host}:{port}:{ip}".encode()])
        response = session.get(
            str(url),
            impersonate=_IMPERSONATE_PROFILE,
            timeout=_IMPERSONATE_TIMEOUT,
            allow_redirects=False,
            stream=True,
        )
        try:
            body = next(iter(response.iter_content()), b"")
            return response.status_code, _is_challenge(response, body)
        finally:
            response.close()


async def _impersonated_status(url: httpx.URL, ip: str) -> int | None:
    """Status code of a browser-shaped retry, or None if it told us nothing new.

    None covers every "no": the flag is off, curl_cffi is not installed, the
    request failed, or this attempt was challenged as well. Callers keep their
    original result on None, so this can only ever add information.

    Like the DNS executor call, the thread cannot be cancelled;
    _IMPERSONATE_TIMEOUT keeps it well inside _CHECK_BUDGET.
    """
    if not _IMPERSONATE or curl_requests is None:
        return None
    try:
        status_code, challenged = await asyncio.to_thread(_impersonated_get, url, ip)
    except Exception:
        # A bonus check must never turn a usable result into an error.
        return None
    return None if challenged else status_code


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


def _is_challenge(response, body: bytes = b"") -> bool:
    """Whether this response is an anti-bot challenge page rather than the site.

    Takes any response exposing .headers, so it reads an httpx and a curl_cffi
    response alike, and the already-capped opening bytes of its body.
    """
    if "cf-mitigated" in response.headers:
        return True
    if "html" not in response.headers.get("content-type", ""):
        return False
    # A HEAD has no body to sniff; a challenge names itself in the header above.
    return _CHALLENGE_TITLE in body[:_CHALLENGE_SNIFF].lower()


def _classify(status_code: int, challenged: bool = False) -> str:
    if status_code < 400:
        return "up"
    if challenged or status_code in _REFUSED_CODES:
        # The server responded quickly and correctly — it is reachable and
        # healthy. It simply declined to serve this particular client. A
        # challenge says the same thing whatever code it arrives under (older
        # Cloudflare interstitials used 503), so it outranks the code.
        return "up"
    if status_code < 500:
        return "degraded"
    return "down"


def _describe_bypassed(status_code: int) -> str:
    return f"Site is up — bot protection challenged this check, but a browser-shaped retry got through ({status_code})."


def _describe(status_code: int, challenged: bool = False) -> str:
    if challenged:
        return f"Site is up, but served a bot-protection challenge ({status_code}). A human browser will reach it fine."
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
        response, body = await _fetch_hop(url, ips[0], transport)
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

    challenged = _is_challenge(response, body)
    status_code = response.status_code
    detail = _describe(status_code, challenged)
    if challenged:
        # Only a direct answer counts as getting through. A 3xx would mean "go
        # somewhere else", and this path deliberately does not follow redirects.
        bypassed = await _impersonated_status(url, ips[0])
        if bypassed is not None and bypassed < 300:
            status_code, challenged = bypassed, False
            detail = _describe_bypassed(bypassed)

    return {
        "status": _classify(status_code, challenged),
        "stage": "done",
        "detail": detail,
        "http_status": status_code,
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

    target, ignored_path = _to_origin(target)

    # Attached to every outcome below: a site that is down is exactly when
    # "whose address is this?" and "what was actually checked?" are most worth answering.
    found: dict = {"ignored_path": ignored_path} if ignored_path else {}
    try:
        async with asyncio.timeout(_CHECK_BUDGET):
            try:
                ips = await _resolve_public(target)
            except NotPublic:
                detail = "Target resolves to a non-public address"
                return {"status": "invalid", "stage": "input", "detail": detail, **found}
            except Unresolvable:
                return {"status": "down", "stage": "dns", "detail": "Domain does not resolve", **found}
            found |= {"resolved_ips": ips, "ip_geo": _geo_for(ips)}
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
