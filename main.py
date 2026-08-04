import asyncio
import ipaddress
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from time import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import geo
import upcheck

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("ipinfo")


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(geo.retry_readers())
    yield


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time()
    response = await call_next(request)
    duration_ms = (time() - start) * 1000
    log_ip = _truncate_ip(_client_ip(request))
    logger.info(
        "%s %s %s %d %.1fms",
        log_ip,
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

app.include_router(upcheck.router)


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _truncate_ip(ip: str) -> str:
    try:
        addr = ipaddress.ip_address(ip)
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
            addr = addr.ipv4_mapped
        if isinstance(addr, ipaddress.IPv4Address):
            return str(ipaddress.IPv4Network(f"{addr}/24", strict=False).network_address)
        else:
            return str(ipaddress.IPv6Network(f"{addr}/48", strict=False).network_address)
    except ValueError:
        return ip


def _is_browser(request: Request) -> bool:
    return "Mozilla" in request.headers.get("User-Agent", "")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ip")
def get_ip(request: Request):
    ip = _client_ip(request)
    return {"ip": ip, "geo": geo.lookup(ip)}


@app.get("/getip")
async def getip():
    return FileResponse("static/getip.html")


@app.get("/cidr")
async def cidr():
    return FileResponse("static/cidr.html")


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
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ipv4": ip if is_v4 else None,
        "ipv6": ip if not is_v4 else None,
    }


app.mount("/", StaticFiles(directory="static", html=True), name="static")
