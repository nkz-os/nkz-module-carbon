"""Crop cycles of a parcel, resolved by entity-manager (internal route)."""

import logging
import os
from datetime import date

import httpx

from app.platform.errors import SourceUnavailable
from app.platform.http import http_get

logger = logging.getLogger(__name__)

ENTITY_MANAGER_URL = os.getenv("ENTITY_MANAGER_URL", "http://entity-manager-service:5000")
INTERNAL_SERVICE_SECRET = os.getenv("INTERNAL_SERVICE_SECRET", "")


async def fetch_cycles(
    parcel_urn: str,
    tenant_id: str,
    at: date,
    client: httpx.AsyncClient | None = None,
) -> list[dict]:
    """All cycles of the parcel (the endpoint's ``cycles`` list), as returned."""
    try:
        resp = await http_get(
            client,
            f"{ENTITY_MANAGER_URL}/api/internal/parcels/{parcel_urn}/crop-cycles",
            params={"tenant_id": tenant_id, "at": at.isoformat()},
            headers={"X-Internal-Service-Secret": INTERNAL_SERVICE_SECRET},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        logger.warning("crop-cycles unreachable tenant=%s parcel=%s: %s", tenant_id, parcel_urn, exc)
        raise SourceUnavailable(f"entity-manager unreachable: {exc}") from exc
    if resp.status_code == 404:
        return []
    if resp.status_code != 200:
        logger.warning("crop-cycles status=%s tenant=%s parcel=%s", resp.status_code, tenant_id, parcel_urn)
        raise SourceUnavailable(f"entity-manager answered {resp.status_code}")
    return list(resp.json().get("cycles", []))
