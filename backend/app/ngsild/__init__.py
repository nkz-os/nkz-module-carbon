"""NGSI-LD client and entity builder package for the NKZ Carbon Module."""

__all__ = [
    "upsert_entity",
    "query_entities",
    "get_entity",
    "build_carbon_assessment",
    "build_carbon_stock",
    "build_baseline_scenario",
    "build_project_scenario",
    "build_calculation_run",
    "ORION_URL",
    "CONTEXT_URL",
    "NGSI_LD_CONTEXT",
]

from .client import (
    ORION_URL,
    CONTEXT_URL,
    NGSI_LD_CONTEXT,
    upsert_entity,
    query_entities,
    get_entity,
)
from .entities import build_carbon_assessment, build_carbon_stock
from .scenarios import (
    build_baseline_scenario,
    build_project_scenario,
    build_calculation_run,
)
