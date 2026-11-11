import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from test_campaign_reports import START, _row  # noqa: E402
from test_campaign_runner import env  # noqa: E402,F401

from app.platform.weather_history_client import HistoryDay, HistoryResult  # noqa: E402
from app.services import campaign_runner as cr  # noqa: E402
from app.services.campaign_reports import (  # noqa: E402
    combine_months, months_from_row, project_soc, project_soc_ensemble, summarize,
)

BASELINE = {"id": "urn:ngsi-ld:BaselineScenario:t1:abc", "type": "BaselineScenario",
            "validFrom": {"type": "Property", "value": "2025-01-01"}}


def _years(temps):
    """One RothC climate year per temperature (12 identical months)."""
    ref = months_from_row(_row(2025))
    return [[m.__class__(t, m.rain_mm, m.pan_evap_mm, False) for m in ref] for t in temps]


def test_single_climate_year_equals_project_soc():
    ref = months_from_row(_row(2025))
    clim = [[m.__class__(m.temp_c, m.rain_mm, m.pan_evap_mm, False) for m in ref]]
    (traj,) = project_soc_ensemble(START, clim, ref, 20.0, 30.0, 5)
    assert traj == pytest.approx(project_soc(START, ref, 20.0, 30.0, 5))


def test_trajectory_s_year_k_uses_climate_index_s_plus_k_mod_n():
    clim = _years([5.0, 10.0, 15.0])
    inputs = months_from_row(_row(2025))
    trajs = project_soc_ensemble(START, clim, inputs, 20.0, 30.0, 4)
    assert len(trajs) == 3 and all(len(t) == 4 for t in trajs)
    from app.services.roth_c_model import run_months
    state, expect = START, []
    for k in range(4):
        state = run_months(state, combine_months(clim[(1 + k) % 3], inputs), 20.0, 30.0).final
        expect.append(state.pools.total)
    assert trajs[1] == pytest.approx(expect)


def test_summarize_percentiles_on_a_hand_made_set():
    trajs = [[float(v)] for v in range(1, 12)]  # 1..11, n=11
    med, lo, hi = summarize(trajs)
    assert med == [6.0]
    assert lo == pytest.approx([1.0 + 0.025 * 10])    # linear interpolation, position q*(n-1)
    assert hi == pytest.approx([1.0 + 0.975 * 10])
    med2, _, _ = summarize([[1.0, 4.0], [3.0, 8.0]])
    assert med2 == [2.0, 6.0]


def _hist(n_years=30, last=2025, ready=True, shift=0.0):
    days = []
    for i, y in enumerate(range(last - n_years + 1, last + 1)):
        d = date(y, 1, 1)
        while d.year == y:
            days.append(HistoryDay(d, 10.0 + (i % 5) + shift, 1.5, 2.0))
            d += timedelta(days=1)
    return HistoryResult(ready=ready, days=days, years_label=f"{last - n_years + 1}–{last}",
                         attribution="Copernicus", latest_available=date(last, 12, 31))


def _patch(monkeypatch, result):
    calls = []

    async def fake(urn, tenant, start, end, client=None):
        calls.append((urn, tenant, start, end))
        return result

    monkeypatch.setattr(cr, "fetch_climate_history", fake)
    return calls


@pytest.mark.asyncio
async def test_history_path_codes_climate_key_and_bands(env, monkeypatch):  # noqa: F811
    calls = _patch(monkeypatch, _hist())
    await cr.run_campaign("t1", "abc", 2025, today=date(2026, 10, 10))
    p = await cr.projection("t1", "abc", years=4)
    assert calls[0][2:] == (date(1996, 1, 1), date(2025, 12, 31))
    assert p["climate"] == {"source": "history", "years": "1996–2025", "n_years": 30,
                            "attribution": "Copernicus"}
    assert p["assumption_codes"][:2] == [{"code": "climate_history", "from": 1996, "to": 2025, "n": 30},
                                         {"code": "repeat_reference_management", "year": 2025}]
    assert len(p["assumptions"]) == len(p["assumption_codes"])
    assert not any(m["item"] == "climate_history" for m in p["missing"])
    assert len(p["project_soc"]) == 4
    for lo, med, hi in zip(p["project_soc_p025"], p["project_soc"], p["project_soc_p975"]):
        assert lo <= med <= hi
    assert any(hi > lo for lo, hi in zip(p["project_soc_p025"], p["project_soc_p975"]))
    assert p["baseline_soc_p025"] == [] and p["annual_delta_p025"] == []


@pytest.mark.asyncio
async def test_history_baseline_deltas_are_per_trajectory(env, monkeypatch):  # noqa: F811
    store, _ = env
    _patch(monkeypatch, _hist())
    await cr.run_campaign("t1", "abc", 2025, today=date(2026, 10, 10))
    store.entities[("t1", BASELINE["id"])] = BASELINE
    p = await cr.projection("t1", "abc", years=3)
    assert len(p["baseline_soc"]) == len(p["annual_delta_p025"]) == len(p["annual_delta_p975"]) == 3
    assert all(lo <= m <= hi for lo, m, hi in
               zip(p["annual_delta_p025"], p["annual_delta_tC_ha_yr"], p["annual_delta_p975"]))
    assert p["assumption_codes"][-1] == {"code": "baseline_same_climate", "year": 2025}


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [
    HistoryResult(ready=False, reason="weather-api answered 503"),
    HistoryResult(ready=False, reason="weather-api answered 401"),
    _hist(n_years=24),   # fewer than 25 complete years
])
async def test_fallback_keeps_today_behaviour_and_says_so(env, monkeypatch, result):  # noqa: F811
    _patch(monkeypatch, result)
    await cr.run_campaign("t1", "abc", 2025, today=date(2026, 10, 10))
    p = await cr.projection("t1", "abc", years=3)
    assert p["climate"] == {"source": "reference_campaign"}
    assert p["assumption_codes"][0] == {"code": "repeat_reference", "year": 2025}
    assert {"item": "climate_history", "reason": "parcel climate history not ready (being prepared)",
            "effect": "projection uses the reference campaign's climate"} in p["missing"]
    assert p["project_soc_p025"] == [] and p["project_soc_p975"] == []
    assert len(p["project_soc"]) == 3


@pytest.mark.asyncio
async def test_incomplete_current_year_is_excluded_not_mixed(env, monkeypatch):  # noqa: F811
    # 26 complete years plus a partial reference year: the partial year is dropped, 26 >= 25 still usable
    res = _hist(n_years=26, last=2024)
    partial = [HistoryDay(date(2025, 1, 1) + timedelta(days=i), 10.0, 1.0, 1.0) for i in range(100)]
    _patch(monkeypatch, HistoryResult(True, res.days + partial, "x", "c", date(2025, 4, 10)))
    await cr.run_campaign("t1", "abc", 2025, today=date(2026, 10, 10))
    p = await cr.projection("t1", "abc", years=2)
    assert p["climate"]["n_years"] == 26 and p["climate"]["years"] == "1999–2024"


@pytest.mark.asyncio
async def test_no_complete_campaign_does_not_fetch_history(env, monkeypatch):  # noqa: F811
    calls = _patch(monkeypatch, _hist())
    p = await cr.projection("t1", "abc", years=3)
    assert calls == [] and p["project_soc"] == []


def test_fifty_years_by_thirty_trajectories_stays_within_budget():
    ref = months_from_row(_row(2025))
    clim = _years([8.0 + 0.1 * i for i in range(30)])
    t0 = time.perf_counter()
    trajs = project_soc_ensemble(START, clim, ref, 20.0, 30.0, 50)
    elapsed = time.perf_counter() - t0
    print(f"ensemble 50y x 30 traj: {elapsed:.3f}s")
    assert len(trajs) == 30 and len(trajs[0]) == 50
    assert elapsed < 1.0   # one call; project + baseline stay under the 2 s budget
