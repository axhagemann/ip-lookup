import upcheck


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_getip_serves_html(client):
    res = client.get("/getip")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "IPv4" in res.text


def test_cidr_serves_html(client):
    res = client.get("/cidr")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "CIDR" in res.text


def test_index_serves_html_for_browser(client):
    res = client.get("/", headers={"User-Agent": "Mozilla/5.0"})
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]


def test_index_serves_json_for_script(client):
    res = client.get("/", headers={"User-Agent": "curl/8.5.0"})
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"timestamp", "ipv4", "ipv6"}
    assert body["ipv4"] or body["ipv6"]


def test_up_serves_html(client):
    res = client.get("/up")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]


def test_up_invalid_url_has_no_geo(client):
    """Nothing was resolved, so there is nothing to geolocate."""
    res = client.get("/api/up", params={"url": "ftp://example.com"})
    body = res.json()
    assert body["status"] == "invalid"
    assert "ip_geo" not in body
    assert "resolved_ips" not in body


def test_up_dns_failure_has_no_geo(client):
    res = client.get("/api/up", params={"url": "this-domain-definitely-does-not-exist.invalid"})
    body = res.json()
    assert body["status"] == "down"
    assert body["stage"] == "dns"
    assert "ip_geo" not in body


def test_ip_endpoint_returns_ip_and_geo(client):
    res = client.get("/ip", headers={"X-Forwarded-For": "203.0.113.42"})
    assert res.status_code == 200
    body = res.json()
    assert body["ip"] == "203.0.113.42"
    assert "geo" in body


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
