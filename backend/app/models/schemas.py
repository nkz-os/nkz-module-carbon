"""Pydantic request/response models for carbon API.

Maps to spec §9 (API contract) and §7 (NGSI-LD entity shapes).
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pool / Sub-response models
# ---------------------------------------------------------------------------

class PoolStateResponse(BaseModel):
    """RothC pool state in tC/ha."""
    dpm_tC_ha: float
    rpm_tC_ha: float
    bio_tC_ha: float
    hum_tC_ha: float
    iom_tC_ha: float
    total_tC_ha: float


class TierGap(BaseModel):
    """Describes a data gap that prevents moving to the next tier."""
    source: str
    missing: bool = True
    action: str
    auto_fill: str | None = None


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CalculateRequest(BaseModel):
    """Trigger a carbon calculation for a parcel.

    All fields are optional — the engine falls back to defaults or
    platform-service lookup when the caller doesn't supply them.
    """
    entity_id: str
    tenant_id: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    date: Optional[date] = None
    crop_species: Optional[str] = None
    morph_type: Optional[str] = None  # "herbaceous" | "woody"
    management: Optional[dict] = None  # management data for Tier 2+


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class CarbonAssessmentResponse(BaseModel):
    """Full assessment result returned to the caller (spec §9.1)."""
    entity_id: str
    assessment_date: str
    tier: int
    methodology: str
    confidence: float
    confidence_interval_pct: float
    gpp_daily: dict  # {"value": 3.54, "unit": "gC/m2/day"}
    npp_daily: dict
    co2_sequestered_daily: dict
    co2_sequestered_cumulative: dict
    agb_dry: dict
    bgb_dry: dict
    soil_carbon_delta: Optional[dict] = None
    carbon_stock_total: Optional[dict] = None
    pools: Optional[PoolStateResponse] = None
    co2eq_net_daily: Optional[dict] = None
    co2eq_net_cumulative: Optional[dict] = None
    gwp_standard: str = "AR6"
    missing_for_next_tier: list[str] = []
    data_sources: list[str] = []
    data_provenance: dict = {}


class TierInfoResponse(BaseModel):
    """Describes the current tier and what is needed to advance."""
    current_tier: int
    confidence: float
    available_data: list[str]
    gaps: list[TierGap]


class HistoryResponse(BaseModel):
    """Paginated history of assessments for a parcel."""
    entity_id: str
    assessments: list[CarbonAssessmentResponse]
    count: int


class ProjectionResponse(BaseModel):
    """20-year RothC projection comparing baseline vs project management."""
    entity_id: str
    projection_years: int
    baseline_soc: list[float]
    project_soc: list[float]
    annual_delta_tC_ha_yr: list[float]


# ---------------------------------------------------------------------------
# Scenario models
# ---------------------------------------------------------------------------

class ScenarioResponse(BaseModel):
    """A baseline or project scenario."""
    scenario_id: str
    scenario_type: str  # "BaselineScenario" | "ProjectScenario"
    parcel_id: str
    valid_from: str
    valid_to: str
    management_params: dict
    calculation_run_id: str | None = None
    baseline_scenario_id: str | None = None


class CreateBaselineRequest(BaseModel):
    """Create a baseline scenario."""
    valid_from: str
    valid_to: str
    management_params: dict


class CreateProjectRequest(BaseModel):
    """Create a project scenario referencing a baseline."""
    baseline_scenario_id: str
    valid_from: str
    valid_to: str
    management_params: dict


class CalculationRunResponse(BaseModel):
    """A single calculation run within a scenario."""
    run_id: str
    timestamp: str
    tier: int
    confidence: float
    engine_version: str
    inputs_snapshot: dict
    outputs: dict
    uncertainty: Optional[dict] = None


# ---------------------------------------------------------------------------
# Error model
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    """Standard error payload."""
    error: str
    error_code: str
    detail: Optional[str] = None
