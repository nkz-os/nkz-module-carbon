"""Management practices declared by the farmer.

Only what the platform does not record elsewhere: tillage and cover crops come
from field operations and crop cycles, weather from the parcel daily series.
Every field is optional and None means "not declared"; nothing is defaulted.
"""

from typing import Optional

from pydantic import BaseModel, Field


class ManagementInput(BaseModel):
    """Farmer-declared management practices (all optional)."""
    residue_removal_fraction: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Share of the crop residue removed (e.g. baled straw)",
    )
    organic_amendments_tC_ha_yr: Optional[float] = Field(
        default=None, ge=0.0,
        description="Carbon in organic amendments (manure/compost), tC/ha/yr",
    )
    n_synthetic_kgN_ha_yr: Optional[float] = Field(
        default=None, ge=0.0, description="Synthetic N applied, kgN/ha/yr (0 = none applied)",
    )
    n_organic_kgN_ha_yr: Optional[float] = Field(
        default=None, ge=0.0, description="Organic N applied, kgN/ha/yr (0 = none applied)",
    )
    irrigated: Optional[bool] = Field(default=None, description="Used only without recorded irrigations")
    harvest_export_fraction: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Share of the above-ground biomass exported at harvest",
    )
    soil_lab_soc_tC_ha: Optional[float] = Field(
        default=None, gt=0.0, description="Lab-measured SOC stock, tC/ha (0-30 cm)",
    )
    soil_lab_clay_pct: Optional[float] = Field(
        default=None, ge=0.0, le=100.0, description="Lab-measured clay content, %",
    )
