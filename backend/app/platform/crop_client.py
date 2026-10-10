"""Parcel helpers for carbon (tenant-scoped).

Species keys for the carbon tables, parcel URN helpers and the parcel centroid.
Crop cycles come from the platform resolver (crop_cycles_client).
"""

from __future__ import annotations

import logging
from typing import Any

from app.common.orion import get_orion_client

logger = logging.getLogger(__name__)

# EPPO → carbon engine lookup keys (LUE / fAPAR / root fraction tables)
EPPO_TO_CARBON_SPECIES: dict[str, str] = {
    "TRZAX": "wheat",
    "TRZDU": "wheat",  # durum wheat: same LUE/fAPAR calibration as bread wheat
    "HORVX": "barley",
    "ZEAMX": "corn",
    "ORYSA": "rice",
    "HELAN": "sunflower",
    "GLXMA": "soybean",
    "SACAR": "sugarcane",
    "OLEPL": "olive",
    "OLVEU": "olive",
    "VITVI": "vineyard",
    "PRNDU": "almond",
    "CITLO": "citrus",
    "CITSI": "citrus",
}


def normalize_parcel_short_id(parcel_id: str) -> str:
    """Return the short parcel id from a URN or plain id."""
    return parcel_id.split(":")[-1] if ":" in parcel_id else parcel_id


def parcel_short(parcel_id: str) -> str:
    """Short parcel id (last URN segment)."""
    return parcel_id.rsplit(":", 1)[-1]


def canonical_parcel_urn(parcel_id: str) -> str:
    """The AgriParcel id as stored in the broker: urn:ngsi-ld:AgriParcel:{short}, no tenant."""
    return f"urn:ngsi-ld:AgriParcel:{parcel_short(parcel_id)}"


def parcel_urn(tenant_id: str, parcel_short: str) -> str:
    return f"urn:ngsi-ld:AgriParcel:{tenant_id}:{parcel_short}"


def carbon_species_key(raw_species: str) -> str:
    """Map Orion species (EPPO or common name) to carbon engine dict keys."""
    raw = raw_species.strip()
    if not raw:
        return ""
    mapped = EPPO_TO_CARBON_SPECIES.get(raw.upper())
    if mapped:
        return mapped
    return raw.lower()


def phenology_species_param(raw_species: str) -> str:
    """Species token for BioOrchestrator phenology-params."""
    raw = raw_species.strip()
    if raw.upper() in EPPO_TO_CARBON_SPECIES:
        return raw.upper()
    if raw.isupper() and len(raw) <= 6 and raw.isalpha():
        return raw.upper()
    return raw.lower()


def _ngsild_prop(entity: dict[str, Any], attr: str) -> Any | None:
    prop = entity.get(attr)
    if isinstance(prop, dict):
        if "value" in prop:
            val = prop["value"]
            if isinstance(val, dict) and "@value" in val:
                return val["@value"]
            return val
        if "object" in prop:
            return prop["object"]
    if prop is not None and not isinstance(prop, dict):
        return prop
    return None


def _ngsild_rel_object(entity: dict[str, Any], attr: str) -> str | None:
    prop = entity.get(attr)
    if isinstance(prop, dict):
        obj = prop.get("object") or prop.get("value")
        if obj:
            return str(obj)
    if isinstance(prop, str) and prop.startswith("urn:"):
        return prop
    return None


async def _fetch_parcel_entity(parcel_id: str, tenant_id: str) -> dict[str, Any] | None:
    orion = get_orion_client()
    short = normalize_parcel_short_id(parcel_id)

    if parcel_id.startswith("urn:"):
        entity = await orion.get_entity(parcel_id, tenant_id)
        if entity:
            return entity

    canonical = parcel_urn(tenant_id, short)
    entity = await orion.get_entity(canonical, tenant_id)
    if entity:
        return entity

    results = await orion.query_entities(
        entity_type="AgriParcel",
        tenant_id=tenant_id,
        query=f'id=="{canonical}"',
        limit=1,
    )
    return results[0] if results else None


async def fetch_parcel_entity(parcel_id: str, tenant_id: str) -> dict[str, Any] | None:
    """The AgriParcel entity, or None when the tenant has no such parcel (broker errors propagate)."""
    return await _fetch_parcel_entity(parcel_id, tenant_id)


def _centroid_from_location(location: Any) -> tuple[float, float] | None:
    if not isinstance(location, dict):
        return None
    geom = location.get("value") if "value" in location else location
    if not isinstance(geom, dict):
        return None
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if gtype == "Point" and isinstance(coords, (list, tuple)) and len(coords) >= 2:
        return float(coords[1]), float(coords[0])
    if gtype == "Polygon" and isinstance(coords, list) and coords:
        ring = coords[0]
        if ring:
            lats = [p[1] for p in ring]
            lons = [p[0] for p in ring]
            return sum(lats) / len(lats), sum(lons) / len(lons)
    return None


async def fetch_parcel_coordinates(
    parcel_id: str,
    tenant_id: str,
) -> tuple[float, float] | None:
    """Return (lat, lon) centroid for a parcel from AgriParcel.location."""
    parcel = await _fetch_parcel_entity(parcel_id, tenant_id)
    if not parcel:
        return None
    loc = parcel.get("location")
    return _centroid_from_location(loc)
