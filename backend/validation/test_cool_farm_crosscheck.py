"""Cross-check against Cool Farm Tool expected ranges (spec 12.2).

5 typical Mediterranean agricultural scenarios.
Validates that RothC NEE is within physically reasonable ranges
and that scenario rankings are correct.

Scenarios calibrated for Mediterranean climate with realistic C inputs.
"""

import pytest

from app.services.roth_c_model import (
    MonthlyInputs,
    init_pools_weihermuller,
    run_rothc_monthly,
)

SCENARIOS = {
    "cereal_dryland": {
        "label": "Cereal dryland (wheat, conventional tillage)",
        "soc_initial_tC_ha": 40.0, "clay_pct": 18.0,
        "c_aerea_active": 0.25, "c_raices_active": 0.12,
        "c_aerea_bare": 0.03, "c_raices_bare": 0.01,
        "irrigated": False, "cover_months": [11,12,1,2,3,4,5,6],
        "expected_nee_range": (-0.5, 0.3),  # near-neutral to small source
    },
    "cereal_irrigated": {
        "label": "Cereal irrigated (corn, conventional)",
        "soc_initial_tC_ha": 45.0, "clay_pct": 20.0,
        "c_aerea_active": 0.40, "c_raices_active": 0.18,
        "c_aerea_bare": 0.03, "c_raices_bare": 0.01,
        "irrigated": True, "cover_months": [4,5,6,7,8,9],
        "expected_nee_range": (-0.8, 0.2),
    },
    "olive_traditional": {
        "label": "Traditional olive (extensive, 100 trees/ha, rainfed)",
        "soc_initial_tC_ha": 35.0, "clay_pct": 25.0,
        "c_aerea_active": 0.10, "c_raices_active": 0.04,
        "c_aerea_bare": 0.0, "c_raices_bare": 0.0,
        "irrigated": False, "cover_months": list(range(1,13)),  # evergreen
        "expected_nee_range": (-1.5, -0.2),  # weak to moderate sink
    },
    "olive_intensive": {
        "label": "Intensive olive (irrigated, 400 trees/ha, cover crop)",
        "soc_initial_tC_ha": 30.0, "clay_pct": 22.0,
        "c_aerea_active": 0.30, "c_raices_active": 0.10,
        "c_aerea_bare": 0.0, "c_raices_bare": 0.0,
        "irrigated": True, "cover_months": list(range(1,13)),
        "expected_nee_range": (-2.0, -0.3),  # moderate sink
    },
    "vineyard": {
        "label": "Vineyard (trellised, cover crop inter-row)",
        "soc_initial_tC_ha": 32.0, "clay_pct": 20.0,
        "c_aerea_active": 0.20, "c_raices_active": 0.08,
        "c_aerea_bare": 0.05, "c_raices_bare": 0.02,
        "irrigated": False, "cover_months": [3,4,5,6,7,8,9,10],
        "expected_nee_range": (-1.8, -0.2),
    },
}


def _run_scenario(scenario: dict, years: int = 20) -> dict:
    """Run a scenario and return modeled results."""
    pools = init_pools_weihermuller(
        scenario["soc_initial_tC_ha"], scenario["clay_pct"]
    )
    clay = scenario["clay_pct"]

    # Mediterranean climate template
    temps = [9, 10, 13, 15, 19, 24, 27, 27, 23, 18, 13, 10]
    precip = [50, 45, 40, 45, 35, 15, 5, 8, 30, 65, 60, 55]
    etp = [20, 30, 60, 90, 130, 170, 200, 180, 120, 70, 30, 20]

    monthly = []
    for year in range(years):
        for month in range(1, 13):
            t = temps[month - 1]
            p = precip[month - 1]
            e = etp[month - 1]
            cover = month in scenario["cover_months"]

            c_aerea = scenario["c_aerea_active"] if cover else scenario["c_aerea_bare"]
            c_raices = scenario["c_raices_active"] if cover else scenario["c_raices_bare"]

            if scenario["irrigated"]:
                # Supplement rainfall during dry months
                if month in [5, 6, 7, 8, 9]:
                    p = max(p, 80)  # supplemental irrigation
                e = min(e * 1.1, 220)  # slightly higher ETp with full canopy

            monthly.append(MonthlyInputs(
                temp_celsius=t, precip_mm=p, etp_mm=e,
                cover_present=cover,
                c_input_aerea_tC_ha=c_aerea,
                c_input_raices_tC_ha=c_raices,
                c_input_exudados_tC_ha=c_aerea * 0.07,
                clay_pct=clay,
            ))

    result = run_rothc_monthly(pools, monthly, clay)

    soc_initial = scenario["soc_initial_tC_ha"]
    soc_final = result.pools.total_tC_ha
    return {
        "soc_final_tC_ha": soc_final,
        "soc_delta_tC_ha_yr": (soc_final - soc_initial) / years,
        "rh_tC_ha_yr": result.rh_tC_ha_yr,
    }


class TestCoolFarmCrosscheck:
    """Cross-check RothC against expected CFT-like behavior."""

    @pytest.mark.parametrize("key", SCENARIOS.keys())
    def test_annual_nee_within_range(self, key: str):
        scenario = SCENARIOS[key]
        result = _run_scenario(scenario)
        delta = result["soc_delta_tC_ha_yr"]
        nee = -delta  # neg delta = sink = neg NEE
        lo, hi = scenario["expected_nee_range"]

        assert lo - 0.5 <= nee <= hi + 0.5, (
            f"{scenario['label']}: "
            f"modeled NEE = {nee:+.2f} tC/ha/yr, "
            f"expected range = [{lo:+.1f}, {hi:+.1f}]"
        )

    def test_irrigated_higher_soc_than_dryland(self):
        """Irrigated cereal should have higher SOC end state than dryland."""
        dry = _run_scenario(SCENARIOS["cereal_dryland"])
        irr = _run_scenario(SCENARIOS["cereal_irrigated"])
        assert irr["soc_final_tC_ha"] > dry["soc_final_tC_ha"], (
            f"Irrigated={irr['soc_final_tC_ha']:.1f} <= Dryland={dry['soc_final_tC_ha']:.1f}"
        )

    def test_intensive_olive_more_sink_than_traditional(self):
        """Intensive olive should sequester more than traditional."""
        trad = _run_scenario(SCENARIOS["olive_traditional"])
        intensive = _run_scenario(SCENARIOS["olive_intensive"])
        # Higher C inputs → more SOC
        assert intensive["soc_final_tC_ha"] > trad["soc_final_tC_ha"], (
            f"Intensive={intensive['soc_final_tC_ha']:.1f} <= "
            f"Traditional={trad['soc_final_tC_ha']:.1f}"
        )

    def test_all_scenarios_positive_soc(self):
        """All scenarios must maintain positive SOC."""
        for key, scenario in SCENARIOS.items():
            result = _run_scenario(scenario)
            assert result["soc_final_tC_ha"] > 0, (
                f"{key}: SOC went negative ({result['soc_final_tC_ha']:.1f})"
            )
