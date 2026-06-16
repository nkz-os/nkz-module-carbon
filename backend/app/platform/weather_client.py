"""
HTTP client for weather data — canonical weather-api-service endpoint.

The carbon module fetches weather through the core weather-api-service
(GET /api/weather/parcel/{parcel_id}) rather than calling modules directly.
This endpoint resolves parcel location, fetches Open-Meteo or cached
WeatherObserved, applies spatial downscaling, and returns observations
with solar_rad_w_m2, temp_avg, precip_mm, eto_mm.
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

WEATHER_API_URL = os.getenv(
    "WEATHER_API_URL", "http://weather-api-service:8000"
)
ORION_URL = os.getenv(
    "FIWARE_CONTEXT_BROKER_URL", "http://orion-ld-service:1026"
)


@dataclass
class WeatherSnapshot:
    par_MJ_m2_day: float
    temp_air_celsius: float
    precip_mm: float
    eto_mm: float | None
    data_quality: str  # "measured" | "synthetic_par" | "sensor"


def _solar_wm2_to_par_mj(solar_rad_w_m2: float) -> float:
    """Convert solar radiation (W/m²) to PAR (MJ/m²/day).

    48% of solar radiation is PAR (photosynthetically active).
    W/m² -> MJ/m²/day: multiply by 86400 s/day * 1e-6 MJ/J = 0.0864
    """
    return solar_rad_w_m2 * 0.0864 * 0.48


async def fetch_parcel_weather(
    entity_id: str,
    tenant_id: str,
    client: httpx.AsyncClient | None = None,
) -> WeatherSnapshot | None:
    """Fetch parcel weather from the canonical weather-api-service endpoint.

    Returns WeatherSnapshot with PAR derived from solar_rad_w_m2.
    Returns None if the endpoint is unreachable or returns no data
    (caller should fall back to clear-sky PAR).
    """
    async with (client or httpx.AsyncClient()) as c:
        try:
            resp = await c.get(
                f"{WEATHER_API_URL}/api/weather/parcel/{entity_id}",
                headers={"NGSILD-Tenant": tenant_id},
                timeout=10,
            )
            if resp.status_code == 404:
                logger.info("Parcel %s not found in weather-api", entity_id)
                return None
            resp.raise_for_status()
            data = resp.json()
            observations = data.get("observations", [])
            if not observations:
                logger.info("No weather observations for parcel %s", entity_id)
                return None

            obs = observations[0]
            solar_rad = obs.get("solar_rad_w_m2")
            if solar_rad is None or solar_rad <= 0:
                return None  # signal caller to use clear-sky fallback

            par_MJ_m2_day = _solar_wm2_to_par_mj(float(solar_rad))
            temp_avg = float(obs.get("temp_avg", 20.0))
            precip = float(obs.get("precip_mm", 0.0))
            eto = float(obs.get("eto_mm")) if obs.get("eto_mm") is not None else None

            return WeatherSnapshot(
                par_MJ_m2_day=par_MJ_m2_day,
                temp_air_celsius=temp_avg,
                precip_mm=precip,
                eto_mm=eto,
                data_quality="measured",
            )
        except httpx.TimeoutException:
            logger.warning("Weather API timeout for parcel %s", entity_id)
            return None
        except Exception as exc:
            logger.warning("Weather fetch failed for %s: %s", entity_id, exc)
            return None


async def fetch_weather_from_sensor(
    entity_id: str,
    tenant_id: str,
    sensor_id: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> WeatherSnapshot | None:
    """Fetch weather from tenant AgriSensor via Orion-LD WeatherObserved entities."""
    async with (client or httpx.AsyncClient()) as c:
        try:
            params: dict[str, str] = {
                "type": "WeatherObserved",
                "limit": "5",
            }
            if sensor_id:
                params["q"] = f'refDevice=="{sensor_id}"'

            headers = {
                "NGSILD-Tenant": tenant_id,
                "Accept": "application/ld+json",
            }

            resp = await c.get(
                f"{ORION_URL}/ngsi-ld/v1/entities",
                params=params,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            entities = resp.json()

            if not entities:
                logger.info("No WeatherObserved found for sensor %s", sensor_id)
                return None

            for ent in entities:
                temp_val = _extract_property(ent, "temperature")
                precip_val = _extract_property(ent, "precipitation")
                solar_val = _extract_property(ent, "solarRadiation")

                if temp_val is not None:
                    par_mj = _solar_wm2_to_par_mj(solar_val or 200)
                    return WeatherSnapshot(
                        par_MJ_m2_day=par_mj,
                        temp_air_celsius=temp_val,
                        precip_mm=precip_val or 0.0,
                        eto_mm=None,
                        data_quality="sensor",
                    )
            return None
        except Exception as exc:
            logger.warning("Sensor weather fetch failed: %s", exc)
            return None


async def list_tenant_sensors(
    tenant_id: str,
    client: httpx.AsyncClient | None = None,
) -> list[dict]:
    """List AgriSensor entities for a tenant from Orion-LD."""
    async with (client or httpx.AsyncClient()) as c:
        try:
            resp = await c.get(
                f"{ORION_URL}/ngsi-ld/v1/entities",
                params={"type": "AgriSensor", "limit": "100"},
                headers={
                    "NGSILD-Tenant": tenant_id,
                    "Accept": "application/ld+json",
                },
                timeout=10,
            )
            resp.raise_for_status()
            entities = resp.json()
            sensors = []
            for ent in entities:
                loc = ent.get("location", {})
                coords = None
                if isinstance(loc, dict):
                    coords = loc.get("value", {}).get("coordinates", [None, None])
                sensors.append({
                    "id": ent.get("id", ""),
                    "name": (
                        ent.get("name", {}).get("value", "Unnamed")
                        if isinstance(ent.get("name"), dict)
                        else str(ent.get("name", "Unnamed"))
                    ),
                    "sensor_type": (
                        ent.get("sensorType", {}).get("value", "")
                        if isinstance(ent.get("sensorType"), dict)
                        else ""
                    ),
                    "latitude": coords[1] if coords else None,
                    "longitude": coords[0] if coords else None,
                })
            return sensors
        except Exception as exc:
            logger.warning("Sensor listing failed: %s", exc)
            return []


def _extract_property(entity: dict, attr_name: str) -> float | None:
    """Extract a numeric NGSI-LD property value."""
    prop = entity.get(attr_name, {})
    if isinstance(prop, dict):
        val = prop.get("value")
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
    if isinstance(prop, (int, float)):
        return float(prop)
    return None
