"""Tests for upcheck.py — input rules, address checks, pinned requests, and the full check."""

import asyncio
import gzip
import http.server
import socket
import threading
import time
import zlib
from pathlib import Path

import httpx
import pytest

import geo
import upcheck


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


def _recording(status=200, headers=None):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, headers=headers)

    return httpx.MockTransport(handler), seen


UP_HTML = Path(__file__).resolve().parent.parent / "static" / "up.html"


def _run(raw, handler):
    return asyncio.run(upcheck._run_check(raw, httpx.MockTransport(handler)))


class TestClassify:
    def test_2xx_is_up(self):
        assert upcheck._classify(200) == "up"
        assert upcheck._classify(204) == "up"

    def test_3xx_is_up(self):
        assert upcheck._classify(301) == "up"

    def test_5xx_is_down(self):
        assert upcheck._classify(500) == "down"
        assert upcheck._classify(503) == "down"

    def test_refused_codes_are_up(self):
        # Server answered — it's alive, just declined this client
        assert upcheck._classify(401) == "up"
        assert upcheck._classify(403) == "up"
        assert upcheck._classify(429) == "up"

    def test_other_4xx_is_degraded(self):
        assert upcheck._classify(404) == "degraded"
        assert upcheck._classify(410) == "degraded"

    def test_challenge_is_up_whatever_the_code(self):
        # Old Cloudflare interstitials came as 503; the challenge still proves a server answered.
        assert upcheck._classify(503, challenged=True) == "up"
        assert upcheck._classify(403, challenged=True) == "up"


def _response(status=403, headers=None, body=b""):
    return httpx.Response(status, headers=headers, content=body)


def _challenge(status=403, headers=None, body=b""):
    """_is_challenge() over a response and the capped body read alongside it."""
    return upcheck._is_challenge(_response(status, headers), body)


CHALLENGE_BODY = b'<!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title>'


def _challenge_handler(request):
    """Answers every request with a Cloudflare challenge."""
    headers = {"content-type": "text/html; charset=UTF-8", "cf-mitigated": "challenge"}
    return httpx.Response(403, headers=headers, content=CHALLENGE_BODY)


def _stub_impersonation(status):
    async def impersonated(url, ip):
        return status

    return impersonated


class TestIsChallenge:
    def test_cf_mitigated_header_is_enough(self):
        assert _challenge(headers={"cf-mitigated": "challenge"})

    def test_interstitial_title_is_enough(self):
        headers = {"content-type": "text/html; charset=UTF-8"}
        assert _challenge(headers=headers, body=CHALLENGE_BODY)

    def test_head_without_body_relies_on_the_header(self):
        headers = {"content-type": "text/html", "cf-mitigated": "challenge"}
        assert _challenge(headers=headers)

    def test_plain_403_behind_cloudflare_is_not_a_challenge(self):
        # A site's own 403 carries server/cf-ray too, so those must not count.
        headers = {"server": "cloudflare", "cf-ray": "abc-HEL", "content-type": "text/html"}
        assert not _challenge(headers=headers, body=b"<h1>Forbidden</h1>")

    def test_ordinary_page_is_not_a_challenge(self):
        headers = {"content-type": "text/html"}
        assert not _challenge(200, headers=headers, body=b"<title>Home</title>")

    def test_title_far_into_a_large_body_is_ignored(self):
        headers = {"content-type": "text/html"}
        assert not _challenge(headers=headers, body=b"<x>" * 2000 + CHALLENGE_BODY)

    def test_non_html_body_is_not_sniffed(self):
        headers = {"content-type": "application/octet-stream"}
        assert not _challenge(headers=headers, body=CHALLENGE_BODY)


class TestInflate:
    def test_identity_body_passes_through_capped(self):
        assert upcheck._inflate(b"x" * 5000, "") == b"x" * upcheck._CHALLENGE_SNIFF

    def test_gzip_bomb_yields_at_most_the_sniff_size(self):
        bomb = gzip.compress(b"\0" * (16 * 1024 * 1024))  # 16 MB from ~16 KB
        assert len(bomb) < upcheck._SNIFF_RAW  # the whole bomb fits in what we read
        assert len(upcheck._inflate(bomb, "gzip")) == upcheck._CHALLENGE_SNIFF

    def test_zlib_wrapped_deflate_is_read(self):
        assert upcheck._inflate(zlib.compress(b"<title>Just a moment..."), "deflate").startswith(b"<title>")

    def test_bare_deflate_is_read(self):
        compressor = zlib.compressobj(wbits=-15)
        raw = compressor.compress(b"<title>Just a moment...") + compressor.flush()
        assert upcheck._inflate(raw, "deflate").startswith(b"<title>")

    def test_encoding_we_cannot_bound_is_skipped(self):
        # br/zstd have no stdlib bounded decoder; _is_challenge falls back to the header.
        assert upcheck._inflate(b"anything", "br") == b""

    def test_corrupt_body_is_not_an_error(self):
        assert upcheck._inflate(b"not actually gzip", "gzip") == b""


class TestBodyReadIsBounded:
    """A target picks its own compression ratio, so the read must be capped."""

    @staticmethod
    def _serve(body, headers):
        class Handler(http.server.BaseHTTPRequestHandler):
            def _headers(self):
                self.send_response(403)  # in _RETRY_AS_GET, so HEAD is retried as GET
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()

            def do_HEAD(self):
                self._headers()

            def do_GET(self):
                self._headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    def _fetch(self, body, headers):
        server = self._serve(body, headers)
        try:
            url = httpx.URL(f"http://127.0.0.1:{server.server_port}/")
            return asyncio.run(upcheck._fetch_hop(url, "127.0.0.1"))
        finally:
            server.shutdown()

    def test_a_gzip_bomb_is_not_buffered(self):
        # 64 MB of body behind a few KB on the wire. Reading it whole is the bug.
        body = gzip.compress(CHALLENGE_BODY + b"\0" * (64 * 1024 * 1024))
        headers = {"Content-Type": "text/html", "Content-Encoding": "gzip"}
        hop = self._fetch(body, headers)
        assert hop.response.status_code == 403
        assert len(hop.body) <= upcheck._CHALLENGE_SNIFF
        # Bounded, and still enough to recognise the interstitial.
        assert upcheck._is_challenge(hop.response, hop.body)

    def test_a_huge_uncompressed_body_is_not_buffered(self):
        body = b"<html>" + b"\0" * (8 * 1024 * 1024)
        hop = self._fetch(body, {"Content-Type": "text/html"})
        assert len(hop.body) <= upcheck._CHALLENGE_SNIFF


class TestDescribe:
    def test_challenge_is_named_as_such(self):
        message = upcheck._describe(403, challenged=True)
        assert message == "Site is up, but served a bot-protection challenge (403). A human browser will reach it fine."

    def test_refusal_without_a_challenge_stays_hedged(self):
        assert "most likely" in upcheck._describe(403)


class _FakeCurl:
    def __init__(self):
        self.options = {}

    def setopt(self, option, value):
        self.options[option] = value


class _FakeSession:
    """Stands in for curl_cffi.requests.Session, recording what it was asked to do."""

    last = None

    def __init__(self, result):
        self.curl = _FakeCurl()
        self.result = result
        self.call = None
        type(self).last = self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, **kwargs):
        self.call = {"url": url, **kwargs}
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _FakeCurlResponse:
    """A curl_cffi response: streamed in chunks, closed by the caller."""

    def __init__(self, status=403, headers=None, chunks=()):
        self.status_code = status
        self.headers = httpx.Headers(headers or {})
        self.chunks = list(chunks)
        self.read = []
        self.closed = False

    def iter_content(self):
        for chunk in self.chunks:
            self.read.append(chunk)
            yield chunk

    def close(self):
        self.closed = True


def _fake_curl_module(monkeypatch, result):
    """Enable impersonation with a stubbed curl_cffi that returns `result`."""
    monkeypatch.setattr(upcheck, "_IMPERSONATE", True)
    monkeypatch.setattr(upcheck, "CurlOpt", type("CurlOpt", (), {"RESOLVE": 10203}))
    module = type("curl_requests", (), {"Session": staticmethod(lambda: _FakeSession(result))})
    monkeypatch.setattr(upcheck, "curl_requests", module)


def _impersonate(raw="https://www.allianz.de/", ip="1.1.1.1"):
    return asyncio.run(upcheck._impersonated_status(httpx.URL(raw), ip))


class TestImpersonatedStatus:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.setattr(upcheck, "_IMPERSONATE", False)
        assert _impersonate() is None

    def test_returns_none_when_curl_cffi_is_not_installed(self, monkeypatch):
        monkeypatch.setattr(upcheck, "_IMPERSONATE", True)
        monkeypatch.setattr(upcheck, "curl_requests", None)
        assert _impersonate() is None

    def test_returns_status_when_the_retry_gets_through(self, monkeypatch):
        _fake_curl_module(monkeypatch, _FakeCurlResponse(200, {"content-type": "text/html"}, [b"<h1>Hallo</h1>"]))
        assert _impersonate() == 200

    def test_returns_none_when_the_retry_is_challenged_too(self, monkeypatch):
        headers = {"content-type": "text/html", "cf-mitigated": "challenge"}
        _fake_curl_module(monkeypatch, _FakeCurlResponse(403, headers, [CHALLENGE_BODY]))
        assert _impersonate() is None

    def test_a_failing_retry_is_swallowed(self, monkeypatch):
        _fake_curl_module(monkeypatch, OSError("TLS handshake failed"))
        assert _impersonate() is None

    def test_pins_to_the_checked_ip_and_never_follows_redirects(self, monkeypatch):
        _fake_curl_module(monkeypatch, _FakeCurlResponse(200, {"content-type": "text/html"}))
        _impersonate("https://www.allianz.de/", "8.8.8.8")
        session = _FakeSession.last
        assert session.curl.options[upcheck.CurlOpt.RESOLVE] == [b"www.allianz.de:443:8.8.8.8"]
        assert session.call["allow_redirects"] is False
        assert session.call["impersonate"] == upcheck._IMPERSONATE_PROFILE

    def test_pin_uses_the_explicit_port_when_there_is_one(self, monkeypatch):
        _fake_curl_module(monkeypatch, _FakeCurlResponse(200, {"content-type": "text/html"}))
        _impersonate("https://www.allianz.de:8080/", "8.8.8.8")
        assert _FakeSession.last.curl.options[upcheck.CurlOpt.RESOLVE] == [b"www.allianz.de:8080:8.8.8.8"]


class TestGeoFor:
    def test_empty_when_no_databases(self, monkeypatch):
        monkeypatch.setattr(geo, "_city_reader", None)
        monkeypatch.setattr(geo, "_asn_reader", None)
        assert upcheck._geo_for(["93.184.216.34"]) == []

    def test_entries_carry_their_ip(self, monkeypatch):
        monkeypatch.setattr(geo, "_geo_lookup", lambda ip: {"country": "Testland"})
        assert upcheck._geo_for(["203.0.113.1"]) == [{"ip": "203.0.113.1", "country": "Testland"}]

    def test_preserves_input_order(self, monkeypatch):
        monkeypatch.setattr(geo, "_geo_lookup", lambda ip: {"country": "Testland"})
        ips = ["203.0.113.3", "203.0.113.1", "203.0.113.2"]
        assert [entry["ip"] for entry in upcheck._geo_for(ips)] == ips

    def test_caps_number_of_lookups(self, monkeypatch):
        monkeypatch.setattr(geo, "_geo_lookup", lambda ip: {"country": "Testland"})
        ips = [f"203.0.113.{n}" for n in range(1, 11)]
        assert len(upcheck._geo_for(ips)) == upcheck._GEO_MAX_IPS

    def test_skips_ips_with_no_known_location(self, monkeypatch):
        monkeypatch.setattr(
            geo,
            "_geo_lookup",
            lambda ip: {"country": "Testland"} if ip == "203.0.113.1" else {},
        )
        located = upcheck._geo_for(["203.0.113.1", "203.0.113.2"])
        assert [entry["ip"] for entry in located] == ["203.0.113.1"]


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


class TestFetchHop:
    def _fetch(self, raw, ip, transport):
        return asyncio.run(upcheck._fetch_hop(httpx.URL(raw), ip, transport)).response

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


class TestRunCheck:
    def test_challenge_page_reports_up_and_says_it_was_challenged(self, monkeypatch):
        # The allianz.de shape: apex redirects to www, which serves a Cloudflare challenge.
        _fake_dns(monkeypatch, {"allianz.de": ["1.1.1.1"], "www.allianz.de": ["8.8.8.8"]})

        def handler(request):
            if request.headers["host"] == "allianz.de":
                return httpx.Response(301, headers={"Location": "https://www.allianz.de:443/"})
            headers = {"content-type": "text/html; charset=UTF-8", "cf-mitigated": "challenge"}
            return httpx.Response(403, headers=headers, content=CHALLENGE_BODY)

        result = _run("allianz.de", handler)
        assert result["status"] == "up"
        assert result["http_status"] == 403
        assert result["detail"] == (
            "Site is up, but served a bot-protection challenge (403). A human browser will reach it fine."
        )

    def test_impersonated_retry_reports_what_it_got_through_to(self, monkeypatch):
        _fake_dns(monkeypatch, {"allianz.de": ["1.1.1.1"]})
        monkeypatch.setattr(upcheck, "_impersonated_status", _stub_impersonation(200))

        result = _run("allianz.de", _challenge_handler)
        assert result["status"] == "up"
        assert result["http_status"] == 200
        assert result["detail"] == (
            "Site is up — bot protection challenged this check, but a browser-shaped retry got through (200)."
        )

    def test_failed_impersonation_leaves_the_challenge_result_alone(self, monkeypatch):
        _fake_dns(monkeypatch, {"allianz.de": ["1.1.1.1"]})
        monkeypatch.setattr(upcheck, "_impersonated_status", _stub_impersonation(None))

        result = _run("allianz.de", _challenge_handler)
        assert result["status"] == "up"
        assert result["http_status"] == 403
        assert "bot-protection challenge" in result["detail"]

    def test_impersonated_redirect_is_not_treated_as_getting_through(self, monkeypatch):
        # 302 means "go elsewhere", and that target has not been vetted.
        _fake_dns(monkeypatch, {"allianz.de": ["1.1.1.1"]})
        monkeypatch.setattr(upcheck, "_impersonated_status", _stub_impersonation(302))

        result = _run("allianz.de", _challenge_handler)
        assert result["http_status"] == 403
        assert "bot-protection challenge" in result["detail"]

    def test_impersonation_is_only_tried_on_a_challenge(self, monkeypatch):
        _fake_dns(monkeypatch, {"spiegel.de": ["1.1.1.1"]})
        calls = []

        async def never(url, ip):
            calls.append(url)
            return 200

        monkeypatch.setattr(upcheck, "_impersonated_status", never)
        result = _run("spiegel.de", lambda request: httpx.Response(403))
        assert result["http_status"] == 403
        assert calls == []

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
        assert result["redirects"] == ["https://spiegel.de/", "https://www.spiegel.de/"]
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
        assert result["redirects"] == ["https://spiegel.de/"]
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
        assert result["redirects"] == ["https://spiegel.de/"]

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


class TestOriginOnly:
    """The entered URL is reduced to its origin; only redirect targets keep a path."""

    def test_path_and_query_are_never_requested(self, monkeypatch):
        _fake_dns(monkeypatch, {"spiegel.de": ["1.1.1.1"]})
        transport, seen = _recording()
        result = asyncio.run(upcheck._run_check("spiegel.de/admin?token=abc", transport))
        assert result["status"] == "up"
        assert result["ignored_path"] == "/admin?token=abc"
        assert result["final_url"] == "https://spiegel.de/"
        assert [str(r.url) for r in seen] == ["https://1.1.1.1/"]

    def test_query_without_a_path_is_reported(self, monkeypatch):
        _fake_dns(monkeypatch, {"spiegel.de": ["1.1.1.1"]})
        transport, seen = _recording()
        result = asyncio.run(upcheck._run_check("spiegel.de?token=abc", transport))
        assert result["ignored_path"] == "/?token=abc"
        assert [str(r.url) for r in seen] == ["https://1.1.1.1/"]

    def test_port_and_scheme_survive_truncation(self, monkeypatch):
        _fake_dns(monkeypatch, {"spiegel.de": ["1.1.1.1"]})
        transport, seen = _recording()
        result = asyncio.run(upcheck._run_check("http://spiegel.de:8080/x", transport))
        assert result["ignored_path"] == "/x"
        assert [str(r.url) for r in seen] == ["http://1.1.1.1:8080/"]

    @pytest.mark.parametrize("raw", ["spiegel.de", "spiegel.de/", "https://spiegel.de/#top"])
    def test_nothing_to_ignore_reports_nothing(self, monkeypatch, raw):
        _fake_dns(monkeypatch, {"spiegel.de": ["1.1.1.1"]})
        transport, _seen = _recording()
        result = asyncio.run(upcheck._run_check(raw, transport))
        assert "ignored_path" not in result

    def test_reported_even_when_the_domain_does_not_resolve(self, monkeypatch):
        _fake_dns(monkeypatch, {})
        result = _run("spiegel.de/admin", lambda request: httpx.Response(200))
        assert result["status"] == "down"
        assert result["stage"] == "dns"
        assert result["ignored_path"] == "/admin"

    def test_reported_even_when_the_address_is_not_public(self, monkeypatch):
        _fake_dns(monkeypatch, {"spiegel.de": ["10.0.0.1"]})
        result = _run("spiegel.de/admin", lambda request: httpx.Response(200))
        assert result["status"] == "invalid"
        assert result["ignored_path"] == "/admin"

    def test_redirect_target_keeps_its_path(self, monkeypatch):
        _fake_dns(monkeypatch, {"spiegel.de": ["1.1.1.1"]})
        seen = []

        def handler(request):
            seen.append(request)
            if request.url.path == "/":
                return httpx.Response(302, headers={"Location": "/en/home"})
            return httpx.Response(200)

        result = _run("spiegel.de/admin", handler)
        assert result["status"] == "up"
        assert result["final_url"] == "https://spiegel.de/en/home"
        assert [r.url.path for r in seen] == ["/", "/en/home"]


class TestUpPage:
    html = UP_HTML.read_text(encoding="utf-8")

    def test_input_is_length_limited(self):
        assert 'maxlength="2048"' in self.html

    def test_knows_blocked_status_and_redirect_stage(self):
        assert 'blocked: "Can\'t be checked"' in self.html
        assert 'redirect: "Redirect"' in self.html
        # Status styles live in the shared stylesheet since the light/dark redesign.
        assert ".status-blocked" in UP_HTML.with_name("style.css").read_text(encoding="utf-8")

    def test_says_up_front_that_only_the_domain_is_checked(self):
        assert "Only the domain is checked" in self.html

    def test_renders_the_ignored_path_from_the_response(self):
        assert "ignored_path" in self.html

    def test_server_text_is_never_injected_as_html(self):
        assert "innerHTML" not in self.html
