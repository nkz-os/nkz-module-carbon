"""
Internal Arrow IPC adapter for DataHub scatter-gather.

Mirrors the contract defined in ADAPTER_SPEC.md:
  POST /api/internal/timeseries/export-arrow
  Response: Arrow IPC stream, timestamp in Float64 Unix SECONDS.

Attributes served:
  carbonFixationRateDaily   → daily GPP  [gC/m²]
  co2SequesteredCumulative  → cumulative CO2 [kgCO2]
  gppDaily                  → same as carbonFixationRateDaily (alias)
  nppDaily                  → net primary production [gC/m²]
"""

import io
import logging
from datetime import datetime, timezone
from typing import List

import pyarrow as pa
import pyarrow.ipc
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["internal"])

ARROW_MIME = "application/vnd.apache.arrow.stream"

# TODO: replace with real carbon_readings table once DB schema is defined.
# Placeholder — returns empty series until table exists.
ATTRIBUTE_TO_COLUMN: dict[str, str] = {
    "carbonFixationRateDaily":  "gpp",
    "gppDaily":                 "gpp",
    "nppDaily":                 "npp",
    "co2SequesteredCumulative": "co2_cumulative",
}


class SeriesRequest(BaseModel):
    entity_id: str
    attribute: str


class ArrowExportRequest(BaseModel):
    series: List[SeriesRequest]
    start_time: str
    end_time: str
    resolution: int = 1000


@router.post("/api/internal/timeseries/export-arrow")
async def export_arrow(body: ArrowExportRequest):
    """
    Stub — returns empty Arrow tables until the carbon_readings table is created.
    Replace the placeholder query below with real DB access once migrations run.
    """
    # Empty table with correct schema (DataHub BFF handles empty gracefully)
    schema = pa.schema([
        pa.field("timestamp", pa.float64()),
        pa.field("value",     pa.float64()),
    ])
    table = pa.table(
        {"timestamp": pa.array([], type=pa.float64()),
         "value":     pa.array([], type=pa.float64())},
        schema=schema,
    )
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, schema) as writer:
        writer.write_table(table)
    return Response(content=sink.getvalue().to_pybytes(), media_type=ARROW_MIME)
