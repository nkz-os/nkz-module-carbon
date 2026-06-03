"""Arrow IPC timeseries endpoints for DataHub integration.

Provides:

  GET /api/carbon/timeseries/entities/{entity_id}/data
      Arrow IPC stream for a single entity's carbon time series.

Returns `application/vnd.apache.arrow.stream` media type.
"""

import io
import logging
from datetime import date, datetime, timezone
from typing import Optional

import pyarrow as pa
import pyarrow.ipc
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.common.auth import require_tenant_header
from app.models.schemas import ErrorResponse
from app.ngsild.client import query_entities

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/carbon", tags=["timeseries"])

ARROW_MIME = "application/vnd.apache.arrow.stream"

# Attribute mapping: API name → column name in Arrow table
ATTRIBUTE_TO_COLUMN: dict[str, str] = {
    "carbonFixationRateDaily": "gpp",
    "gppDaily": "gpp",
    "nppDaily": "npp",
    "co2SequesteredDaily": "co2_daily",
    "co2SequesteredCumulative": "co2_cumulative",
    "agbDry": "agb",
    "bgbDry": "bgb",
    "soilCarbonDelta": "soc_delta",
    "co2eqNetDaily": "co2eq_net_daily",
    "co2eqNetCumulative": "co2eq_net_cumulative",
}


# Schema for single-series Arrow output
_SERIES_SCHEMA = pa.schema([
    pa.field("timestamp", pa.float64()),  # Unix SECONDS
    pa.field("value", pa.float64()),
])


async def _entity_assessments_to_arrow(
    entity_id: str,
    tenant_id: str,
    attribute: str = "gppDaily",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
) -> pa.Table:
    """Fetch CarbonAssessment entities from Orion-LD and build an Arrow table."""
    try:
        results = await query_entities(
            entity_type="CarbonAssessment",
            tenant_id=tenant_id,
            query=f'refAgriParcel=="urn:ngsi-ld:AgriParcel:{tenant_id}:{entity_id}"',
            limit=limit,
        )
    except Exception as exc:
        logger.warning("Orion-LD query failed for %s: %s", entity_id, exc)
        results = []

    timestamps: list[float] = []
    values: list[float] = []

    for ent in results:
        props = {k: v.get("value") if isinstance(v, dict) and "value" in v else v
                 for k, v in ent.items()
                 if k not in ("id", "type", "@context")}

        date_str = props.get("assessmentDate", "")
        if date_str:
            try:
                dt = datetime.fromisoformat(date_str)
                timestamps.append(dt.timestamp())
            except (ValueError, TypeError):
                timestamps.append(0.0)
        else:
            timestamps.append(0.0)

        val = props.get(attribute, 0.0)
        try:
            values.append(float(val))
        except (ValueError, TypeError):
            values.append(0.0)

    return pa.table(
        {"timestamp": pa.array(timestamps, type=pa.float64()),
         "value": pa.array(values, type=pa.float64())},
        schema=_SERIES_SCHEMA,
    )


def _empty_arrow() -> bytes:
    """Return an empty Arrow IPC stream with the correct schema."""
    table = pa.table(
        {"timestamp": pa.array([], type=pa.float64()),
         "value": pa.array([], type=pa.float64())},
        schema=_SERIES_SCHEMA,
    )
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, _SERIES_SCHEMA) as writer:
        writer.write_table(table)
    return sink.getvalue().to_pybytes()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/timeseries/entities/{entity_id}/data",
    responses={
        200: {"content": {ARROW_MIME: {}}},
        404: {"model": ErrorResponse},
    },
)
async def get_entity_timeseries(
    entity_id: str,
    attribute: str = Query(default="gppDaily", description="Attribute name"),
    tenant_id: str = require_tenant_header,
    limit: int = Query(default=100, ge=1, le=1000),
):
    """Arrow IPC stream of time-series data for a single entity.

    Returns an Arrow IPC stream (application/vnd.apache.arrow.stream)
    with Float64 columns: timestamp (Unix seconds), value.
    """
    try:
        arrow_bytes = await _entity_assessments_to_arrow(
            entity_id=entity_id,
            tenant_id=tenant_id,
            attribute=attribute,
            limit=limit,
        )
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, _SERIES_SCHEMA) as writer:
            writer.write_table(arrow_bytes)
        return Response(content=sink.getvalue().to_pybytes(), media_type=ARROW_MIME)
    except Exception as exc:
        logger.exception("Error building Arrow stream for %s", entity_id)
        return Response(content=_empty_arrow(), media_type=ARROW_MIME)



