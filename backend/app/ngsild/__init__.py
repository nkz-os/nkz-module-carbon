"""NGSI-LD entity builder package for the NKZ Carbon Module."""

import os

__all__ = [
    "build_carbon_assessment",
    "build_carbon_stock",
    "build_baseline_scenario",
    "build_project_scenario",
    "build_calculation_run",
    "build_management_practice",
    "ORION_URL",
    "CONTEXT_URL",
    "NGSI_LD_CONTEXT",
]

# Legacy URL constants — imported by platform clients
ORION_URL = os.getenv("FIWARE_CONTEXT_BROKER_URL", "http://orion-ld-service:1026")
CONTEXT_URL = os.getenv("CONTEXT_URL", "http://api-gateway-service:5000/ngsi-ld-context.json")
NGSI_LD_CONTEXT = [
    "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
    CONTEXT_URL,
]

from .entities import build_carbon_assessment, build_carbon_stock, build_management_practice
from .scenarios import (
    build_baseline_scenario,
    build_project_scenario,
    build_calculation_run,
)
