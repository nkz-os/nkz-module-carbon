"""Carbon projection, tenant summary and sensor listing.

Mount at /api/carbon (handled by main.py include_router).

Endpoints:
  GET    /parcels/{entity_id}/projection           — SOC projection from stored campaigns
  GET    /sensors/available                        — List tenant AgriSensors
  GET    /tenant/summary                           — Carbon by campaign across parcels

The per-campaign balance lives in app/api/campaigns.py.
"""

import asyncio
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.common.auth import AuthContext, require_auth
from app.common.orion import get_orion_client
from app.models.schemas import (
    ErrorResponse,
    ParcelSummary,
    ProjectionResponse,
    SensorInfo,
    TierSummaryResponse,
    YearlyAggregation,
)
from app.platform.errors import SourceUnavailable
from app.platform.weather_client import list_tenant_sensors
from app.services.campaign_runner import list_campaigns, projection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/carbon", tags=["assessments"])


@router.get(
    "/parcels/{entity_id}/projection",
    response_model=ProjectionResponse,
    responses={503: {"model": ErrorResponse}},
)
async def get_projection(
    entity_id: str,
    years: int = Query(default=20, ge=1, le=50),
    auth: AuthContext = require_auth(),
):
    """SOC projection from the last complete campaign (its climate and management repeated).

    With a baseline scenario, its reference campaign is replayed under the same climate.
    Without a complete campaign the lists are empty and ``missing`` says why.
    """
    try:
        return await projection(auth.tenant_id, entity_id, years)
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail={"error": "source_unavailable", "detail": str(exc)})


# ---------------------------------------------------------------------------
# Sensor listing
# ---------------------------------------------------------------------------


@router.get(
    "/sensors/available",
    response_model=list[SensorInfo],
)
async def list_sensors(
    auth: AuthContext = require_auth(),
):
    """List tenant's AgriSensor entities available as weather data sources."""
    tenant_id = auth.tenant_id
    sensors = await list_tenant_sensors(tenant_id)
    return [
        SensorInfo(
            id=s["id"],
            name=s["name"],
            sensor_type=s.get("sensor_type", ""),
            latitude=s.get("latitude"),
            longitude=s.get("longitude"),
        )
        for s in sensors
    ]


# ---------------------------------------------------------------------------
# Multi-parcel summary
# ---------------------------------------------------------------------------


@router.get(
    "/tenant/summary",
    response_model=TierSummaryResponse,
)
async def get_tenant_summary(
    year: Optional[int] = Query(default=None),
    auth: AuthContext = require_auth(),
):
    """Carbon by campaign across the tenant's parcels (default: the current campaign)."""
    tenant_id = auth.tenant_id
    year = year or date.today().year
    try:
        parcels = await _tenant_parcels(tenant_id)
        sem = asyncio.Semaphore(10)

        async def campaigns_of(pid: str):
            async with sem:
                return await list_campaigns(tenant_id, pid)

        all_rows = await asyncio.gather(*(campaigns_of(p["id"]) for p in parcels))
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail={"error": "source_unavailable", "detail": str(exc)})
    except Exception as exc:  # noqa: BLE001
        logger.exception("summary failed tenant=%s", tenant_id)
        raise HTTPException(status_code=503, detail={"error": "source_unavailable", "detail": str(exc)})

    summary: list[ParcelSummary] = []
    by_year: dict[int, list[dict]] = {}
    for parcel, rows in zip(parcels, all_rows):
        short = parcel["id"].rsplit(":", 1)[-1]
        for r in rows:
            by_year.setdefault(r["campaign_label"], []).append(r)
        row = next((r for r in rows if r["campaign_label"] == year), None)
        cycles = (row or {}).get("cycle_breakdown") or []
        summary.append(ParcelSummary(
            parcel_id=short,
            parcel_name=_extract_ngsild_value(parcel, "name", short),
            crop_species=str(cycles[0].get("species") or "") if cycles else "",
            campaign_year=year if row else None,
            computed_through=(row or {}).get("computed_through"),
            tier=int((row or {}).get("data_tier") or 0),
            co2_gross_tCO2_ha=(row or {}).get("co2_sequestered_gross"),
            delta_soc_tC_ha=(row or {}).get("soil_carbon_delta"),
            co2eq_net_tCO2eq_ha=(row or {}).get("co2eq_net"),
            tier1_coverage=(row or {}).get("tier1_coverage"),
        ))

    def mean(values):
        vals = [v for v in values if v is not None]
        return sum(vals) / len(vals) if vals else None

    aggregations = [
        YearlyAggregation(
            year=y,
            parcel_count=len(rs),
            co2_gross_tCO2_ha_mean=mean(r.get("co2_sequestered_gross") for r in rs
                                        if (r.get("tier1_coverage") or 0) >= 1.0),
            delta_soc_tC_ha_mean=mean(r.get("soil_carbon_delta") for r in rs),
        )
        for y, rs in sorted(by_year.items())
    ]
    return TierSummaryResponse(tenant_id=tenant_id, year=year, parcels=summary, yearly_aggregations=aggregations)


async def _tenant_parcels(tenant_id: str) -> list[dict]:
    """Every AgriParcel of the tenant, paged (no attrs filter: it hides entities)."""
    out, offset = [], 0
    orion = get_orion_client()
    while True:
        page = await orion.query_entities(entity_type="AgriParcel", tenant_id=tenant_id, limit=100, offset=offset)
        out.extend(page or [])
        if not page or len(page) < 100:
            return out
        offset += 100


def _extract_ngsild_value(entity: dict, attr: str, default: str = "") -> str:
    """Extract a string NGSI-LD Property value."""
    prop = entity.get(attr, {})
    if isinstance(prop, dict):
        val = prop.get("value", "")
        return str(val) if val else default
    if isinstance(prop, str):
        return prop
    return default
