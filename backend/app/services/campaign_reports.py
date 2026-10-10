"""Projection and monitoring report built from stored campaign balances.

Nothing here invents inputs: the projection repeats a computed campaign, and the
baseline is a computed reference campaign replayed under each campaign's own
climate. The report is a monitoring estimate, not a certification.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from app.services.campaign_balance import ENGINE_VERSION
from app.services.roth_c_model import RothCMonth, RothCState, pan_evap_from_et0, run_months

C_TO_CO2 = 44.0 / 12.0

# What a monitoring estimate lacks to be certified (VM0042 / CRCF-style schemes).
CERTIFICATION_GAPS = (
    "baseline_soil_sampling",       # measured SOC at project start
    "periodic_soil_resampling",     # re-measurement during the project
    "third_party_verification",     # independent validation and verification
)


def months_from_row(row: dict) -> list[RothCMonth]:
    """RothC months of a stored campaign (its climate and its soil inputs)."""
    out = []
    for m in sorted(row.get("monthly_balance") or [], key=lambda x: x["month"]):
        out.append(RothCMonth(
            temp_c=float(m["temp_c"]), rain_mm=float(m["rain_mm"]),
            pan_evap_mm=pan_evap_from_et0(float(m["et0_mm"])), plant_cover=bool(m["covered"]),
            plant_c=float(m["plant_c_tC_ha"]), fym_c=float(m["fym_c_tC_ha"]),
        ))
    return out


def combine_months(climate: Sequence[RothCMonth], inputs: Sequence[RothCMonth]) -> list[RothCMonth]:
    """Climate of one campaign with the cover and soil inputs of another, month by month."""
    return [RothCMonth(c.temp_c, c.rain_mm, c.pan_evap_mm, i.plant_cover, i.plant_c, i.dpm_rpm, i.fym_c)
            for c, i in zip(climate, inputs)]


def project_soc(start: RothCState, months: Sequence[RothCMonth], clay: float, depth: float,
                years: int) -> list[float]:
    """SOC at the end of each year while the given year repeats."""
    soc, state = [], start
    for _ in range(years):
        state = run_months(state, months, clay, depth).final
        soc.append(state.pools.total)
    return soc


def is_complete(row: dict) -> bool:
    return str(row.get("computed_through") or "") == f"{row['campaign_label']}-12-31"


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def build_monitoring_report(
    tenant_id: str,
    parcel_urn: str,
    standard: str,
    rows: Sequence[dict],
    baseline: Optional[dict],
) -> dict:
    """Report over the given stored campaigns. ``baseline`` holds the replayed reference:
    {"reference_year": int, "delta_soc_by_year": {year: tC/ha}, "n2o_by_year": {year: tCO2eq/ha}}."""
    rows = sorted(rows, key=lambda r: r["campaign_label"])
    campaigns = []
    reductions: Optional[float] = 0.0 if baseline else None
    for r in rows:
        year = r["campaign_label"]
        entry = {
            "year": year, "computed_through": r.get("computed_through"), "tier": r.get("data_tier"),
            "delta_soc_tC_ha": r.get("soil_carbon_delta"), "n2o_tCO2eq_ha": r.get("n2o_emissions"),
            "co2eq_net_tCO2eq_ha": r.get("co2eq_net"), "missing": r.get("missing") or [],
        }
        if baseline is not None:
            b_delta = baseline["delta_soc_by_year"].get(year)
            entry["baseline_delta_soc_tC_ha"] = b_delta
            if b_delta is None or entry["delta_soc_tC_ha"] is None:
                reductions = None
            elif reductions is not None:
                reductions += (entry["delta_soc_tC_ha"] - b_delta) * C_TO_CO2
                b_n2o, p_n2o = baseline.get("n2o_by_year", {}).get(year), entry["n2o_tCO2eq_ha"]
                if b_n2o is not None and p_n2o is not None:
                    reductions -= p_n2o - b_n2o
        campaigns.append(entry)

    tiers = [r.get("data_tier") or 0 for r in rows]
    gaps = list(CERTIFICATION_GAPS)
    if baseline is None:
        gaps.append("baseline_not_defined")
    if not tiers or min(tiers) < 3:
        gaps.append("tier3_not_reached")
    if rows and not is_complete(rows[-1]):
        gaps.append("open_campaign")

    deltas = [r.get("soil_carbon_delta") for r in rows]
    nets = [r.get("co2eq_net") for r in rows]
    payload_rows = [{k: r.get(k) for k in ("campaign_label", "computed_through", "data_tier", "soil_carbon_delta",
                                           "n2o_emissions", "co2eq_net", "monthly_balance")} for r in rows]
    first, last = (rows[0]["campaign_label"], rows[-1]) if rows else (None, None)
    return {
        "report_id": f"MON-{standard}-{tenant_id}-{parcel_urn.rsplit(':', 1)[-1]}-{first}",
        "report_type": "monitoring_estimate",
        "title": "Monitoring estimate — not certified",
        "standard_structure": standard,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine_version": ENGINE_VERSION,
        "tenant_id": tenant_id,
        "parcel_id": parcel_urn,
        "reporting_period_start": f"{first}-01-01" if first else None,
        "reporting_period_end": last.get("computed_through") if last else None,
        "campaigns": campaigns,
        "total_delta_soc_tC_ha": sum(deltas) if rows and None not in deltas else None,
        "total_co2eq_net_tCO2eq_ha": sum(nets) if rows and None not in nets else None,
        "baseline_reference_year": baseline["reference_year"] if baseline else None,
        "net_emission_reductions_tCO2eq_ha": reductions,
        "tier": min(tiers) if tiers else 0,
        "data_sources": sorted({s for r in rows for s in (r.get("data_sources") or [])}),
        "assumptions": sorted({a for r in rows for a in (r.get("assumptions") or [])}),
        "certification_gaps": gaps,
        "inputs_hash": _hash({"rows": payload_rows, "baseline": baseline, "engine": ENGINE_VERSION}),
    }
