"""Pydantic request/response models for carbon API.

Maps to spec §9 (API contract) and §7 (NGSI-LD entity shapes).
"""

from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Pool / Sub-response models
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class ProjectionResponse(BaseModel):
    """RothC projection from the last complete campaign; baseline only when defined."""
    entity_id: str
    projection_years: int
    reference_year: Optional[int] = None
    baseline_soc: list[float] = []
    project_soc: list[float] = []
    annual_delta_tC_ha_yr: list[float] = []
    assumptions: list[str] = []
    missing: list[dict] = []


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
# Summary / Aggregation models
# ---------------------------------------------------------------------------

class ParcelSummary(BaseModel):
    """One parcel in the tenant summary for a campaign; None = not computed."""
    parcel_id: str
    parcel_name: str = ""
    crop_species: str = ""
    campaign_year: Optional[int] = None
    computed_through: Optional[str] = None
    tier: int = 0
    co2_gross_tCO2_ha: Optional[float] = None
    delta_soc_tC_ha: Optional[float] = None
    co2eq_net_tCO2eq_ha: Optional[float] = None
    tier1_coverage: Optional[float] = None  # < 1: production computed on part of the cycle days


class YearlyAggregation(BaseModel):
    """Means over the parcels with that campaign computed (null values excluded;
    gross CO2 only from campaigns whose production covers every cycle day)."""
    year: int
    parcel_count: int = 0
    co2_gross_tCO2_ha_mean: Optional[float] = None
    delta_soc_tC_ha_mean: Optional[float] = None


class TierSummaryResponse(BaseModel):
    """Tenant-level carbon summary for one campaign."""
    tenant_id: str
    year: int
    parcels: list[ParcelSummary] = []
    yearly_aggregations: list[YearlyAggregation] = []


# ---------------------------------------------------------------------------
# Error model
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    """Standard error payload."""
    error: str
    error_code: str
    detail: Optional[str] = None
