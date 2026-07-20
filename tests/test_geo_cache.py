import main


def test_cache_roundtrip():
    main._cache_set("203.0.113.1", {"country": "Testland"})
    assert main._cache_get("203.0.113.1") == {"country": "Testland"}


def test_cache_miss_returns_none():
    assert main._cache_get("203.0.113.2") is None


def test_cache_expires_after_ttl(monkeypatch):
    times = iter([1000.0, 1000.0 + main._GEO_TTL + 1])
    monkeypatch.setattr(main, "time", lambda: next(times))

    main._cache_set("203.0.113.3", {"country": "Testland"})
    assert main._cache_get("203.0.113.3") is None
    assert "203.0.113.3" not in main._geo_cache


def test_cache_evicts_oldest_when_full(monkeypatch):
    monkeypatch.setattr(main, "_GEO_MAX", 2)

    times = iter([1.0, 2.0, 3.0])
    monkeypatch.setattr(main, "time", lambda: next(times))

    main._cache_set("a", {})
    main._cache_set("b", {})
    main._cache_set("c", {})

    assert "a" not in main._geo_cache
    assert "b" in main._geo_cache
    assert "c" in main._geo_cache
