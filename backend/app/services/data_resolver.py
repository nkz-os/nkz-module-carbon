"""Data Resolver -- automatic tier selection based on available data sources.

Zero-friction: user never chooses tier. The resolver checks what data
exists for a parcel and selects the highest possible tier.
"""

import logging
from dataclasses import dataclass, field
from enum import IntEnum

logger = logging.getLogger(__name__)


class Tier(IntEnum):
    ONE = 1
    TWO = 2
    THREE = 3


@dataclass
class DataAvailability:
    """What data sources are available for a parcel."""
    ndvi_available: bool = False
    lai_available: bool = False
    meteo_available: bool = False
    soil_available: bool = False          # SoilGrids or lab analysis
    phenology_available: bool = False     # BioOrchestrator has this species
    management_available: bool = False    # Farmer declared management
    sensors_soil_available: bool = False  # Soil moisture/T sensors
    sensors_plant_available: bool = False # IR canopy, dendrometer
    fertilization_available: bool = False # N application data
    soc_lab_available: bool = False       # Lab soil organic carbon
    soc_provenance: str = ""              # Where SOC data comes from


@dataclass
class TierResult:
    """Tier selection result with actionable gaps."""
    tier: Tier
    confidence: float
    available_sources: list[str] = field(default_factory=list)
    missing_for_next_tier: list[str] = field(default_factory=list)
    gap_details: list[dict] = field(default_factory=list)
    soc_provenance: str = ""


def resolve_tier(available: DataAvailability, uncertainty_ci_width: float | None = None) -> TierResult:
    """Determine the highest tier given available data sources.

    Tier requirements:
      1: ndvi OR lai, meteo (always available if we have a parcel)
      2: + soil, phenology, management
      3: + sensors_soil, sensors_plant, fertilization
    """
    sources = _collect_available(available)

    # Check Tier 3
    if all([
        available.ndvi_available or available.lai_available,
        available.meteo_available,
        available.soil_available,
        available.phenology_available,
        available.management_available,
        available.sensors_soil_available,
        available.sensors_plant_available,
        available.fertilization_available,
    ]):
        tier = Tier.THREE
        missing = []
    # Check Tier 2
    elif all([
        available.ndvi_available or available.lai_available,
        available.meteo_available,
        available.soil_available,
        available.phenology_available,
        available.management_available,
    ]):
        tier = Tier.TWO
        missing = _tier3_gaps(available)
    # Tier 1
    elif available.ndvi_available or available.lai_available:
        tier = Tier.ONE
        missing = _tier2_gaps(available)
    else:
        tier = Tier.ONE
        missing = ["ndvi (no satellite data available yet)"]

    # Confidence from uncertainty if available, otherwise a priori bounds
    if uncertainty_ci_width is not None:
        confidence = _confidence_from_ci(uncertainty_ci_width)
    else:
        confidence = _a_priori_confidence(tier)

    return TierResult(
        tier=tier,
        confidence=confidence,
        available_sources=sources,
        missing_for_next_tier=missing,
        gap_details=_build_gap_details(available, tier),
        soc_provenance=available.soc_provenance,
    )


def _collect_available(a: DataAvailability) -> list[str]:
    sources = []
    if a.ndvi_available:
        sources.append("ndvi")
    if a.lai_available:
        sources.append("lai")
    if a.meteo_available:
        sources.append("meteo")
    if a.soil_available:
        sources.append("soil")
    if a.phenology_available:
        sources.append("phenology")
    if a.management_available:
        sources.append("management")
    if a.sensors_soil_available:
        sources.append("sensors_soil")
    if a.sensors_plant_available:
        sources.append("sensors_plant")
    if a.fertilization_available:
        sources.append("fertilization")
    if a.soc_lab_available:
        sources.append("soc_lab")
    return sources


def _tier2_gaps(a: DataAvailability) -> list[str]:
    gaps = []
    if not a.soil_available:
        gaps.append("soil_type (se usara SoilGrids automaticamente al alcanzar Tier 2)")
    if not a.phenology_available:
        gaps.append("phenology (especie no encontrada en BioOrchestrator)")
    if not a.management_available:
        gaps.append("management (completar datos de manejo en 2 minutos)")
    return gaps


def _tier3_gaps(a: DataAvailability) -> list[str]:
    gaps = []
    if not a.sensors_soil_available:
        gaps.append("soil_moisture_sensor (instalar sonda de humedad)")
    if not a.sensors_plant_available:
        gaps.append("canopy_sensor (instalar sensor IR de copa)")
    if not a.fertilization_available:
        gaps.append("fertilization_log (registrar aplicaciones de N)")
    return gaps


def _build_gap_details(a: DataAvailability, current_tier: Tier) -> list[dict]:
    """Build detailed gap info for UI (i18n-friendly keys)."""
    gap_map = {
        "soil_type": {
            "source": "soil_type",
            "missing": not a.soil_available,
            "action": "No action needed",
            "auto_fill": "SoilGrids regional will be used automatically at Tier 2",
            "required_for_tier": 2,
        },
        "phenology": {
            "source": "phenology",
            "missing": not a.phenology_available,
            "action": "Species not in BioOrchestrator database",
            "auto_fill": None,
            "required_for_tier": 2,
        },
        "management": {
            "source": "management",
            "missing": not a.management_available,
            "action": "Complete management data (2 minutes)",
            "auto_fill": None,
            "required_for_tier": 2,
        },
        "sensors_soil": {
            "source": "sensors_soil",
            "missing": not a.sensors_soil_available,
            "action": "Install 1 soil moisture probe (~100 EUR)",
            "auto_fill": None,
            "required_for_tier": 3,
        },
        "sensors_plant": {
            "source": "sensors_plant",
            "missing": not a.sensors_plant_available,
            "action": "Install IR canopy sensor",
            "auto_fill": None,
            "required_for_tier": 3,
        },
        "fertilization": {
            "source": "fertilization",
            "missing": not a.fertilization_available,
            "action": "Log fertilizer N applications",
            "auto_fill": None,
            "required_for_tier": 3,
        },
    }
    return [
        v for k, v in gap_map.items()
        if v["missing"] and v["required_for_tier"] > current_tier
    ]


def _confidence_from_ci(ci95_width: float) -> float:
    """Derive confidence from CI95 width relative to estimate."""
    # Normalize: width of 40% relative → confidence ~0.6
    # width of 10% relative → confidence ~0.9
    conf = 1.0 - min(ci95_width, 1.0)
    return round(max(0.0, min(1.0, conf)), 3)


def _a_priori_confidence(tier: Tier) -> float:
    """Conservative a priori confidence bounds per tier."""
    return {Tier.ONE: 0.60, Tier.TWO: 0.75, Tier.THREE: 0.85}[tier]
