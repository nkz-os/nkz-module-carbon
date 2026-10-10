"""Arrow IPC series for DataHub: one point per computed campaign.

  GET /api/carbon/timeseries/entities/{entity_id}/data?attribute=soilCarbonDelta

Float64 columns ``timestamp`` (Unix seconds of the campaign's computedThrough)
and ``value``. A campaign without the value is skipped, never sent as zero.
"""

import logging
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.ipc
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.common.auth import require_tenant_header
from app.models.schemas import ErrorResponse
from app.platform.errors import SourceUnavailable
from app.services.campaign_runner import list_campaigns

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/carbon", tags=["timeseries"])

ARROW_MIME = "application/vnd.apache.arrow.stream"

# API attribute name -> stored campaign field
ATTRIBUTES: dict[str, str] = {
    "co2SequesteredGross": "co2_sequestered_gross",
    "soilCarbonDelta": "soil_carbon_delta",
    "socEnd": "soc_end",
    "co2eqNet": "co2eq_net",
    "nppTotal": "npp_total",
    "gppTotal": "gpp_total",
}

_SCHEMA = pa.schema([
    pa.field("timestamp", pa.float64()),  # Unix SECONDS
    pa.field("value", pa.float64()),
])


@router.get(
    "/timeseries/entities/{entity_id}/data",
    responses={200: {"content": {ARROW_MIME: {}}}, 422: {"model": ErrorResponse}},
)
async def get_entity_timeseries(
    entity_id: str,
    attribute: str = Query(default="soilCarbonDelta", description="Campaign attribute"),
    tenant_id: str = Depends(require_tenant_header),
):
    field = ATTRIBUTES.get(attribute)
    if field is None:
        raise HTTPException(status_code=422, detail=f"attribute must be one of {', '.join(ATTRIBUTES)}")
    try:
        rows = await list_campaigns(tenant_id, entity_id)
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail={"error": "source_unavailable", "detail": str(exc)})
    stamps, values = [], []
    for r in rows:
        value, through = r.get(field), r.get("computed_through")
        if value is None or not through:
            continue
        stamps.append(datetime.fromisoformat(f"{through}T00:00:00").replace(tzinfo=timezone.utc).timestamp())
        values.append(float(value))
    table = pa.table({"timestamp": pa.array(stamps, type=pa.float64()),
                      "value": pa.array(values, type=pa.float64())}, schema=_SCHEMA)
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, _SCHEMA) as writer:
        writer.write_table(table)
    return Response(content=sink.getvalue().to_pybytes(), media_type=ARROW_MIME)
