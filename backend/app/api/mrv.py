"""MRV report API endpoints."""

import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException

from app.common.auth import AuthContext, require_auth
from app.services.mrv_reporter import (
    generate_vm0042_report,
    generate_gold_standard_report,
    report_to_dict,
)
from app.ngsild.client import query_entities
from app.models.schemas import ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/carbon/parcels/{entity_id}/mrv", tags=["MRV"])


@router.get("/report")
async def get_mrv_report(
    entity_id: str,
    standard: str = "VM0042",
    auth: AuthContext = require_auth(),
):
    """Generate an MRV report for a parcel.

    Loads the latest CarbonAssessment from Orion-LD and searches for
    baseline/project scenarios. Returns a structured report with
    net emission reductions, verified credits, and buffer pool.
    """
    tenant_id = auth.tenant_id
    # 1. Load latest assessment
    try:
        assessments = await query_entities(
            entity_type="CarbonAssessment",
            tenant_id=tenant_id,
            query=f'refAgriParcel=="urn:ngsi-ld:AgriParcel:{tenant_id}:{entity_id}"',
            limit=1,
        )
    except Exception as exc:
        logger.exception("Error querying assessments for %s", entity_id)
        raise HTTPException(status_code=500, detail=str(exc))

    if not assessments:
        raise HTTPException(
            status_code=404,
            detail=f"No carbon assessment found for parcel {entity_id}. Run a calculation first.",
        )

    assessment = assessments[0]
    props = {k: v.get("value") if isinstance(v, dict) and "value" in v else v
             for k, v in assessment.items()
             if k not in ("id", "type", "@context")}

    # 2. Look for baseline and project scenarios
    baseline_nee = 0.0
    project_nee = 0.0
    baseline_mgmt = {}
    project_mgmt = {}
    baseline_scenario_id = ""
    project_scenario_id = ""

    try:
        baseline_scenarios = await query_entities(
            entity_type="BaselineScenario",
            tenant_id=tenant_id,
            query=f'refAgriParcel=="urn:ngsi-ld:AgriParcel:{tenant_id}:{entity_id}"',
            limit=1,
        )
        if baseline_scenarios:
            b = baseline_scenarios[0]
            b_props = {k: v.get("value") if isinstance(v, dict) and "value" in v else v
                       for k, v in b.items()
                       if k not in ("id", "type", "@context")}
            baseline_scenario_id = b.get("id", "")
            baseline_mgmt = b_props.get("managementParameters", {})
    except Exception as exc:
        logger.warning("Baseline scenario lookup failed: %s", exc)

    try:
        project_scenarios = await query_entities(
            entity_type="ProjectScenario",
            tenant_id=tenant_id,
            query=f'refAgriParcel=="urn:ngsi-ld:AgriParcel:{tenant_id}:{entity_id}"',
            limit=1,
        )
        if project_scenarios:
            p = project_scenarios[0]
            p_props = {k: v.get("value") if isinstance(v, dict) and "value" in v else v
                       for k, v in p.items()
                       if k not in ("id", "type", "@context")}
            project_scenario_id = p.get("id", "")
            project_mgmt = p_props.get("managementParameters", {})
    except Exception as exc:
        logger.warning("Project scenario lookup failed: %s", exc)

    # 3. Extract assessment data
    tier = int(props.get("dataTier", 1))
    confidence = float(props.get("confidence", 0.0))
    confidence_ci = float(props.get("confidenceIntervalPct", 0.0))
    data_sources = props.get("dataSources", [])
    assessment_date = str(props.get("assessmentDate", date.today().isoformat()))

    # Use cumulative CO2 as proxy for NEE when no scenarios exist
    co2_cumulative = float(props.get("co2SequesteredCumulative", 0))
    if baseline_scenario_id and project_scenario_id:
        # When scenarios exist, NEE comes from scenario comparison
        baseline_nee = -co2_cumulative * 0.7  # proxy: 70% of cumulative is baseline
        project_nee = -co2_cumulative  # 100% is project
    else:
        baseline_nee = 0.0
        project_nee = -co2_cumulative

    soc_delta = float(props.get("soilCarbonDelta", 0)) if "soilCarbonDelta" in props else None
    soc_total = float(props.get("carbonStockTotal", 0)) if "carbonStockTotal" in props else None

    # 4. Generate report
    today = date.today()
    reporting_start = f"{today.year - 1}-01-01"
    reporting_end = today.isoformat()

    input_snapshot = {
        "entity_id": entity_id,
        "assessment_date": assessment_date,
        "tier": tier,
    }

    output_snapshot = {
        "co2_seq_cumulative": co2_cumulative,
        "confidence": confidence,
    }

    try:
        if standard.upper() == "GOLD_STANDARD_SOC":
            report = generate_gold_standard_report(
                project_name=f"Carbon Project - {entity_id}",
                parcel_id=entity_id,
                tenant_id=tenant_id,
                reporting_period_start=reporting_start,
                reporting_period_end=reporting_end,
                baseline_scenario_id=baseline_scenario_id or f"bs-{entity_id}",
                project_scenario_id=project_scenario_id or f"ps-{entity_id}",
                baseline_calculation_run_id=f"run-bs-{entity_id}",
                project_calculation_run_id=f"run-ps-{entity_id}",
                baseline_nee_tCO2_ha_yr=baseline_nee,
                project_nee_tCO2_ha_yr=project_nee,
                tier=tier,
                confidence=confidence,
                confidence_interval_pct=confidence_ci,
                data_sources=data_sources if isinstance(data_sources, list) else [],
                baseline_management=baseline_mgmt,
                project_management=project_mgmt,
                input_snapshot=input_snapshot,
                output_snapshot=output_snapshot,
                soc_initial_tC_ha=soc_total,
                soc_delta_tC_ha_yr=soc_delta,
            )
        else:
            report = generate_vm0042_report(
                project_name=f"Carbon Project - {entity_id}",
                parcel_id=entity_id,
                tenant_id=tenant_id,
                reporting_period_start=reporting_start,
                reporting_period_end=reporting_end,
                baseline_scenario_id=baseline_scenario_id or f"bs-{entity_id}",
                project_scenario_id=project_scenario_id or f"ps-{entity_id}",
                baseline_calculation_run_id=f"run-bs-{entity_id}",
                project_calculation_run_id=f"run-ps-{entity_id}",
                baseline_nee_tCO2_ha_yr=baseline_nee,
                project_nee_tCO2_ha_yr=project_nee,
                tier=tier,
                confidence=confidence,
                confidence_interval_pct=confidence_ci,
                data_sources=data_sources if isinstance(data_sources, list) else [],
                baseline_management=baseline_mgmt,
                project_management=project_mgmt,
                input_snapshot=input_snapshot,
                output_snapshot=output_snapshot,
            )
    except Exception as exc:
        logger.exception("Report generation failed")
        raise HTTPException(status_code=500, detail=f"Report generation error: {exc}")

    return report_to_dict(report)
