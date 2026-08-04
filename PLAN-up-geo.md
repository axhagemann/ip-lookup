# Plan — Geolocation for resolved IPs in `/up`

Add server-side geolocation for the IPs that the "Is It Up?" checker resolves,
reusing the existing GeoLite2 readers and per-IP cache.

## Constraint that shapes everything

`main.py:15` imports `upcheck`, so `upcheck.py` cannot import geo helpers back
from `main.py` (circular import). The geo code has to move out first.

---

## Step 1 — Extract `geo.py`

New module `geo.py`, moved verbatim from `main.py:59-122`: `_geo_cache`,
`_GEO_TTL`, `_GEO_MAX`, `_city_reader`/`_asn_reader`, `_load_readers()`,
`_retry_readers()`, `_cache_get`, `_cache_set`, `_geo_lookup`.

Add the one thing currently inlined in the `/ip` handler (`main.py:158-161`) as
the module's public entry point:

```python
def lookup(ip: str) -> dict:
    cached = _cache_get(ip)
    if cached is not None:
        return cached
    result = _geo_lookup(ip)
    _cache_set(ip, result)
    return result
```

`main.py` then: `import geo`, `/ip` returns `{"ip": ip, "geo": geo.lookup(ip)}`,
lifespan calls `geo.retry_readers()`. Pure refactor, no behavior change.

## Step 2 — Geo in the `/api/up` response

In `upcheck.py`, after the SSRF guard has already resolved the host (no extra
DNS needed):

```python
_GEO_MAX_IPS = 4  # bound work when DNS round-robins many A records

def _geo_for(ips: list[str]) -> list[dict]:
    out = []
    for ip in ips[:_GEO_MAX_IPS]:
        data = geo.lookup(ip)
        if data:
            out.append({"ip": ip, **data})
    return out
```

**Attach it on every path that already returns `resolved_ips`** — including the
`connect`/timeout/`http` failure branches. A site that is *down* is exactly when
"whose IP is this?" is most useful. The five `except` blocks at
`upcheck.py:151-160` already repeat `"resolved_ips": ips`; fold that into a
shared `base = {"resolved_ips": ips, "ip_geo": _geo_for(ips)}` dict merged into
each return, which removes the existing duplication rather than doubling it.

Response shape — a **list**, ordered like `resolved_ips`:

```json
"resolved_ips": ["93.184.216.34"],
"ip_geo": [{"ip": "93.184.216.34", "country": "United States",
            "city": "Los Angeles", "isp": "AS15133 EDGECAST", "...": "..."}]
```

Empty list when GeoLite2 hasn't loaded or the IP isn't in the DB — the UI just
omits the line, no error path.

> Alternative rejected: geolocating only the first IP. Anycast/CDN hosts
> legitimately resolve to several, and a per-IP list costs nothing since lookups
> are memory-mapped mmdb reads (microseconds, same as `/ip` does synchronously
> today).

## Step 3 — Render in `up.html`

`addField` (line 193) is `textContent`-only, so it can't hold a two-line cell.
Add a sibling that accepts a node, and render the resolved-IP field as one block
per IP:

```
RESOLVED IPS   93.184.216.34
               Los Angeles, United States · AS15133 EDGECAST
```

The secondary line gets `#999`, `0.75rem` — no new borders, no hue, no radius,
consistent with the existing `dl`. Falls back to today's plain comma-joined list
when `ip_geo` is empty.

Two accessibility items while in there:

- `#result` (line 153) has **no** `aria-live` — it's dynamic content, so per
  CLAUDE.md it needs `aria-live="polite"`. Pre-existing gap; fixing it here
  since we're adding more dynamic content to that region.
- Add the approximate-geolocation disclaimer line that `getip.html:226` already
  carries, for consistency.

## Step 4 — Tests

- `tests/test_geo_cache.py` + `tests/conftest.py`: retarget `main._cache_set` →
  `geo._cache_set`, and the monkeypatches of `main.time` / `main._GEO_MAX` →
  `geo.*`. Required — those tests patch module attributes, so aliasing in `main`
  would silently break them.
- `tests/test_upcheck.py`: new `TestGeoFor` — returns `[]` when readers are
  absent, caps at 4, each entry carries `ip`. Monkeypatch `geo._geo_lookup` with
  a fake so no `.mmdb` file is needed.
- `tests/test_routes.py`: assert the invalid/DNS-failure branches still return no
  `ip_geo` key (guard never passed, so nothing was resolved).
- `node --test` untouched.

## Step 5 — Verify

```bash
ruff check . && ruff format . && python -m pytest
docker compose up -d --build
curl 'localhost:8000/api/up?url=example.com'
```

---

## Files touched

- `geo.py` (new)
- `main.py`
- `upcheck.py`
- `static/up.html`
- `tests/conftest.py`
- `tests/test_geo_cache.py`
- `tests/test_upcheck.py`
- `tests/test_routes.py`

## Open decision

Target IPs now share the 1000-entry `_geo_cache` with client IPs, so heavy
checker use could evict client-IP entries early. Cheap fix is bumping
`_GEO_MAX` to 2000 (still trivial memory) — not included unless you want it.
