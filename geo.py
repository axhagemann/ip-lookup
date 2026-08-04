"""GeoLite2 lookups: local MaxMind readers plus an in-process per-IP cache.

Lives in its own module because both main.py (client IP for /ip) and upcheck.py
(resolved target IPs for /api/up) need it, and upcheck.py cannot import main.py
— main.py already imports upcheck.

Readers are loaded once at import and retried every 30s by retry_readers() if
missing, since geoipupdate may not have populated the volume yet on first boot.
"""

import asyncio
import logging
from time import time

import geoip2.database
import geoip2.errors

logger = logging.getLogger("ipinfo")

_geo_cache: dict[str, tuple[dict, float]] = {}
_GEO_TTL = 3600  # seconds before a cached result expires
_GEO_MAX = 1000  # max entries to keep in memory

_city_reader: geoip2.database.Reader | None = None
_asn_reader: geoip2.database.Reader | None = None


def _load_readers() -> None:
    global _city_reader, _asn_reader
    try:
        _city_reader = geoip2.database.Reader("/app/geoip/GeoLite2-City.mmdb")
        _asn_reader = geoip2.database.Reader("/app/geoip/GeoLite2-ASN.mmdb")
    except FileNotFoundError:
        logger.warning("GeoLite2 databases not found — geo lookups will be empty until geoipupdate runs")


_load_readers()


async def retry_readers():
    while _city_reader is None:
        await asyncio.sleep(30)
        _load_readers()
        if _city_reader is not None:
            logger.info("GeoLite2 databases loaded successfully")


def _cache_get(ip: str) -> dict | None:
    entry = _geo_cache.get(ip)
    if entry and time() - entry[1] < _GEO_TTL:
        return entry[0]
    _geo_cache.pop(ip, None)
    return None


def _cache_set(ip: str, data: dict) -> None:
    if len(_geo_cache) >= _GEO_MAX:
        oldest = min(_geo_cache, key=lambda k: _geo_cache[k][1])
        del _geo_cache[oldest]
    _geo_cache[ip] = (data, time())


def _geo_lookup(ip: str) -> dict:
    if _city_reader is None:
        return {}
    geo = {}
    try:
        city = _city_reader.city(ip)
        geo["country"] = city.country.name
        geo["region"] = city.subdivisions.most_specific.name or None
        geo["city"] = city.city.name
        geo["latitude"] = city.location.latitude
        geo["longitude"] = city.location.longitude
        geo["timezone"] = city.location.time_zone
    except geoip2.errors.AddressNotFoundError:
        pass
    if _asn_reader is not None:
        try:
            asn = _asn_reader.asn(ip)
            geo["isp"] = f"AS{asn.autonomous_system_number} {asn.autonomous_system_organization}"
        except geoip2.errors.AddressNotFoundError:
            pass
    return geo


def lookup(ip: str) -> dict:
    """Cached geo lookup for a single IP. Returns {} when nothing is known."""
    cached = _cache_get(ip)
    if cached is not None:
        return cached
    result = _geo_lookup(ip)
    _cache_set(ip, result)
    return result
