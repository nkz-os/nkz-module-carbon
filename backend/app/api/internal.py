"""
Internal endpoints for carbon module: health probes, DataHub Arrow IPC adapter,
and module activation (setup-parcel).

Health:
  GET /health    — Basic health check
  GET /healthz   — K8s liveness probe (always 200 while process alive)
  GET /readyz    — K8s readiness probe (checks Orion-LD connectivity)

Module activation:
  POST /api/carbon/internal/setup-parcel
      Called by entity-manager when user activates the carbon module.
      Authenticated by X-Internal-Service-Secret (not JWT).

Arrow IPC:
  POST /api/internal/timeseries/export-arrow
      Stub returning empty Arrow IPC stream until carbon_readings
      table is created. DataHub BFF handles empty gracefully.
"""

import hmac
import logging
import os
from datetime import date

import pyarrow as pa
import pyarrow.ipc
from fastapi import APIRouter, BackgroundTasks, HTTPException, Header
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List

from app.common.orion import get_orion_client
from app.services.campaign_runner import run_campaign

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


# ---------------------------------------------------------------------------
# Module activation (entity-manager callback)
# ---------------------------------------------------------------------------


@router.post("/api/carbon/internal/setup-parcel")
async def setup_parcel(
    body: dict,
    background_tasks: BackgroundTasks,
    x_internal_secret: str = Header(default="", alias="X-Internal-Service-Secret"),
):
    """Activate carbon for a parcel: compute its current campaign in the background.

    Called by entity-manager when the module is activated on a parcel.
    Authenticated by X-Internal-Service-Secret (not JWT).

    Request body: { "parcel_id": "<AgriParcel id>", "tenant_id": "<tenant>", "action"?: "activate" }
    """
    internal_secret = os.getenv("INTERNAL_SERVICE_SECRET", "")
    if not internal_secret or not hmac.compare_digest(x_internal_secret, internal_secret):
        raise HTTPException(status_code=403, detail="Invalid internal secret")

    parcel_id = body.get("parcel_id", "")
    tenant_id = body.get("tenant_id", "")
    if not parcel_id or not tenant_id:
        raise HTTPException(status_code=400, detail="parcel_id and tenant_id required")

    action = body.get("action") or "activate"
    if action not in ("activate", "deactivate", "teardown"):
        raise HTTPException(status_code=400, detail="Invalid action")
    # Only activation computes; deactivating or deleting the parcel keeps its campaigns.
    if action != "activate":
        return {"status": action, "parcel_id": parcel_id, "tenant_id": tenant_id}

    async def _run():
        try:
            await run_campaign(tenant_id, parcel_id, date.today().year)
        except Exception as exc:  # noqa: BLE001 — the daily job retries
            logger.warning("setup-parcel campaign failed tenant=%s parcel=%s: %s", tenant_id, parcel_id, exc)

    background_tasks.add_task(_run)
    return {"status": "ok", "parcel_id": parcel_id, "tenant_id": tenant_id, "scheduled": True}
