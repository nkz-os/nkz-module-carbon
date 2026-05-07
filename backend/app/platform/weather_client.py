"""HTTP clients for weather data — weather-worker API and sensor-based sources."""

import logging
import os
from dataclasses import dataclass
from datetime import date

import httpx

from app.services.solar_geometry import clear_sky_par_MJ_m2_day, doy_from_date

logger = logging.getLogger(__name__)

WEATHER_WORKER_URL = os.getenv(
    "WEATHER_WORKER_URL", "http://weather-worker-service:8000"
)
# The entity-manager serves the canonical parcel weather endpoint
ENTITY_MANAGER_URL = os.getenv(
    "ENTITY_MANAGER_URL", "http://entity-manager-service:5000"
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


async def fetch_weather(
    lat: float, lon: float, obs_date, client: httpx.AsyncClient | None = None
) -> WeatherSnapshot:
    """Fetch weather from weather-worker API. Clear-sky PAR fallback on failure."""
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


async def fetch_parcel_weather(
    entity_id: str,
    tenant_id: str,
    client: httpx.AsyncClient | None = None,
) -> WeatherSnapshot | None:
    """Fetch weather for a parcel via the entity-manager canonical endpoint.

    Uses GET /api/weather/parcel/{entity_id} which resolves the parcel's
    location from Orion-LD, finds the nearest weather municipality, queries
    TimescaleDB weather_observations, and applies spatial downscaling.

    Returns None if the endpoint is unreachable or returns no data.
    """
    async with (client or httpx.AsyncClient()) as c:
        try:
            resp = await c.get(
                f"{ENTITY_MANAGER_URL}/api/weather/parcel/{entity_id}",
                headers={"NGSILD-Tenant": tenant_id},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            # entity-manager returns { temp_avg, precip_mm, eto_mm, solar_rad_w_m2, ... }
            solar_w_m2 = float(data.get("solar_rad_w_m2", 0))
            # Convert W/m² to MJ/m²/day: W/m² × 86400 s/day × 1e-6 MJ/J = W/m² × 0.0864
            par_MJ_m2_day = solar_w_m2 * 0.0864 * 0.48  # 48% of solar is PAR
            temp_air = float(data.get("temp_avg", 20.0))
            precip = float(data.get("precip_mm", 0.0))
            eto = float(data.get("eto_mm")) if data.get("eto_mm") is not None else None

            if par_MJ_m2_day <= 0:
                return None  # signal caller to use clear-sky fallback

            return WeatherSnapshot(
                par_MJ_m2_day=par_MJ_m2_day,
                temp_air_celsius=temp_air,
                precip_mm=precip,
                eto_mm=eto,
                data_quality="measured",
            )
        except Exception as exc:
            logger.warning("Parcel weather fetch failed for %s: %s", entity_id, exc)
            return None


async def fetch_weather_from_sensor(
    entity_id: str,
    tenant_id: str,
    sensor_id: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> WeatherSnapshot | None:
    """Fetch weather from tenant AgriSensors via Orion-LD WeatherObserved entities.

    If sensor_id is provided, queries that specific sensor's WeatherObserved.
    Otherwise, queries all WeatherObserved near the parcel.

    Returns None if no valid sensor observation is found.
    """
    async with (client or httpx.AsyncClient()) as c:
        try:
            # Build NGSI-LD query for WeatherObserved
            params: dict[str, str] = {
                "type": "WeatherObserved",
                "limit": "5",
            }

            if sensor_id:
                # Filter to observations from a specific sensor
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

            # Extract weather values from the first valid entity
            for ent in entities:
                temp_val = _extract_property(ent, "temperature")
                precip_val = _extract_property(ent, "precipitation")
                solar_val = _extract_property(ent, "solarRadiation")

                if temp_val is not None:
                    par_mj = (solar_val or 200) * 0.0864 * 0.48
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
    """List AgriSensor entities for a tenant from Orion-LD.

    Returns list of {id, name, sensorType, location}.
    """
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
                    "name": ent.get("name", {}).get("value", "Unnamed") if isinstance(ent.get("name"), dict) else str(ent.get("name", "Unnamed")),
                    "sensor_type": ent.get("sensorType", {}).get("value", "") if isinstance(ent.get("sensorType"), dict) else "",
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
