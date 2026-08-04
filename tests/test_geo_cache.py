import geo


def test_cache_roundtrip():
    geo._cache_set("203.0.113.1", {"country": "Testland"})
    assert geo._cache_get("203.0.113.1") == {"country": "Testland"}


def test_cache_miss_returns_none():
    assert geo._cache_get("203.0.113.2") is None


def test_cache_expires_after_ttl(monkeypatch):
    times = iter([1000.0, 1000.0 + geo._GEO_TTL + 1])
    monkeypatch.setattr(geo, "time", lambda: next(times))

    geo._cache_set("203.0.113.3", {"country": "Testland"})
    assert geo._cache_get("203.0.113.3") is None
    assert "203.0.113.3" not in geo._geo_cache


def test_cache_evicts_oldest_when_full(monkeypatch):
    monkeypatch.setattr(geo, "_GEO_MAX", 2)

    times = iter([1.0, 2.0, 3.0])
    monkeypatch.setattr(geo, "time", lambda: next(times))

    geo._cache_set("a", {})
    geo._cache_set("b", {})
    geo._cache_set("c", {})

    assert "a" not in geo._geo_cache
    assert "b" in geo._geo_cache
    assert "c" in geo._geo_cache


def test_lookup_caches_result(monkeypatch):
    calls = []

    def fake_lookup(ip):
        calls.append(ip)
        return {"country": "Testland"}

    monkeypatch.setattr(geo, "_geo_lookup", fake_lookup)

    assert geo.lookup("203.0.113.4") == {"country": "Testland"}
    assert geo.lookup("203.0.113.4") == {"country": "Testland"}
    assert calls == ["203.0.113.4"]


def test_lookup_caches_empty_result(monkeypatch):
    """An unknown IP must not be re-queried on every request."""
    calls = []
    monkeypatch.setattr(geo, "_geo_lookup", lambda ip: calls.append(ip) or {})

    assert geo.lookup("203.0.113.5") == {}
    assert geo.lookup("203.0.113.5") == {}
    assert calls == ["203.0.113.5"]
