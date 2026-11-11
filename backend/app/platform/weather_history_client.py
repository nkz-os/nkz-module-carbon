"""Parcel climate history from weather-api (GET /api/weather/parcel/{id}/history).

Daily tmin, tmax, precipitation and ET0 since 1991 (ERA5 reanalysis, corrected to the parcel).
The first request for a parcel can come back "not ready" (503, or ``incomplete_years``)
while weather-api warms its cache; this client never raises: it returns ``ready=False``
with a reason and the caller falls back and says so. Nothing is filled in here.

A failure is either transient (503, timeout, ``incomplete_years``, no days: it may be ready
later) or ``permanent`` (any other 4xx: retrying will not help). One 400 is neither: "end is
after the latest available day" (``end_after_latest``), which the caller answers with an
earlier end.
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import httpx

from app.platform.daily_weather_client import WEATHER_API_URL, _num, _weather_api_headers
from app.platform.http import http_get

logger = logging.getLogger(__name__)

HISTORY_VARS = "tmin_c,tmax_c,precip_mm,et0_mm"
# A cold history can take far longer; the caller falls back. The server's own deadline is 20 s.
HISTORY_TIMEOUT_S = 12.0


@dataclass(frozen=True)
class HistoryDay:
    day: date
    tmin_c: Optional[float]
    tmax_c: Optional[float]
    precip_mm: Optional[float]
    et0_mm: Optional[float]

    @property
    def tmean_c(self) -> Optional[float]:
        """Same definition as the campaign balance: (tmin + tmax) / 2."""
        if self.tmin_c is None or self.tmax_c is None:
            return None
        return (self.tmin_c + self.tmax_c) / 2.0

    @property
    def complete(self) -> bool:
        return None not in (self.tmin_c, self.tmax_c, self.precip_mm, self.et0_mm)


@dataclass(frozen=True)
class HistoryResult:
    ready: bool
    days: list[HistoryDay] = field(default_factory=list)
    years_label: Optional[str] = None
    attribution: Optional[str] = None
    latest_available: Optional[date] = None
    reason: Optional[str] = None
    status: Optional[int] = None
    permanent: bool = False          # a 4xx that retrying will not fix
    end_after_latest: bool = False   # 400: the requested end is past the latest available day


def _not_ready(reason: str, **kw) -> HistoryResult:
    return HistoryResult(ready=False, reason=reason, **kw)


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
        status = resp.status_code
        if status == 400 and "latest available" in resp.text:
            return _not_ready("weather-api answered 400 (end after latest available day)",
                              status=status, end_after_latest=True)
        permanent = 400 <= status < 500 and status not in (408, 425, 429)
        return _not_ready(f"weather-api answered {status}", status=status, permanent=permanent)
    try:
        body = resp.json()
        days = [HistoryDay(date.fromisoformat(d["date"]), _num(d.get("tmin_c")), _num(d.get("tmax_c")),
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
