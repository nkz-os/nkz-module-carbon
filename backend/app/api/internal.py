"""
Internal endpoints for carbon module: health probes and DataHub Arrow IPC adapter.

Health:
  GET /health    — Basic health check
  GET /healthz   — K8s liveness probe (always 200 while process alive)
  GET /readyz    — K8s readiness probe (checks Orion-LD connectivity)

Arrow IPC:
  POST /api/internal/timeseries/export-arrow
      Stub returning empty Arrow IPC stream until carbon_readings
      table is created. DataHub BFF handles empty gracefully.
"""

import logging

import pyarrow as pa
import pyarrow.ipc
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List

from app.common.orion import get_orion_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["internal"])

ARROW_MIME = "application/vnd.apache.arrow.stream"


# ---------------------------------------------------------------------------
# Health probes
# ---------------------------------------------------------------------------


@router.get("/health")
async def health():
    """Basic health check."""
    return {"status": "healthy", "module": "carbon", "version": "0.1.0"}


@router.get("/healthz")
async def healthz():
    """K8s liveness probe — minimal, always returns 200 if process is alive."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz():
    """K8s readiness probe — checks Orion-LD connectivity."""
    try:
        orion = get_orion_client()
        await orion.query_entities(
            entity_type="AgriParcel",
            tenant_id="default",
            limit=1,
        )
        return {"status": "ready", "orion_ld": "connected"}
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Orion-LD not reachable: {exc}",
        )


# ---------------------------------------------------------------------------
# Arrow IPC adapter (stub — real data once carbon_readings table exists)
# ---------------------------------------------------------------------------

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
