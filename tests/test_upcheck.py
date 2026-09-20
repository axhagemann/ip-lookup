"""Tests for upcheck.py — input rules, address checks, pinned requests, and the full check."""

import asyncio
import socket
import time
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
