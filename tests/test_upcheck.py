"""Tests for upcheck.py — URL normalization, SSRF guard, and response classification."""

import pytest

import geo
import upcheck


class TestNormalizeUrl:
    def test_adds_https_when_scheme_missing(self):
        assert upcheck._normalize_url("example.com") == "https://example.com"

    def test_keeps_explicit_http(self):
        assert upcheck._normalize_url("http://example.com") == "http://example.com"

    def test_rejects_empty(self):
        assert upcheck._normalize_url("") is None
        assert upcheck._normalize_url("   ") is None

    def test_rejects_non_http_schemes(self):
        assert upcheck._normalize_url("ftp://example.com") is None
        assert upcheck._normalize_url("file:///etc/passwd") is None

    def test_rejects_missing_host(self):
        assert upcheck._normalize_url("https://") is None

    def test_rejects_oversized_input(self):
        assert upcheck._normalize_url("https://example.com/" + "a" * 3000) is None


class TestSsrfGuard:
    def test_blocks_loopback(self):
        _, error = upcheck._guard_ssrf("localhost")
        assert error == "blocked"

    def test_blocks_private_ipv4_literal(self):
        _, error = upcheck._guard_ssrf("192.168.1.1")
        assert error == "blocked"

    def test_blocks_ipv4_mapped_ipv6(self):
        _, error = upcheck._guard_ssrf("::ffff:127.0.0.1")
        assert error == "blocked"

    def test_blocks_link_local_metadata_range(self):
        # Cloud metadata endpoints live at 169.254.169.254
        _, error = upcheck._guard_ssrf("169.254.169.254")
        assert error == "blocked"

    def test_dns_failure_reported(self):
        _, error = upcheck._guard_ssrf("this-domain-definitely-does-not-exist.invalid")
        assert error == "dns"


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
