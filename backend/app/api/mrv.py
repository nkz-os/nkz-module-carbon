"""Monitoring report over stored campaigns (not a certification)."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.common.auth import AuthContext, require_auth
from app.platform.errors import SourceUnavailable
from app.services.campaign_runner import monitoring_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/carbon/parcels/{entity_id}/mrv", tags=["MRV"])

STANDARDS = ("VM0042", "GOLD_STANDARD_SOC")


@router.get("/report")
async def get_mrv_report(
    entity_id: str,
    standard: str = "VM0042",
    from_year: Optional[int] = Query(default=None),
    to_year: Optional[int] = Query(default=None),
    auth: AuthContext = require_auth(),
):
    """Monitoring estimate for the campaigns in [from_year, to_year] (default: the latest).

    ``standard`` only selects the report structure; the result is never a certified figure.
    """
    if standard.upper() not in STANDARDS:
        raise HTTPException(status_code=422, detail=f"standard must be one of {', '.join(STANDARDS)}")
    try:
        return await monitoring_report(auth.tenant_id, entity_id, standard.upper(), from_year, to_year)
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail={"error": "source_unavailable", "detail": str(exc)})
