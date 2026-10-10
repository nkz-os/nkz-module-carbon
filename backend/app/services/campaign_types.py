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
