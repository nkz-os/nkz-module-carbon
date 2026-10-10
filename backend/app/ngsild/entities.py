"""NGSI-LD context helper and the ManagementPractice builder.

Per-campaign CarbonAssessment/CarbonStock live in campaign_entities.py.
"""

from datetime import datetime, timezone

from app.ngsild import CONTEXT_URL

NGSI_LD_CONTEXT = [
    "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
    CONTEXT_URL,
]


def _context() -> list[str]:
    return list(NGSI_LD_CONTEXT)


def build_management_practice(
    tenant_id: str,
    parcel_id: str,
    practices: dict,
) -> dict:
    """Build a ManagementPractice NGSI-LD entity for persisting farmer input."""
    entity_id = f"urn:ngsi-ld:ManagementPractice:{tenant_id}:{parcel_id}"

    entity = {
        "id": entity_id,
        "type": "ManagementPractice",
        "@context": _context(),
        "hasAgriParcel": {
            "type": "Relationship",
            "object": f"urn:ngsi-ld:AgriParcel:{tenant_id}:{parcel_id}",
        },
        "lastUpdated": {
            "type": "Property",
            "value": datetime.now(timezone.utc).isoformat(),
        },
        "source": {"type": "Property", "value": "carbon"},
    }

    # Map all practice fields to NGSI-LD properties
    for key, value in practices.items():
        if value is not None:
            entity[key] = {"type": "Property", "value": value}

    return entity
