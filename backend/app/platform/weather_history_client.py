"""Parcel climate history from weather-api (GET /api/weather/parcel/{id}/history).

Daily tmean, precipitation and ET0 since 1991 (ERA5 reanalysis, corrected to the parcel).
The first request for a parcel can come back "not ready" (503, or ``incomplete_years``)
while weather-api warms its cache; this client never raises: it returns ``ready=False``
with a reason and the caller falls back and says so. Nothing is filled in here.
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import httpx

from app.platform.daily_weather_client import WEATHER_API_URL, _num, _weather_api_headers
from app.platform.http import http_get

logger = logging.getLogger(__name__)

HISTORY_VARS = "tmean_c,precip_mm,et0_mm"
# Shorter than the daily client: a cold history can take far longer; the caller falls back.
HISTORY_TIMEOUT_S = 8.0


@dataclass(frozen=True)
class HistoryDay:
    day: date
    tmean_c: Optional[float]
    precip_mm: Optional[float]
    et0_mm: Optional[float]

    @property
    def complete(self) -> bool:
        return None not in (self.tmean_c, self.precip_mm, self.et0_mm)


@dataclass(frozen=True)
class HistoryResult:
    ready: bool
    days: list[HistoryDay] = field(default_factory=list)
    years_label: Optional[str] = None
    attribution: Optional[str] = None
    latest_available: Optional[date] = None
    reason: Optional[str] = None


def _not_ready(reason: str) -> HistoryResult:
    return HistoryResult(ready=False, reason=reason)


async def fetch_climate_history(
    parcel_urn: str,
    tenant_id: str,
    start: date,
    end: date,
    client: httpx.AsyncClient | None = None,
    timeout: float = HISTORY_TIMEOUT_S,
) -> HistoryResult:
    short = parcel_urn.split(":")[-1]
    try:
        resp = await http_get(
            client,
            f"{WEATHER_API_URL}/api/weather/parcel/{short}/history",
            params={"start": start.isoformat(), "end": end.isoformat(),
                    "resolution": "daily", "vars": HISTORY_VARS},
            headers=_weather_api_headers(tenant_id),
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        logger.warning("climate history unreachable tenant=%s parcel=%s: %s", tenant_id, short, exc)
        return _not_ready(f"weather-api unreachable: {exc}")
    if resp.status_code != 200:
        logger.warning("climate history status=%s tenant=%s parcel=%s", resp.status_code, tenant_id, short)
        return _not_ready(f"weather-api answered {resp.status_code}")
    try:
        body = resp.json()
        days = [HistoryDay(date.fromisoformat(d["date"]), _num(d.get("tmean_c")),
                           _num(d.get("precip_mm")), _num(d.get("et0_mm")))
                for d in body.get("days", [])]
        latest = date.fromisoformat(body["latest_available"]) if body.get("latest_available") else None
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        logger.warning("climate history unreadable tenant=%s parcel=%s: %s", tenant_id, short, exc)
        return _not_ready("weather-api answer unreadable")
    if body.get("incomplete_years"):
        logger.warning("climate history incomplete tenant=%s parcel=%s years=%s", tenant_id, short,
                       body["incomplete_years"])
        return HistoryResult(ready=False, latest_available=latest,
                             reason=f"history incomplete for years {body['incomplete_years']}")
    if not days:
        logger.warning("climate history empty tenant=%s parcel=%s", tenant_id, short)
        return HistoryResult(ready=False, latest_available=latest, reason="history has no days")
    years = sorted({d.day.year for d in days})
    label = f"{years[0]}–{years[-1]}"
    return HistoryResult(ready=True, days=days, years_label=label,
                         attribution=body.get("attribution"), latest_available=latest)
