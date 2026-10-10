"""Tenant sensor listing for the management form.

Campaign weather comes from daily_weather_client (weather-api closed-day series).
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

ORION_URL = os.getenv(
    "FIWARE_CONTEXT_BROKER_URL", "http://orion-ld-service:1026"
)


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
