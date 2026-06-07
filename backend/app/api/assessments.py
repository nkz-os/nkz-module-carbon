"""Core carbon calculation and assessment endpoints.

Mount at /api/carbon (handled by main.py include_router).

Endpoints:
  GET    /parcels/{entity_id}/assessment          — Latest assessment
  POST   /parcels/{entity_id}/calculate            — Trigger calculation
  GET    /parcels/{entity_id}/assessment/history   — Historical assessments
  GET    /parcels/{entity_id}/tier-info            — Tier & gap analysis
  GET    /parcels/{entity_id}/projection           — 20-year SOC projection
  GET    /sensors/available                        — List tenant AgriSensors
  GET    /tenant/summary                           — Multi-parcel carbon summary
"""

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.common.auth import AuthContext, require_auth
from app.common.tier_check import check_tier
from app.models.schemas import (
    CalculateRequest,
    CarbonAssessmentResponse,
    ErrorResponse,
    HistoryResponse,
    ParcelSummary,
    PoolStateResponse,
    ProjectionResponse,
    SensorInfo,
    TierGap,
    TierInfoResponse,
    TierSummaryResponse,
    YearlyAggregation,
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
from app.common.orion import upsert_entity, query_entities, get_entity
from app.ngsild.entities import build_carbon_assessment, build_carbon_stock
from app.db.database import insert_carbon_calculation
from app.platform.weather_client import (
    WeatherSnapshot,
    fetch_weather,
    fetch_parcel_weather,
    fetch_weather_from_sensor,
    list_tenant_sensors,
)
from app.platform.vegetation_client import resolve_vi_for_parcel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/carbon", tags=["assessments"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Species-specific LUE values [gC/MJ] per spec 3.2
# Only species with peer-reviewed calibration are listed.
# Species NOT in this dict must fail explicitly — no generic fallback.
LUE_BY_SPECIES: dict[str, float] = {
    "wheat": 1.1,
    "barley": 1.0,
    "olive": 0.9,
    "corn": 1.7,
    "rice": 1.3,
    "sunflower": 1.3,
    "soybean": 1.2,
    "sugarcane": 1.8,
}

# Species-specific root fractions [0-1] per spec 3.4
ROOT_FRACTION_BY_SPECIES: dict[str, float] = {
    "wheat": 0.22, "barley": 0.22, "corn": 0.18, "rice": 0.15,
    "sunflower": 0.20, "soybean": 0.20, "sugarcane": 0.20,
    "olive": 0.20, "vineyard": 0.20, "almond": 0.25,
    "citrus": 0.25, "pasture": 0.55,
}

# Species-specific fAPAR params [a, b, VI_type] per spec 3.1
FAPAR_PARAMS: dict[str, tuple[float, float, str]] = {
    "wheat": (1.24, -0.168, "NDVI"),
    "barley": (1.24, -0.168, "NDVI"),
    "corn": (1.24, -0.168, "NDVI"),
    "rice": (1.24, -0.168, "NDVI"),
    "sunflower": (1.24, -0.168, "NDVI"),
    "soybean": (1.24, -0.168, "NDVI"),
    "sugarcane": (1.24, -0.168, "NDVI"),
    "olive": (1.40, -0.240, "OSAVI"),
    "vineyard": (1.40, -0.240, "OSAVI"),
    "almond": (1.40, -0.240, "OSAVI"),
    "citrus": (1.40, -0.240, "OSAVI"),
}


def _get_lue(species: str) -> float | None:
    """Get LUE for species. Returns None if species not calibrated."""
    return LUE_BY_SPECIES.get(species.lower())


def _get_root_fraction(species: str) -> float | None:
    """Get root fraction for species. Returns None if not calibrated."""
    return ROOT_FRACTION_BY_SPECIES.get(species.lower())


def _get_fapar_params(species: str) -> tuple[float, float, str] | None:
    """Get fAPAR (a, b, VI_type) for species. None if not calibrated."""
    return FAPAR_PARAMS.get(species.lower())


async def _get_existing_cumulative(tenant_id: str, parcel_id: str) -> float:
    """Get the latest cumulative CO2 value from Orion-LD for a parcel."""
    try:
        prev = await query_entities(
            entity_type="CarbonAssessment",
            tenant_id=tenant_id,
            query=f'hasAgriParcel=="urn:ngsi-ld:AgriParcel:{tenant_id}:{parcel_id}"',
            attrs="co2SequesteredCumulative",
            limit=1,
        )
        if prev:
            props = {k: v.get("value") if isinstance(v, dict) and "value" in v else v
                     for k, v in prev[0].items()
                     if k not in ("id", "type", "@context")}
            return float(props.get("co2SequesteredCumulative", 0))
    except Exception:
        pass
    return 0.0


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
    auth: AuthContext = require_auth(),
):
    """Get the latest CarbonAssessment entity from Orion-LD.

    If no assessment exists yet, returns 404 — the caller should POST
    to /calculate first.
    """
    tenant_id = auth.tenant_id
    try:
        results = await query_entities(
            entity_type="CarbonAssessment",
            tenant_id=tenant_id,
            query=f'hasAgriParcel=="urn:ngsi-ld:AgriParcel:{tenant_id}:{entity_id}"',
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
    auth: AuthContext = require_auth(),
    _tier_ok: None = Depends(check_tier),
):
    """Run Tier 1 (always) + Tier 2/3 if sufficient data.

    Fetches real vegetation index from vegetation-prime and weather from
    weather-worker or tenant sensors depending on configuration.
    """
    _tid = auth.tenant_id
    calc_date = body.date or date.today()
    doy = doy_from_date(calc_date)
    species = (body.crop_species or "unknown").lower()
    morph_type_str = body.morph_type or _resolve_morph_type(species).value
    lat = body.lat if body.lat is not None else 42.0
    lon = body.lon if body.lon is not None else -2.0

    # --- 1. Resolve vegetation index from vegetation-prime ---
    vi_value, vi_type_name, vi_quality = await resolve_vi_for_parcel(
        entity_id, _tid, species,
    )

    # Species-specific fAPAR params per spec 3.1
    fapar_params = _get_fapar_params(species)
    if fapar_params is None:
        raise HTTPException(
            status_code=422,
            detail=f"Species '{species}' has no calibrated fAPAR parameters. "
                   f"Available: {', '.join(sorted(FAPAR_PARAMS.keys()))}",
        )
    fapar_a, fapar_b, _ = fapar_params
    fapar = compute_fapar_frac(vi_value, a=fapar_a, b=fapar_b)

    # --- 2. Weather: weather-worker or tenant sensor ---
    management = body.management or {}
    weather_source = body.weather_source or management.get("weather_source", "weather_worker")
    sensor_id = body.weather_sensor_id or management.get("weather_sensor_id")

    weather: WeatherSnapshot | None = None

    if weather_source == "sensor" and sensor_id:
        weather = await fetch_weather_from_sensor(entity_id, _tid, sensor_id)

    if weather is None:
        # Try parcel-specific weather from entity-manager
        weather = await fetch_parcel_weather(entity_id, _tid)

    if weather is None:
        # Fall back to clear-sky PAR + generic temperature
        par_MJ_m2_day = clear_sky_par_MJ_m2_day(lat, doy)
        temp_celsius = 20.0
        weather_data_quality = "synthetic_par"
    else:
        par_MJ_m2_day = weather.par_MJ_m2_day
        temp_celsius = weather.temp_air_celsius
        weather_data_quality = weather.data_quality

    # --- 3. Crop parameters ---
    lue = _get_lue(species)
    if lue is None:
        raise HTTPException(
            status_code=422,
            detail=f"Species '{species}' has no calibrated LUE value. "
                   f"Available: {', '.join(sorted(LUE_BY_SPECIES.keys()))}",
        )
    root_frac_val = _get_root_fraction(species)
    if root_frac_val is None:
        raise HTTPException(
            status_code=422,
            detail=f"Species '{species}' has no calibrated root fraction. "
                   f"Available: {', '.join(sorted(ROOT_FRACTION_BY_SPECIES.keys()))}",
        )
    root_frac = root_frac_val

    # --- 4. Tier determination via Data Resolver ---
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
    data_sources = tier_result.available_sources
    if weather_data_quality != "synthetic_par":
        data_sources.append(f"weather_{weather_data_quality}")

    # --- 5. Run Tier 1 ---
    quality_flags = []
    if vi_quality == "simulated":
        quality_flags.append("vi_simulated")
    if weather_data_quality == "synthetic_par":
        quality_flags.append("par_synthetic")

    tier1_input = Tier1Input(
        par_MJ_m2_day=par_MJ_m2_day,
        fapar_frac=fapar,
        lue_gC_per_MJ=lue,
        root_fraction=root_frac,
        species=species,
        data_quality_flags=quality_flags,
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
            co2_sequestered_cumulative=(
                await _get_existing_cumulative(_tid, entity_id)
                + tier1_out.co2_seq_kgCO2_ha_day
            ),
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
    auth: AuthContext = require_auth(),
):
    """List historical CarbonAssessment entities for a parcel."""
    tenant_id = auth.tenant_id
    try:
        results = await query_entities(
            entity_type="CarbonAssessment",
            tenant_id=tenant_id,
            query=f'hasAgriParcel=="urn:ngsi-ld:AgriParcel:{tenant_id}:{entity_id}"',
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
    crop_species: str | None = Query(default=None),
    has_management: bool = Query(default=False),
    has_soil_lab: bool = Query(default=False),
    has_sensors: bool = Query(default=False),
    has_fertilization: bool = Query(default=False),
    auth: AuthContext = require_auth(),
):
    """Analyze available data and report current tier + gaps.

    Query params let the frontend pass what it knows about data availability.
    Phase 6 adds automatic detection via platform service queries.
    """
    tenant_id = auth.tenant_id
    species_ok = crop_species is not None and crop_species.lower() in LUE_BY_SPECIES

    avail = DataAvailability(
        ndvi_available=True,
        meteo_available=True,
        soil_available=has_soil_lab,
        phenology_available=species_ok,
        management_available=has_management,
        sensors_soil_available=has_sensors,
        sensors_plant_available=has_sensors,
        fertilization_available=has_fertilization,
        soc_provenance="soilgrids_250m_v2" if not has_soil_lab else "lab_analysis",
    )

    tier_result = resolve_tier(avail)

    return TierInfoResponse(
        current_tier=tier_result.tier,
        confidence=tier_result.confidence,
        available_data=tier_result.available_sources,
        gaps=[
            TierGap(
                source=g["source"],
                missing=g["missing"],
                action=g["action"],
                auto_fill=g["auto_fill"],
            )
            for g in tier_result.gap_details
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
    auth: AuthContext = require_auth(),
):
    """Run a RothC 20-year (default) projection.

    Uses default soil params and climate normals. Provide management
    data via POST management endpoint to refine.
    """
    tenant_id = auth.tenant_id
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

    # Build all months upfront for correct TSMD accumulation (runs once)
    baseline_months: list[MonthlyInputs] = []
    project_months: list[MonthlyInputs] = []

    for y in range(years):
        for m in range(12):
            c_input_base = 0.4 if cover_months[m] else 0.1
            c_input_proj = 0.6 if cover_months[m] else 0.1

            baseline_months.append(MonthlyInputs(
                temp_celsius=monthly_temps[m],
                precip_mm=monthly_precip[m],
                etp_mm=monthly_etp[m],
                cover_present=cover_months[m],
                c_input_aerea_tC_ha=c_input_base * 0.6,
                c_input_raices_tC_ha=c_input_base * 0.3,
                c_input_exudados_tC_ha=c_input_base * 0.07,
                clay_pct=clay_pct,
            ))
            project_months.append(MonthlyInputs(
                temp_celsius=monthly_temps[m],
                precip_mm=monthly_precip[m],
                etp_mm=monthly_etp[m],
                cover_present=True,  # cover crop extends year-round cover
                c_input_aerea_tC_ha=c_input_proj * 0.6,
                c_input_raices_tC_ha=c_input_proj * 0.3,
                c_input_exudados_tC_ha=c_input_proj * 0.07,
                c_input_enmienda_tC_ha=0.1,
                clay_pct=clay_pct,
            ))

    # Run RothC once across the full timeseries for correct TSMD dynamics
    base_result = run_rothc_monthly(initial_pools, baseline_months, clay_pct)
    proj_result = run_rothc_monthly(initial_pools, project_months, clay_pct)

    # Extract yearly SOC from the monthly TSMD (take last month of each year)
    baseline_tsmd = base_result.monthly_tsmd
    # Reconstruct yearly progression: rerun year-by-year for tracking
    b_pools = initial_pools
    p_pools = initial_pools
    for y in range(years):
        year_slice = slice(y * 12, (y + 1) * 12)
        b_year = run_rothc_monthly(b_pools, baseline_months[year_slice], clay_pct)
        p_year = run_rothc_monthly(p_pools, project_months[year_slice], clay_pct)
        b_pools = b_year.pools
        p_pools = p_year.pools
        baseline_soc_progression.append(round(b_pools.total_tC_ha, 4))
        project_soc_progression.append(round(p_pools.total_tC_ha, 4))

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
    """Aggregate carbon assessments across all parcels for the tenant.

    Queries all AgriParcel entities in Orion-LD, fetches their latest
    CarbonAssessment, and builds a summary table with yearly aggregation.
    """
    tenant_id = auth.tenant_id
    logger.info("Summary requested for tenant=%s year=%s", tenant_id, year)
    # 1. Fetch all AgriParcel entities for the tenant
    parcels: list[dict] = []
    try:
        parcels = await query_entities(
            entity_type="AgriParcel",
            tenant_id=tenant_id,
            limit=500,
        )
    except Exception as exc:
        logger.exception("Error querying AgriParcel for tenant %s", tenant_id)
        raise HTTPException(status_code=500, detail=str(exc))


    if not parcels:
        return TierSummaryResponse(tenant_id=tenant_id, parcels=[], yearly_aggregations=[])

    # 2. Extract parcel IDs and names
    parcel_infos = []
    for ent in parcels:
        pid = ent.get("id", "")
        # Extract short ID from URN
        short_id = pid.split(":")[-1] if ":" in pid else pid
        name = _extract_ngsild_value(ent, "name", short_id)
        crop = _extract_ngsild_value(ent, "cropSpecies", "")
        parcel_infos.append((pid, short_id, str(name), str(crop)))

    # 3. Fetch latest CarbonAssessment for each parcel (parallel, max 10 concurrent)
    sem = asyncio.Semaphore(10)

    async def _fetch_one(parcel_id: str, short_id: str):
        async with sem:
            try:
                results = await query_entities(
                    entity_type="CarbonAssessment",
                    tenant_id=tenant_id,
                    query=f'hasAgriParcel=="{parcel_id}"',
                    limit=1,
                )
                if not results:
                    return None
                ent = results[0]
                props = {k: v.get("value") if isinstance(v, dict) and "value" in v else v
                         for k, v in ent.items()
                         if k not in ("id", "type", "@context")}
                return {
                    "parcel_id": short_id,
                    "assessment_date": str(props.get("assessmentDate", "")),
                    "tier": int(props.get("dataTier", 1)),
                    "methodology": str(props.get("methodology", "")),
                    "co2_seq_cum": float(props.get("co2SequesteredCumulative", 0)),
                    "carbon_stock": float(props.get("carbonStockTotal", 0)),
                }
            except Exception as exc:
                logger.debug("No assessment for parcel %s: %s", short_id, exc)
                return None

    tasks = [_fetch_one(pid, sid) for pid, sid, _, _ in parcel_infos]
    results = await asyncio.gather(*tasks)

    # 4. Build summary rows
    parcels_summary: list[ParcelSummary] = []
    for (_, short_id, name, crop), result in zip(parcel_infos, results):
        if result is None:
            parcels_summary.append(ParcelSummary(
                parcel_id=short_id,
                parcel_name=name,
                crop_species=crop,
                co2_captured_cumulative=0.0,
                carbon_stock_total=0.0,
                tier=1,
                methodology="",
                last_calculation_date=None,
            ))
        else:
            # Filter by year if specified
            assess_year = None
            if result["assessment_date"]:
                try:
                    assess_year = int(result["assessment_date"][:4])
                except (ValueError, IndexError):
                    pass
            if year is not None and assess_year != year:
                continue

            parcels_summary.append(ParcelSummary(
                parcel_id=short_id,
                parcel_name=name,
                crop_species=crop,
                co2_captured_cumulative=round(result["co2_seq_cum"], 2),
                carbon_stock_total=round(result["carbon_stock"], 2),
                tier=result["tier"],
                methodology=result["methodology"],
                last_calculation_date=result["assessment_date"] or None,
            ))

    # 5. Build yearly aggregation
    yearly: dict[int, dict] = {}
    for p in parcels_summary:
        if p.last_calculation_date:
            try:
                y = int(p.last_calculation_date[:4])
            except (ValueError, IndexError):
                continue
            if y not in yearly:
                yearly[y] = {"total_co2": 0.0, "total_stock": 0.0, "count": 0}
            yearly[y]["total_co2"] += p.co2_captured_cumulative
            yearly[y]["total_stock"] += p.carbon_stock_total
            yearly[y]["count"] += 1

    yearly_aggs = [
        YearlyAggregation(
            year=y,
            total_co2_captured_kg=round(d["total_co2"], 2),
            avg_carbon_stock_tC_ha=round(d["total_stock"] / d["count"], 2) if d["count"] else 0,
            parcel_count=d["count"],
        )
        for y, d in sorted(yearly.items())
    ]

    return TierSummaryResponse(
        tenant_id=tenant_id,
        parcels=parcels_summary,
        yearly_aggregations=yearly_aggs,
    )


def _extract_ngsild_value(entity: dict, attr: str, default: str = "") -> str:
    """Extract a string NGSI-LD Property value."""
    prop = entity.get(attr, {})
    if isinstance(prop, dict):
        val = prop.get("value", "")
        return str(val) if val else default
    if isinstance(prop, str):
        return prop
    return default
