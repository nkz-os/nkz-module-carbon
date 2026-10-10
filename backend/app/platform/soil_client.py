"""
HTTP client for soil data — queries Orion-LD AgriSoilExtended entities.

The carbon module fetches soil data through Orion-LD (the context broker)
to avoid coupling to the soil module's internal API. AgriSoilExtended
entities are created/maintained by the soil module via NGSI-LD subscriptions.

If no entity exists for a parcel, the soil is reported missing; nothing is defaulted.
"""

import logging
from typing import Optional

from app.common.orion import get_orion_client
from app.platform.errors import SourceUnavailable
from app.services.campaign_types import Missing, SoilInit

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Soil for the campaign balance: horizons only, no defaults.
# ---------------------------------------------------------------------------

_TOPSOIL_CM = 30.0
# Plausible mineral-soil bulk density, g/cm3. Outside it the value is a NODATA
# sentinel or a unit error, never a measurement.
_BD_RANGE = (0.5, 2.2)
# Mineral soils (bulk density > 0.8) stay well below 12 % organic carbon; a higher
# value there is g/kg written into the % field, which would inflate SOC tenfold.
_MAX_MINERAL_OC_PCT = 12.0
_MINERAL_BD = 0.8


def _attr(entity: dict, name: str):
    v = entity.get(name)
    if isinstance(v, dict):
        return v.get("value", v.get("object"))
    return v


def _num_or_none(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _topsoil_from_horizons(horizons: list) -> tuple[Optional[float], Optional[float], float, list[Missing]]:
    """(SOC tC/ha, clay %, covered depth cm, missing) over 0-30 cm."""
    layers = []
    for h in horizons or []:
        top, bottom = _num_or_none(h.get("depthFrom")), _num_or_none(h.get("depthTo"))
        if top is None or bottom is None or bottom <= top or top >= _TOPSOIL_CM:
            continue
        layers.append((top, min(bottom, _TOPSOIL_CM), h))
    layers.sort(key=lambda x: x[0])
    depth = 0.0
    soc, clay_w = 0.0, 0.0
    soc_ok, clay_ok = True, True
    for top, bottom, h in layers:
        if abs(top - depth) > 1e-9:
            break  # a gap: the topsoil is covered only down to here
        thick = bottom - top
        oc, bd = _num_or_none(h.get("organicCarbon")), _num_or_none(h.get("bulkDensity"))
        cf = _num_or_none(h.get("coarseFragments")) or 0.0
        clay = _num_or_none(h.get("clay"))
        if oc is None or oc < 0 or bd is None or not _BD_RANGE[0] < bd < _BD_RANGE[1] or not 0 <= cf < 100:
            soc_ok = False
        elif oc > _MAX_MINERAL_OC_PCT and bd > _MINERAL_BD:
            soc_ok = False
        else:
            soc += oc * bd * thick * (1.0 - cf / 100.0)  # %·g/cm3·cm = tC/ha
        if clay is None or not 0 <= clay <= 100:
            clay_ok = False
        else:
            clay_w += clay * thick
        depth = bottom
    missing: list[Missing] = []
    if depth <= 0:
        return None, None, 0.0, [Missing("soil", "no horizons in 0-30 cm", "tier2_unavailable")]
    if not soc_ok:
        missing.append(Missing("soil_soc", "organic carbon or bulk density invalid or implausible in a 0-30 cm horizon",
                               "tier2_unavailable"))
    if not clay_ok:
        missing.append(Missing("soil_clay", "clay invalid in a 0-30 cm horizon", "tier2_unavailable"))
    return (soc if soc_ok else None), (clay_w / depth if clay_ok else None), depth, missing


async def fetch_soil_init(
    parcel_urn: str,
    tenant_id: str,
    lab: tuple[Optional[float], Optional[float]] = (None, None),
) -> tuple[Optional[SoilInit], list[Missing]]:
    """Topsoil (0-30 cm) SOC stock and clay for RothC. Lab values override."""
    lab_soc, lab_clay = lab
    if lab_soc is not None and lab_clay is not None:
        return SoilInit(float(lab_soc), float(lab_clay), _TOPSOIL_CM, "lab"), []

    orion = get_orion_client()
    q = f'refAgriParcel=="{parcel_urn}"|hasAgriParcel=="{parcel_urn}"'
    try:
        entities = await orion.query_entities(entity_type="AgriSoilExtended", tenant_id=tenant_id, query=q, limit=1)
        if not entities:
            entities = await orion.query_entities(entity_type="AgriSoil", tenant_id=tenant_id, query=q, limit=1)
    except Exception as exc:  # noqa: BLE001 — broker failure is unknown, not "no soil"
        logger.warning("soil query failed tenant=%s parcel=%s: %s", tenant_id, parcel_urn, exc)
        raise SourceUnavailable(f"soil query failed: {exc}") from exc
    if not entities:
        return None, [Missing("soil", "no AgriSoil/AgriSoilExtended for the parcel", "tier2_unavailable")]

    entity = entities[0]
    source = str(_attr(entity, "dataSource") or _attr(entity, "source") or "orion")
    horizons = _attr(entity, "horizons")
    soc, clay, depth, missing = _topsoil_from_horizons(horizons if isinstance(horizons, list) else [])
    if lab_soc is not None:
        soc, source = float(lab_soc), f"lab+{source}"
        missing = [m for m in missing if m.item != "soil_soc"]
    if lab_clay is not None:
        clay, source = float(lab_clay), f"lab+{source}"
        missing = [m for m in missing if m.item != "soil_clay"]
    if soc is None or clay is None:
        return None, missing
    return SoilInit(soc, clay, depth or _TOPSOIL_CM, source), missing
