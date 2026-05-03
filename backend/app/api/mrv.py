"""MRV report API endpoints."""

from fastapi import APIRouter, HTTPException, Header

from app.services.mrv_reporter import (
    generate_vm0042_report,
    generate_gold_standard_report,
    report_to_dict,
)
from app.models.schemas import ErrorResponse

router = APIRouter(prefix="/parcels/{entity_id}/mrv", tags=["MRV"])


@router.get("/report")
async def get_mrv_report(
    entity_id: str,
    standard: str = "VM0042",
    tenant: str = Header(..., alias="NGSILD-Tenant"),
):
    """Generate MRV report for a parcel. Currently returns template.

    Full implementation requires baseline/project scenarios to exist.
    """
    # TODO Phase 6: load actual scenarios from Orion-LD
    raise HTTPException(
        status_code=501,
        detail="MRV report generation requires baseline/project scenarios. Complete Phase 6 integration first.",
    )
