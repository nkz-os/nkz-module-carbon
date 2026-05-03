"""Arrow IPC timeseries endpoints for DataHub integration.

Provides two endpoints:

  GET /api/carbon/timeseries/entities/{entity_id}/data
      Arrow IPC stream for a single entity's carbon time series.

  POST /api/carbon/timeseries/internal/export-arrow
      Multi-series Arrow export used by DataHub scatter-gather.
      Replaces the stub in internal.py once carbon readings are available.

Both return `application/vnd.apache.arrow.stream` media type.
"""

import io
import logging
from datetime import date, datetime, timezone
from typing import Optional

import pyarrow as pa
import pyarrow.ipc
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

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


class SeriesRequest(BaseModel):
    """Single time series request in a multi-export."""
    entity_id: str
    attribute: str


class ArrowExportRequest(BaseModel):
    """Multi-series export request body."""
    series: list[SeriesRequest]
    start_time: str
    end_time: str
    resolution: int = 1000


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


def _get_tenant_id(
    ngsild_tenant: str = Header(default="", alias="NGSILD-Tenant"),
) -> str:
    if not ngsild_tenant:
        raise HTTPException(status_code=400, detail="NGSILD-Tenant header is required")
    return ngsild_tenant


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
    tenant_id: str = Depends(_get_tenant_id),
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


@router.post(
    "/timeseries/internal/export-arrow",
    responses={
        200: {"content": {ARROW_MIME: {}}},
    },
    include_in_schema=False,  # Internal: not shown in public docs
)
async def export_arrow(body: ArrowExportRequest):
    """Multi-series Arrow export for DataHub scatter-gather.

    Replaces the legacy internal.py stub when carbon_readings table
    is available. Currently returns empty Arrow tables.
    """
    # TODO: Replace with real DB-backed multi-series query once
    #       carbon_readings table is populated.
    return Response(content=_empty_arrow(), media_type=ARROW_MIME)
