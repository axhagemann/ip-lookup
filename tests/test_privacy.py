"""Keep the promises in datenschutz.html / privacy.html deliverable by the code."""

import logging
from pathlib import Path

import main  # noqa: F401  (imported for its logging setup)

ROOT = Path(__file__).resolve().parent.parent
POLICIES = [ROOT / "static" / name for name in ("datenschutz.html", "privacy.html")]
CONF = (ROOT / "nginx.docker.conf").read_text(encoding="utf-8")


def _https_block(server_name):
    for block in CONF.split("\nserver {")[1:]:
        if f"server_name {server_name};" in block and "8443 ssl;" in block:
            return block
    raise AssertionError(f"no HTTPS server block for {server_name}")


def test_httpx_does_not_log_checked_urls():
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


def test_up_checker_is_rate_limited_wherever_it_is_reachable():
    assert "location /api/up {" in _https_block("alexander-hagemann.de")
    assert CONF.count("location /api/up {") == CONF.count("limit_req zone=upcheck")


def test_proxy_sets_client_ip_instead_of_trusting_the_client():
    for name in ("alexander-hagemann.de", "ip4.alexander-hagemann.de", "ip6.alexander-hagemann.de"):
        for location in _https_block(name).split("location ")[1:]:
            if "proxy_pass http://ipinfo;" in location:
                assert "proxy_set_header X-Forwarded-For $remote_addr;" in location, (name, location)


def test_policies_cover_the_up_checker():
    for path in POLICIES:
        assert "Is It Up?" in path.read_text(encoding="utf-8")
