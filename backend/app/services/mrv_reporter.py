"""MRV Reporter -- VM0042 and Gold Standard structured report generation.

Generates auditable carbon credit reports with complete traceability.
Every report includes input hashing and calculation run anchoring for
Verra VM0042 5.5 and 8 audit requirements.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

ENGINE_VERSION = "2.1.0"
REPORT_STANDARDS = ["VM0042", "GOLD_STANDARD_SOC"]


@dataclass
class MRVReport:
    """Structured MRV report."""
    report_id: str
    standard: str  # "VM0042" | "GOLD_STANDARD_SOC"
    generated_at: str
    engine_version: str

    # Project identification
    project_name: str
    parcel_id: str
    tenant_id: str
    reporting_period_start: str
    reporting_period_end: str

    # Calculation anchoring (VM0042 5.5 + 8)
    baseline_calculation_run_id: str
    project_calculation_run_id: str
    baseline_scenario_id: str
    project_scenario_id: str
    inputs_hash: str

    # Results
    baseline_nee_tCO2_ha_yr: float
    project_nee_tCO2_ha_yr: float
    net_emission_reductions_tCO2eq_ha_yr: float
    buffer_pool_pct: float = 20.0  # Verra standard buffer
    verified_credits_tCO2eq_ha_yr: float = 0.0

    # Methodology details
    tier: int = 1
    confidence: float = 0.0
    confidence_interval_pct: float = 0.0
    data_sources: list[str] = field(default_factory=list)
    methodology_description: str = ""
    uncertainty_method: str = ""

    # GHG breakdown (Tier 3 only)
    n2o_emissions_tCO2eq_ha_yr: Optional[float] = None
    ch4_emissions_tCO2eq_ha_yr: Optional[float] = None

    # SOC pools (Tier 2+)
    soc_initial_tC_ha: Optional[float] = None
    soc_final_tC_ha: Optional[float] = None
    soc_delta_tC_ha_yr: Optional[float] = None

    # Management comparison
    baseline_management: dict = field(default_factory=dict)
    project_management: dict = field(default_factory=dict)

    # Audit trail
    calculation_timestamp: str = ""
    input_snapshot: dict = field(default_factory=dict)
    output_snapshot: dict = field(default_factory=dict)


def generate_vm0042_report(
    project_name: str,
    parcel_id: str,
    tenant_id: str,
    reporting_period_start: str,
    reporting_period_end: str,
    baseline_scenario_id: str,
    project_scenario_id: str,
    baseline_calculation_run_id: str,
    project_calculation_run_id: str,
    baseline_nee_tCO2_ha_yr: float,
    project_nee_tCO2_ha_yr: float,
    tier: int,
    confidence: float,
    confidence_interval_pct: float,
    data_sources: list[str],
    baseline_management: dict,
    project_management: dict,
    input_snapshot: dict,
    output_snapshot: dict,
    uncertainty_method: str = "gaussian_analytical",
    n2o_emissions_tCO2eq_ha_yr: Optional[float] = None,
    ch4_emissions_tCO2eq_ha_yr: Optional[float] = None,
    soc_initial_tC_ha: Optional[float] = None,
    soc_final_tC_ha: Optional[float] = None,
    soc_delta_tC_ha_yr: Optional[float] = None,
) -> MRVReport:
    """Generate a VM0042-compliant MRV report.

    VM0042 5.5 requires: baseline scenario, project scenario, additionality demonstration.
    VM0042 8 requires: calculation methodology, uncertainty, buffer pool.
    """
    net_reductions = baseline_nee_tCO2_ha_yr - project_nee_tCO2_ha_yr

    # Buffer pool: 20% of net reductions (Verra standard for agriculture)
    buffer_pool = 0.20
    verified_credits = net_reductions * (1.0 - buffer_pool)

    inputs_hash = _hash_report_inputs(
        baseline_management, project_management,
        baseline_nee_tCO2_ha_yr, project_nee_tCO2_ha_yr,
        input_snapshot,
    )

    report_id = _generate_report_id(tenant_id, parcel_id, reporting_period_start)

    methodology_parts = [f"Tier {tier}"]
    if tier >= 2:
        methodology_parts.append("RothC soil carbon model (Jenkinson 1990)")
    if tier >= 3:
        methodology_parts.append("IPCC 2019 Refinement N2O/CH4")

    return MRVReport(
        report_id=report_id,
        standard="VM0042",
        generated_at=datetime.now(timezone.utc).isoformat(),
        engine_version=ENGINE_VERSION,
        project_name=project_name,
        parcel_id=parcel_id,
        tenant_id=tenant_id,
        reporting_period_start=reporting_period_start,
        reporting_period_end=reporting_period_end,
        baseline_calculation_run_id=baseline_calculation_run_id,
        project_calculation_run_id=project_calculation_run_id,
        baseline_scenario_id=baseline_scenario_id,
        project_scenario_id=project_scenario_id,
        inputs_hash=inputs_hash,
        baseline_nee_tCO2_ha_yr=baseline_nee_tCO2_ha_yr,
        project_nee_tCO2_ha_yr=project_nee_tCO2_ha_yr,
        net_emission_reductions_tCO2eq_ha_yr=net_reductions,
        buffer_pool_pct=buffer_pool * 100,
        verified_credits_tCO2eq_ha_yr=verified_credits,
        tier=tier,
        confidence=confidence,
        confidence_interval_pct=confidence_interval_pct,
        data_sources=data_sources,
        methodology_description="; ".join(methodology_parts),
        uncertainty_method=uncertainty_method,
        n2o_emissions_tCO2eq_ha_yr=n2o_emissions_tCO2eq_ha_yr,
        ch4_emissions_tCO2eq_ha_yr=ch4_emissions_tCO2eq_ha_yr,
        soc_initial_tC_ha=soc_initial_tC_ha,
        soc_final_tC_ha=soc_final_tC_ha,
        soc_delta_tC_ha_yr=soc_delta_tC_ha_yr,
        baseline_management=baseline_management,
        project_management=project_management,
        calculation_timestamp=datetime.now(timezone.utc).isoformat(),
        input_snapshot=input_snapshot,
        output_snapshot=output_snapshot,
    )


def generate_gold_standard_report(
    project_name: str,
    parcel_id: str,
    tenant_id: str,
    reporting_period_start: str,
    reporting_period_end: str,
    baseline_scenario_id: str,
    project_scenario_id: str,
    baseline_calculation_run_id: str,
    project_calculation_run_id: str,
    baseline_nee_tCO2_ha_yr: float,
    project_nee_tCO2_ha_yr: float,
    tier: int,
    confidence: float,
    confidence_interval_pct: float,
    data_sources: list[str],
    baseline_management: dict,
    project_management: dict,
    input_snapshot: dict,
    output_snapshot: dict,
    soc_initial_tC_ha: Optional[float] = None,
    soc_delta_tC_ha_yr: Optional[float] = None,
) -> MRVReport:
    """Generate a Gold Standard SOC Framework report.

    Gold Standard requires: SOC baseline measurement, additionality,
    leakage assessment, and sustainable development contributions.
    """
    report = generate_vm0042_report(
        project_name=project_name,
        parcel_id=parcel_id,
        tenant_id=tenant_id,
        reporting_period_start=reporting_period_start,
        reporting_period_end=reporting_period_end,
        baseline_scenario_id=baseline_scenario_id,
        project_scenario_id=project_scenario_id,
        baseline_calculation_run_id=baseline_calculation_run_id,
        project_calculation_run_id=project_calculation_run_id,
        baseline_nee_tCO2_ha_yr=baseline_nee_tCO2_ha_yr,
        project_nee_tCO2_ha_yr=project_nee_tCO2_ha_yr,
        tier=tier,
        confidence=confidence,
        confidence_interval_pct=confidence_interval_pct,
        data_sources=data_sources,
        baseline_management=baseline_management,
        project_management=project_management,
        input_snapshot=input_snapshot,
        output_snapshot=output_snapshot,
        soc_initial_tC_ha=soc_initial_tC_ha,
        soc_delta_tC_ha_yr=soc_delta_tC_ha_yr,
    )
    report.standard = "GOLD_STANDARD_SOC"
    report.report_id = report.report_id.replace("VM0042", "GS-SOC")
    # Gold Standard buffer: 20% same as Verra
    return report


def _hash_report_inputs(
    baseline_mgmt: dict,
    project_mgmt: dict,
    baseline_nee: float,
    project_nee: float,
    input_snapshot: dict,
) -> str:
    """Generate deterministic hash of all report inputs."""
    import hashlib
    canonical = json.dumps(
        {
            "baseline_management": baseline_mgmt,
            "project_management": project_mgmt,
            "baseline_nee": baseline_nee,
            "project_nee": project_nee,
            "input_snapshot": input_snapshot,
            "engine_version": ENGINE_VERSION,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _generate_report_id(tenant_id: str, parcel_id: str, period_start: str) -> str:
    """Generate unique report ID."""
    return f"MRV-VM0042-{tenant_id}-{parcel_id}-{period_start}"


def report_to_dict(report: MRVReport) -> dict:
    """Serialize an MRVReport to a JSON-serializable dict."""
    import dataclasses
    return dataclasses.asdict(report)


def report_to_json(report: MRVReport, indent: int = 2) -> str:
    """Serialize an MRVReport to formatted JSON string."""
    return json.dumps(report_to_dict(report), indent=indent, default=str)
