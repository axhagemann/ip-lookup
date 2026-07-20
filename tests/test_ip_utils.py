import pytest
from starlette.datastructures import Headers
from starlette.requests import Request

import main


def _request(headers: dict[str, str] | None = None, client_host: str | None = "203.0.113.5"):
    scope = {
        "type": "http",
        "headers": Headers(headers or {}).raw,
        "client": (client_host, 12345) if client_host else None,
    }
    return Request(scope)


@pytest.mark.parametrize(
    ("ip", "expected"),
    [
        ("203.0.113.42", "203.0.113.0"),
        ("2001:db8:1234:5678::1", "2001:db8:1234::"),
        ("::ffff:203.0.113.42", "203.0.113.0"),
        ("not-an-ip", "not-an-ip"),
    ],
)
def test_truncate_ip(ip, expected):
    assert main._truncate_ip(ip) == expected


def test_client_ip_prefers_forwarded_for():
    req = _request({"X-Forwarded-For": "198.51.100.9, 10.0.0.1"})
    assert main._client_ip(req) == "198.51.100.9"


def test_client_ip_falls_back_to_socket_peer():
    req = _request(client_host="203.0.113.5")
    assert main._client_ip(req) == "203.0.113.5"


def test_client_ip_unknown_without_peer_or_header():
    req = _request(client_host=None)
    assert main._client_ip(req) == "unknown"


@pytest.mark.parametrize(
    ("user_agent", "expected"),
    [
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", True),
        ("curl/8.5.0", False),
        ("", False),
    ],
)
def test_is_browser(user_agent, expected):
    req = _request({"User-Agent": user_agent} if user_agent else {})
    assert main._is_browser(req) is expected
