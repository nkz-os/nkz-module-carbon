"""Core carbon calculation and assessment endpoints.

Mount at /api/carbon (handled by main.py include_router).

Endpoints:
  GET    /parcels/{entity_id}/assessment          — Latest assessment
  POST   /parcels/{entity_id}/calculate            — Trigger calculation
  GET    /parcels/{entity_id}/assessment/history   — Historical assessments
  GET    /parcels/{entity_id}/tier-info            — Tier & gap analysis
  GET    /parcels/{entity_id}/projection           — 20-year SOC projection
"""

import logging
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.models.schemas import (
    CalculateRequest,
    CarbonAssessmentResponse,
    ErrorResponse,
    HistoryResponse,
    PoolStateResponse,
    ProjectionResponse,
    TierGap,
    TierInfoResponse,
)
from app.models.management import ManagementInput
from app.services.carbon_engine import (
    Tier1Input,
    calculate_tier1,
    compute_fapar_frac,
)
from app.services.roth_c_model import (
    MonthlyInputs,
    PoolState,
    init_pools_weihermuller,
    run_rothc_monthly,
)
from app.services.ghg_model import (
    N2OInputs,
    NEEInputs,
    compute_n2o,
    compute_nee,
    compute_co2eq_net,
)
from app.services.uncertainty import (
    tier1_gpp_uncertainty,
    UncertaintyResult,
)
from app.services.data_resolver import (
    DataAvailability,
    Tier as DataTier,
    resolve_tier,
)
from app.services.spectral import MorphologicalType, VegetationIndex, select_index
from app.services.solar_geometry import clear_sky_par_MJ_m2_day, doy_from_date
from app.services.units import C_TO_CO2
from app.ngsild.client import upsert_entity, query_entities
from app.ngsild.entities import build_carbon_assessment, build_carbon_stock
from app.db.database import insert_carbon_calculation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/carbon", tags=["assessments"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Default LUE per crop species (gC/MJ)
DEFAULT_LUE: dict[str, float] = {
    "wheat": 2.8,
    "barley": 2.6,
    "corn": 3.2,
    "rice": 2.2,
    "soybean": 1.8,
    "sunflower": 2.0,
    "rapeseed": 2.4,
    "sugarcane": 3.5,
    "pasture": 2.5,
    "forest": 1.5,
    "olive": 1.2,
    "vineyard": 1.4,
    "almond": 1.3,
    "citrus": 1.6,
    "unknown": 2.0,
}

DEFAULT_ROOT_FRACTION: dict[str, float] = {
    "wheat": 0.30,
    "barley": 0.30,
    "corn": 0.25,
    "rice": 0.20,
    "soybean": 0.35,
    "sunflower": 0.30,
    "rapeseed": 0.30,
    "sugarcane": 0.20,
    "pasture": 0.50,
    "forest": 0.60,
    "olive": 0.50,
    "vineyard": 0.40,
    "almond": 0.55,
    "citrus": 0.45,
    "unknown": 0.30,
}


def _get_tenant_id(ngsild_tenant: str = Header(default="", alias="NGSILD-Tenant")) -> str:
    """Extract tenant ID from NGSILD-Tenant header."""
    if not ngsild_tenant:
        raise HTTPException(status_code=400, detail="NGSILD-Tenant header is required")
    return ngsild_tenant


def _build_assessment_response(
    entity_id: str,
    tier: int,
    methodology: str,
    tier1_out,
    confidence: float,
    confidence_interval_pct: float,
    assessment_date: str,
    soil_carbon_delta: Optional[float] = None,
    carbon_stock_total_val: Optional[float] = None,
    pools: Optional[PoolState] = None,
    co2eq_net_daily: Optional[float] = None,
    co2eq_net_cumulative: Optional[float] = None,
    missing_next: Optional[list[str]] = None,
    data_sources: Optional[list[str]] = None,
) -> CarbonAssessmentResponse:
    """Build a CarbonAssessmentResponse from calculation results."""
    return CarbonAssessmentResponse(
        entity_id=entity_id,
        assessment_date=assessment_date,
        tier=tier,
        methodology=methodology,
        confidence=round(confidence, 3),
        confidence_interval_pct=round(confidence_interval_pct, 1),
        gpp_daily={"value": round(tier1_out.gpp_gC_m2_day, 4), "unit": "gC/m2/day"},
        npp_daily={"value": round(tier1_out.npp_total_gC_m2_day, 4), "unit": "gC/m2/day"},
        co2_sequestered_daily={
            "value": round(tier1_out.co2_seq_kgCO2_ha_day, 4),
            "unit": "kgCO2/ha/day",
        },
        co2_sequestered_cumulative={
            "value": round(tier1_out.co2_seq_kgCO2_ha_day, 4),
            "unit": "kgCO2/ha",
        },
        agb_dry={"value": round(tier1_out.agb_dry_tDM_ha, 4), "unit": "tDM/ha"},
        bgb_dry={"value": round(tier1_out.bgb_dry_tDM_ha, 4), "unit": "tDM/ha"},
        soil_carbon_delta=(
            {"value": round(soil_carbon_delta, 4), "unit": "tC/ha/yr"}
            if soil_carbon_delta is not None else None
        ),
        carbon_stock_total=(
            {"value": round(carbon_stock_total_val, 4), "unit": "tC/ha"}
            if carbon_stock_total_val is not None else None
        ),
        pools=(
            PoolStateResponse(
                dpm_tC_ha=round(pools.dpm_tC_ha, 4),
                rpm_tC_ha=round(pools.rpm_tC_ha, 4),
                bio_tC_ha=round(pools.bio_tC_ha, 4),
                hum_tC_ha=round(pools.hum_tC_ha, 4),
                iom_tC_ha=round(pools.iom_tC_ha, 4),
                total_tC_ha=round(pools.total_tC_ha, 4),
            ) if pools else None
        ),
        co2eq_net_daily=(
            {"value": round(co2eq_net_daily, 4), "unit": "tCO2eq/ha/day"}
            if co2eq_net_daily is not None else None
        ),
        co2eq_net_cumulative=(
            {"value": round(co2eq_net_cumulative, 4), "unit": "tCO2eq/ha"}
            if co2eq_net_cumulative is not None else None
        ),
        gwp_standard="AR6",
        missing_for_next_tier=missing_next or [],
        data_sources=data_sources or [],
        data_provenance={
            "engine_version": "0.1.0",
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def _resolve_morph_type(crop_species: str) -> MorphologicalType:
    """Determine morphological type from crop species name."""
    woody_crops = {"olive", "vineyard", "almond", "citrus", "apple", "pear",
                   "peach", "plum", "cherry", "orange", "lemon", "forest",
                   "walnut", "pistachio"}
    if crop_species.lower() in woody_crops:
        return MorphologicalType.WOODY
    return MorphologicalType.HERBACEOUS


def _get_lue(species: str) -> float:
    return DEFAULT_LUE.get(species.lower(), DEFAULT_LUE["unknown"])


def _get_root_fraction(species: str) -> float:
    return DEFAULT_ROOT_FRACTION.get(species.lower(), DEFAULT_ROOT_FRACTION["unknown"])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/parcels/{entity_id}/assessment",
    response_model=CarbonAssessmentResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_assessment(
    entity_id: str,
    tenant_id: str = Depends(_get_tenant_id),
):
    """Get the latest CarbonAssessment entity from Orion-LD.

    If no assessment exists yet, returns 404 — the caller should POST
    to /calculate first.
    """
    try:
        results = await query_entities(
            entity_type="CarbonAssessment",
            tenant_id=tenant_id,
            query=f'refAgriParcel=="urn:ngsi-ld:AgriParcel:{tenant_id}:{entity_id}"',
            attrs="assessmentDate,tier,gppDaily,nppDaily,confidence",
            limit=1,
        )
        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"No assessment found for parcel {entity_id}",
            )
        latest = results[0]
        # Transform raw NGSI-LD entity into the response shape
        props = {k: v.get("value") if isinstance(v, dict) and "value" in v else v
                 for k, v in latest.items()
                 if k not in ("id", "type", "@context")}
        # For full details we re-fetch with all attributes
        full = latest
        # Build a conservative response from what Orion-LD returns
        return CarbonAssessmentResponse(
            entity_id=entity_id,
            assessment_date=str(props.get("assessmentDate", "")),
            tier=int(props.get("dataTier", 1)),
            methodology=props.get("methodology", "Tier 1 — LUE"),
            confidence=float(props.get("confidence", 0.0)),
            confidence_interval_pct=float(props.get("confidenceIntervalPct", 0.0)),
            gpp_daily={"value": float(props.get("gppDaily", 0)), "unit": "gC/m2/day"},
            npp_daily={"value": float(props.get("nppDaily", 0)), "unit": "gC/m2/day"},
            co2_sequestered_daily={
                "value": float(props.get("co2SequesteredDaily", 0)),
                "unit": "kgCO2/ha/day",
            },
            co2_sequestered_cumulative={
                "value": float(props.get("co2SequesteredCumulative", 0)),
                "unit": "kgCO2/ha",
            },
            agb_dry={"value": float(props.get("agbDry", 0)), "unit": "tDM/ha"},
            bgb_dry={"value": float(props.get("bgbDry", 0)), "unit": "tDM/ha"},
            soil_carbon_delta=(
                {"value": float(props["soilCarbonDelta"]), "unit": "tC/ha/yr"}
                if "soilCarbonDelta" in props else None
            ),
            carbon_stock_total=(
                {"value": float(props["carbonStockTotal"]), "unit": "tC/ha"}
                if "carbonStockTotal" in props else None
            ),
            gwp_standard=props.get("gwpStandard", "AR6"),
            missing_for_next_tier=props.get("missingForNextTier", []),
            data_sources=props.get("dataSources", []),
            data_provenance={
                "source": "orion-ld",
                "entity_id": latest.get("id", ""),
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error fetching assessment for %s", entity_id)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/parcels/{entity_id}/calculate",
    response_model=CarbonAssessmentResponse,
    status_code=201,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def calculate(
    entity_id: str,
    body: CalculateRequest,
    tenant_id: str = Depends(_get_tenant_id),
):
    """Run Tier 1 (always) + Tier 2/3 if sufficient data.

    Accepts calculation parameters directly in the request body.
    Platform service integration (vegetation-prime, weather-worker,
    bioorchestrator) will be wired in Phase 6.
    """
    _tid = body.tenant_id or tenant_id
    calc_date = body.date or date.today()
    doy = doy_from_date(calc_date)
    species = (body.crop_species or "unknown").lower()
    morph_type_str = body.morph_type or _resolve_morph_type(species).value
    lat = body.lat if body.lat is not None else 42.0
    lon = body.lon if body.lon is not None else -2.0

    # --- 1. Resolve vegetation index ---
    # Phase 6: query vegetation-prime via platform/vegetation_client.py
    # For now use default values
    morph_type = MorphologicalType(morph_type_str)
    vi_type = select_index(morph_type)
    vi_value = 0.7  # placeholder — replace with real VI in Phase 6
    fapar = compute_fapar_frac(vi_value, a=1.0, b=-0.05)

    # --- 2. Weather ---
    # Phase 6: query weather-worker via platform/weather_client.py
    par_MJ_m2_day = clear_sky_par_MJ_m2_day(lat, doy)
    temp_celsius = 15.0  # placeholder

    # --- 3. Crop parameters ---
    lue = _get_lue(species)
    root_frac = _get_root_fraction(species)

    # --- 4. Tier determination via Data Resolver ---
    management = body.management or {}
    has_management = bool(management and management.get("tillage_type"))
    has_soil_lab = bool(
        management and (
            management.get("soil_lab_soc_tC_ha") is not None
            or management.get("soil_lab_clay_pct") is not None
        )
    )
    has_n_data = bool(
        management and (
            management.get("n_synthetic_kgN_ha_yr", 0) > 0
            or management.get("n_organic_kgN_ha_yr", 0) > 0
        )
    )

    # Build data availability from request and resolve tier
    avail = DataAvailability(
        ndvi_available=True,  # satellite VI always available via vegetation-prime
        lai_available=False,
        meteo_available=True,  # weather-worker always available
        soil_available=has_soil_lab,
        phenology_available=bool(body.crop_species),
        management_available=has_management,
        sensors_soil_available=bool(management.get("sensors_soil_moisture")),
        sensors_plant_available=bool(management.get("sensors_canopy_ir")),
        fertilization_available=has_n_data,
    )
    tier_result = resolve_tier(avail)
    tier = tier_result.tier
    methodology = {
        DataTier.ONE: "Tier 1 — LUE (Light Use Efficiency)",
        DataTier.TWO: "Tier 2 — RothC + LUE",
        DataTier.THREE: "Tier 3 — RothC + GHG (N2O/NEE) + LUE",
    }[tier_result.tier]
    missing_for_next_tier = tier_result.missing_for_next_tier
    data_sources = tier_result.available_sources + ["solar_geometry"]

    # --- 5. Run Tier 1 ---
    tier1_input = Tier1Input(
        par_MJ_m2_day=par_MJ_m2_day,
        fapar_frac=fapar,
        lue_gC_per_MJ=lue,
        root_fraction=root_frac,
        species=species,
        data_quality_flags=["simulated"] if vi_value == 0.7 else [],
    )
    tier1_out = calculate_tier1(tier1_input)

    # --- 6. Uncertainty (Tier 1 analytical) ---
    uncertainty = tier1_gpp_uncertainty(
        par=par_MJ_m2_day, sigma_par=par_MJ_m2_day * 0.1,
        fapar=fapar, sigma_fapar=fapar * 0.08,
        lue=lue, sigma_lue=lue * 0.15,
    )
    confidence = uncertainty.confidence
    ci95_pct = uncertainty.ci95_width / uncertainty.mean * 100 if uncertainty.mean != 0 else 0

    # --- 7. Tier 2 — RothC (if enough data) ---
    pools: Optional[PoolState] = None
    soc_delta: Optional[float] = None
    carbon_stock_total_val: Optional[float] = None

    if tier >= 2:
        clay_pct = management.get("soil_lab_clay_pct", 20.0)
        soc_initial = management.get("soil_lab_soc_tC_ha", 50.0)
        initial_pools = init_pools_weihermuller(soc_initial, clay_pct)
        # Build a simplified 12-month input loop
        monthly_inputs = []
        for m in range(12):
            monthly_inputs.append(MonthlyInputs(
                temp_celsius=temp_celsius + 5.0 * (1 if m > 4 and m < 10 else 0),
                precip_mm=50.0,
                etp_mm=80.0,
                cover_present=(m > 2 and m < 11),
                c_input_aerea_tC_ha=tier1_out.agb_dry_tDM_ha * 0.45 / 12.0,
                c_input_raices_tC_ha=tier1_out.bgb_dry_tDM_ha * 0.45 / 12.0,
                c_input_exudados_tC_ha=tier1_out.npp_total_gC_m2_day * 0.07 * 0.01 / 12.0,
                clay_pct=clay_pct,
            ))
        rothc_result = run_rothc_monthly(initial_pools, monthly_inputs, clay_pct)
        pools = rothc_result.pools
        soc_delta = rothc_result.soc_delta_tC_ha_yr
        carbon_stock_total_val = rothc_result.pools.total_tC_ha

    # --- 8. Tier 3 — GHG (if enough data) ---
    n2o_co2eq_t_ha_yr: Optional[float] = None
    nee_co2_t_ha_yr: Optional[float] = None
    co2eq_net_daily_val: Optional[float] = None
    co2eq_net_cum_val: Optional[float] = None

    if tier >= 3:
        n_syn = management.get("n_synthetic_kgN_ha_yr", 0.0)
        n_org = management.get("n_organic_kgN_ha_yr", 0.0)
        irrigated = management.get("irrigated", False)

        n2o_input = N2OInputs(
            n_applied_synthetic_kgN_ha_yr=n_syn,
            n_applied_organic_kgN_ha_yr=n_org,
            precip_annual_mm=600.0,
            etp_annual_mm=960.0,
            irrigated=irrigated,
        )
        n2o_result = compute_n2o(n2o_input)

        harvest_export = management.get("harvest_export_fraction", 0.9)
        c_exported = tier1_out.npp_total_gC_m2_day * 0.01 * 365 * harvest_export

        nee_input = NEEInputs(
            gpp_gC_m2_yr=tier1_out.gpp_gC_m2_day * 365,
            npp_total_gC_m2_yr=tier1_out.npp_total_gC_m2_day * 365,
            rh_tC_ha_yr=soc_delta if soc_delta is not None else 0.0,
            c_exported_harvest_tC_ha_yr=c_exported,
        )
        nee_result = compute_nee(nee_input)

        n2o_co2eq_t_ha_yr = n2o_result.n2o_co2eq_tCO2eq_ha_yr
        nee_co2_t_ha_yr = nee_result.nee_co2_tCO2_ha_yr

        co2eq_net_t_ha_yr = compute_co2eq_net(
            nee_tCO2_ha_yr=nee_co2_t_ha_yr,
            n2o_tCO2eq_ha_yr=n2o_co2eq_t_ha_yr,
        )
        co2eq_net_daily_val = co2eq_net_t_ha_yr / 365.0
        co2eq_net_cum_val = co2eq_net_t_ha_yr

    assessment_date_str = calc_date.isoformat()

    # --- 9. Persist to Orion-LD ---
    try:
        assessment_entity = build_carbon_assessment(
            tenant_id=_tid,
            parcel_id=entity_id,
            assessment_date=calc_date,
            tier=tier,
            methodology=methodology,
            confidence=confidence,
            confidence_interval_pct=ci95_pct,
            gpp_daily=tier1_out.gpp_gC_m2_day,
            npp_daily=tier1_out.npp_total_gC_m2_day,
            co2_sequestered_daily=tier1_out.co2_seq_kgCO2_ha_day,
            co2_sequestered_cumulative=tier1_out.co2_seq_kgCO2_ha_day,
            agb_dry=tier1_out.agb_dry_tDM_ha,
            bgb_dry=tier1_out.bgb_dry_tDM_ha,
            soil_carbon_delta=soc_delta,
            carbon_stock_total=carbon_stock_total_val,
            data_sources=data_sources,
            missing_for_next_tier=missing_for_next_tier,
            co2eq_net_daily=co2eq_net_daily_val,
            co2eq_net_cumulative=co2eq_net_cum_val,
            gwp_standard="AR6",
        )
        await upsert_entity(assessment_entity, _tid)

        if pools is not None:
            stock_entity = build_carbon_stock(
                tenant_id=_tid,
                parcel_id=entity_id,
                pools=pools.to_dict(),
                total_soc=pools.total_tC_ha,
            )
            await upsert_entity(stock_entity, _tid)
    except Exception as exc:
        logger.warning("Orion-LD persistence failed (non-fatal): %s", exc)

    # --- 10. Audit log ---
    try:
        await insert_carbon_calculation(
            tenant_id=_tid,
            entity_id=entity_id,
            tier=tier,
            methodology=methodology,
            data_sources=data_sources,
            input_params={
                "lat": lat, "lon": lon,
                "species": species, "morph_type": morph_type_str,
                "vi_value": vi_value, "par": par_MJ_m2_day,
            },
            results={
                "gpp": tier1_out.gpp_gC_m2_day,
                "npp": tier1_out.npp_total_gC_m2_day,
                "co2_seq": tier1_out.co2_seq_kgCO2_ha_day,
                "confidence": confidence,
            },
            confidence=confidence,
            confidence_interval_pct=ci95_pct,
            calculated_by="api",
        )
    except Exception as exc:
        logger.warning("Audit log insert failed (non-fatal): %s", exc)

    # --- 11. Return response ---
    return _build_assessment_response(
        entity_id=entity_id,
        tier=tier,
        methodology=methodology,
        tier1_out=tier1_out,
        confidence=uncertainty.confidence,
        confidence_interval_pct=ci95_pct,
        assessment_date=assessment_date_str,
        soil_carbon_delta=soc_delta,
        carbon_stock_total_val=carbon_stock_total_val,
        pools=pools,
        co2eq_net_daily=co2eq_net_daily_val,
        co2eq_net_cumulative=co2eq_net_cum_val,
        missing_next=missing_for_next_tier,
        data_sources=data_sources,
    )


@router.get(
    "/parcels/{entity_id}/assessment/history",
    response_model=HistoryResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_assessment_history(
    entity_id: str,
    limit: int = Query(default=10, ge=1, le=100),
    tenant_id: str = Depends(_get_tenant_id),
):
    """List historical CarbonAssessment entities for a parcel."""
    try:
        results = await query_entities(
            entity_type="CarbonAssessment",
            tenant_id=tenant_id,
            query=f'refAgriParcel=="urn:ngsi-ld:AgriParcel:{tenant_id}:{entity_id}"',
            limit=limit,
        )
    except Exception as exc:
        logger.exception("Error fetching assessment history for %s", entity_id)
        raise HTTPException(status_code=500, detail=str(exc))

    assessments = []
    for ent in results:
        props = {k: v.get("value") if isinstance(v, dict) and "value" in v else v
                 for k, v in ent.items()
                 if k not in ("id", "type", "@context")}
        assessments.append(CarbonAssessmentResponse(
            entity_id=entity_id,
            assessment_date=str(props.get("assessmentDate", "")),
            tier=int(props.get("dataTier", 1)),
            methodology=props.get("methodology", ""),
            confidence=float(props.get("confidence", 0.0)),
            confidence_interval_pct=float(props.get("confidenceIntervalPct", 0.0)),
            gpp_daily={"value": float(props.get("gppDaily", 0)), "unit": "gC/m2/day"},
            npp_daily={"value": float(props.get("nppDaily", 0)), "unit": "gC/m2/day"},
            co2_sequestered_daily={
                "value": float(props.get("co2SequesteredDaily", 0)),
                "unit": "kgCO2/ha/day",
            },
            co2_sequestered_cumulative={
                "value": float(props.get("co2SequesteredCumulative", 0)),
                "unit": "kgCO2/ha",
            },
            agb_dry={"value": float(props.get("agbDry", 0)), "unit": "tDM/ha"},
            bgb_dry={"value": float(props.get("bgbDry", 0)), "unit": "tDM/ha"},
            gwp_standard=props.get("gwpStandard", "AR6"),
            missing_for_next_tier=props.get("missingForNextTier", []),
            data_sources=props.get("dataSources", []),
        ))

    return HistoryResponse(
        entity_id=entity_id,
        assessments=assessments,
        count=len(assessments),
    )


@router.get(
    "/parcels/{entity_id}/tier-info",
    response_model=TierInfoResponse,
)
async def get_tier_info(
    entity_id: str,
    tenant_id: str = Depends(_get_tenant_id),
):
    """Analyze available data and report current tier + gaps.

    Phase 6: query platform services to determine actual data availability.
    For now, report Tier 1 with simulated data.
    """
    return TierInfoResponse(
        current_tier=1,
        confidence=0.85,
        available_data=["solar_geometry", "vegetation_index_default"],
        gaps=[
            TierGap(
                source="weather",
                missing=True,
                action="Connect weather-worker for live PAR / temperature",
                auto_fill="clear_sky_PAR + seasonal_climate_normals",
            ),
            TierGap(
                source="crop_type",
                missing=False,
                action="Set crop_species for accurate LUE / root fraction",
                auto_fill="default_LUE_2.0_gC_MJ",
            ),
            TierGap(
                source="management",
                missing=True,
                action="POST management data to enable Tier 2 RothC",
                auto_fill="conventional_tillage_defaults",
            ),
            TierGap(
                source="soil_lab",
                missing=True,
                action="Provide SOC and clay lab analysis for Tier 3",
                auto_fill="generalized_pedotransfer_functions",
            ),
            TierGap(
                source="nitrogen",
                missing=True,
                action="Provide N fertiliser rates for Tier 3 GHG",
                auto_fill="regional_defaults_by_crop",
            ),
        ],
    )


@router.get(
    "/parcels/{entity_id}/projection",
    response_model=ProjectionResponse,
    responses={400: {"model": ErrorResponse}},
)
async def get_projection(
    entity_id: str,
    years: int = Query(default=20, ge=1, le=50),
    tenant_id: str = Depends(_get_tenant_id),
):
    """Run a RothC 20-year (default) projection.

    Uses default soil params and climate normals. Provide management
    data via POST management endpoint to refine.
    """
    # Default soil parameters for projection
    clay_pct = 20.0
    soc_initial = 50.0
    initial_pools = init_pools_weihermuller(soc_initial, clay_pct)

    # Simplified monthly climate normals
    monthly_temps = [6, 7, 10, 13, 17, 21, 25, 24, 20, 15, 10, 7]
    monthly_precip = [40, 35, 40, 50, 55, 40, 25, 25, 35, 50, 50, 45]
    monthly_etp = [20, 30, 60, 90, 120, 140, 160, 140, 100, 60, 30, 20]
    cover_months = [False, False, True, True, True, True, True, True, True, True, False, False]

    # Baseline: conventional tillage, no cover crop, residues left
    # Project: reduced tillage, cover crop, residues retained

    total_months = years * 12
    baseline_pools = initial_pools
    project_pools = initial_pools
    baseline_soc_progression: list[float] = []
    project_soc_progression: list[float] = []

    for y in range(years):
        for m in range(12):
            c_input_base = 0.4 if cover_months[m] else 0.1
            c_input_proj = 0.6 if cover_months[m] else 0.1

            base_month = MonthlyInputs(
                temp_celsius=monthly_temps[m],
                precip_mm=monthly_precip[m],
                etp_mm=monthly_etp[m],
                cover_present=cover_months[m],
                c_input_aerea_tC_ha=c_input_base * 0.6,
                c_input_raices_tC_ha=c_input_base * 0.3,
                c_input_exudados_tC_ha=c_input_base * 0.07,
                clay_pct=clay_pct,
            )
            proj_month = MonthlyInputs(
                temp_celsius=monthly_temps[m],
                precip_mm=monthly_precip[m],
                etp_mm=monthly_etp[m],
                cover_present=cover_months[m] or True,  # cover crop extends cover
                c_input_aerea_tC_ha=c_input_proj * 0.6,
                c_input_raices_tC_ha=c_input_proj * 0.3,
                c_input_exudados_tC_ha=c_input_proj * 0.07,
                c_input_enmienda_tC_ha=0.1,  # organic amendment
                clay_pct=clay_pct,
            )

            result_base = run_rothc_monthly(baseline_pools, [base_month], clay_pct)
            result_proj = run_rothc_monthly(project_pools, [proj_month], clay_pct)

            baseline_pools = result_base.pools
            project_pools = result_proj.pools

        baseline_soc_progression.append(round(baseline_pools.total_tC_ha, 4))
        project_soc_progression.append(round(project_pools.total_tC_ha, 4))

    annual_delta = [
        round(p - b, 4)
        for p, b in zip(project_soc_progression, baseline_soc_progression)
    ]

    return ProjectionResponse(
        entity_id=entity_id,
        projection_years=years,
        baseline_soc=baseline_soc_progression,
        project_soc=project_soc_progression,
        annual_delta_tC_ha_yr=annual_delta,
    )
