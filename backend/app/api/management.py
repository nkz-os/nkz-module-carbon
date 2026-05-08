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

from fastapi import APIRouter, Depends, Header, HTTPException

from app.models.management import ManagementInput

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/carbon", tags=["management"])

# In-memory store: {tenant_id: {entity_id: ManagementInput}}
_management_store: dict[str, dict[str, ManagementInput]] = {}


def _get_tenant_id(ngsild_tenant: str = Header(default="", alias="NGSILD-Tenant")) -> str:
    if not ngsild_tenant:
        raise HTTPException(status_code=400, detail="NGSILD-Tenant header is required")
    from app.common.tenant_utils import normalize_tenant_id
    return normalize_tenant_id(ngsild_tenant)


@router.post(
    "/parcels/{entity_id}/management",
    response_model=ManagementInput,
    status_code=201,
)
async def save_management(
    entity_id: str,
    body: ManagementInput,
    tenant_id: str = Depends(_get_tenant_id),
):
    """Save farmer-declared management practices for a parcel.

    Replaces any previously stored management data for this
    tenant+parcel pair.
    """
    if tenant_id not in _management_store:
        _management_store[tenant_id] = {}
    _management_store[tenant_id][entity_id] = body
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
    tenant_id: str = Depends(_get_tenant_id),
):
    """Get the currently stored management data for a parcel.

    Returns 404 if no management data has been saved yet.
    """
    tenant_store = _management_store.get(tenant_id, {})
    if entity_id not in tenant_store:
        raise HTTPException(
            status_code=404,
            detail=f"No management data found for parcel {entity_id}",
        )
    return tenant_store[entity_id]
