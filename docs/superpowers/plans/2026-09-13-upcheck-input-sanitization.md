# "Is It Up?" Input Sanitization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/api/up` refuse unsafe input and unsafe redirect targets, and pin every request to the address that passed the SSRF check.

**Architecture:** All logic stays in `upcheck.py`. Four small units are added bottom-up — `_parse_target` (input rules), `_resolve_public` (DNS + public-address check), `_fetch_hop` (one pinned request) and `_http_check` (manual redirect loop) — and `_run_check` wires them into the existing endpoint. `static/up.html` learns one new status and one new stage.

**Tech Stack:** Python 3.12, FastAPI, httpx 0.28.1 / httpcore 1.0.9, pytest, vanilla JS.

**Spec:** `docs/superpowers/specs/2026-09-13-upcheck-input-sanitization-design.md`

**Status (2026-09-20):** Tasks 1-5 are implemented and committed (`1e405a9`, `f7d29b3`, `f87400e`, `acaf44e`, `7b977f1`); the full suite is green (146 tests). Only Task 6 (deploy) is outstanding, and the stack has been shut down since 2026-09-13, so Task 6 is what brings the live site back up.

**Note on `ruff format .`:** ruff 0.16.7 also reformats Python code blocks inside `README.md` and `PLAN-up-geo.md`. Those edits are unrelated to this work — revert them with `git checkout -- README.md PLAN-up-geo.md` before committing.

## Global Constraints

- No new dependencies. Versions as in the app image: Python 3.12.13, httpx 0.28.1, httpcore 1.0.9.
- Allowed ports exactly: 80, 443, 8080, 8443.
- Limits: URL ≤ 2048 characters (enforced by `_parse_target` alone, so the visitor gets the plain-language message instead of a FastAPI 422); DNS timeout 5 s; total check budget 12 s; per-operation httpx timeout `_TIMEOUT` = 10 s (unchanged); at most 5 redirects.
- Visitor-facing messages, verbatim: "Enter a URL to check", "URL is too long", "URL contains spaces or control characters", "Not a valid URL", "Only http and https URLs can be checked", "URLs with a username or password aren't accepted", "Not a public hostname or IP address", "Port {n} isn't allowed — only 80, 443, 8080 and 8443", "Target resolves to a non-public address", "Domain does not resolve", "Redirected to a URL that can't be checked: {reason}", "Redirected to a non-public address", "Redirect target does not resolve", "More than 5 redirects", "Check took too long".
- `{reason}` = the rule message with its first letter lower-cased, unless the message starts with an acronym ("URL…"), which stays as is.
- Every hop uses a **fresh** `httpx.AsyncClient` with `follow_redirects=False` and `trust_env=False`. httpcore reuses connections by scheme + IP + port only, so a shared client could send a second hostname over a TLS session that was verified for the first.
- Nothing new is logged. Raw input and rejection details never reach a log.
- `static/up.html` renders server-provided strings only via `textContent`; `.status-blocked` uses the existing grey `#c0c0c0` (no new colour).
- Tests make no network calls. Async code is driven with `asyncio.run(...)` inside ordinary test functions (there is no pytest-asyncio).
- Test data: public addresses are `1.1.1.1`, `8.8.8.8`, `2606:4700:4700::1111`. Do **not** use `203.0.113.0/24` as "public" — Python 3.12 treats it as non-global. The example website is `spiegel.de`.
- Run tests and lint in the development environment. The dev box has a project venv at `.venv/` (gitignored) with pytest and ruff already installed: run `source .venv/bin/activate` once per shell so the bare `python -m pytest` / `ruff` commands below resolve to it, or call `.venv/bin/python -m pytest` / `.venv/bin/ruff` directly. Don't install anything into it without asking. pytest and ruff are not installed on the production server; do not install them there.
- Every commit message ends with:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_016XZeNp625iwqJNCyWfdhRM
  ```

## File Map

| File | Change |
|---|---|
| `upcheck.py` | Add `_parse_target`, `_resolve_public`, `_fetch_hop`, new `_http_check`, `_run_check`; remove `_normalize_url`, `_guard_ssrf`, old `_http_check`, `urlsplit` import |
| `tests/test_upcheck.py` | Add `TestParseTarget`, `TestResolvePublic`, `TestFetchHop`, `TestRunCheck`, `TestUpPage`; remove `TestNormalizeUrl`, `TestSsrfGuard` |
| `tests/test_routes.py` | Add two rejection tests that must not touch DNS |
| `tests/test_privacy.py` | Add a test that a rejected URL is not logged |
| `static/up.html` | `maxlength`, `blocked` status label and style, `redirect` stage label |

---

### Task 1: Input rules — `_parse_target`

**Files:**
- Modify: `upcheck.py` (imports; new code directly below `_normalize_url`)
- Test: `tests/test_upcheck.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `class Rejected(Exception)` — `str(exc)` is the visitor-facing message.
  - `_is_ip(host: str) -> bool`
  - `_parse_target(raw: str) -> httpx.URL` — raises `Rejected`.
  - Constants `_MAX_URL_LENGTH = 2048`, `_ALLOWED_PORTS = frozenset({80, 443, 8080, 8443})`.

- [x] **Step 1: Write the failing tests**

In `tests/test_upcheck.py`, add `import pytest` so the import block reads:

```python
import pytest

import geo
import upcheck
```

Append this class to the end of the file:

```python
class TestParseTarget:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("spiegel.de", "https://spiegel.de"),
            ("  spiegel.de  ", "https://spiegel.de"),
            ("http://spiegel.de", "http://spiegel.de"),
            ("HTTPS://WWW.Spiegel.DE/", "https://www.spiegel.de/"),
            ("https://www.spiegel.de/politik/?x=1#top", "https://www.spiegel.de/politik/?x=1"),
            ("https://spiegel.de:443/", "https://spiegel.de/"),
            ("spiegel.de:8080", "https://spiegel.de:8080"),
            ("spiegel.de.", "https://spiegel.de."),
            ("bücher.de", "https://xn--bcher-kva.de"),
            ("[2001:db8::1]:8443", "https://[2001:db8::1]:8443"),
            ("1.1.1.1", "https://1.1.1.1"),
        ],
    )
    def test_accepts_and_normalizes(self, raw, expected):
        assert str(upcheck._parse_target(raw)) == expected

    @pytest.mark.parametrize(
        ("raw", "message"),
        [
            ("", "Enter a URL to check"),
            ("   ", "Enter a URL to check"),
            ("https://spiegel.de/" + "a" * 3000, "URL is too long"),
            ("spie gel.de", "URL contains spaces or control characters"),
            ("spiegel.de\t/politik", "URL contains spaces or control characters"),
            ("https://[zz]/", "Not a valid URL"),
            ("javascript:alert(1)", "Not a valid URL"),
            ("https://☃.de", "Not a valid URL"),
            ("ftp://spiegel.de", "Only http and https URLs can be checked"),
            ("file:///etc/passwd", "Only http and https URLs can be checked"),
            ("https://user:pass@spiegel.de", "URLs with a username or password aren't accepted"),
            ("mailto:x@spiegel.de", "URLs with a username or password aren't accepted"),
            ("https://", "Not a public hostname or IP address"),
            ("localhost", "Not a public hostname or IP address"),
            ("localhost:8081", "Not a public hostname or IP address"),
            ("intranet", "Not a public hostname or IP address"),
            ("2130706433", "Not a public hostname or IP address"),
            ("0x7f.1", "Not a public hostname or IP address"),
            ("127.1", "Not a public hostname or IP address"),
            ("exa_mple.de", "Not a public hostname or IP address"),
            ("spiegel.de:22", "Port 22 isn't allowed — only 80, 443, 8080 and 8443"),
            ("spiegel.de:0", "Port 0 isn't allowed — only 80, 443, 8080 and 8443"),
            ("spiegel.de:99999", "Port 99999 isn't allowed — only 80, 443, 8080 and 8443"),
        ],
    )
    def test_rejects_with_reason(self, raw, message):
        with pytest.raises(upcheck.Rejected) as exc_info:
            upcheck._parse_target(raw)
        assert str(exc_info.value) == message
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_upcheck.py::TestParseTarget -v`
Expected: FAIL — `AttributeError: module 'upcheck' has no attribute '_parse_target'`

- [x] **Step 3: Implement**

In `upcheck.py`, add `import re` so the stdlib imports read:

```python
import asyncio
import ipaddress
import re
import socket
import time
from urllib.parse import urlsplit
```

Directly below `_GEO_MAX_IPS = 4`, add:

```python
_MAX_URL_LENGTH = 2048
_ALLOWED_PORTS = frozenset({80, 443, 8080, 8443})
_WHITESPACE_OR_CONTROL = re.compile(r"[\x00-\x20\x7f]")
_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
```

Directly below the existing `_normalize_url` function, add:

```python
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
```

Notes for the implementer: `url.raw_host` is already the ASCII (punycode) form; httpx drops default ports, so `https://spiegel.de:443` has `url.port is None`.

- [x] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_upcheck.py -v`
Expected: PASS (new `TestParseTarget` cases and all existing tests)

- [x] **Step 5: Format and lint**

Run: `ruff format upcheck.py tests/test_upcheck.py && ruff check upcheck.py tests/test_upcheck.py`
Expected: the formatter may rewrap lines; `ruff check` reports no findings

- [x] **Step 6: Commit**

```bash
git add upcheck.py tests/test_upcheck.py
git commit -m "Add input rules for Is It Up? URLs" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016XZeNp625iwqJNCyWfdhRM"
```

---

### Task 2: Public-address resolution — `_resolve_public`

**Files:**
- Modify: `upcheck.py` (new code directly below `_parse_target`)
- Test: `tests/test_upcheck.py`

**Interfaces:**
- Consumes: `_is_ip(host: str) -> bool` (Task 1).
- Produces:
  - `class NotPublic(Exception)`, `class Unresolvable(Exception)`
  - `_lookup(host: str) -> list[str]` — the only DNS call; tests replace it.
  - `async _resolve_public(url: httpx.URL) -> list[str]` — deduplicated, IPv4 first; raises `NotPublic` or `Unresolvable`.
  - Constant `_DNS_TIMEOUT = 5.0` (read at call time, so tests can patch it).

- [x] **Step 1: Write the failing tests**

In `tests/test_upcheck.py`, extend the imports to:

```python
import asyncio
import socket
import time

import httpx
import pytest

import geo
import upcheck
```

Add these helpers directly below the imports:

```python
def _fake_dns(monkeypatch, answers):
    """Replace DNS. answers maps host -> list of IPs, or a callable taking the per-host call count."""
    calls = []

    def lookup(host):
        calls.append(host)
        if host not in answers:
            raise socket.gaierror("not found")
        answer = answers[host]
        return answer(calls.count(host)) if callable(answer) else answer

    monkeypatch.setattr(upcheck, "_lookup", lookup)
    return calls


def _resolve(raw):
    return asyncio.run(upcheck._resolve_public(httpx.URL(raw)))
```

Append this class to the end of the file:

```python
class TestResolvePublic:
    def test_returns_ipv4_first_without_duplicates(self, monkeypatch):
        _fake_dns(monkeypatch, {"spiegel.de": ["2606:4700:4700::1111", "1.1.1.1", "8.8.8.8", "1.1.1.1"]})
        assert _resolve("https://spiegel.de") == ["1.1.1.1", "8.8.8.8", "2606:4700:4700::1111"]

    def test_ip_literal_skips_dns(self, monkeypatch):
        calls = _fake_dns(monkeypatch, {})
        assert _resolve("https://1.1.1.1") == ["1.1.1.1"]
        assert calls == []

    @pytest.mark.parametrize(
        "addresses",
        [
            ["1.1.1.1", "10.0.0.1"],
            ["127.0.0.1"],
            ["169.254.169.254"],
            ["::ffff:127.0.0.1"],
            ["2002:7f00:1::"],
            ["64:ff9b::7f00:1"],
        ],
    )
    def test_blocks_when_any_address_is_not_public(self, monkeypatch, addresses):
        _fake_dns(monkeypatch, {"spiegel.de": addresses})
        with pytest.raises(upcheck.NotPublic):
            _resolve("https://spiegel.de")

    def test_nat64_of_public_ipv4_is_allowed(self, monkeypatch):
        _fake_dns(monkeypatch, {"spiegel.de": ["64:ff9b::808:808"]})
        assert _resolve("https://spiegel.de") == ["64:ff9b::808:808"]

    def test_private_ip_literal_is_blocked(self, monkeypatch):
        _fake_dns(monkeypatch, {})
        with pytest.raises(upcheck.NotPublic):
            _resolve("https://192.168.1.1")

    def test_unknown_host_is_unresolvable(self, monkeypatch):
        _fake_dns(monkeypatch, {})
        with pytest.raises(upcheck.Unresolvable):
            _resolve("https://spiegel.de")

    def test_slow_dns_is_unresolvable(self, monkeypatch):
        monkeypatch.setattr(upcheck, "_DNS_TIMEOUT", 0.05)
        _fake_dns(monkeypatch, {"spiegel.de": lambda _count: time.sleep(0.3) or ["1.1.1.1"]})
        with pytest.raises(upcheck.Unresolvable):
            _resolve("https://spiegel.de")
```

`64:ff9b::7f00:1` matters: Python reports it as `is_global == True`, so only the explicit NAT64 check catches the embedded `127.0.0.1`.

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_upcheck.py::TestResolvePublic -v`
Expected: FAIL — `AttributeError: module 'upcheck' has no attribute '_lookup'`

- [x] **Step 3: Implement**

In `upcheck.py`, below `_DNS_LABEL = ...`, add:

```python
_DNS_TIMEOUT = 5.0  # seconds
_NAT64 = ipaddress.IPv6Network("64:ff9b::/96")
```

Directly below `_parse_target`, add:

```python
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
```

`sorted` is stable, so IPv4 addresses come first and each family keeps resolver order.

- [x] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_upcheck.py -v`
Expected: PASS

- [x] **Step 5: Format and lint**

Run: `ruff format upcheck.py tests/test_upcheck.py && ruff check upcheck.py tests/test_upcheck.py`
Expected: the formatter may rewrap lines; `ruff check` reports no findings

- [x] **Step 6: Commit**

```bash
git add upcheck.py tests/test_upcheck.py
git commit -m "Resolve Is It Up? hosts and require every address to be public" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016XZeNp625iwqJNCyWfdhRM"
```

---

### Task 3: One pinned request — `_fetch_hop`

**Files:**
- Modify: `upcheck.py` (new code directly below `_resolve_public`)
- Test: `tests/test_upcheck.py`

**Interfaces:**
- Consumes: `_is_ip` (Task 1); existing `_TIMEOUT`, `_HEADERS`, `_RETRY_AS_GET`.
- Produces:
  - `_pinned(url: httpx.URL, ip: str) -> tuple[httpx.URL, dict[str, str], dict[str, str]]` — (request URL aimed at `ip`, headers with `Host`, request extensions).
  - `async _fetch_hop(url: httpx.URL, ip: str, transport: httpx.AsyncBaseTransport | None = None) -> httpx.Response` — never follows redirects.
  - Constant `_CONNECT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout)`.

- [x] **Step 1: Write the failing tests**

In `tests/test_upcheck.py`, add this helper below `_resolve`:

```python
def _recording(status=200, headers=None):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, headers=headers)

    return httpx.MockTransport(handler), seen
```

Append this class to the end of the file:

```python
class TestFetchHop:
    def _fetch(self, raw, ip, transport):
        return asyncio.run(upcheck._fetch_hop(httpx.URL(raw), ip, transport))

    def test_connects_to_checked_ip_with_real_host_name(self):
        transport, seen = _recording()
        response = self._fetch("https://www.spiegel.de:8443/politik/?x=1", "1.1.1.1", transport)
        assert response.status_code == 200
        [request] = seen
        assert request.method == "HEAD"
        assert str(request.url) == "https://1.1.1.1:8443/politik/?x=1"
        assert request.headers["host"] == "www.spiegel.de:8443"
        assert request.extensions["sni_hostname"] == "www.spiegel.de"

    def test_ipv6_address_is_bracketed(self):
        transport, seen = _recording()
        self._fetch("https://www.spiegel.de/", "2606:4700:4700::1111", transport)
        [request] = seen
        assert str(request.url) == "https://[2606:4700:4700::1111]/"
        assert request.headers["host"] == "www.spiegel.de"

    def test_ip_literal_host_sends_no_tls_name(self):
        transport, seen = _recording()
        self._fetch("https://1.1.1.1/", "1.1.1.1", transport)
        [request] = seen
        assert request.headers["host"] == "1.1.1.1"
        assert "sni_hostname" not in request.extensions

    def test_plain_http_sends_no_tls_name(self):
        transport, seen = _recording()
        self._fetch("http://spiegel.de/", "1.1.1.1", transport)
        [request] = seen
        assert request.headers["host"] == "spiegel.de"
        assert "sni_hostname" not in request.extensions

    def test_trailing_dot_is_dropped_from_host_header_and_tls_name(self):
        transport, seen = _recording()
        self._fetch("https://spiegel.de./", "1.1.1.1", transport)
        [request] = seen
        assert request.headers["host"] == "spiegel.de"
        assert request.extensions["sni_hostname"] == "spiegel.de"

    def test_rejected_head_is_retried_as_get_on_the_same_ip(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(405 if request.method == "HEAD" else 200)

        response = self._fetch("https://spiegel.de/", "1.1.1.1", httpx.MockTransport(handler))
        assert response.status_code == 200
        assert [(r.method, r.url.host) for r in seen] == [("HEAD", "1.1.1.1"), ("GET", "1.1.1.1")]

    def test_does_not_follow_redirects(self):
        transport, seen = _recording(302, {"Location": "http://127.0.0.1/"})
        response = self._fetch("https://spiegel.de/", "1.1.1.1", transport)
        assert response.status_code == 302
        assert len(seen) == 1

    def test_connect_failure_is_not_retried_as_get(self):
        seen = []

        def handler(request):
            seen.append(request)
            raise httpx.ConnectError("refused", request=request)

        with pytest.raises(httpx.ConnectError):
            self._fetch("https://spiegel.de/", "1.1.1.1", httpx.MockTransport(handler))
        assert [r.method for r in seen] == ["HEAD"]

    def test_head_protocol_error_still_falls_back_to_get(self):
        seen = []

        def handler(request):
            seen.append(request)
            if request.method == "HEAD":
                raise httpx.RemoteProtocolError("bad line", request=request)
            return httpx.Response(200)

        response = self._fetch("https://spiegel.de/", "1.1.1.1", httpx.MockTransport(handler))
        assert response.status_code == 200
        assert [r.method for r in seen] == ["HEAD", "GET"]

    def test_failing_get_retry_is_not_repeated(self):
        seen = []

        def handler(request):
            seen.append(request)
            if request.method == "HEAD":
                return httpx.Response(405)
            raise httpx.ReadError("boom", request=request)

        with pytest.raises(httpx.ReadError):
            self._fetch("https://spiegel.de/", "1.1.1.1", httpx.MockTransport(handler))
        assert [r.method for r in seen] == ["HEAD", "GET"]
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_upcheck.py::TestFetchHop -v`
Expected: FAIL — `AttributeError: module 'upcheck' has no attribute '_fetch_hop'`

- [x] **Step 3: Implement**

In `upcheck.py`, add below `_RETRY_AS_GET`:

```python
# A connect-level failure is the target's answer, not HEAD's — see _fetch_hop.
_CONNECT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout)
```

Then, directly below `_resolve_public`, add:

```python
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
```

`_CONNECT_ERRORS` needs both names: `httpx.ConnectTimeout` is a `TimeoutException`, not a subclass of `ConnectError`.

Why this is safe: httpcore passes `sni_hostname` to TLS as `server_hostname`, and httpx's default SSL context has `check_hostname` enabled, so the certificate is verified against the real hostname even though the socket goes to an IP.

- [x] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_upcheck.py -v`
Expected: PASS

- [x] **Step 5: Format and lint**

Run: `ruff format upcheck.py tests/test_upcheck.py && ruff check upcheck.py tests/test_upcheck.py`
Expected: the formatter may rewrap lines; `ruff check` reports no findings

- [x] **Step 6: Commit**

```bash
git add upcheck.py tests/test_upcheck.py
git commit -m "Pin Is It Up? requests to the checked address" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016XZeNp625iwqJNCyWfdhRM"
```

---

### Task 4: Redirect loop, endpoint wiring, removal of the old guard

**Files:**
- Modify: `upcheck.py` (module docstring; replace `_http_check` and `check_up`; delete `_normalize_url`, `_guard_ssrf`, `urlsplit` import)
- Test: `tests/test_upcheck.py`, `tests/test_routes.py`, `tests/test_privacy.py`

**Interfaces:**
- Consumes: `Rejected`, `_parse_target`, `_MAX_URL_LENGTH` (Task 1); `NotPublic`, `Unresolvable`, `_resolve_public` (Task 2); `_fetch_hop` (Task 3); existing `_classify`, `_describe`, `_geo_for`, `_MAX_REDIRECTS`.
- Produces:
  - `async _http_check(url: httpx.URL, ips: list[str], transport: httpx.AsyncBaseTransport | None = None) -> dict`
  - `async _run_check(raw: str, transport: httpx.AsyncBaseTransport | None = None) -> dict` — the full check the endpoint returns.
  - Constants `_CHECK_BUDGET = 12.0`, `_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})`.

- [x] **Step 1: Write the failing tests in `tests/test_upcheck.py`**

Add this helper below `_recording`:

```python
def _run(raw, handler):
    return asyncio.run(upcheck._run_check(raw, httpx.MockTransport(handler)))
```

Append this class to the end of the file:

```python
class TestRunCheck:
    def test_follows_redirects_and_reports_host_names(self, monkeypatch):
        _fake_dns(monkeypatch, {"spiegel.de": ["1.1.1.1"], "www.spiegel.de": ["8.8.8.8"]})
        seen = []

        def handler(request):
            seen.append(request)
            if request.headers["host"] == "spiegel.de":
                return httpx.Response(301, headers={"Location": "https://www.spiegel.de/"})
            if request.url.path == "/":
                return httpx.Response(302, headers={"Location": "/start"})
            return httpx.Response(200)

        result = _run("spiegel.de", handler)
        assert result["status"] == "up"
        assert result["stage"] == "done"
        assert result["http_status"] == 200
        assert result["final_url"] == "https://www.spiegel.de/start"
        assert result["redirects"] == ["https://spiegel.de", "https://www.spiegel.de/"]
        assert result["resolved_ips"] == ["1.1.1.1"]
        assert [r.url.host for r in seen] == ["1.1.1.1", "8.8.8.8", "8.8.8.8"]

    def test_redirect_to_disallowed_port_is_blocked_before_any_request(self, monkeypatch):
        _fake_dns(monkeypatch, {"spiegel.de": ["1.1.1.1"]})
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(302, headers={"Location": "http://127.0.0.1:8081/"})

        result = _run("spiegel.de", handler)
        assert result["status"] == "blocked"
        assert result["stage"] == "redirect"
        assert result["detail"] == (
            "Redirected to a URL that can't be checked: port 8081 isn't allowed — only 80, 443, 8080 and 8443"
        )
        assert result["redirects"] == ["https://spiegel.de"]
        assert "final_url" not in result
        assert len(seen) == 1

    def test_redirect_to_internal_address_is_blocked_before_any_request(self, monkeypatch):
        _fake_dns(monkeypatch, {"spiegel.de": ["1.1.1.1"], "intern.spiegel.de": ["10.0.0.1"]})
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(302, headers={"Location": "https://intern.spiegel.de/"})

        result = _run("spiegel.de", handler)
        assert result["status"] == "blocked"
        assert result["stage"] == "redirect"
        assert result["detail"] == "Redirected to a non-public address"
        assert len(seen) == 1

    def test_redirect_message_keeps_leading_acronym(self, monkeypatch):
        _fake_dns(monkeypatch, {"spiegel.de": ["1.1.1.1"]})

        def handler(request):
            return httpx.Response(302, headers={"Location": "https://user:pass@spiegel.de/"})

        result = _run("spiegel.de", handler)
        assert result["detail"] == (
            "Redirected to a URL that can't be checked: URLs with a username or password aren't accepted"
        )

    def test_redirect_to_unresolvable_host_is_down(self, monkeypatch):
        _fake_dns(monkeypatch, {"spiegel.de": ["1.1.1.1"]})

        def handler(request):
            return httpx.Response(302, headers={"Location": "https://gone.spiegel.de/"})

        result = _run("spiegel.de", handler)
        assert result["status"] == "down"
        assert result["stage"] == "dns"
        assert result["detail"] == "Redirect target does not resolve"
        assert result["redirects"] == ["https://spiegel.de"]

    def test_five_redirects_are_followed(self, monkeypatch):
        _fake_dns(monkeypatch, {"spiegel.de": ["1.1.1.1"]})
        seen = []

        def handler(request):
            seen.append(request)
            if len(seen) <= 5:
                return httpx.Response(302, headers={"Location": f"/hop{len(seen)}"})
            return httpx.Response(200)

        result = _run("spiegel.de", handler)
        assert result["status"] == "up"
        assert len(result["redirects"]) == 5
        assert len(seen) == 6

    def test_more_than_five_redirects_is_degraded(self, monkeypatch):
        _fake_dns(monkeypatch, {"spiegel.de": ["1.1.1.1"]})
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(302, headers={"Location": f"/hop{len(seen)}"})

        result = _run("spiegel.de", handler)
        assert result["status"] == "degraded"
        assert result["stage"] == "http"
        assert result["detail"] == "More than 5 redirects"
        assert len(result["redirects"]) == 6
        assert len(seen) == 6

    def test_redirect_status_without_location_is_final(self, monkeypatch):
        _fake_dns(monkeypatch, {"spiegel.de": ["1.1.1.1"]})
        transport, seen = _recording(302)
        result = asyncio.run(upcheck._run_check("spiegel.de", transport))
        assert result["status"] == "up"
        assert result["http_status"] == 302
        assert result["redirects"] == []
        assert len(seen) == 1

    def test_dns_is_not_asked_again_within_a_hop(self, monkeypatch):
        calls = _fake_dns(monkeypatch, {"spiegel.de": lambda count: ["1.1.1.1"] if count == 1 else ["127.0.0.1"]})
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(405 if request.method == "HEAD" else 200)

        result = _run("spiegel.de", handler)
        assert result["status"] == "up"
        assert calls == ["spiegel.de"]
        assert [(r.method, r.url.host) for r in seen] == [("HEAD", "1.1.1.1"), ("GET", "1.1.1.1")]

    def test_check_budget_is_enforced(self, monkeypatch):
        monkeypatch.setattr(upcheck, "_CHECK_BUDGET", 0.05)
        _fake_dns(monkeypatch, {"spiegel.de": ["1.1.1.1"]})

        async def handler(request):
            await asyncio.sleep(1)
            return httpx.Response(200)

        result = _run("spiegel.de", handler)
        assert result["status"] == "down"
        assert result["stage"] == "http"
        assert result["detail"] == "Check took too long"
        assert result["resolved_ips"] == ["1.1.1.1"]

    def test_entered_host_with_private_address_is_invalid(self, monkeypatch):
        _fake_dns(monkeypatch, {"spiegel.de": ["10.0.0.1"]})
        result = _run("spiegel.de", lambda request: httpx.Response(200))
        assert result == {"status": "invalid", "stage": "input", "detail": "Target resolves to a non-public address"}

    def test_rejected_input_has_no_geo(self, monkeypatch):
        calls = _fake_dns(monkeypatch, {})
        result = _run("spiegel.de:22", lambda request: httpx.Response(200))
        assert result == {
            "status": "invalid",
            "stage": "input",
            "detail": "Port 22 isn't allowed — only 80, 443, 8080 and 8443",
        }
        assert calls == []
```

- [x] **Step 2: Write the failing route tests in `tests/test_routes.py`**

Add `import upcheck` as the first line of the file, then append:

```python
def _no_dns(host):
    raise AssertionError(f"DNS must not be queried for rejected input, got {host!r}")


def test_up_rejects_disallowed_port_without_dns(client, monkeypatch):
    monkeypatch.setattr(upcheck, "_lookup", _no_dns)
    res = client.get("/api/up", params={"url": "spiegel.de:22"})
    assert res.json() == {
        "status": "invalid",
        "stage": "input",
        "detail": "Port 22 isn't allowed — only 80, 443, 8080 and 8443",
    }


def test_up_rejects_credentials_without_dns(client, monkeypatch):
    monkeypatch.setattr(upcheck, "_lookup", _no_dns)
    res = client.get("/api/up", params={"url": "user:pass@spiegel.de"})
    assert res.json() == {
        "status": "invalid",
        "stage": "input",
        "detail": "URLs with a username or password aren't accepted",
    }


def test_up_rejects_overlong_url_with_a_readable_message(client, monkeypatch):
    monkeypatch.setattr(upcheck, "_lookup", _no_dns)
    res = client.get("/api/up", params={"url": "https://spiegel.de/" + "a" * 3000})
    assert res.status_code == 200
    assert res.json() == {"status": "invalid", "stage": "input", "detail": "URL is too long"}
```

- [x] **Step 3: Write the failing privacy test in `tests/test_privacy.py`**

Append:

```python
def test_rejected_up_check_url_is_not_logged(client, caplog):
    marker = "privacy-marker-7f3a"
    with caplog.at_level(logging.DEBUG):
        res = client.get("/api/up", params={"url": f"https://{marker}.spiegel.de:22/"})
    assert res.json()["stage"] == "input"
    assert all(marker not in record.getMessage() for record in caplog.records)
```

With the old code the `stage` assertion fails: it accepts port 22, looks up the made-up host and answers `stage: dns`. The marker assertion guards future logging changes — the TestClient's own httpx request log would contain the marker if `main.py` ever stopped silencing the `httpx` logger.

- [x] **Step 4: Run the tests to verify they fail**

Run: `python -m pytest tests/test_upcheck.py::TestRunCheck -v`
Expected: FAIL — `AttributeError: module 'upcheck' has no attribute '_run_check'`

Do not run the new route and privacy tests yet: the old code accepts `spiegel.de:22` and would make real DNS and HTTP requests. They run with the full suite in Step 6.

- [x] **Step 5: Implement**

In `upcheck.py`:

1. Replace the module docstring with:

```python
"""Is-it-up checker: layered DNS -> TCP/TLS -> HTTP check for a user-supplied URL.

Mounted into main.py via `app.include_router(router)`.

Security note: this endpoint makes the server fetch user-supplied URLs. Every URL,
including each redirect target, must pass _parse_target() (scheme, credentials, host
form, port) and _resolve_public() (every address public). Each request is then pinned
to the checked address, so DNS rebinding cannot swap in an internal target.
"""
```

2. Remove `from urllib.parse import urlsplit` from the imports.

3. Below `_NAT64 = ...`, add:

```python
_CHECK_BUDGET = 12.0  # seconds for all DNS lookups and requests; nginx gives up after 15
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
```

4. Delete the functions `_normalize_url` and `_guard_ssrf` entirely.

5. Replace the existing `_http_check` function (the one using `follow_redirects=True`) with:

```python
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
```

6. Replace the whole `check_up` endpoint function with:

```python
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
```

`asyncio.timeout` turns the cancellation into the built-in `TimeoutError`; httpx's own timeouts are `httpx.TimeoutException` subclasses and are unaffected by the first `except`.

7. In `_resolve_public` (shipped in Task 2), add the note above the `wait_for` call explaining that the executor call cannot be cancelled — the Task 2 code block above now carries it:

```python
            # An executor call cannot be cancelled: after the timeout the thread stays in
            # getaddrinfo until the OS resolver gives up. Bounded in practice by the nginx
            # rate limit on /api/up (10/min, burst 3).
```

8. In `tests/test_upcheck.py`, delete the classes `TestNormalizeUrl` and `TestSsrfGuard` (the functions they test no longer exist; their cases are covered by `TestParseTarget` and `TestResolvePublic`).

- [x] **Step 6: Run the full test suite**

Run: `python -m pytest -v`
Expected: PASS. `test_up_dns_failure_has_no_geo` in `tests/test_routes.py` still performs a real DNS lookup for `this-domain-definitely-does-not-exist.invalid`; `.invalid` never resolves, so it passes offline too.

- [x] **Step 7: Format and lint**

Run: `ruff format . && ruff check .`
Expected: the formatter may rewrap lines; `ruff check` reports no findings

- [x] **Step 8: Commit**

```bash
git add upcheck.py tests/test_upcheck.py tests/test_routes.py tests/test_privacy.py
git commit -m "Re-check every Is It Up? redirect and enforce a total time budget" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016XZeNp625iwqJNCyWfdhRM"
```

---

### Task 5: Page support for the new status

**Files:**
- Modify: `static/up.html` (CSS line with `.status-invalid`; `<input id="url">`; `STATUS_LABELS`; `STAGE_LABELS`)
- Test: `tests/test_upcheck.py`

**Interfaces:**
- Consumes: API values `status: "blocked"` and `stage: "redirect"` (Task 4).
- Produces: nothing used by other tasks.

- [x] **Step 1: Write the failing tests**

In `tests/test_upcheck.py`, add `from pathlib import Path` to the stdlib imports, add below the helpers:

```python
UP_HTML = Path(__file__).resolve().parent.parent / "static" / "up.html"
```

and append:

```python
class TestUpPage:
    html = UP_HTML.read_text(encoding="utf-8")

    def test_input_is_length_limited(self):
        assert 'maxlength="2048"' in self.html

    def test_knows_blocked_status_and_redirect_stage(self):
        assert 'blocked: "Can\'t be checked"' in self.html
        assert 'redirect: "Redirect"' in self.html
        assert ".status-blocked" in self.html

    def test_server_text_is_never_injected_as_html(self):
        assert "innerHTML" not in self.html
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_upcheck.py::TestUpPage -v`
Expected: FAIL on the first two tests; `test_server_text_is_never_injected_as_html` already passes.

- [x] **Step 3: Implement**

In `static/up.html`:

Replace

```css
    .status-invalid { color: #c0c0c0; }
```

with

```css
    .status-invalid,
    .status-blocked { color: #c0c0c0; }
```

Replace

```html
        <input type="text" id="url" placeholder="example.com"
               autocomplete="off" spellcheck="false"
               aria-label="URL to check" />
```

with

```html
        <input type="text" id="url" placeholder="example.com"
               maxlength="2048" autocomplete="off" spellcheck="false"
               aria-label="URL to check" />
```

Replace

```js
    const STATUS_LABELS = {
      up: "Up",
      degraded: "Reachable, but erroring",
      down: "Down",
      invalid: "Invalid input",
    };

    const STAGE_LABELS = {
      dns: "DNS resolution",
      connect: "TCP connection",
      http: "HTTP request",
      input: "Input validation",
    };
```

with

```js
    const STATUS_LABELS = {
      up: "Up",
      degraded: "Reachable, but erroring",
      down: "Down",
      invalid: "Invalid input",
      blocked: "Can't be checked",
    };

    const STAGE_LABELS = {
      dns: "DNS resolution",
      connect: "TCP connection",
      http: "HTTP request",
      input: "Input validation",
      redirect: "Redirect",
    };
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest -v`
Expected: PASS

- [ ] **Step 5: Check the page in a browser**

> **Partly done (2026-09-20).** Verified against a local `uvicorn` on port 8765: `/up` serves `maxlength="2048"`, `.status-blocked`, `blocked: "Can't be checked"` and `redirect: "Redirect"`; `/api/up?url=spiegel.de:22` returns the expected `invalid`/`input` body; focus styling comes from `:focus-visible` in the shared `static/style.css` and `up.html` has no animation, so no `prefers-reduced-motion` fallback is needed. **Not** confirmed visually in a browser: the rendered result block and the input's typing limit.

Run: `uvicorn main:app --reload --port 8000`, open `http://localhost:8000/up`, and check:
- typing past 2048 characters is not possible;
- `spiegel.de:22` shows **Invalid input** with "Port 22 isn't allowed — only 80, 443, 8080 and 8443" and "Failed at: Input validation";
- keyboard focus is still visible on the input and the button.

- [x] **Step 6: Commit**

```bash
git add static/up.html tests/test_upcheck.py
git commit -m "Show blocked redirects on the Is It Up? page" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016XZeNp625iwqJNCyWfdhRM"
```

---

### Task 6: Deploy and smoke-check (only with the owner's approval)

**Files:** none

**Interfaces:**
- Consumes: the committed work from Tasks 1–5.
- Produces: the change running in production.

- [ ] **Step 1: Ask the owner for approval to deploy**

The whole stack was shut down with `docker compose down` on 2026-09-13 until this work is implemented, so this step brings the live site back online. Do not continue without an explicit yes.

- [ ] **Step 2: Rebuild and start the whole stack**

Run:
```bash
docker compose up -d --build
timeout 90 sh -c 'until curl -sf http://127.0.0.1:8000/health >/dev/null; do sleep 1; done' && echo app healthy
timeout 30 sh -c 'until curl -sko /dev/null -H "Host: alexander-hagemann.de" https://127.0.0.1:8443/; do sleep 1; done' && echo nginx up
docker compose ps
```
Expected: `app healthy`, `nginx up`, and `app`, `nginx`, `goatcounter`, `geoipupdate` and `certbot` all listed as running. The named volumes `goatcounter_data` and `geoip_data` were kept, so analytics history and GeoIP databases are still there.

- [ ] **Step 3: Smoke-check through nginx**

Run (each call is rate-limited to 10/min with burst 3, so the last ones may take a few seconds):
```bash
q() { curl -sk -G -H "Host: alexander-hagemann.de" --data-urlencode "url=$1" https://127.0.0.1:8443/api/up; echo; }
q spiegel.de
q spiegel.de:22
q 127.0.0.1.nip.io
q "https://httpbin.org/redirect-to?url=http://127.0.0.1/"
```
Expected, in order:
1. `"status":"up"`, `"stage":"done"`, a `final_url` on a spiegel.de host, and every URL in `redirects` using a hostname, never an IP.
2. `{"status":"invalid","stage":"input","detail":"Port 22 isn't allowed — only 80, 443, 8080 and 8443"}`
3. `{"status":"invalid","stage":"input","detail":"Target resolves to a non-public address"}`
4. `"status":"blocked"`, `"stage":"redirect"`, `"detail":"Redirected to a non-public address"`

Checks 3 and 4 depend on the third-party services nip.io and httpbin.org; if one is unavailable, note it and move on.

- [ ] **Step 4: Confirm nothing was logged**

Run: `docker compose logs --since 5m app | grep -cE "spiegel|nip\.io|httpbin"`
Expected: `0`
