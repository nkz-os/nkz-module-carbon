"""Client for querying CropHealthAssessment entities from Orion-LD."""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

import httpx

from app.ngsild.client import query_entities, ORION_URL

logger = logging.getLogger(__name__)


@dataclass
class CropHealthSnapshot:
    """Latest crop health indicators for a parcel."""
    cwsi_value: Optional[float] = None
    mds_value: Optional[float] = None
    water_balance_deficit: Optional[float] = None
    vigor_index: Optional[float] = None
    overall_severity: str = ""
    assessed_at: str = ""


async def fetch_latest_crop_health(
    parcel_id: str,
    tenant_id: str,
    client: httpx.AsyncClient | None = None,
) -> CropHealthSnapshot | None:
    """Fetch latest CropHealthAssessment for a parcel from Orion-LD."""
    async with (client or httpx.AsyncClient()) as c:
        try:
            # Query Orion-LD for CropHealthAssessment entities
            resp = await c.get(
                f"{ORION_URL}/ngsi-ld/v1/entities",
                params={
                    "type": "CropHealthAssessment",
                    "q": f'refAgriParcel=="urn:ngsi-ld:AgriParcel:{tenant_id}:{parcel_id}"',
                    "limit": 1,
                    "options": "sort=desc:assessedAt",
                },
                headers={
                    "NGSILD-Tenant": tenant_id,
                    "Accept": "application/ld+json",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data:
                return None

            entity = data[0] if isinstance(data, list) else data
            return CropHealthSnapshot(
                cwsi_value=_extract_prop(entity, "cwsiValue"),
                mds_value=_extract_prop(entity, "mdsValue"),
                water_balance_deficit=_extract_prop(entity, "waterBalanceDeficit"),
                vigor_index=_extract_prop(entity, "vigorIndex"),
                overall_severity=_extract_prop(entity, "overallSeverity", ""),
                assessed_at=_extract_prop(entity, "assessedAt", ""),
            )
        except Exception as exc:
            logger.warning("Crop health fetch failed for %s: %s", parcel_id, exc)
            return None


def _extract_prop(entity: dict, attr: str, default=None):
    """Extract a Property value from an NGSI-LD entity."""
    prop = entity.get(attr, {})
    if isinstance(prop, dict):
        return prop.get("value", default)
    return default
