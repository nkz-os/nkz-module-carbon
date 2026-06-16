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
    try:
        orion = get_orion_client()
        entities = await orion.query_entities(
            entity_type="AgriSoilExtended",
            tenant_id=tenant_id,
            query=(
                f'refAgriParcel=="urn:ngsi-ld:AgriParcel:{tenant_id}:{parcel_id}"'
                f'||hasAgriParcel=="urn:ngsi-ld:AgriParcel:{tenant_id}:{parcel_id}"'
            ),
            limit=1,
        )
        if not entities:
            # Fall back to plain AgriSoil
            entities = await orion.query_entities(
                entity_type="AgriSoil",
                tenant_id=tenant_id,
                query=(
                    f'refAgriParcel=="urn:ngsi-ld:AgriParcel:{tenant_id}:{parcel_id}"'
                    f'||hasAgriParcel=="urn:ngsi-ld:AgriParcel:{tenant_id}:{parcel_id}"'
                ),
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
