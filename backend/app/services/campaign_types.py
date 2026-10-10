"""Immutable inputs and outputs of the per-campaign carbon balance."""

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class WeatherDay:
    day: date
    tmin_c: Optional[float]
    tmax_c: Optional[float]
    precip_mm: Optional[float]
    et0_mm: Optional[float]
    radiation_mj_m2: Optional[float]

    @property
    def complete(self) -> bool:
        return None not in (self.tmin_c, self.tmax_c, self.precip_mm, self.et0_mm, self.radiation_mj_m2)


@dataclass(frozen=True)
class CropParams:
    lue_gC_MJ: float
    fapar_a: float
    fapar_b: float
    vi_type: str
    root_fraction: float
    source: str  # "bioorchestrator" | "table"


@dataclass(frozen=True)
class CycleSpan:
    crop_id: str
    species: str
    role: str
    lifecycle: str  # "annual" | "perennial" | "unknown"
    start: date
    end: Optional[date]
    start_provenance: str
    end_provenance: Optional[str]
    campaign_label: Optional[int]
    params: Optional[CropParams]


@dataclass(frozen=True)
class HarvestEvent:
    day: date
    exported_c_tC_ha: Optional[float]
    source: str


@dataclass(frozen=True)
class FertilizationEvent:
    day: date
    n_kg_ha: Optional[float]
    organic: bool
    source: str


@dataclass(frozen=True)
class TillageEvent:
    day: date
    tillage_type: str


@dataclass(frozen=True)
class BalingEvent:
    day: date


@dataclass(frozen=True)
class DeclaredManagement:
    """Values the farmer saved in the management form; all None when never saved."""
    harvest_export_fraction: Optional[float]
    residue_removal_fraction: Optional[float]
    organic_amendments_tC_ha_yr: Optional[float]
    n_synthetic_kgN_ha_yr: Optional[float]
    n_organic_kgN_ha_yr: Optional[float]
    irrigated: Optional[bool]


NO_DECLARED_MANAGEMENT = DeclaredManagement(None, None, None, None, None, None)


@dataclass(frozen=True)
class SoilInit:
    soc_tC_ha: float
    clay_pct: float
    depth_cm: float
    source: str


@dataclass(frozen=True)
class Missing:
    item: str
    reason: str
    effect: str

    def to_dict(self) -> dict[str, str]:
        return {"item": self.item, "reason": self.reason, "effect": self.effect}


# Imported here (not at the top) to keep the input types free of model imports.
from app.services.roth_c_model import RothCState  # noqa: E402


@dataclass(frozen=True)
class CampaignInputs:
    year: int
    today: date
    weather: tuple[WeatherDay, ...]           # may start before 1 Jan for cycles crossing the year
    ndvi: tuple[tuple[date, float], ...]
    cycles: tuple[CycleSpan, ...]
    soil: Optional[SoilInit]
    initial_state: Optional[RothCState]        # end state of the previous complete campaign
    initial_state_source: str                  # "previous_campaign" | "soil"
    harvests: tuple[HarvestEvent, ...]
    fertilizations: tuple[FertilizationEvent, ...]
    tillages: tuple[TillageEvent, ...]
    balings: tuple[BalingEvent, ...]
    declared: DeclaredManagement
    missing_in: tuple[Missing, ...]            # gaps found while reading the sources


@dataclass(frozen=True)
class CycleResult:
    crop_id: str
    species: str
    role: str
    start: date
    end: Optional[date]
    start_provenance: str
    end_provenance: Optional[str]
    campaign_label: Optional[int]
    days_in_period: int
    days_computed: int
    npp_tC_ha: float                       # produced inside the period
    c_to_soil_tC_ha: Optional[float]       # exudates in the period + closure, None if unknown
    exported_c_tC_ha: Optional[float]      # None while open or unknown


@dataclass(frozen=True)
class MonthResult:
    month: int
    temp_c: float
    rain_mm: float
    et0_mm: float
    covered: bool
    cover_days: int
    plant_c_tC_ha: float
    fym_c_tC_ha: float
    co2_c_tC_ha: Optional[float]


@dataclass(frozen=True)
class CampaignBalance:
    year: int
    period_start: date
    period_end: date
    computed_through: Optional[date]
    tier: int
    cover_days: int
    bare_days: int
    gpp_tC_ha: Optional[float]
    npp_tC_ha: Optional[float]
    co2_gross_tCO2_ha: Optional[float]
    tier1_coverage: float
    rh_tC_ha: Optional[float]
    soc_start_tC_ha: Optional[float]
    soc_end_tC_ha: Optional[float]
    delta_soc_tC_ha: Optional[float]
    nee_tCO2_ha: Optional[float]
    necb_tC_ha: Optional[float]            # NPP - Rh - exported + imported C
    n2o_tCO2eq_ha: Optional[float]
    co2eq_net_tCO2eq_ha: Optional[float]
    gpp_ci95_pct: Optional[float]
    delta_soc_ci95_tC_ha: Optional[float]
    end_state: Optional[RothCState]
    initial_state_source: str
    cycles: tuple[CycleResult, ...]
    months: tuple[MonthResult, ...]
    missing: tuple[Missing, ...]
    assumptions: tuple[str, ...]
