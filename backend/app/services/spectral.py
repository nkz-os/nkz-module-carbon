"""Spectral index selection and computation (spec 2).

Olive pixel unmixing is deferred to Phase 8 (historical reconstructor).
Cloud masking is handled by vegetation-prime during scene processing.
"""

import math
from enum import Enum


class MorphologicalType(str, Enum):
    HERBACEOUS = "herbaceous"
    WOODY = "woody"


class VegetationIndex(str, Enum):
    NDVI = "NDVI"
    OSAVI = "OSAVI"
    MSAVI2 = "MSAVI2"


# OSAVI soil adjustment factor for woody crops
OSAVI_L_WOODY = 0.16


def select_index(morph_type: MorphologicalType) -> VegetationIndex:
    """Select vegetation index by crop morphological type.

    Herbaceous -> NDVI
    Woody      -> OSAVI (L=0.16)
    """
    if morph_type == MorphologicalType.HERBACEOUS:
        return VegetationIndex.NDVI
    if morph_type == MorphologicalType.WOODY:
        return VegetationIndex.OSAVI
    return VegetationIndex.MSAVI2


def compute_ndvi(nir: float, red: float) -> float:
    """NDVI = (NIR - RED) / (NIR + RED)."""
    denom = nir + red
    if denom == 0:
        return 0.0
    return (nir - red) / denom


def compute_osavi(nir: float, red: float, L: float = OSAVI_L_WOODY) -> float:
    """OSAVI = (NIR - RED) / (NIR + RED + L)."""
    return (nir - red) / (nir + red + L)


def compute_msavi2(nir: float, red: float) -> float:
    """MSAVI2 = (2 NIR + 1 - sqrt((2 NIR + 1)^2 - 8 (NIR - RED))) / 2."""
    discriminant = (2 * nir + 1) ** 2 - 8 * (nir - red)
    if discriminant < 0:
        return 0.0
    return (2 * nir + 1 - math.sqrt(discriminant)) / 2


def compute_index(
    vi: VegetationIndex, nir: float, red: float
) -> float:
    """Compute the selected vegetation index from NIR and RED bands."""
    if vi == VegetationIndex.NDVI:
        return compute_ndvi(nir, red)
    if vi == VegetationIndex.OSAVI:
        return compute_osavi(nir, red)
    if vi == VegetationIndex.MSAVI2:
        return compute_msavi2(nir, red)
    raise ValueError(f"Unknown vegetation index: {vi}")
