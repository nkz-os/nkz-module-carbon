"""Management input schema for Tier 2/3 carbon calculations.

Captures farmer-declared or remotely-sensed management practices used
to parameterise RothC (Tier 2) and GHG (Tier 3) models.
"""

from typing import Optional

from pydantic import BaseModel, Field


class ManagementInput(BaseModel):
    """Farmer-declared management practices.

    Defaults represent conventional tillage, no cover crop, no irrigation,
    synthetic-only fertiliser at zero rate, and full residue retention.
    """
    weather_source: str = Field(
        default="api",
        description='"api" for weather-api-service (canonical), "sensor" for on-farm sensor',
    )
    weather_sensor_id: Optional[str] = Field(
        default=None,
        description="AgriSensor entity ID when weather_source='sensor'",
    )
    residues_removed: bool = False
    residue_removal_fraction: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Fraction of crop residues removed from the field",
    )
    tillage_type: str = Field(
        default="conventional",
        description='One of: "conventional", "reduced", "no_till"',
    )
    cover_crop_months: int = Field(
        default=0, ge=0, le=12,
        description="Months per year with active cover crop",
    )
    organic_amendments_tC_ha_yr: float = Field(
        default=0.0, ge=0.0,
        description="Organic amendments (manure/compost) in tC/ha/yr",
    )
    n_synthetic_kgN_ha_yr: float = Field(
        default=0.0, ge=0.0,
        description="Synthetic N fertiliser rate in kgN/ha/yr",
    )
    n_organic_kgN_ha_yr: float = Field(
        default=0.0, ge=0.0,
        description="Organic N fertiliser rate in kgN/ha/yr",
    )
    irrigated: bool = False
    harvest_export_fraction: float = Field(
        default=0.9, ge=0.0, le=1.0,
        description="Fraction of above-ground biomass exported at harvest",
    )
    soil_lab_soc_tC_ha: Optional[float] = Field(
        default=None,
        description="Lab-measured total SOC in tC/ha (0-30 cm)",
    )
    soil_lab_clay_pct: Optional[float] = Field(
        default=None, ge=0.0, le=100.0,
        description="Lab-measured clay content in percent",
    )
