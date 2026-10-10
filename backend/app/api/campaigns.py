"""Per-campaign carbon balance.

  GET  /api/carbon/parcels/{entity_id}/campaigns                    stored campaigns
  GET  /api/carbon/parcels/{entity_id}/campaigns/{year}             one stored campaign
  POST /api/carbon/parcels/{entity_id}/campaigns/{year}/calculate   (re)compute one campaign
  POST /api/carbon/internal/campaigns/recalculate-open              daily job, internal secret only
"""

import asyncio
import hmac
import logging
import os
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException

from app.common.auth import AuthContext, require_auth
from app.common.orion import get_orion_client
from app.common.tier_check import check_tier
from app.db.database import list_tenants_with_module
from app.platform.crop_client import canonical_parcel_urn
from app.platform.errors import SourceUnavailable
from app.ngsild.campaign_entities import stock_state
from app.services.campaign_runner import get_campaign, get_campaign_stock, list_campaigns, run_campaign

logger = logging.getLogger(__name__)

router = APIRouter(tags=["campaigns"])

INTERNAL_SERVICE_SECRET = os.getenv("INTERNAL_SERVICE_SECRET", "")
_RECALC_CONCURRENCY = 2


async def _row_with_pools(tenant_id: str, entity_id: str, year: int) -> dict | None:
    row = await get_campaign(tenant_id, entity_id, year)
    if row is None:
        return None
    stock = await get_campaign_stock(tenant_id, entity_id, year)
    if stock:
        state, when = stock_state(stock)
        row["pools_end"], row["pools_state_date"] = state.pools.to_dict(), when.isoformat()
    else:
        row["pools_end"], row["pools_state_date"] = None, None
    return row


def _unavailable(exc: SourceUnavailable) -> HTTPException:
    return HTTPException(status_code=503, detail={"error": "source_unavailable", "detail": str(exc)})


@router.get("/api/carbon/parcels/{entity_id}/campaigns")
async def get_campaigns(entity_id: str, auth: AuthContext = require_auth()):
    try:
        rows = await list_campaigns(auth.tenant_id, entity_id)
    except SourceUnavailable as exc:
        raise _unavailable(exc)
    return {"parcel_id": canonical_parcel_urn(entity_id), "campaigns": rows}


@router.get("/api/carbon/parcels/{entity_id}/campaigns/{year}")
async def get_one_campaign(entity_id: str, year: int, auth: AuthContext = require_auth()):
    try:
        row = await _row_with_pools(auth.tenant_id, entity_id, year)
    except SourceUnavailable as exc:
        raise _unavailable(exc)
    if row is None:
        raise HTTPException(status_code=404, detail=f"campaign {year} not computed for this parcel")
    return row


@router.post("/api/carbon/parcels/{entity_id}/campaigns/{year}/calculate")
async def calculate_campaign(
    entity_id: str,
    year: int,
    auth: AuthContext = require_auth(),
    _tier_ok: None = Depends(check_tier),
):
    try:
        await run_campaign(auth.tenant_id, entity_id, year)
        row = await _row_with_pools(auth.tenant_id, entity_id, year)
    except SourceUnavailable as exc:
        raise _unavailable(exc)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if row is None:  # written a moment ago: a broker that loses it is a broker fault
        raise HTTPException(status_code=503, detail={"error": "source_unavailable", "detail": "result not readable"})
    return row


async def list_parcel_ids(tenant_id: str) -> list[str]:
    """Every AgriParcel id of the tenant (paged; no attrs filter, which hides entities)."""
    orion = get_orion_client()
    ids, offset = [], 0
    while True:
        page = await orion.query_entities(entity_type="AgriParcel", tenant_id=tenant_id, limit=100, offset=offset)
        ids.extend(e["id"] for e in page or [])
        if not page or len(page) < 100:
            return ids
        offset += 100


@router.post("/api/carbon/internal/campaigns/recalculate-open")
async def recalculate_open(x_internal_service_secret: str = Header(default="", alias="X-Internal-Service-Secret")):
    if not INTERNAL_SERVICE_SECRET or not hmac.compare_digest(x_internal_service_secret, INTERNAL_SERVICE_SECRET):
        raise HTTPException(status_code=401, detail="invalid internal secret")
    year = date.today().year
    tenants = await list_tenants_with_module("carbon")
    sem = asyncio.Semaphore(_RECALC_CONCURRENCY)
    counts = {"tenants": len(tenants), "parcels": 0, "ok": 0, "failed": 0}

    async def one(tenant_id: str, parcel_id: str):
        async with sem:
            try:
                await run_campaign(tenant_id, parcel_id, year, cascade=False)
                counts["ok"] += 1
            except Exception as exc:  # noqa: BLE001 — one parcel must not stop the sweep
                counts["failed"] += 1
                logger.warning("carbon recalc failed tenant=%s parcel=%s: %s", tenant_id, parcel_id, exc)

    for tenant_id in tenants:
        try:
            parcels = await list_parcel_ids(tenant_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("carbon recalc: parcels unavailable tenant=%s: %s", tenant_id, exc)
            continue
        counts["parcels"] += len(parcels)
        await asyncio.gather(*(one(tenant_id, p) for p in parcels))
    logger.info("carbon recalc done %s", counts)
    return counts
