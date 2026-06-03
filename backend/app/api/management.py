"""Management input CRUD endpoints.

Mount at /api/carbon (handled by main.py include_router).

Stores management data in-memory for now. Phase 6 will add
Orion-LD persistence via a dedicated ManagementPractice entity type.

Endpoints:
  POST   /parcels/{entity_id}/management   — Save management data
  GET    /parcels/{entity_id}/management    — Get current management data
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.common.auth import AuthContext, require_auth
from app.models.management import ManagementInput

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/carbon", tags=["management"])


@router.post(
    "/parcels/{entity_id}/management",
    response_model=ManagementInput,
    status_code=201,
)
async def save_management(
    entity_id: str,
    body: ManagementInput,
    auth: AuthContext = require_auth(),
):
    """Save farmer-declared management practices for a parcel.

    Persists as an NGSI-LD entity in Orion-LD so data survives pod restarts.
    """
    tenant_id = auth.tenant_id
    from app.common.orion import get_orion_client
    from app.ngsild.entities import build_management_practice

    entity = build_management_practice(
        tenant_id=tenant_id,
        parcel_id=entity_id,
        practices=body.model_dump(),
    )
    orion = get_orion_client()
    await orion.upsert_entity(entity, tenant_id)
    logger.info(
        "Management saved for tenant=%s parcel=%s tillage=%s",
        tenant_id, entity_id, body.tillage_type,
    )
    return body


@router.get(
    "/parcels/{entity_id}/management",
    response_model=ManagementInput,
    responses={404: {"model": dict}},
)
async def get_management(
    entity_id: str,
    auth: AuthContext = require_auth(),
):
    """Get the currently stored management data for a parcel from Orion-LD.

    Returns 404 if no management data has been saved yet.
    """
    tenant_id = auth.tenant_id
    from app.common.orion import get_orion_client

    mgmt_id = f"urn:ngsi-ld:ManagementPractice:{tenant_id}:{entity_id}"
    orion = get_orion_client()
    entity = await orion.get_entity(mgmt_id, tenant_id)
    if entity is None:
        raise HTTPException(
            status_code=404,
            detail=f"No management data found for parcel {entity_id}",
        )
    return _entity_to_management_input(entity)


def _entity_to_management_input(entity: dict) -> ManagementInput:
    """Convert NGSI-LD entity to ManagementInput model."""
    props = {k: v.get("value") if isinstance(v, dict) and "value" in v else v
             for k, v in entity.items()
             if k not in ("id", "type", "@context", "refAgriParcel",
                          "lastUpdated", "source")}
    return ManagementInput(**props)
