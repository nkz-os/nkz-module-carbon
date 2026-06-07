"""Baseline/Project scenario CRUD endpoints.

Mount at /api/carbon (handled by main.py include_router).

Scenarios persist to Orion-LD via the entity builders in
app.ngsild.scenarios. Calculation runs are returned from
the engine but also persisted as CarbonCalculationRun entities.

Endpoints:
  POST   /parcels/{entity_id}/scenarios/baseline            — Create baseline
  POST   /parcels/{entity_id}/scenarios/project             — Create project
  GET    /parcels/{entity_id}/scenarios                     — List all scenarios
  GET    /parcels/{entity_id}/scenarios/{scenario_id}       — Get single scenario
  GET    /parcels/{entity_id}/scenarios/{scenario_id}/calculation-runs  — List runs
  POST   /parcels/{entity_id}/scenarios/{scenario_id}/recalculate       — Re-run
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.common.auth import AuthContext, require_auth
from app.models.schemas import (
    CalculationRunResponse,
    CreateBaselineRequest,
    CreateProjectRequest,
    ScenarioResponse,
)
from app.services.carbon_engine import Tier1Input, calculate_tier1
from app.services.roth_c_model import init_pools_weihermuller, run_rothc_monthly
from app.common.orion import upsert_entity, query_entities, get_entity
from app.ngsild.scenarios import (
    build_baseline_scenario,
    build_project_scenario,
    build_calculation_run,
)
from app.db.database import insert_carbon_calculation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/carbon", tags=["scenarios"])


def _generate_scenario_id(prefix: str, tenant_id: str, parcel_id: str) -> str:
    """Generate a unique scenario entity ID."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"urn:ngsi-ld:{prefix}:{tenant_id}:{parcel_id}-{ts}"


# ---------------------------------------------------------------------------
# Create baseline scenario
# ---------------------------------------------------------------------------


@router.post(
    "/parcels/{entity_id}/scenarios/baseline",
    response_model=ScenarioResponse,
    status_code=201,
)
async def create_baseline(
    entity_id: str,
    body: CreateBaselineRequest,
    auth: AuthContext = require_auth(),
):
    """Create a baseline scenario for a parcel.

    A baseline scenario represents the "business as usual" management.
    It is persisted as a BaselineScenario NGSI-LD entity.
    """
    tenant_id = auth.tenant_id
    calculation_run_id = f"urn:ngsi-ld:CarbonCalculationRun:{tenant_id}:{entity_id}-baseline"

    entity = build_baseline_scenario(
        tenant_id=tenant_id,
        parcel_id=entity_id,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        management_params=body.management_params,
        calculation_run_id=calculation_run_id,
    )

    try:
        await upsert_entity(entity, tenant_id)
    except Exception as exc:
        logger.exception("Failed to persist baseline scenario")
        raise HTTPException(status_code=500, detail=f"Orion-LD persistence failed: {exc}")

    return ScenarioResponse(
        scenario_id=entity["id"],
        scenario_type="BaselineScenario",
        parcel_id=entity_id,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        management_params=body.management_params,
        calculation_run_id=calculation_run_id,
    )


# ---------------------------------------------------------------------------
# Create project scenario
# ---------------------------------------------------------------------------


@router.post(
    "/parcels/{entity_id}/scenarios/project",
    response_model=ScenarioResponse,
    status_code=201,
)
async def create_project(
    entity_id: str,
    body: CreateProjectRequest,
    auth: AuthContext = require_auth(),
):
    """Create a project scenario referencing a baseline.

    A project scenario represents a planned change in management
    (e.g., transition to no-till + cover crops). It references the
    baseline scenario via baseline_scenario_id.
    """
    tenant_id = auth.tenant_id
    # Verify baseline scenario exists
    if body.baseline_scenario_id:
        existing = await get_entity(body.baseline_scenario_id, tenant_id)
        if existing is None:
            raise HTTPException(
                status_code=404,
                detail=f"Baseline scenario {body.baseline_scenario_id} not found",
            )

    calculation_run_id = f"urn:ngsi-ld:CarbonCalculationRun:{tenant_id}:{entity_id}-project"

    entity = build_project_scenario(
        tenant_id=tenant_id,
        parcel_id=entity_id,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        management_params=body.management_params,
        calculation_run_id=calculation_run_id,
        baseline_scenario_id=body.baseline_scenario_id,
    )

    try:
        await upsert_entity(entity, tenant_id)
    except Exception as exc:
        logger.exception("Failed to persist project scenario")
        raise HTTPException(status_code=500, detail=f"Orion-LD persistence failed: {exc}")

    return ScenarioResponse(
        scenario_id=entity["id"],
        scenario_type="ProjectScenario",
        parcel_id=entity_id,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        management_params=body.management_params,
        calculation_run_id=calculation_run_id,
        baseline_scenario_id=body.baseline_scenario_id,
    )


# ---------------------------------------------------------------------------
# List scenarios
# ---------------------------------------------------------------------------


@router.get(
    "/parcels/{entity_id}/scenarios",
    response_model=list[ScenarioResponse],
)
async def list_scenarios(
    entity_id: str,
    auth: AuthContext = require_auth(),
):
    """List all scenarios (baseline + project) for a parcel."""
    tenant_id = auth.tenant_id
    scenario_types = ["BaselineScenario", "ProjectScenario"]
    all_scenarios: list[ScenarioResponse] = []

    for sc_type in scenario_types:
        try:
            results = await query_entities(
                entity_type=sc_type,
                tenant_id=tenant_id,
                query=f'hasAgriParcel=="urn:ngsi-ld:AgriParcel:{tenant_id}:{entity_id}"',
                limit=50,
            )
        except Exception as exc:
            logger.warning("Error querying %s scenarios: %s", sc_type, exc)
            continue

        for ent in results:
            props = {k: v.get("value") if isinstance(v, dict) and "value" in v else v
                     for k, v in ent.items()
                     if k not in ("id", "type", "@context", "hasAgriParcel")}
            all_scenarios.append(ScenarioResponse(
                scenario_id=ent["id"],
                scenario_type=sc_type,
                parcel_id=entity_id,
                valid_from=str(props.get("validFrom", "")),
                valid_to=str(props.get("validTo", "")),
                management_params=props.get("managementParameters", {}),
                calculation_run_id=props.get("calculationRunId", None),
                baseline_scenario_id=props.get("baselineRef", None),
            ))

    return all_scenarios


# ---------------------------------------------------------------------------
# Get single scenario
# ---------------------------------------------------------------------------


@router.get(
    "/parcels/{entity_id}/scenarios/{scenario_id}",
    response_model=ScenarioResponse,
    responses={404: {"model": dict}},
)
async def get_scenario(
    entity_id: str,
    scenario_id: str,
    auth: AuthContext = require_auth(),
):
    """Get a single scenario by entity ID."""
    tenant_id = auth.tenant_id
    try:
        entity = await get_entity(scenario_id, tenant_id)
    except Exception as exc:
        logger.exception("Error fetching scenario %s", scenario_id)
        raise HTTPException(status_code=500, detail=str(exc))

    if entity is None:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")

    sc_type = entity.get("type", "Unknown")
    props = {k: v.get("value") if isinstance(v, dict) and "value" in v else v
             for k, v in entity.items()
             if k not in ("id", "type", "@context", "hasAgriParcel")}

    return ScenarioResponse(
        scenario_id=entity["id"],
        scenario_type=sc_type,
        parcel_id=entity_id,
        valid_from=str(props.get("validFrom", "")),
        valid_to=str(props.get("validTo", "")),
        management_params=props.get("managementParameters", {}),
        calculation_run_id=props.get("calculationRunId", None),
        baseline_scenario_id=props.get("baselineRef", None),
    )


# ---------------------------------------------------------------------------
# List calculation runs for scenario
# ---------------------------------------------------------------------------


@router.get(
    "/parcels/{entity_id}/scenarios/{scenario_id}/calculation-runs",
    response_model=list[CalculationRunResponse],
)
async def list_calculation_runs(
    entity_id: str,
    scenario_id: str,
    auth: AuthContext = require_auth(),
):
    """List CarbonCalculationRun entities associated with a scenario."""
    tenant_id = auth.tenant_id
    try:
        results = await query_entities(
            entity_type="CarbonCalculationRun",
            tenant_id=tenant_id,
            limit=50,
        )
    except Exception as exc:
        logger.exception("Error querying calculation runs")
        raise HTTPException(status_code=500, detail=str(exc))

    runs = []
    for ent in results:
        props = {k: v.get("value") if isinstance(v, dict) and "value" in v else v
                 for k, v in ent.items()
                 if k not in ("id", "type", "@context")}
        runs.append(CalculationRunResponse(
            run_id=ent["id"],
            timestamp=str(props.get("timestamp", "")),
            tier=int(props.get("tier", 1)),
            confidence=float(props.get("confidence", 0.0)),
            engine_version=props.get("engineVersion", "0.1.0"),
            inputs_snapshot=props.get("inputsSnapshot", {}),
            outputs=props.get("outputs", {}),
            uncertainty=props.get("uncertaintyDistribution", None),
        ))

    return runs


# ---------------------------------------------------------------------------
# Recalculate for an existing scenario
# ---------------------------------------------------------------------------


@router.post(
    "/parcels/{entity_id}/scenarios/{scenario_id}/recalculate",
    response_model=CalculationRunResponse,
    status_code=201,
)
async def recalculate_scenario(
    entity_id: str,
    scenario_id: str,
    auth: AuthContext = require_auth(),
):
    """Re-run the carbon engine for an existing scenario.

    Fetches the scenario management params and runs Tier 1 calculation.
    The run is persisted as a CarbonCalculationRun entity.
    """
    tenant_id = auth.tenant_id
    # Fetch the scenario entity to get management params
    entity = await get_entity(scenario_id, tenant_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")

    props = {k: v.get("value") if isinstance(v, dict) and "value" in v else v
             for k, v in entity.items()
             if k not in ("id", "type", "@context", "hasAgriParcel")}
    management_params = props.get("managementParameters", {})

    # Run a quick Tier 1 calculation
    tier1_in = Tier1Input(
        par_MJ_m2_day=management_params.get("par", 15.0),
        fapar_frac=management_params.get("fapar", 0.5),
        lue_gC_per_MJ=management_params.get("lue", 2.0),
        root_fraction=management_params.get("root_fraction", 0.3),
        species=management_params.get("species", "unknown"),
    )
    tier1_out = calculate_tier1(tier1_in)

    outputs = {
        "gpp_tC_m2_day": tier1_out.gpp_gC_m2_day,
        "npp_tC_m2_day": tier1_out.npp_total_gC_m2_day,
        "co2_seq_kgCO2_ha_day": tier1_out.co2_seq_kgCO2_ha_day,
        "agb_dry_tDM_ha": tier1_out.agb_dry_tDM_ha,
        "bgb_dry_tDM_ha": tier1_out.bgb_dry_tDM_ha,
    }

    run_entity = build_calculation_run(
        tenant_id=tenant_id,
        engine_version="0.1.0",
        tier=1,
        confidence=0.85,
        inputs_snapshot=management_params,
        outputs=outputs,
    )

    try:
        await upsert_entity(run_entity, tenant_id)
    except Exception as exc:
        logger.warning("Failed to persist calculation run (non-fatal): %s", exc)

    return CalculationRunResponse(
        run_id=run_entity["id"],
        timestamp=run_entity.get("timestamp", {}).get("value", ""),
        tier=1,
        confidence=0.85,
        engine_version="0.1.0",
        inputs_snapshot=management_params,
        outputs=outputs,
    )
