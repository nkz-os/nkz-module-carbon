"""Crop parameters for the LUE model: BioOrchestrator, then sourced tables, else missing."""

import logging
from typing import Optional

from app.platform.bioorchestrator_client import fetch_phenology_params
from app.platform.crop_client import carbon_species_key, phenology_species_param
from app.services.campaign_types import CropParams, Missing

logger = logging.getLogger(__name__)

# Sources in METHODOLOGY.md. Species not listed have no calibration: no generic fallback.
LUE_BY_SPECIES: dict[str, float] = {
    "wheat": 1.1, "barley": 1.0, "olive": 0.9, "corn": 1.7,
    "rice": 1.3, "sunflower": 1.3, "soybean": 1.2, "sugarcane": 1.8,
}

ROOT_FRACTION_BY_SPECIES: dict[str, float] = {
    "wheat": 0.22, "barley": 0.22, "corn": 0.18, "rice": 0.15,
    "sunflower": 0.20, "soybean": 0.20, "sugarcane": 0.20,
    "olive": 0.20, "vineyard": 0.20, "almond": 0.25,
    "citrus": 0.25, "pasture": 0.55,
}

FAPAR_PARAMS: dict[str, tuple[float, float, str]] = {
    "wheat": (1.24, -0.168, "NDVI"), "barley": (1.24, -0.168, "NDVI"),
    "corn": (1.24, -0.168, "NDVI"), "rice": (1.24, -0.168, "NDVI"),
    "sunflower": (1.24, -0.168, "NDVI"), "soybean": (1.24, -0.168, "NDVI"),
    "sugarcane": (1.24, -0.168, "NDVI"),
    "olive": (1.40, -0.240, "OSAVI"), "vineyard": (1.40, -0.240, "OSAVI"),
    "almond": (1.40, -0.240, "OSAVI"), "citrus": (1.40, -0.240, "OSAVI"),
}

# Species whose cycles are perennial when the crop record does not say so.
WOODY_SPECIES = {"olive", "vineyard", "almond", "citrus"}

# Indices the platform publishes per acquisition (EOProduct).
AVAILABLE_VI = {"NDVI", "OSAVI"}

# Plausible ranges for parameters received from BioOrchestrator; outside them a value is
# a data error, not a calibration. The root share must cover the exudates the balance
# takes from it (campaign_balance.EXUDATE_FRACTION), or root inputs turn negative.
_LUE_RANGE = (0.0, 5.0)          # gC/MJ PAR, exclusive lower bound
_FAPAR_A_RANGE = (0.0, 5.0)      # slope of fAPAR on the index, exclusive lower bound
_FAPAR_B_RANGE = (-1.0, 1.0)
_ROOT_FRACTION_RANGE = (0.07, 0.9)


def _plausible(lue: float, a: float, b: float, root: float) -> bool:
    return (_LUE_RANGE[0] < lue <= _LUE_RANGE[1] and _FAPAR_A_RANGE[0] < a <= _FAPAR_A_RANGE[1]
            and _FAPAR_B_RANGE[0] <= b <= _FAPAR_B_RANGE[1]
            and _ROOT_FRACTION_RANGE[0] <= root <= _ROOT_FRACTION_RANGE[1])


async def resolve_crop_params(
    species: str,
    lat: Optional[float],
    lon: Optional[float],
) -> tuple[Optional[CropParams], list[Missing]]:
    key = carbon_species_key(species or "")
    bio = await fetch_phenology_params(phenology_species_param(species or ""), lat=lat, lon=lon) if species else None
    params: Optional[CropParams] = None
    complete = bio and None not in (bio.lue_gC_per_MJ, bio.fapar_a, bio.fapar_b, bio.root_fraction)
    if complete and not _plausible(float(bio.lue_gC_per_MJ), float(bio.fapar_a), float(bio.fapar_b),
                                   float(bio.root_fraction)):
        logger.warning("implausible BioOrchestrator crop params species=%s lue=%s fapar=(%s, %s) root=%s",
                       species, bio.lue_gC_per_MJ, bio.fapar_a, bio.fapar_b, bio.root_fraction)
        complete = False
    if complete:
        params = CropParams(float(bio.lue_gC_per_MJ), float(bio.fapar_a), float(bio.fapar_b),
                            str(bio.fapar_vi_type or "NDVI").upper(), float(bio.root_fraction), "bioorchestrator")
    elif key in LUE_BY_SPECIES and key in FAPAR_PARAMS and key in ROOT_FRACTION_BY_SPECIES:
        a, b, vi = FAPAR_PARAMS[key]
        params = CropParams(LUE_BY_SPECIES[key], a, b, vi, ROOT_FRACTION_BY_SPECIES[key], "table")
    elif key in FAPAR_PARAMS and FAPAR_PARAMS[key][2] not in AVAILABLE_VI:
        return None, [Missing("vi_type", f"{species}: fAPAR calibrated on {FAPAR_PARAMS[key][2]}, not published",
                              "tier1_unavailable")]
    if params is None:
        return None, [Missing("crop_params", f"{species or 'unknown'}: no calibrated LUE/fAPAR/root fraction",
                              "tier1_unavailable")]
    if params.vi_type not in AVAILABLE_VI:
        return None, [Missing("vi_type", f"{species}: fAPAR calibrated on {params.vi_type}, not published",
                              "tier1_unavailable")]
    return params, []
