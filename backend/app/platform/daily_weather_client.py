"""Closed-day parcel weather from weather-api (GET /api/weather/parcel/{id}/daily).

Days the parcel series lacks are filled on demand from Open-Meteo by weather-api
(model analysis for recent days, reanalysis before). A day it cannot provide comes
back with null fields and is never invented here.
"""

import logging
import os
from datetime import date
from typing import Optional

import httpx
from nkz_platform_sdk.crypto import generate_hmac_signature

from app.platform.errors import SourceUnavailable
from app.platform.http import http_get
from app.services.campaign_types import WeatherDay

logger = logging.getLogger(__name__)

WEATHER_API_URL = os.getenv("WEATHER_API_URL", "http://weather-api-service:8000")
# The fill has a 25 s budget server-side; leave room for the closed-day query.
_TIMEOUT_S = 40.0


def _num(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _weather_api_headers(tenant_id: str) -> dict[str, str]:
    """Service identity for weather-api: the tenant plus the platform signature.

    weather-api trusts X-Tenant-ID only when X-Auth-Signature verifies; a
    service call has no user token, so the signed token is empty (SDK
    convention). Without HMAC_SECRET the call goes unsigned and a backend
    that requires the signature answers 401 (SourceUnavailable below).
    """
    headers = {"X-Tenant-ID": tenant_id, "X-User-ID": "carbon-worker"}
    secret = os.getenv("HMAC_SECRET", "")
    if secret:
        headers["X-Auth-Signature"] = generate_hmac_signature(secret, "", tenant_id)
    return headers


async def fetch_daily_weather(
    parcel_urn: str,
    tenant_id: str,
    start: date,
    end: date,
    client: httpx.AsyncClient | None = None,
) -> list[WeatherDay]:
    short = parcel_urn.split(":")[-1]
    try:
        resp = await http_get(
            client,
            f"{WEATHER_API_URL}/api/weather/parcel/{short}/daily",
            params={"start": start.isoformat(), "end": end.isoformat(), "fill": "open_meteo"},
            headers=_weather_api_headers(tenant_id),
            timeout=_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        logger.warning("daily weather unreachable tenant=%s parcel=%s: %s", tenant_id, short, exc)
        raise SourceUnavailable(f"weather-api unreachable: {exc}") from exc
    if resp.status_code == 404:
        return []
    if resp.status_code != 200:
        logger.warning("daily weather status=%s tenant=%s parcel=%s", resp.status_code, tenant_id, short)
        raise SourceUnavailable(f"weather-api answered {resp.status_code}")
    days = []
    for d in resp.json().get("days", []):
        days.append(WeatherDay(
            day=date.fromisoformat(d["date"]),
            tmin_c=_num(d.get("tmin_c")),
            tmax_c=_num(d.get("tmax_c")),
            precip_mm=_num(d.get("precip_mm")),
            et0_mm=_num(d.get("et0_mm")),
            radiation_mj_m2=_num(d.get("radiation_mj_m2")),
            source=d.get("source"),
        ))
    return days
