"""NGSI-LD entity builders for VM0042 scenarios (spec 7.3)."""

import hashlib
import json
from datetime import datetime, timezone


def _context() -> list[str]:
    return ["https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"]


def hash_inputs(inputs: dict) -> str:
    """SHA-256 hash of inputs for audit trail."""
    canonical = json.dumps(inputs, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def build_baseline_scenario(
    tenant_id: str,
    parcel_id: str,
    valid_from: str,
    valid_to: str,
    management_params: dict,
    calculation_run_id: str,
) -> dict:
    """Build BaselineScenario entity."""
    scenario_id = f"urn:ngsi-ld:BaselineScenario:{tenant_id}:{parcel_id}"
    inputs_hash = hash_inputs(management_params)

    return {
        "id": scenario_id,
        "type": "BaselineScenario",
        "@context": _context(),
        "hasAgriParcel": {
            "type": "Relationship",
            "object": f"urn:ngsi-ld:AgriParcel:{tenant_id}:{parcel_id}",
        },
        "validFrom": {"type": "Property", "value": valid_from},
        "validTo": {"type": "Property", "value": valid_to},
        "inputsHash": {"type": "Property", "value": inputs_hash},
        "managementParameters": {"type": "Property", "value": management_params},
        "calculationRunId": {
            "type": "Relationship",
            "object": calculation_run_id,
        },
        "source": {"type": "Property", "value": "carbon"},
    }


def build_project_scenario(
    tenant_id: str,
    parcel_id: str,
    valid_from: str,
    valid_to: str,
    management_params: dict,
    calculation_run_id: str,
    baseline_scenario_id: str,
) -> dict:
    """Build ProjectScenario entity."""
    scenario_id = f"urn:ngsi-ld:ProjectScenario:{tenant_id}:{parcel_id}"
    inputs_hash = hash_inputs(management_params)

    return {
        "id": scenario_id,
        "type": "ProjectScenario",
        "@context": _context(),
        "hasAgriParcel": {
            "type": "Relationship",
            "object": f"urn:ngsi-ld:AgriParcel:{tenant_id}:{parcel_id}",
        },
        "validFrom": {"type": "Property", "value": valid_from},
        "validTo": {"type": "Property", "value": valid_to},
        "inputsHash": {"type": "Property", "value": inputs_hash},
        "managementParameters": {"type": "Property", "value": management_params},
        "calculationRunId": {
            "type": "Relationship",
            "object": calculation_run_id,
        },
        "baselineRef": {
            "type": "Relationship",
            "object": baseline_scenario_id,
        },
        "source": {"type": "Property", "value": "carbon"},
    }


def build_calculation_run(
    tenant_id: str,
    engine_version: str,
    tier: int,
    confidence: float,
    inputs_snapshot: dict,
    outputs: dict,
    uncertainty: dict | None = None,
) -> dict:
    """Build CarbonCalculationRun entity."""
    run_id = f"urn:ngsi-ld:CarbonCalculationRun:{tenant_id}:{hash_inputs(inputs_snapshot)}"
    now = datetime.now(timezone.utc).isoformat()

    entity = {
        "id": run_id,
        "type": "CarbonCalculationRun",
        "@context": _context(),
        "timestamp": {"type": "Property", "value": now},
        "engineVersion": {"type": "Property", "value": engine_version},
        "tier": {"type": "Property", "value": tier},
        "confidence": {"type": "Property", "value": confidence},
        "inputsSnapshot": {"type": "Property", "value": inputs_snapshot},
        "outputs": {"type": "Property", "value": outputs},
        "source": {"type": "Property", "value": "carbon"},
    }

    if uncertainty:
        entity["uncertaintyDistribution"] = {
            "type": "Property",
            "value": uncertainty,
        }

    return entity
