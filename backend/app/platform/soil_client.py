"""
HTTP client for soil data — queries Orion-LD AgriSoilExtended entities.

The carbon module fetches soil data through Orion-LD (the context broker)
to avoid coupling to the soil module's internal API. AgriSoilExtended
entities are created/maintained by the soil module via NGSI-LD subscriptions.

If no entity exists for a parcel, defaults are returned (soilgrids estimates).
"""

import logging
from dataclasses import dataclass
from typing import Optional

from app.common.orion import get_orion_client
from app.platform.crop_client import normalize_parcel_short_id
from app.platform.errors import SourceUnavailable
from app.services.campaign_types import Missing, SoilInit

logger = logging.getLogger(__name__)


@dataclass
class SoilSnapshot:
    clay_pct: float = 20.0
    sand_pct: float = 30.0
    silt_pct: float = 50.0
    soc_tC_ha: float = 50.0  # 0-30cm topsoil
    bulk_density_kg_m3: float = 1300.0
    ph: float = 7.0
    awc_mm: float = 150.0  # available water capacity
    source: str = "default"  # "lab", "lucas", "esdb", "soilgrids", "default"


async def fetch_parcel_soil(
    parcel_id: str,
    tenant_id: str,
) -> SoilSnapshot:
    """Fetch soil data for a parcel from Orion-LD AgriSoilExtended entities.

    Checks both old (refAgriParcel) and new (hasAgriParcel) relationship
    names to stay compatible during the FIWARE naming migration window.

    Returns default values if no entity is found.
    """
    # Parcel URNs are tenant-less (urn:ngsi-ld:AgriParcel:{id}) — the soil
    # entity's hasAgriParcel/refAgriParcel point at that shape. NGSI-LD OR is a
    # single pipe; a double pipe is an invalid Q-Filter (400).
    parcel_ref = f"urn:ngsi-ld:AgriParcel:{normalize_parcel_short_id(parcel_id)}"
    try:
        orion = get_orion_client()
        entities = await orion.query_entities(
            entity_type="AgriSoilExtended",
            tenant_id=tenant_id,
            query=f'refAgriParcel=="{parcel_ref}"|hasAgriParcel=="{parcel_ref}"',
            limit=1,
        )
        if not entities:
            # Fall back to plain AgriSoil
            entities = await orion.query_entities(
                entity_type="AgriSoil",
                tenant_id=tenant_id,
                query=f'refAgriParcel=="{parcel_ref}"|hasAgriParcel=="{parcel_ref}"',
                limit=1,
            )

        if not entities:
            logger.info(
                "No AgriSoilExtended/AgriSoil for parcel %s in tenant %s, using defaults",
                parcel_id, tenant_id,
            )
            return SoilSnapshot(source="default")

        entity = entities[0]
        return _parse_soil_entity(entity)

    except Exception as exc:
        logger.warning("Soil fetch failed for %s: %s", parcel_id, exc)
        return SoilSnapshot(source="default")


def _parse_soil_entity(entity: dict) -> SoilSnapshot:
    """Parse an NGSI-LD AgriSoil or AgriSoilExtended entity into SoilSnapshot."""
    props = {
        k: (v.get("value") if isinstance(v, dict) and "value" in v else v)
        for k, v in entity.items()
        if k not in ("id", "type", "@context")
    }

    clay = _float_or(props.get("clayContent"), None)
    sand = _float_or(props.get("sandContent"), None)
    silt = _float_or(props.get("siltContent"), None)
    soc = _float_or(props.get("socTotal"), None)
    bd = _float_or(props.get("bulkDensity"), None)
    ph = _float_or(props.get("ph"), None)
    awc = _float_or(props.get("availableWaterCapacityMm"), None)
    source = str(props.get("source", "orion-ld"))

    # If no top-level SOC, try horizons array
    if soc is None:
        horizons = props.get("horizons", None)
        if isinstance(horizons, list) and horizons:
            for h in horizons:
                h_clay = _float_or(h.get("clayPercent"), None)
                h_sand = _float_or(h.get("sandPercent"), None)
                h_silt = _float_or(h.get("siltPercent"), None)
                h_soc = _float_or(h.get("socPercent"), None)
                h_bd = _float_or(h.get("bulkDensity"), None)
                if h_soc is not None:
                    soc = h_soc * 2  # rough: 0-30cm mean from % to tC/ha
                    clay = clay or h_clay
                    sand = sand or h_sand
                    silt = silt or h_silt
                    bd = bd or h_bd
                    source = "horizons"

    return SoilSnapshot(
        clay_pct=clay or 20.0,
        sand_pct=sand or 30.0,
        silt_pct=silt or 50.0,
        soc_tC_ha=soc or 50.0,
        bulk_density_kg_m3=bd or 1300.0,
        ph=ph or 7.0,
        awc_mm=awc or 150.0,
        source=source,
    )


def _float_or(val, default: Optional[float]) -> Optional[float]:
    """Return float value or default if None/invalid."""
    if val is None:
        return default
    try:
        v = float(val)
        return v if v > 0 else default
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Soil for the campaign balance: horizons only, no defaults.
# ---------------------------------------------------------------------------

_TOPSOIL_CM = 30.0
# Plausible mineral-soil bulk density, g/cm3. Outside it the value is a NODATA
# sentinel or a unit error, never a measurement.
_BD_RANGE = (0.5, 2.2)


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
        missing.append(Missing("soil_soc", "organic carbon or bulk density invalid in a 0-30 cm horizon", "tier2_unavailable"))
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
