"""Mass conservation and monotonicity of the official RothC step (spec 12.3, 12.4).

sum(inputs) - sum(CO2) - delta_SOC = 0 for every input type, and more organic
amendment never lowers the final SOC.
"""
import pytest

from app.services.roth_c_model import RothCMonth, RothCState, run_months, weihermuller_pools

TEMPS = [3.8, 4.2, 6.0, 8.2, 11.5, 14.8, 16.8, 16.5, 13.8, 10.2, 6.5, 4.5]
RAIN = [55, 42, 47, 50, 52, 55, 52, 58, 55, 62, 60, 57]
PAN = [7, 16, 40, 67, 109, 136, 149, 127, 80, 40, 16, 7]


def _months(years, plant, fym, dpm_rpm=1.44):
    return [RothCMonth(TEMPS[m], RAIN[m], PAN[m], m not in (7, 8), plant, dpm_rpm, fym)
            for _ in range(years) for m in range(12)]


@pytest.mark.parametrize("years", [1, 5, 10, 20])
@pytest.mark.parametrize("plant,fym,ratio", [(0.2, 0.0, 1.44), (0.0, 0.25, 1.44), (0.15, 0.1, 0.67), (0.0, 0.0, 1.44)])
def test_mass_balance_closes(years, plant, fym, ratio):
    start = RothCState(weihermuller_pools(45.0, 22.0), 0.0)
    run = run_months(start, _months(years, plant, fym, ratio), 22.0, 23.0)
    inputs = (plant + fym) * 12 * years
    assert abs(inputs - sum(run.co2) - (run.final.pools.total - start.pools.total)) < 1e-9


def test_more_amendment_never_lowers_soc():
    start = RothCState(weihermuller_pools(45.0, 22.0), 0.0)
    finals = [run_months(start, _months(10, 0.1, f), 22.0, 23.0).final.pools.total
              for f in (0.0, 0.05, 0.1, 0.2, 0.4)]
    assert finals == sorted(finals)


def test_iom_never_changes():
    start = RothCState(weihermuller_pools(45.0, 22.0), 0.0)
    run = run_months(start, _months(20, 0.2, 0.1), 22.0, 23.0)
    assert all(s.pools.iom == start.pools.iom for s in run.states)
