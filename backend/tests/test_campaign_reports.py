import pytest

from app.services.campaign_reports import (
    CERTIFICATION_GAPS, build_monitoring_report, combine_months, months_from_row, project_soc,
)
from app.services.roth_c_model import RothCPools, RothCState, run_months


def _row(year, plant=0.1, fym=0.0, temp=12.0, tier=2, delta=0.5, n2o=None, net=None, through=None):
    months = [{"month": m, "temp_c": temp, "rain_mm": 50.0, "et0_mm": 60.0, "covered": m <= 6,
               "cover_days": 30 if m <= 6 else 0, "plant_c_tC_ha": plant, "fym_c_tC_ha": fym, "co2_c_tC_ha": 0.1}
              for m in range(1, 13)]
    return {"campaign_label": year, "computed_through": through or f"{year}-12-31", "data_tier": tier,
            "monthly_balance": months, "soil_carbon_delta": delta, "soc_start": 40.0, "soc_end": 40.0 + delta,
            "n2o_emissions": n2o, "co2eq_net": net, "soil_clay_pct": 20.0, "soil_depth_cm": 30.0,
            "data_sources": ["weather_api_daily"], "assumptions": [], "missing": []}


START = RothCState(RothCPools(0.2, 5.0, 0.8, 30.0, 3.0), 0.0)


def test_months_from_row_converts_et0_to_pan():
    m = months_from_row(_row(2025))[0]
    assert m.pan_evap_mm == pytest.approx(60.0 / 0.75) and m.plant_cover and m.plant_c == 0.1


def test_project_soc_repeats_reference_year():
    months = months_from_row(_row(2025))
    soc = project_soc(START, months, 20.0, 30.0, years=3)
    one = run_months(START, months, 20.0, 30.0).final
    assert len(soc) == 3 and soc[0] == pytest.approx(one.pools.total)


def test_combine_takes_climate_from_one_and_inputs_from_other():
    climate = months_from_row(_row(2026, temp=20.0))
    inputs = months_from_row(_row(2024, plant=0.3))
    mixed = combine_months(climate, inputs)
    assert mixed[0].temp_c == 20.0 and mixed[0].plant_c == 0.3


def test_report_without_baseline_has_no_reductions():
    r = build_monitoring_report("t", "urn:ngsi-ld:AgriParcel:p", "VM0042", [_row(2026, through="2026-09-30")],
                                baseline=None)
    assert r["report_type"] == "monitoring_estimate" and "not certified" in r["title"].lower()
    assert r["net_emission_reductions_tCO2eq_ha"] is None
    assert "baseline_not_defined" in r["certification_gaps"]
    assert r["reporting_period_start"] == "2026-01-01" and r["reporting_period_end"] == "2026-09-30"
    assert "verified_credits" not in r and "buffer_pool_pct" not in r


def test_report_with_baseline_compares_soc_change():
    rows = [_row(2025, delta=0.8), _row(2026, delta=0.6)]
    baseline = {"reference_year": 2024, "delta_soc_by_year": {2025: 0.3, 2026: 0.1}, "n2o_by_year": {}}
    r = build_monitoring_report("t", "urn:ngsi-ld:AgriParcel:p", "VM0042", rows, baseline=baseline)
    assert r["net_emission_reductions_tCO2eq_ha"] == pytest.approx(((0.8 - 0.3) + (0.6 - 0.1)) * 44 / 12)
    assert r["baseline_reference_year"] == 2024 and "baseline_not_defined" not in r["certification_gaps"]


def test_report_hash_is_stable_and_gaps_listed():
    rows = [_row(2026)]
    a = build_monitoring_report("t", "urn:ngsi-ld:AgriParcel:p", "VM0042", rows, None)
    b = build_monitoring_report("t", "urn:ngsi-ld:AgriParcel:p", "VM0042", rows, None)
    assert a["inputs_hash"] == b["inputs_hash"]
    assert set(CERTIFICATION_GAPS) <= set(a["certification_gaps"])
    assert "tier3_not_reached" in a["certification_gaps"]
