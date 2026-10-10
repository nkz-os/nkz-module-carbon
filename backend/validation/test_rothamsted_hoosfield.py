"""Hoosfield worked example of the official RothC description (Coleman & Jenkinson).

Plant inputs and manure are the published ones; the climate and the starting
equilibrium are those of the official RothC_Py example (Rothamsted).
  - unmanured: 1.60 tC/ha/yr (0.16 Apr, 0.32 May, 0.48 Jun, 0.64 Jul), cover Apr-Jul
  - FYM annually: plant 2.80 tC/ha/yr (same split) + FYM 3.0 tC/ha/yr in February
  - FYM 1852-1871 only, then the unmanured inputs
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from test_rothc_official import _read_input  # noqa: E402

from app.services.roth_c_model import RothCMonth, equilibrium, run_months  # noqa: E402

YEARS = 149  # 1852-2000
SPLIT = {4: 0.1, 5: 0.2, 6: 0.3, 7: 0.4}


def _scenario(plant_per_year, fym_feb, fym_years=None):
    clay, depth, iom, _, months = _read_input()
    climate = months[:12]
    start = equilibrium(climate, clay, depth, iom)
    series = []
    for y in range(YEARS):
        fym_now = fym_feb if fym_years is None or y < fym_years else 0.0
        plant = plant_per_year if fym_years is None or y < 25 else 1.60
        for i, c in enumerate(climate):
            month = i + 1
            series.append(RothCMonth(
                temp_c=c.temp_c, rain_mm=c.rain_mm, pan_evap_mm=c.pan_evap_mm,
                plant_cover=month in SPLIT, plant_c=plant * SPLIT.get(month, 0.0),
                fym_c=fym_now if month == 2 else 0.0,
            ))
    final = run_months(start, series, clay, depth).final.pools.total
    return start.pools.total, final


def test_unmanured_declines_below_the_pre_experiment_input():
    # The example's equilibrium carries 1.74 tC/ha/yr; 1.60 must end lower.
    start, final = _scenario(1.60, 0.0)
    assert final < start


def test_annual_fym_accumulates():
    start, final = _scenario(2.80, 3.0)
    assert final > start * 1.5


def test_fym_for_twenty_years_ends_between_the_two():
    _, unmanured = _scenario(1.60, 0.0)
    _, annual = _scenario(2.80, 3.0)
    _, twenty = _scenario(2.80, 3.0, fym_years=20)
    assert unmanured < twenty < annual


def test_all_positive():
    for args in ((1.60, 0.0), (2.80, 3.0)):
        assert _scenario(*args)[1] > 0
