import asyncio
import ipaddress
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from time import time

import geoip2.database
import geoip2.errors
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import upcheck

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("ipinfo")


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_retry_readers())
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


async def _retry_readers():
    while _city_reader is None:
        await asyncio.sleep(30)
        _load_readers()
        if _city_reader is n