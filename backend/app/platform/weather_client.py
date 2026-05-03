"""HTTP client for weather-worker API."""

import logging
import os
from dataclasses import dataclass

import httpx

from app.services.solar_geometry import clear_sky_par_MJ_m2_day, doy_from_date

logger = logging.getLogger(__name__)

WEATHER_WORKER_URL = os.getenv(
    "WEATHER_WORKER_URL", "http://weather-worker-service:8000"
)


@dataclass
class WeatherSnapshot:
    par_MJ_m2_day: float
    temp_air_celsius: float
    precip_mm: float
    eto_mm: float | None
    data_quality: str  # "measured" | "synthetic_par"


async def fetch_weather(
    lat: float, lon: float, obs_date, client: httpx.AsyncClient | None = None
) -> WeatherSnapshot:
    """Fetch weather data. PAR from API, clear-sky fallback on failure."""
    par_MJ_m2_day = None
    data_quality = "measured"
    temp_air_celsius = 20.0
    precip_mm = 0.0
    eto_mm = None

    async with (client or httpx.AsyncClient()) as c:
        try:
            resp = await c.get(
                f"{WEATHER_WORKER_URL}/api/weather/par",
                params={"lat": lat, "lon": lon, "date": obs_date.isoformat()},
                timeout=5,
            )
            resp.raise_for_status()
            par_MJ_m2_day = float(resp.json()["par_mj_m2"])
        except Exception as exc:
            logger.warning("PAR fetch failed (%s), using clear-sky fallback", exc)
            doy = doy_from_date(obs_date)
            par_MJ_m2_day = clear_sky_par_MJ_m2_day(lat, doy)
            data_quality = "synthetic_par"

        try:
            resp = await c.get(
                f"{WEATHER_WORKER_URL}/api/weather/current",
                params={"lat": lat, "lon": lon},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            temp_air_celsius = float(data.get("temp_avg", 20.0))
            precip_mm = float(data.get("precip_mm", 0.0))
            eto_mm = float(data["eto_mm"]) if data.get("eto_mm") is not None else None
        except Exception as exc:
            logger.warning("Weather current fetch failed: %s", exc)

    return WeatherSnapshot(
        par_MJ_m2_day=par_MJ_m2_day,
        temp_air_celsius=temp_air_celsius,
        precip_mm=precip_mm,
        eto_mm=eto_mm,
        data_quality=data_quality,
    )
