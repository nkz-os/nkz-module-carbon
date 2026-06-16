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

import logging
import os

import pyarrow as pa
import pyarrow.ipc
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List

from app.common.orion import get_orion_client
from app.ngsild.entities import build_carbon_stock
from app.services.roth_c_model import init_pools_weihermuller
from app.platform.soil_client import fetch_parcel_soil

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
    x_internal_secret: str = Header(default="", alias="X-Internal-Service-Secret"),
):
    """Activate carbon module for a parcel.

    Called by entity-manager when user activates the carbon module.
    Creates initial CarbonStock entity with SOC data from Orion-LD
    (AgriSoilExtended) or SoilGrids defaults.

    Request body:
        { "parcel_id": "urn:ngsi-ld:AgriParcel:{tenant}:{id}",
          "tenant_id": "tenant_name" }
    """
    internal_secret = os.getenv("INTERNAL_SERVICE_SECRET", "")
    if not x_internal_secret or x_internal_secret != internal_secret:
        raise HTTPException(status_code=403, detail="Invalid internal secret")

    parcel_id = body.get("parcel_id", "")
    tenant_id = body.get("tenant_id", "")

    if not parcel_id or not tenant_id:
        raise HTTPException(status_code=400, detail="parcel_id and tenant_id required")

    # Extract short parcel ID from URN
    short_id = parcel_id.split(":")[-1] if ":" in parcel_id else parcel_id

    # Fetch real soil data from Orion-LD, fall back to defaults
    soil = await fetch_parcel_soil(short_id, tenant_id)
    pools = init_pools_weihermuller(soil.soc_tC_ha, soil.clay_pct)

    stock_entity = build_carbon_stock(
        tenant_id=tenant_id,
        parcel_id=short_id,
        pools=pools.to_dict(),
        total_soc=pools.total_tC_ha,
    )

    from app.common.orion import upsert_entity
    await upsert_entity(stock_entity, tenant_id)

    return {
        "status": "ok",
        "parcel_id": parcel_id,
        "tenant_id": tenant_id,
        "initial_soc_tC_ha": round(pools.total_tC_ha, 2),
        "soil_source": soil.source,
    }
