"""Carbon balance of one parcel over one campaign (1 Jan - 31 Dec), from real series only.

Pure and deterministic. Every quantity comes from the inputs or is reported in
``missing`` with the reason and what it blocks; nothing is defaulted.

Accounting is by time: the campaign holds what happens between 1 January and
``computed_through``. A crop cycle that crosses the year contributes to each
campaign the days that fall in it, and returns its biomass to the soil (minus
what was exported) in the month it ends, with everything it grew since sowing.
"""

from __future__ import annotations

import calendar
import math
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, timedelta
from statistics import NormalDist
from typing import Optional

import numpy as np

from app.services.campaign_types import (
    CampaignBalance, CampaignInputs, CycleResult, CycleSpan, Missing, MonthResult,
)
from app.services.ghg_model import N2OInputs, compute_n2o
from app.services.ndvi_series import interpolate_daily
from app.services.roth_c_model import (
    RothCMonth, RothCState, pan_evap_from_et0, run_months, weihermuller_pools,
)

ENGINE_VERSION = "3.2.0"

PAR_FRACTION = 0.48          # PAR share of global radiation
CUE = 0.5                    # NPP / GPP
EXUDATE_FRACTION = 0.07      # share of NPP released as root exudates (Pausch & Kuzyakov 2018)
FAPAR_MAX = 0.95
MATCH_DAYS = 60              # harvest/baling matched to a cycle end within this window
MAX_VI_GAP_DAYS = 60
# NDVI at or above this is green vegetation, not bare soil (bare soil is ~0.1-0.2).
GREEN_NDVI = 0.3
SIGMA_REL = {"par": 0.10, "fapar": 0.08, "lue": 0.15}
LHS_SAMPLES = 500
G_M2_TO_T_HA = 0.01
C_TO_CO2 = 44.0 / 12.0

_REL_SIGMA_GPP = math.sqrt(sum(v * v for v in SIGMA_REL.values()))

# End dates that are an intention, not a fact: once passed, the cycle is still open.
_UNCONFIRMED_END = {"planned", "default"}


@dataclass
class _CycleAcc:
    span: CycleSpan
    assigned: int = 0           # all days given to the cycle, whole cycle
    computed: int = 0
    in_period: int = 0
    computed_in_period: int = 0
    npp_period_g: float = 0.0
    shoot_g: float = 0.0        # whole cycle
    root_g: float = 0.0         # whole cycle, net of exudates


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def computed_through(year: int, today: date, weather) -> Optional[date]:
    """Last day of the last complete month of daily weather before ``today`` (None: none yet)."""
    return _computed_through(year, today, {w.day: w for w in weather})


def _computed_through(year: int, today: date, by_day: dict) -> Optional[date]:
    last = None
    for month in range(1, 13):
        end = _month_end(year, month)
        if end >= today:
            break
        d = date(year, month, 1)
        while d <= end:
            w = by_day.get(d)
            if w is None or not w.complete:
                return last
            d += timedelta(days=1)
        last = end
    return last


def _days(first: date, last: date) -> list[date]:
    return [first + timedelta(days=i) for i in range((last - first).days + 1)] if last >= first else []


def _empty(inp: CampaignInputs, missing: list[Missing], assumptions: list[str]) -> CampaignBalance:
    last = min(date(inp.year, 12, 31), inp.today - timedelta(days=1))
    irrigated_value, irrigated_source = _irrigation(inp, date(inp.year, 1, 1), last)
    return CampaignBalance(
        year=inp.year, period_start=date(inp.year, 1, 1), period_end=date(inp.year, 12, 31),
        computed_through=None, tier=0, cover_days=0, bare_days=0, gpp_tC_ha=None, npp_tC_ha=None,
        co2_gross_tCO2_ha=None, tier1_coverage=0.0, rh_tC_ha=None, soc_start_tC_ha=None,
        soc_end_tC_ha=None, delta_soc_tC_ha=None, nee_tCO2_ha=None, necb_tC_ha=None, n2o_tCO2eq_ha=None,
        co2eq_net_tCO2eq_ha=None, gpp_ci95_pct=None, delta_soc_ci95_tC_ha=None, end_state=None,
        initial_state_source=inp.initial_state_source, cycles=(), months=(),
        missing=tuple(missing), assumptions=tuple(assumptions),
        inputs_summary=_inputs_summary(inp, [], None, [], irrigated_value, irrigated_source),
    )


def compute_campaign_balance(inp: CampaignInputs) -> CampaignBalance:
    year = inp.year
    p_start, p_end = date(year, 1, 1), date(year, 12, 31)
    missing: list[Missing] = list(inp.missing_in)
    assumptions: list[str] = [
        f"GPP uncertainty from relative sigmas PAR {SIGMA_REL['par']:.0%}, fAPAR {SIGMA_REL['fapar']:.0%}, "
        f"LUE {SIGMA_REL['lue']:.0%} (model assumptions)",
        "soil-property uncertainty not included",
    ]
    by_day = {w.day: w for w in inp.weather}

    through = _computed_through(year, inp.today, by_day)
    if through is None:
        missing.append(Missing("weather", "no complete month of daily weather in the campaign", "no_balance"))
        return _empty(inp, missing, assumptions)

    # -- cycles that count -------------------------------------------------
    cycles: list[CycleSpan] = []
    for c in inp.cycles:
        if c.end is not None and c.end < c.start:
            missing.append(Missing("cycle", f"{c.crop_id}: end before start", "ignored"))
            continue
        # An end that is only an intention and has passed: the cycle is still open (also in the
        # following years), and without its real end its residue cannot enter: no soil balance.
        if c.end is not None and c.end <= through and c.end_provenance in _UNCONFIRMED_END:
            missing.append(Missing("cycle_end", f"{c.crop_id}: planned end {c.end.isoformat()} passed without "
                                   "a recorded end", "tier2_unavailable"))
            c = replace(c, end=None)
        if c.start > through or (c.end is not None and c.end < p_start):
            continue
        if c.start_provenance == "planned":
            missing.append(Missing("cycle_start", f"{c.crop_id}: start is a planned date, not confirmed",
                                   "uses_planned_date"))
        cycles.append(c)
    if not cycles:
        missing.append(Missing("cycles", "no crop cycle in the period: soil counted as bare", "bare_soil_assumed"))

    first_day = min([p_start] + [c.start for c in cycles])
    all_days = _days(first_day, through)
    period_days = _days(p_start, through)
    vi = interpolate_daily(inp.ndvi, all_days, MAX_VI_GAP_DAYS)
    vi_by_index = {"NDVI": vi, "OSAVI": interpolate_daily(inp.osavi, all_days, MAX_VI_GAP_DAYS)}

    # one producing cycle per day: the latest started among those covering it
    def covering(d: date) -> Optional[CycleSpan]:
        best = None
        for c in cycles:
            if c.start <= d <= (c.end or through):
                if best is None or (c.start, c.crop_id) > (best.start, best.crop_id):
                    best = c
        return best

    accs = {c.crop_id: _CycleAcc(c) for c in cycles}
    exudates_by_month: dict[int, float] = defaultdict(float)
    cover_by_month: dict[int, int] = defaultdict(int)
    gpp_g = npp_g = 0.0
    cycle_days_period = computed_days_period = 0
    no_vi_days: dict[str, int] = defaultdict(int)

    for d in all_days:
        c = covering(d)
        if c is None:
            continue
        acc = accs[c.crop_id]
        acc.assigned += 1
        in_period = d >= p_start
        if in_period:
            acc.in_period += 1
            cycle_days_period += 1
            cover_by_month[d.month] += 1
        w = by_day.get(d)
        v = vi_by_index.get(c.params.vi_type, {}).get(d) if c.params is not None else None
        if c.params is None or v is None or w is None or w.radiation_mj_m2 is None:
            if c.params is not None and v is None and in_period:
                no_vi_days[c.params.vi_type] += 1
            continue
        fapar = max(0.0, min(FAPAR_MAX, c.params.fapar_a * v + c.params.fapar_b))
        gpp = PAR_FRACTION * w.radiation_mj_m2 * fapar * c.params.lue_gC_MJ
        npp = CUE * gpp
        acc.computed += 1
        acc.shoot_g += npp * (1.0 - c.params.root_fraction)
        acc.root_g += npp * (c.params.root_fraction - EXUDATE_FRACTION)
        if in_period:
            acc.computed_in_period += 1
            acc.npp_period_g += npp
            computed_days_period += 1
            gpp_g += gpp
            npp_g += npp
            exudates_by_month[d.month] += npp * EXUDATE_FRACTION * G_M2_TO_T_HA

    # Cover comes from the cycles; NDVI only contrasts it (spec D2).
    green_bare = sum(1 for d in period_days if covering(d) is None and (vi.get(d) or 0.0) >= GREEN_NDVI)
    if green_bare:
        missing.append(Missing("cover_mismatch",
                               f"NDVI shows vegetation on {green_bare} days counted as bare soil",
                               "cover_uncertain"))

    tier1_coverage = computed_days_period / cycle_days_period if cycle_days_period else 1.0
    # Days without the index each cycle is calibrated on, named per index so the
    # user knows which one to compute (woody crops need OSAVI, not NDVI).
    for vi_type, n in sorted(no_vi_days.items()):
        missing.append(Missing(vi_type.lower(), f"{n} cycle days without {vi_type} within {MAX_VI_GAP_DAYS} days",
                               "tier1_partial"))

    # -- cycle closures ------------------------------------------------------
    harvests_of = _assign_events(inp.harvests, cycles)
    balings_of = _assign_events(inp.balings, cycles)
    closure_by_month: dict[int, float] = defaultdict(float)
    cycle_results: list[CycleResult] = []
    tier2_blocked = any(m.effect == "tier2_unavailable" for m in missing)
    for acc in accs.values():
        c = acc.span
        exported: Optional[float] = None
        c_to_soil: Optional[float] = acc.npp_period_g * EXUDATE_FRACTION * G_M2_TO_T_HA
        closes = c.end is not None and p_start <= c.end <= through
        if c.lifecycle == "perennial":
            missing.append(Missing("perennial_litter", f"{c.crop_id}: pruning and litter inputs not known",
                                   "tier2_unavailable"))
            tier2_blocked = True
        if closes:
            closure, exported, gaps = _closure(acc, inp, harvests_of.get(c.crop_id, []),
                                               balings_of.get(c.crop_id, []))
            missing.extend(gaps)
            if closure is None:
                tier2_blocked = True
                c_to_soil = None
            else:
                closure_by_month[c.end.month] += closure
                c_to_soil += closure
        cycle_results.append(CycleResult(
            crop_id=c.crop_id, species=c.species, role=c.role, start=c.start, end=c.end,
            start_provenance=c.start_provenance, end_provenance=c.end_provenance,
            campaign_label=c.campaign_label, days_in_period=acc.in_period,
            days_computed=acc.computed_in_period, npp_tC_ha=acc.npp_period_g * G_M2_TO_T_HA,
            c_to_soil_tC_ha=c_to_soil, exported_c_tC_ha=exported,
        ))
    cycle_results.sort(key=lambda r: (r.start, r.crop_id))

    # -- amendments ----------------------------------------------------------
    fym_by_month, fym_gaps, fym_note = _amendments(inp, through)
    missing.extend(fym_gaps)
    if fym_gaps:
        tier2_blocked = True
    if fym_note:
        assumptions.append(fym_note)

    # -- monthly series --------------------------------------------------------
    months: list[MonthResult] = []
    for month in range(1, through.month + 1):
        days = [by_day[d] for d in _days(date(year, month, 1), _month_end(year, month))]
        n = len(days)
        cover = cover_by_month.get(month, 0)
        months.append(MonthResult(
            month=month,
            temp_c=sum((w.tmin_c + w.tmax_c) / 2.0 for w in days) / n,
            rain_mm=sum(w.precip_mm for w in days),
            et0_mm=sum(w.et0_mm for w in days),
            covered=cover * 2 >= n,
            cover_days=cover,
            plant_c_tC_ha=exudates_by_month.get(month, 0.0) + closure_by_month.get(month, 0.0),
            fym_c_tC_ha=fym_by_month.get(month, 0.0),
            co2_c_tC_ha=None,
        ))

    cover_days = sum(cover_by_month.values())
    tier1_ok = tier1_coverage > 0
    gpp_t = gpp_g * G_M2_TO_T_HA if (computed_days_period or not cycle_days_period) else None
    npp_t = npp_g * G_M2_TO_T_HA if gpp_t is not None else None

    # -- Tier 2: RothC -------------------------------------------------------
    rh = soc_start = soc_end = delta = ci_soc = None
    end_state: Optional[RothCState] = None
    if inp.soil is not None and tier1_coverage == 1.0 and not tier2_blocked:
        if inp.initial_state is not None:
            start_state = inp.initial_state
        else:
            start_state = RothCState(weihermuller_pools(inp.soil.soc_tC_ha, inp.soil.clay_pct), 0.0)
            assumptions.append("initial pools from the soil SOC stock (Weihermüller 2013), no moisture deficit on 1 Jan")
        rmonths = [_rothc_month(m) for m in months]
        run = run_months(start_state, rmonths, inp.soil.clay_pct, inp.soil.depth_cm)
        months = [_with_co2(m, co2) for m, co2 in zip(months, run.co2)]
        rh = sum(run.co2)
        soc_start, soc_end = start_state.pools.total, run.final.pools.total
        delta = soc_end - soc_start
        end_state = run.final
        ci_soc = _delta_soc_ci(start_state, rmonths, inp.soil.clay_pct, inp.soil.depth_cm)

    # -- Tier 3: N2O and NEE ---------------------------------------------------
    nee = necb = n2o = net = None
    irrigated_value, irrigated_source = _irrigation(inp, p_start, through)
    if rh is not None and npp_t is not None:
        n_syn, n_org, n_gaps = _nitrogen(inp, through)
        missing.extend(n_gaps)
        if not n_gaps and not any(m.effect == "tier3_unavailable" for m in missing):
            rain = sum(m.rain_mm for m in months)
            et0 = sum(m.et0_mm for m in months)
            irrigated = bool(irrigated_value)
            if irrigated_value is None:
                assumptions.append("no irrigation recorded or declared: N2O water regime treated as rainfed")
            res = compute_n2o(N2OInputs(
                n_applied_synthetic_kgN_ha_yr=n_syn, n_applied_organic_kgN_ha_yr=n_org,
                precip_annual_mm=rain, etp_annual_mm=et0, irrigated=irrigated, wet_climate=rain > et0,
            ))
            if through < p_end:
                assumptions.append("N2O water regime from the computed months only")
            n2o = res.n2o_co2eq_tCO2eq_ha_yr
            nee = -(npp_t - rh) * C_TO_CO2
            exported = sum(r.exported_c_tC_ha or 0.0 for r in cycle_results if r.end and r.end <= through)
            imported = sum(m.fym_c_tC_ha for m in months)
            necb = npp_t - rh - exported + imported
            # Exported harvest is respired off the farm: the net balance is NECB-based.
            net = -necb * C_TO_CO2 + n2o

    tier = 3 if net is not None else 2 if delta is not None else 1 if tier1_ok else 0
    summary = _inputs_summary(inp, period_days, through, cycle_results, irrigated_value, irrigated_source)
    return CampaignBalance(
        year=year, period_start=p_start, period_end=p_end, computed_through=through, tier=tier,
        cover_days=cover_days, bare_days=len(period_days) - cover_days,
        gpp_tC_ha=gpp_t, npp_tC_ha=npp_t,
        co2_gross_tCO2_ha=npp_t * C_TO_CO2 if npp_t is not None else None,
        tier1_coverage=tier1_coverage, rh_tC_ha=rh, soc_start_tC_ha=soc_start, soc_end_tC_ha=soc_end,
        delta_soc_tC_ha=delta, nee_tCO2_ha=nee, necb_tC_ha=necb, n2o_tCO2eq_ha=n2o, co2eq_net_tCO2eq_ha=net,
        gpp_ci95_pct=1.96 * _REL_SIGMA_GPP * 100.0 if gpp_t else None,
        delta_soc_ci95_tC_ha=ci_soc, end_state=end_state,
        initial_state_source=inp.initial_state_source if inp.initial_state is not None else "soil",
        cycles=tuple(cycle_results), months=tuple(months), missing=tuple(missing),
        assumptions=tuple(assumptions), inputs_summary=summary,
    )


def _irrigation(inp: CampaignInputs, first: date, last: date) -> tuple[Optional[bool], Optional[str]]:
    """Recorded irrigation operations first, the declaration only without records; else unknown."""
    if any(first <= i.day <= last for i in inp.irrigations):
        return True, "operations"
    if inp.declared.irrigated is not None:
        return inp.declared.irrigated, "declared"
    return None, None


# Roles that are not harvested: without a harvest record their biomass stays on the field.
_UNHARVESTED_ROLES = {"cover_crop", "catch_crop"}


def _assign_events(events, cycles) -> dict[str, list]:
    """Each harvest/baling belongs to one cycle: the started cycle whose end is nearest."""
    out: dict[str, list] = defaultdict(list)
    for ev in events:
        best = None
        for c in cycles:
            if c.end is None or c.start > ev.day or abs((ev.day - c.end).days) > MATCH_DAYS:
                continue
            key = (abs((ev.day - c.end).days), -c.start.toordinal())
            if best is None or key < best[0]:
                best = (key, c.crop_id)
        if best is not None:
            out[best[1]].append(ev)
    return out


def _closure(acc: _CycleAcc, inp: CampaignInputs, harvests: list, balings: list,
             ) -> tuple[Optional[float], Optional[float], list[Missing]]:
    """C returned to the soil when the cycle ends (tC/ha), the C exported, and the gaps."""
    c = acc.span
    gaps: list[Missing] = []
    if acc.computed < acc.assigned:
        gaps.append(Missing("cycle_biomass", f"{c.crop_id}: {acc.assigned - acc.computed} cycle days without data",
                            "tier2_unavailable"))
        return None, None, gaps
    shoot = acc.shoot_g * G_M2_TO_T_HA
    root = acc.root_g * G_M2_TO_T_HA
    if harvests:
        if any(h.exported_c_tC_ha is None for h in harvests):
            frac = inp.declared.harvest_export_fraction
            if frac is None:
                gaps.append(Missing("harvest_export", f"{c.crop_id}: exported harvest unknown", "tier2_unavailable"))
                return None, None, gaps
            exported = shoot * frac
        else:
            exported = sum(h.exported_c_tC_ha for h in harvests)
    elif c.role in _UNHARVESTED_ROLES:
        exported = 0.0
    elif inp.declared.harvest_export_fraction is not None:
        exported = shoot * inp.declared.harvest_export_fraction
    else:
        gaps.append(Missing("harvest_export", f"{c.crop_id}: no harvest record near the cycle end",
                            "tier2_unavailable"))
        return None, None, gaps
    exported = min(exported, shoot)
    residue = shoot - exported
    if balings:
        frac = inp.declared.residue_removal_fraction
        if frac is None:
            gaps.append(Missing("residue_removal", f"{c.crop_id}: baled, removed share not declared",
                                "tier2_unavailable"))
            return None, exported, gaps
        removed = residue * frac
        residue -= removed
        exported += removed
    return root + residue, exported, gaps


def _amendments(inp: CampaignInputs, through: date) -> tuple[dict[int, float], list[Missing], Optional[str]]:
    declared = inp.declared.organic_amendments_tC_ha_yr
    organic = [f for f in inp.fertilizations if f.organic and f.day.year == inp.year and f.day <= through]
    if organic:
        if declared is None:
            return {}, [Missing("organic_c", "organic fertilization without declared carbon", "tier2_unavailable")], None
        months = sorted({f.day.month for f in organic})
        return {m: declared / len(months) for m in months}, [], None
    if declared:
        return ({m: declared / 12.0 for m in range(1, through.month + 1)}, [],
                "declared organic amendments spread evenly over the months")
    return {}, [], None


def _nitrogen(inp: CampaignInputs, through: date) -> tuple[float, float, list[Missing]]:
    events = [f for f in inp.fertilizations if f.day.year == inp.year and f.day <= through]
    if events:
        if any(f.n_kg_ha is None for f in events):
            return 0.0, 0.0, [Missing("fertilizer_n", "a fertilization without known N", "tier3_unavailable")]
        return (sum(f.n_kg_ha for f in events if not f.organic),
                sum(f.n_kg_ha for f in events if f.organic), [])
    d = inp.declared
    if d.n_synthetic_kgN_ha_yr is not None or d.n_organic_kgN_ha_yr is not None:
        share = through.month / 12.0
        return (float(d.n_synthetic_kgN_ha_yr or 0.0) * share, float(d.n_organic_kgN_ha_yr or 0.0) * share, [])
    return 0.0, 0.0, [Missing("fertilizer_n", "no fertilization recorded or declared", "tier3_unavailable")]


def _rothc_month(m: MonthResult) -> RothCMonth:
    return RothCMonth(temp_c=m.temp_c, rain_mm=m.rain_mm, pan_evap_mm=pan_evap_from_et0(m.et0_mm),
                      plant_cover=m.covered, plant_c=m.plant_c_tC_ha, fym_c=m.fym_c_tC_ha)


def _with_co2(m: MonthResult, co2: float) -> MonthResult:
    return MonthResult(m.month, m.temp_c, m.rain_mm, m.et0_mm, m.covered, m.cover_days,
                       m.plant_c_tC_ha, m.fym_c_tC_ha, co2)


def _delta_soc_ci(start: RothCState, months: list[RothCMonth], clay: float, depth: float) -> float:
    """Half-width of the 95 % interval of the SOC change from plant-input uncertainty (LHS)."""
    rng = np.random.default_rng(0)
    u = (rng.permutation(LHS_SAMPLES) + rng.uniform(size=LHS_SAMPLES)) / LHS_SAMPLES
    nd = NormalDist(1.0, _REL_SIGMA_GPP)
    deltas = []
    for ui in u:
        k = max(0.0, nd.inv_cdf(min(max(ui, 1e-9), 1 - 1e-9)))
        scaled = [RothCMonth(m.temp_c, m.rain_mm, m.pan_evap_mm, m.plant_cover, m.plant_c * k, m.dpm_rpm, m.fym_c)
                  for m in months]
        deltas.append(run_months(start, scaled, clay, depth).final.pools.total - start.pools.total)
    lo, hi = np.percentile(deltas, [2.5, 97.5])
    return float((hi - lo) / 2.0)


def _vi_summary(series, first: date, last: date) -> Optional[dict]:
    if last < first:  # 1 January: no period yet
        return None
    dates = sorted({d for d, _ in series if first - timedelta(days=MAX_VI_GAP_DAYS) <= d <= last + timedelta(days=MAX_VI_GAP_DAYS)})
    if not dates:
        return None
    # Longest stretch of the period without a scene, the period edges included.
    points = sorted({first, last} | {d for d in dates if first <= d <= last})
    gaps = [(b - a).days for a, b in zip(points, points[1:])]
    return {"scenes": len(dates), "first": dates[0].isoformat(), "last": dates[-1].isoformat(),
            "max_gap_days": max(gaps) if gaps else None}


def _inputs_summary(inp: CampaignInputs, period_days: list, through: Optional[date], cycle_results,
                    irrigated_value, irrigated_source) -> dict:
    """What entered the balance and where it came from (shown to the user as-is)."""
    by_source: dict[str, int] = defaultdict(int)
    weather = {w.day: w for w in inp.weather}
    for d in period_days:
        w = weather.get(d)
        if w is not None:
            by_source[w.source or "unknown"] += 1
    first = date(inp.year, 1, 1)
    last = through or min(date(inp.year, 12, 31), inp.today - timedelta(days=1))
    vi = {}
    for name, series in (("NDVI", inp.ndvi), ("OSAVI", inp.osavi)):
        summary = _vi_summary(series, first, last)
        if summary:
            vi[name] = summary
    ops = []
    for h in inp.harvests:
        ops.append({"type": "harvest", "date": h.day.isoformat(), "exported_c_tC_ha": h.exported_c_tC_ha})
    for f in inp.fertilizations:
        ops.append({"type": "fertilization", "date": f.day.isoformat(), "n_kg_ha": f.n_kg_ha, "organic": f.organic})
    for t in inp.tillages:
        ops.append({"type": "tillage", "date": t.day.isoformat(), "tillage_type": t.tillage_type})
    for b in inp.balings:
        ops.append({"type": "baling", "date": b.day.isoformat()})
    for i in inp.irrigations:
        ops.append({"type": "irrigation", "date": i.day.isoformat(), "water_mm": i.water_mm})
    # Only the operations of the period the balance covers.
    ops = [o for o in ops if first.isoformat() <= o["date"] <= last.isoformat()]
    ops.sort(key=lambda o: (o["date"], o["type"]))
    soil = None
    if inp.soil is not None:
        soil = {"source": inp.soil.source, "soc_tC_ha": inp.soil.soc_tC_ha, "clay_pct": inp.soil.clay_pct,
                "depth_cm": inp.soil.depth_cm}
    return {
        "weather_days_by_source": dict(by_source),
        "vi": vi,
        "soil": soil,
        "operations": ops,
        "irrigated": {"value": irrigated_value, "source": irrigated_source},
    }
