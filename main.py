from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timezone
from time import time
import ipaddress
import httpx
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("ipinfo")

app = FastAPI()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time()
    response = await call_next(request)
    duration_ms = (time() - start) * 1000
    logger.info(
        "%s %s %d %.1fms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
)

_geo_cache: dict[str, tuple[dict, float]] = {}
_GEO_TTL = 30     # seconds before a cached result expires
_GEO_MAX = 1000   # max entries to keep in memory


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


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    return forwarded_for.split(",")[0].strip() if forwarded_for else request.client.host


def _is_browser(request: Request) -> bool:
    return "Mozilla" in request.headers.get("User-Agent", "")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ip")
async def get_ip(request: Request):
    ip = _client_ip(request)

    geo = _cache_get(ip)
    if geo is None:
        geo = {}
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"https://ipapi.co/{ip}/json/")
                data = resp.json()
                geo = {
                    "country": data.get("country_name"),
                    "region": data.get("region"),
                    "city": data.get("city"),
                    "latitude": data.get("latitude"),
                    "longitude": data.get("longitude"),
                    "isp": data.get("org"),
                    "timezone": data.get("timezone"),
                }
        except Exception:
            pass
        _cache_set(ip, geo)

    return {"ip": ip, "geo": geo}


@app.get("/")
async def index(request: Request):
    if _is_browser(request):
        return FileResponse("static/index.html")

    ip = _client_ip(request)
    try:
        addr = ipaddress.ip_address(ip)
        # Unwrap IPv4-mapped IPv6 addresses (::ffff:1.2.3.4)
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
            addr = addr.ipv4_mapped
        is_v4 = isinstance(addr, ipaddress.IPv4Address)
    except ValueError:
        is_v4 = True

    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ipv4": ip if is_v4 else None,
        "ipv6": ip if not is_v4 else None,
    }


app.mount("/", StaticFiles(directory="static", html=True), name="static")
