"""Read assigned crop and parcel geometry from Orion-LD (tenant-scoped).

Carbon consumes the campaign crop commitment written by BioOrchestrator:
AgriParcel.hasAgriCrop → AgriCrop (species, plantingDate, status).
Orion is the sole source of truth for crop identity.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from app.common.orion import get_orion_client

logger = logging.getLogger(__name__)

# EPPO → carbon engine lookup keys (LUE / fAPAR / root fraction tables)
EPPO_TO_CARBON_SPECIES: dict[str, str] = {
    "TRZAX": "wheat",
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


@dataclass(frozen=True)
class AssignedCrop:
    """Active campaign crop for a parcel, as stored in Orion-LD."""

    species_raw: str
    species_key: str
    planting_date: str | None
    variety: str | None
    crop_entity_id: str
    status: str | None


def normalize_parcel_short_id(parcel_id: str) -> str:
    """Return the short parcel id from a URN or plain id."""
    return parcel_id.split(":")[-1] if ":" in parcel_id else parcel_id


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


def _extract_species(crop_entity: dict[str, Any]) -> str | None:
    for attr in (
        "species",
        "cropSpecies",
        "agriCropType",
        "cropType",
        "description",
        "name",
    ):
        val = _ngsild_prop(crop_entity, attr)
        if val:
            return str(val).strip()
    return None


def _crop_from_entity(crop_entity: dict[str, Any]) -> AssignedCrop | None:
    species_raw = _extract_species(crop_entity)
    if not species_raw:
        return None
    crop_id = str(crop_entity.get("id", ""))
    if not crop_id:
        return None
    variety = _ngsild_prop(crop_entity, "variety") or _ngsild_prop(
        crop_entity, "varietyName"
    )
    return AssignedCrop(
        species_raw=species_raw,
        species_key=carbon_species_key(species_raw),
        planting_date=_ngsild_prop(crop_entity, "plantingDate"),
        variety=str(variety) if variety else None,
        crop_entity_id=crop_id,
        status=str(_ngsild_prop(crop_entity, "status") or "").lower() or None,
    )


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


async def _fetch_crop_entity(crop_id: str, tenant_id: str) -> dict[str, Any] | None:
    orion = get_orion_client()
    entity = await orion.get_entity(crop_id, tenant_id)
    if entity:
        return entity
    results = await orion.query_entities(
        entity_type="AgriCrop",
        tenant_id=tenant_id,
        query=f'id=="{crop_id}"',
        limit=1,
    )
    return results[0] if results else None


async def _query_active_crop_for_parcel(
    parcel_ref: str,
    tenant_id: str,
) -> AssignedCrop | None:
    orion = get_orion_client()

    # Query both relationship names (hasAgriParcel / refAgriParcel) — active first
    for attr in ("hasAgriParcel", "refAgriParcel"):
        results = await orion.query_entities(
            entity_type="AgriCrop",
            tenant_id=tenant_id,
            query=f'{attr}=="{parcel_ref}";status=="active"',
            limit=5,
        )
        for ent in results or []:
            crop = _crop_from_entity(ent)
            if crop:
                return crop

    # Fallback: any non-harvested crop (dedupe across both relationship names)
    seen: set[str] = set()
    for attr in ("hasAgriParcel", "refAgriParcel"):
        results = await orion.query_entities(
            entity_type="AgriCrop",
            tenant_id=tenant_id,
            query=f'{attr}=="{parcel_ref}"',
            limit=10,
        )
        for ent in results or []:
            if ent["id"] in seen:
                continue
            seen.add(ent["id"])
            crop = _crop_from_entity(ent)
            if crop and crop.status != "harvested":
                return crop
    return None


async def fetch_assigned_crop(parcel_id: str, tenant_id: str) -> AssignedCrop | None:
    """Return the campaign crop assigned to a parcel via Orion-LD.

    Resolution order:
    1. AgriParcel.hasAgriCrop (preferred) or legacy refAgriCrop
    2. Active AgriCrop linked to the parcel (hasAgriParcel / refAgriParcel)
    """
    parcel = await _fetch_parcel_entity(parcel_id, tenant_id)
    if not parcel:
        logger.info(
            "AgriParcel not found for %s in tenant %s",
            parcel_id,
            tenant_id,
        )
        short = normalize_parcel_short_id(parcel_id)
        return await _query_active_crop_for_parcel(
            parcel_urn(tenant_id, short),
            tenant_id,
        )

    parcel_ref = str(parcel.get("id", ""))
    crop_ref = _ngsild_rel_object(parcel, "hasAgriCrop") or _ngsild_rel_object(
        parcel, "refAgriCrop"
    )

    if crop_ref:
        crop_entity = await _fetch_crop_entity(crop_ref, tenant_id)
        if crop_entity:
            crop = _crop_from_entity(crop_entity)
            if crop and crop.status != "harvested":
                return crop

    if parcel_ref:
        fallback = await _query_active_crop_for_parcel(parcel_ref, tenant_id)
        if fallback:
            return fallback

    short = normalize_parcel_short_id(parcel_id)
    return await _query_active_crop_for_parcel(
        parcel_urn(tenant_id, short),
        tenant_id,
    )


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
