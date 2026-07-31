"""Tests for upcheck.py — URL normalization, SSRF guard, and response classification."""

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