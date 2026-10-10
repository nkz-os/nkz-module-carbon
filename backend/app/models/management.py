"""Management practices declared by the farmer.

Every field is optional and None means "not declared". Nothing here is a
default: the balance only uses what the farmer actually entered.
"""

from typing import Optional

from pydantic import BaseModel, Field


class ManagementInput(BaseModel):
    """Farmer-declared management practices (all optional)."""
    weather_source: Optional[str] = Field(
        default=None,
        description='Legacy selector; campaign weather always comes from the parcel daily series',
    )
    weather_sensor_id: Optional[str] = Field(default=None, description="Legacy sensor id")
    residues_removed: Optional[bool] = None
    residue_removal_fraction: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Share of the crop residue removed (e.g. baled straw)",
    )
    tillage_type: Optional[str] = Field(
        default=None,
        description='One of: "conventional", "reduced", "no_till"',
    )
    cover_crop_months: Optional[int] = Field(default=None, ge=0, le=12)
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
    irrigated: Optional[bool] = None
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
