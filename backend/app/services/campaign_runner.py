"""Runs the carbon balance of one parcel and campaign: gathers the sources,
chains the soil state between campaigns and persists the result."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, timedelta
from typing import Any, Optional

from app.common.orion import get_orion_client
from app.db.database import insert_carbon_calculation
from app.ngsild.campaign_entities import build_campaign_assessment, build_campaign_stock, stock_state
from app.platform.crop_client import canonical_parcel_urn, fetch_parcel_coordinates, parcel_short
from app.platform.crop_cycles_client import fetch_cycles
from app.platform.daily_weather_client import fetch_daily_weather
from app.platform.eo_ndvi_client import fetch_ndvi_series
from app.platform.errors import SourceUnavailable
from app.platform.operations_client import fetch_operations, fetch_parcel_area_ha
from app.platform.soil_client import fetch_soil_init
from app.services.campaign_balance import ENGINE_VERSION, compute_campaign_balance
from app.services.campaign_types import (
    NO_DECLARED_MANAGEMENT, CampaignBalance, CampaignInputs, CycleSpan, DeclaredManagement, Missing,
)
from app.services.campaign_reports import (
    build_monitoring_report, combine_months, is_complete, months_from_row, project_soc,
)
from app.services.crop_params import resolve_crop_params
from app.services.roth_c_model import RothCState, run_months, weihermuller_pools

logger = logging.getLogger(__name__)

# weather-api serves at most 400 days per request.
_WEATHER_CHUNK_DAYS = 366
# Cycles started earlier than this before 1 January are not followed back further.
_MAX_LOOKBACK_DAYS = 400


def _assessment_id(tenant_id: str, short: str, year: int) -> str:
    return f"urn:ngsi-ld:CarbonAssessment:{tenant_id}:{short}:{year}"


def _stock_id(tenant_id: str, short: str, year: int) -> str:
    return f"urn:ngsi-ld:CarbonStock:{tenant_id}:{short}:{year}"


def _v(entity: dict, name: str) -> Any:
    v = entity.get(name)
    return v.get("value", v.get("object")) if isinstance(v, dict) else v


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def entity_to_dict(entity: dict) -> dict:
    """API view of a stored CarbonAssessment: snake_case keys, plain values."""
    # Orion compacts the relationship to either term (same IRI).
    out: dict[str, Any] = {"parcel_id": _v(entity, "hasAgriParcel") or _v(entity, "refAgriParcel")}
    for k in entity:
        if k in ("id", "type", "@context", "hasAgriParcel", "refAgriParcel"):
            continue
        out[_snake(k)] = _v(entity, k)
    return out


async def _get(tenant_id: str, entity_id: str) -> Optional[dict]:
    try:
        return await get_orion_client().get_entity(entity_id, tenant_id)
    except Exception as exc:  # noqa: BLE001 — unknown, not absent
        raise SourceUnavailable(f"broker read failed: {exc}") from exc


async def _declared(tenant_id: str, short: str) -> tuple[DeclaredManagement, tuple[Optional[float], Optional[float]]]:
    e = await _get(tenant_id, f"urn:ngsi-ld:ManagementPractice:{tenant_id}:{short}")
    if not e:
        return NO_DECLARED_MANAGEMENT, (None, None)

    def num(name):
        v = _v(e, name)
        try:
            return None if v is None else float(v)
        except (TypeError, ValueError):
            return None

    irrigated = _v(e, "irrigated")
    declared = DeclaredManagement(
        harvest_export_fraction=num("harvest_export_fraction"),
        residue_removal_fraction=num("residue_removal_fraction"),
        organic_amendments_tC_ha_yr=num("organic_amendments_tC_ha_yr"),
        n_synthetic_kgN_ha_yr=num("n_synthetic_kgN_ha_yr"),
        n_organic_kgN_ha_yr=num("n_organic_kgN_ha_yr"),
        irrigated=bool(irrigated) if irrigated is not None else None,
    )
    return declared, (num("soil_lab_soc_tC_ha"), num("soil_lab_clay_pct"))


def _parse_date(v: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _spans(raw: list[dict], year: int) -> list[dict]:
    """Cycles that touch the campaign, with parsed dates (params resolved later)."""
    out = []
    for c in raw:
        start = _parse_date((c.get("start") or {}).get("date"))
        if start is None:
            continue
        end = _parse_date((c.get("end") or {}).get("date"))
        if start > date(year, 12, 31) or (end is not None and end < date(year, 1, 1)):
            continue
        out.append({**c, "_start": start, "_end": end})
    return out


async def _coordinates(urn: str, tenant_id: str) -> Optional[tuple[float, float]]:
    """Centroid, used only to refine BioOrchestrator crop parameters."""
    try:
        return await fetch_parcel_coordinates(urn, tenant_id)
    except Exception as exc:  # noqa: BLE001 — params then come from the sourced tables
        logger.warning("parcel centroid unavailable tenant=%s parcel=%s: %s", tenant_id, urn, exc)
        return None


async def _weather(urn: str, tenant_id: str, start: date, end: date):
    days = []
    cur = start
    while cur <= end:
        chunk_end = min(end, cur + timedelta(days=_WEATHER_CHUNK_DAYS - 1))
        days.extend(await fetch_daily_weather(urn, tenant_id, cur, chunk_end))
        cur = chunk_end + timedelta(days=1)
    return days


async def run_campaign(
    tenant_id: str,
    parcel_id: str,
    year: int,
    today: Optional[date] = None,
    cascade: bool = True,
) -> CampaignBalance:
    today = today or date.today()
    if year > today.year:
        raise ValueError(f"campaign {year} has not started")
    urn, short = canonical_parcel_urn(parcel_id), parcel_short(parcel_id)
    p_start = date(year, 1, 1)
    through_max = min(date(year, 12, 31), today - timedelta(days=1))

    # A previous campaign still open when it was last computed is finished first,
    # so this one can start from its 31 December state.
    prev_assessment = await _get(tenant_id, _assessment_id(tenant_id, short, year - 1))
    prev_stock = await _get(tenant_id, _stock_id(tenant_id, short, year - 1))
    if prev_assessment and str(_v(prev_assessment, "computedThrough") or "") < f"{year - 1}-12-31":
        await run_campaign(tenant_id, parcel_id, year - 1, today=today, cascade=False)
        prev_stock = await _get(tenant_id, _stock_id(tenant_id, short, year - 1))

    raw_cycles, area, (declared, lab), coords = await asyncio.gather(
        fetch_cycles(urn, tenant_id, date(year, 12, 31)),
        fetch_parcel_area_ha(urn, tenant_id),
        _declared(tenant_id, short),
        _coordinates(urn, tenant_id),
    )
    spans = _spans(raw_cycles, year)
    lookback = p_start - timedelta(days=_MAX_LOOKBACK_DAYS)
    w_start = max(lookback, min([p_start] + [s["_start"] for s in spans]))

    if through_max >= w_start:
        weather, ndvi, (soil, soil_missing), ops = await asyncio.gather(
            _weather(urn, tenant_id, w_start, through_max),
            fetch_ndvi_series(urn, tenant_id, w_start, through_max),
            fetch_soil_init(urn, tenant_id, lab=lab),
            fetch_operations(urn, tenant_id, p_start, through_max, area),
        )
    else:  # 1 January: nothing closed yet
        weather, ndvi, (soil, soil_missing), ops = [], [], (None, []), ([], [], [], [], [])
    harvests, ferts, tills, bales, ops_missing = ops

    lat, lon = coords if coords else (None, None)
    params_by_species: dict[str, tuple] = {}
    missing: list[Missing] = list(soil_missing) + list(ops_missing)
    cycles: list[CycleSpan] = []
    for s in spans:
        species = str(s.get("species") or "")
        if s["_start"] > through_max:
            continue  # not started inside the computed period: nothing to resolve yet
        if species not in params_by_species:
            params_by_species[species] = await resolve_crop_params(species, lat, lon)
            missing.extend(params_by_species[species][1])
        cycles.append(CycleSpan(
            crop_id=str(s.get("crop_id")), species=species, role=str(s.get("role") or "main_crop"),
            lifecycle=str(s.get("lifecycle") or "unknown"), start=s["_start"], end=s["_end"],
            start_provenance=str((s.get("start") or {}).get("provenance") or "unknown"),
            end_provenance=(s.get("end") or {}).get("provenance"),
            campaign_label=s.get("campaign_label"), params=params_by_species[species][0],
        ))

    initial_state, initial_source = None, "soil"
    if prev_stock:
        state, state_date = stock_state(prev_stock)
        if state_date == date(year - 1, 12, 31):
            initial_state, initial_source = state, "previous_campaign"

    balance = compute_campaign_balance(CampaignInputs(
        year=year, today=today, weather=tuple(weather), ndvi=tuple(ndvi), cycles=tuple(cycles), soil=soil,
        initial_state=initial_state, initial_state_source=initial_source, harvests=tuple(harvests),
        fertilizations=tuple(ferts), tillages=tuple(tills), balings=tuple(bales), declared=declared,
        missing_in=tuple(missing),
    ))

    sources = ["weather_api_daily", "crop_cycles", "eo_ndvi", "field_operations"]
    if soil is not None:
        sources.append(f"soil_{soil.source}")
    sources += sorted({f"crop_params_{p.source}" for p, _ in params_by_species.values() if p is not None})
    orion = get_orion_client()
    await orion.upsert_entity(build_campaign_assessment(tenant_id, urn, balance, sources, soil), tenant_id)
    if balance.end_state is not None and balance.computed_through is not None:
        await orion.upsert_entity(
            build_campaign_stock(tenant_id, urn, year, balance.end_state, balance.computed_through), tenant_id)
    if balance.tier >= 1:
        try:
            await insert_carbon_calculation(
                tenant_id=tenant_id, entity_id=urn, tier=balance.tier,
                methodology=f"campaign balance {year} (engine {ENGINE_VERSION})", data_sources=sources,
                input_params={"year": year, "cycles": len(cycles), "weather_days": len(weather),
                              "ndvi_scenes": len(ndvi), "initial_state": initial_source},
                results={"computed_through": balance.computed_through.isoformat() if balance.computed_through else None,
                         "delta_soc_tC_ha": balance.delta_soc_tC_ha, "co2eq_net_tCO2eq_ha": balance.co2eq_net_tCO2eq_ha,
                         "missing": sorted({m.item for m in balance.missing})},
                confidence=0.0, confidence_interval_pct=float(balance.gpp_ci95_pct or 0.0),
                calculated_by="campaign_runner",
            )
        except Exception as exc:  # noqa: BLE001 — the broker entity is the record; the audit row is extra
            logger.warning("carbon audit insert failed tenant=%s parcel=%s: %s", tenant_id, short, exc)
    logger.info(
        "carbon_campaign tenant=%s parcel=%s year=%s tier=%s through=%s missing=%s",
        tenant_id, short, year, balance.tier, balance.computed_through,
        ",".join(sorted({m.item for m in balance.missing})) or "-",
    )

    if cascade and await _get(tenant_id, _assessment_id(tenant_id, short, year + 1)):
        await run_campaign(tenant_id, parcel_id, year + 1, today=today, cascade=True)
    return balance


async def list_campaigns(tenant_id: str, parcel_id: str) -> list[dict]:
    urn = canonical_parcel_urn(parcel_id)
    out, offset = [], 0
    try:
        while True:
            page = await get_orion_client().query_entities(
                entity_type="CarbonAssessment", tenant_id=tenant_id,
                query=f'hasAgriParcel=="{urn}"', limit=100, offset=offset)
            out.extend(page or [])
            if not page or len(page) < 100:
                break
            offset += 100
    except Exception as exc:  # noqa: BLE001
        raise SourceUnavailable(f"broker query failed: {exc}") from exc
    rows = [entity_to_dict(e) for e in out if _v(e, "campaignLabel") is not None]
    return sorted(rows, key=lambda r: r["campaign_label"])


async def get_campaign(tenant_id: str, parcel_id: str, year: int) -> Optional[dict]:
    e = await _get(tenant_id, _assessment_id(tenant_id, parcel_short(parcel_id), year))
    return entity_to_dict(e) if e else None


async def get_campaign_stock(tenant_id: str, parcel_id: str, year: int) -> Optional[dict]:
    return await _get(tenant_id, _stock_id(tenant_id, parcel_short(parcel_id), year))


# ---------------------------------------------------------------------------
# Projection and monitoring report over stored campaigns
# ---------------------------------------------------------------------------

async def _baseline_year(tenant_id: str, short: str) -> Optional[int]:
    e = await _get(tenant_id, f"urn:ngsi-ld:BaselineScenario:{tenant_id}:{short}")
    vf = str(_v(e, "validFrom") or "") if e else ""
    return int(vf[:4]) if vf[:4].isdigit() else None


async def _start_state(tenant_id: str, short: str, row: dict) -> Optional[RothCState]:
    """The state a stored campaign started from: previous 31 Dec stock, or its soil init."""
    year = row["campaign_label"]
    prev = await _get(tenant_id, _stock_id(tenant_id, short, year - 1))
    if prev:
        state, when = stock_state(prev)
        if when == date(year - 1, 12, 31):
            return state
    if row.get("soc_start") is None or row.get("soil_clay_pct") is None:
        return None
    return RothCState(weihermuller_pools(float(row["soc_start"]), float(row["soil_clay_pct"])), 0.0)


def _usable(row: dict) -> bool:
    return (row.get("data_tier") or 0) >= 2 and row.get("soil_clay_pct") is not None and bool(row.get("monthly_balance"))


async def projection(tenant_id: str, parcel_id: str, years: int = 20) -> dict:
    short = parcel_short(parcel_id)
    rows = await list_campaigns(tenant_id, parcel_id)
    ref = next((r for r in reversed(rows) if _usable(r) and is_complete(r)), None)
    out = {"entity_id": short, "projection_years": years, "reference_year": None, "baseline_soc": [],
           "project_soc": [], "annual_delta_tC_ha_yr": [], "assumptions": [], "missing": []}
    if ref is None:
        out["missing"].append({"item": "complete_campaign", "reason": "no complete campaign with a soil balance",
                               "effect": "no_projection"})
        return out
    stock = await _get(tenant_id, _stock_id(tenant_id, short, ref["campaign_label"]))
    if stock is None:
        out["missing"].append({"item": "complete_campaign", "reason": "reference campaign without stored pools",
                               "effect": "no_projection"})
        return out
    start, _ = stock_state(stock)
    clay, depth = float(ref["soil_clay_pct"]), float(ref.get("soil_depth_cm") or 30.0)
    climate = months_from_row(ref)
    out["reference_year"] = ref["campaign_label"]
    out["project_soc"] = project_soc(start, climate, clay, depth, years)
    out["assumptions"].append(f"climate and management of {ref['campaign_label']} repeated every year")
    b_year = await _baseline_year(tenant_id, short)
    b_row = next((r for r in rows if r["campaign_label"] == b_year and _usable(r) and is_complete(r)), None)
    if b_row is None:
        out["assumptions"].append("no baseline defined: only the current management is projected")
    else:
        out["baseline_soc"] = project_soc(start, combine_months(climate, months_from_row(b_row)), clay, depth, years)
        out["annual_delta_tC_ha_yr"] = [p - b for p, b in zip(out["project_soc"], out["baseline_soc"])]
        out["assumptions"].append(f"baseline: management of {b_year} under the same climate")
    return out


async def monitoring_report(tenant_id: str, parcel_id: str, standard: str,
                            from_year: Optional[int], to_year: Optional[int]) -> dict:
    short, urn = parcel_short(parcel_id), canonical_parcel_urn(parcel_id)
    rows = await list_campaigns(tenant_id, parcel_id)
    if rows:
        to_year = to_year or rows[-1]["campaign_label"]
        from_year = from_year or to_year
    chosen = [r for r in rows if from_year is not None and from_year <= r["campaign_label"] <= to_year]
    baseline = None
    b_year = await _baseline_year(tenant_id, short)
    b_row = next((r for r in rows if r["campaign_label"] == b_year and _usable(r) and is_complete(r)), None)
    if b_row is not None:
        inputs = months_from_row(b_row)
        deltas: dict[int, Optional[float]] = {}
        n2o: dict[int, Optional[float]] = {}
        for r in chosen:
            start = await _start_state(tenant_id, short, r) if _usable(r) else None
            if start is None:
                deltas[r["campaign_label"]] = None
                continue
            months = combine_months(months_from_row(r), inputs)
            clay, depth = float(r["soil_clay_pct"]), float(r.get("soil_depth_cm") or 30.0)
            deltas[r["campaign_label"]] = run_months(start, months, clay, depth).final.pools.total - start.pools.total
            if is_complete(r):
                n2o[r["campaign_label"]] = b_row.get("n2o_emissions")
        baseline = {"reference_year": b_year, "delta_soc_by_year": deltas, "n2o_by_year": n2o}
    return build_monitoring_report(tenant_id, urn, standard, chosen, baseline)
