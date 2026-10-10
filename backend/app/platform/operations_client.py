"""Completed field operations of a parcel (AgriParcelOperation) and its area."""

import logging
import math
import re
from datetime import date
from typing import Any, Optional

from app.common.orion import get_orion_client
from app.platform.errors import SourceUnavailable
from app.services.campaign_types import (
    BalingEvent, FertilizationEvent, HarvestEvent, Missing, TillageEvent,
)

logger = logging.getLogger(__name__)

_PAGE = 500
_EARTH_RADIUS_M = 6371008.8
# Carbon fraction of crop dry matter (IPCC default, also used for biomass in METHODOLOGY).
_C_IN_DM = 0.45


def _value(attr: Any) -> Any:
    if isinstance(attr, dict):
        v = attr.get("value", attr.get("object"))
        if isinstance(v, dict) and "@value" in v:
            return v["@value"]
        return v
    return attr


def _num(attr: Any) -> Optional[float]:
    v = _value(attr)
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def parse_n_percent(composition: Optional[str]) -> Optional[float]:
    """N share of an «N-P-K» grade: its first number ("27-0-0" -> 27.0)."""
    if not composition:
        return None
    m = re.match(r"\s*(\d+(?:[.,]\d+)?)", str(composition))
    return float(m.group(1).replace(",", ".")) if m else None


def polygon_area_ha(geometry: Any) -> Optional[float]:
    """Geodesic area of a GeoJSON Polygon on the sphere, in hectares."""
    if not isinstance(geometry, dict) or geometry.get("type") != "Polygon":
        return None
    rings = geometry.get("coordinates") or []
    if not rings:
        return None

    def ring_area(ring):
        total = 0.0
        for (lon1, lat1), (lon2, lat2) in zip(ring, ring[1:]):
            total += math.radians(lon2 - lon1) * (2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2)))
        return abs(total) * _EARTH_RADIUS_M ** 2 / 2.0

    area_m2 = ring_area(rings[0]) - sum(ring_area(r) for r in rings[1:])
    return area_m2 / 10000.0 if area_m2 > 0 else None


async def fetch_parcel_area_ha(parcel_urn: str, tenant_id: str) -> Optional[float]:
    try:
        entity = await get_orion_client().get_entity(parcel_urn, tenant_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("parcel read failed tenant=%s parcel=%s: %s", tenant_id, parcel_urn, exc)
        raise SourceUnavailable(f"parcel read failed: {exc}") from exc
    if not entity:
        return None
    area = _num(entity.get("area"))
    if area is not None and area > 0:
        return area
    return polygon_area_ha(_value(entity.get("location")))


def _op_day(entity: dict) -> Optional[date]:
    for attr in ("endedAt", "startedAt"):
        v = _value(entity.get(attr))
        if v:
            try:
                return date.fromisoformat(str(v)[:10])
            except ValueError:
                continue
    return None


async def fetch_operations(
    parcel_urn: str,
    tenant_id: str,
    start: date,
    end: date,
    area_ha: Optional[float],
) -> tuple[list[HarvestEvent], list[FertilizationEvent], list[TillageEvent], list[BalingEvent], list[Missing]]:
    orion = get_orion_client()
    entities: list[dict] = []
    offset = 0
    try:
        while True:
            page = await orion.query_entities(
                entity_type="AgriParcelOperation",
                tenant_id=tenant_id,
                query=f'hasAgriParcel=="{parcel_urn}";status=="completed"',
                limit=_PAGE,
                offset=offset,
            )
            entities.extend(page or [])
            if not page or len(page) < _PAGE:
                break
            offset += _PAGE
    except Exception as exc:  # noqa: BLE001
        logger.warning("operations query failed tenant=%s parcel=%s: %s", tenant_id, parcel_urn, exc)
        raise SourceUnavailable(f"operations query failed: {exc}") from exc

    harvests, ferts, tills, bales = [], [], [], []
    missing: list[Missing] = []
    for e in entities:
        if _value(e.get("status")) != "completed":
            continue
        day = _op_day(e)
        if day is None or not start <= day <= end:
            continue
        kind = _value(e.get("operationType"))
        if kind == "harvesting":
            weight, moisture = _num(e.get("harvestedWeight")), _num(e.get("moisture"))
            exported = None
            if weight is not None and moisture is not None and area_ha and 0 <= moisture < 100:
                exported = weight * (1 - moisture / 100.0) * _C_IN_DM / 1000.0 / area_ha
            # Unknown export stays None: the balance decides whether a declared fraction covers it.
            harvests.append(HarvestEvent(day, exported, "operation"))
        elif kind == "fertilization":
            rate, n_pct = _num(e.get("fertilizerRate")), parse_n_percent(_value(e.get("fertilizerComposition")))
            n = rate * n_pct / 100.0 if rate is not None and n_pct is not None else None
            if n is None:
                missing.append(Missing("fertilizer_n", f"fertilization {day}: rate or N-P-K grade unknown",
                                       "tier3_unavailable"))
            ferts.append(FertilizationEvent(day, n, bool(_value(e.get("organicFertilizer"))), "operation"))
        elif kind == "tillage":
            tills.append(TillageEvent(day, str(_value(e.get("tillageType")) or "")))
        elif kind == "baling":
            bales.append(BalingEvent(day))
    key = lambda x: x.day  # noqa: E731
    return sorted(harvests, key=key), sorted(ferts, key=key), sorted(tills, key=key), sorted(bales, key=key), missing
