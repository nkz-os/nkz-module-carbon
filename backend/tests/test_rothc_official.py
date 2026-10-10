"""Golden test: our RothC must reproduce the official RothC_Py example."""
import csv
from pathlib import Path

import pytest

from app.services.roth_c_model import (
    RothCMonth, RothCPools, RothCState, equilibrium, run_months, step_month,
)

REF = Path(__file__).parent / "fixtures" / "rothc_reference"


def _read_input():
    lines = (REF / "RothC_input.dat").read_text().splitlines()
    clay, depth, iom, nsteps = lines[4].split()
    rows = [line.split() for line in lines[7:] if line.strip()]
    months = [
        RothCMonth(
            temp_c=float(r[3]), rain_mm=float(r[4]), pan_evap_mm=float(r[5]),
            plant_c=float(r[6]), fym_c=float(r[7]), plant_cover=int(r[8]) == 1,
            dpm_rpm=float(r[9]),
        )
        for r in rows
    ]
    return float(clay), float(depth), float(iom), int(nsteps), months


def _rel(a, b):
    return abs(a - b) / max(abs(b), 1e-12)


def test_equilibrium_matches_official_year_one():
    clay, depth, iom, _, months = _read_input()
    eq = equilibrium(months[:12], clay, depth, iom)
    ref = next(csv.DictReader((REF / "year_results.csv").open()))
    for key, val in (("DPM", eq.pools.dpm), ("RPM", eq.pools.rpm), ("BIO", eq.pools.bio),
                     ("HUM", eq.pools.hum), ("SOC", eq.pools.total)):
        assert _rel(val, float(ref[f"{key}_t_C_ha"])) < 1e-6, key


def test_monthly_run_matches_official_month_results():
    clay, depth, iom, nsteps, months = _read_input()
    state = equilibrium(months[:12], clay, depth, iom)
    run = run_months(state, months[12:nsteps], clay, depth)
    ref = list(csv.DictReader((REF / "month_results.csv").open()))
    assert len(ref) == len(run.states)
    for row, st in zip(ref, run.states):
        stamp = row["Year"] + "-" + row["Month"]
        assert _rel(st.pools.total, float(row["SOC_t_C_ha"])) < 1e-6, stamp
        assert _rel(st.pools.hum, float(row["HUM_t_C_ha"])) < 1e-6, stamp
        assert _rel(st.pools.bio, float(row["BIO_t_C_ha"])) < 1e-6, stamp
        assert _rel(st.pools.dpm, float(row["DPM_t_C_ha"])) < 1e-6, stamp


@pytest.mark.parametrize("plant_c,fym_c", [(0.5, 0.0), (0.0, 0.5), (0.3, 0.2)])
def test_step_conserves_mass(plant_c, fym_c):
    s0 = RothCState(RothCPools(0.2, 5.0, 0.7, 27.0, 3.0), swc_mm=0.0)
    m = RothCMonth(temp_c=12.0, rain_mm=40.0, pan_evap_mm=60.0, plant_cover=True,
                   plant_c=plant_c, fym_c=fym_c)
    s1, co2 = step_month(s0, m, clay_pct=20.0, depth_cm=23.0)
    assert abs((s0.pools.total + plant_c + fym_c - co2) - s1.pools.total) < 1e-12


def test_cold_month_does_not_decompose():
    s0 = RothCState(RothCPools(0.2, 5.0, 0.7, 27.0, 3.0), swc_mm=0.0)
    s1, co2 = step_month(s0, RothCMonth(-6.0, 30.0, 5.0, True), 20.0, 23.0)
    assert co2 == 0.0 and s1.pools == s0.pools


@pytest.mark.parametrize("soc,clay", [(40.0, 20.0), (12.0, 35.0), (80.0, 5.0)])
def test_weihermuller_keeps_the_measured_stock(soc, clay):
    from app.services.roth_c_model import weihermuller_pools
    p = weihermuller_pools(soc, clay)
    assert p.total == pytest.approx(soc, abs=1e-12)
    assert min(p.dpm, p.rpm, p.bio, p.hum, p.iom) >= 0.0
