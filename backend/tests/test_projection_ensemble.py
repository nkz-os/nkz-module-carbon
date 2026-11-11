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
    N_TRAJ, combine_months, months_from_row, project_soc, project_soc_ensemble, sample_sequences, summarize,
)

BASELINE = {"id": "urn:ngsi-ld:BaselineScenario:t1:abc", "type": "BaselineScenario",
            "validFrom": {"type": "Property", "value": "2025-01-01"}}


def _years(temps):
    """One RothC climate year per temperature (12 identical months)."""
    ref = months_from_row(_row(2025))
    return [[m.__class__(t, m.rain_mm, m.pan_evap_mm, False) for m in ref] for t in temps]


@pytest.fixture(autouse=True)
def _fresh_climate_cache():
    cr.clear_climate_cache()
    yield
    cr.clear_climate_cache()


def test_single_climate_year_equals_project_soc():
    ref = months_from_row(_row(2025))
    clim = [[m.__class__(m.temp_c, m.rain_mm, m.pan_evap_mm, False) for m in ref]]
    seqs = sample_sequences(1, 3, 5, "seed")
    trajs = project_soc_ensemble(START, clim, ref, 20.0, 30.0, 5, seqs)
    assert len(trajs) == 3
    for traj in trajs:
        assert traj == pytest.approx(project_soc(START, ref, 20.0, 30.0, 5))


def test_trajectory_follows_the_given_climate_sequence():
    clim = _years([5.0, 10.0, 15.0])
    inputs = months_from_row(_row(2025))
    seqs = [[2, 0, 0, 1], [1, 1, 1, 1]]
    trajs = project_soc_ensemble(START, clim, inputs, 20.0, 30.0, 4, seqs)
    assert len(trajs) == 2 and all(len(t) == 4 for t in trajs)
    from app.services.roth_c_model import run_months
    state, expect = START, []
    for k in range(4):
        state = run_months(state, combine_months(clim[seqs[0][k]], inputs), 20.0, 30.0).final
        expect.append(state.pools.total)
    assert trajs[0] == pytest.approx(expect)


def test_sampler_is_deterministic_bootstrap_with_replacement():
    a = sample_sequences(30, 200, 50, "p|2025|1996|2025")
    assert a == sample_sequences(30, 200, 50, "p|2025|1996|2025")
    assert a != sample_sequences(30, 200, 50, "q|2025|1996|2025")
    assert len(a) == 200 and all(len(q) == 50 for q in a)
    assert all(0 <= i < 30 for q in a for i in q)
    assert any(len(set(q)) < len(q) for q in a)   # with replacement: repeats inside one trajectory
    assert N_TRAJ == 200 or N_TRAJ == 100


def _width_by_year(trajs):
    _, lo, hi = summarize(trajs)
    return [h - l for l, h in zip(lo, hi)]


def test_band_does_not_pinch_near_the_window_length():
    # rotation made every trajectory use all 30 years by year 30 (band -> 0); a bootstrap must not
    ref = months_from_row(_row(2025))
    clim = _years([6.0 + 0.5 * i for i in range(30)])
    seqs = sample_sequences(30, 200, 40, "p|2025|1996|2025")
    w = _width_by_year(project_soc_ensemble(START, clim, ref, 20.0, 30.0, 40, seqs))
    print("band widths y10/y20/y30/y40:", [round(w[i - 1], 4) for i in (10, 20, 30, 40)])
    assert w[29] >= 0.5 * w[9]
    assert w[39] >= 0.5 * w[9]


def test_summarize_percentiles_on_a_hand_made_set():
    trajs = [[float(v)] for v in range(1, 12)]  # 1..11, n=11
    med, lo, hi = summarize(trajs)
    assert med == [6.0]
    assert lo == pytest.approx([1.0 + 0.025 * 10])    # linear interpolation, position q*(n-1)
    assert hi == pytest.approx([1.0 + 0.975 * 10])
    med2, _, _ = summarize([[1.0, 4.0], [3.0, 8.0]])
    assert med2 == [2.0, 6.0]


def _hist(n_years=31, last=2025, ready=True, shift=0.0, latest=None):
    days = []
    for i, y in enumerate(range(last - n_years + 1, last + 1)):
        d = date(y, 1, 1)
        while d.year == y:
            days.append(HistoryDay(d, 5.0 + (i % 5) + shift, 15.0 + (i % 5) + shift, 1.5, 2.0))
            d += timedelta(days=1)
    return HistoryResult(ready=ready, days=days, years_label=f"{last - n_years + 1}–{last}",
                         attribution="Copernicus", latest_available=latest or date(last, 12, 31))


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
    HistoryResult(ready=False, status=503, reason="weather-api answered 503"),
    HistoryResult(ready=False, reason="weather-api unreachable: timeout"),
    HistoryResult(ready=False, reason="history incomplete for years [1996]"),
    HistoryResult(ready=False, reason="history has no days"),
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
@pytest.mark.parametrize("result", [
    HistoryResult(ready=False, status=401, permanent=True, reason="weather-api answered 401"),
    HistoryResult(ready=False, status=404, permanent=True, reason="weather-api answered 404"),
    HistoryResult(ready=False, status=422, permanent=True, reason="weather-api answered 422"),
    _hist(n_years=24),   # fewer than 25 complete years: it is not going to be prepared
])
async def test_permanent_failure_is_not_called_being_prepared(env, monkeypatch, result):  # noqa: F811
    _patch(monkeypatch, result)
    await cr.run_campaign("t1", "abc", 2025, today=date(2026, 10, 10))
    p = await cr.projection("t1", "abc", years=3)
    assert p["climate"] == {"source": "reference_campaign"}
    assert p["assumption_codes"][0] == {"code": "repeat_reference", "year": 2025}
    assert p["missing"] == [{"item": "climate_history_unavailable",
                             "reason": "climate history unavailable for this parcel",
                             "effect": "projection uses the reference campaign's climate"}]
    assert len(p["project_soc"]) == 3 and p["project_soc_p025"] == []


@pytest.mark.asyncio
async def test_incomplete_current_year_is_excluded_not_mixed(env, monkeypatch):  # noqa: F811
    # 26 complete years plus a partial reference year: the partial year is dropped, 26 >= 25 still usable
    res = _hist(n_years=26, last=2024)
    partial = [HistoryDay(date(2025, 1, 1) + timedelta(days=i), 5.0, 15.0, 1.0, 1.0) for i in range(100)]
    _patch(monkeypatch, HistoryResult(True, res.days + partial, "x", "c", date(2025, 4, 10)))
    await cr.run_campaign("t1", "abc", 2025, today=date(2026, 10, 10))
    p = await cr.projection("t1", "abc", years=2)
    assert p["climate"]["n_years"] == 26 and p["climate"]["years"] == "1999–2024"


@pytest.mark.asyncio
async def test_no_complete_campaign_does_not_fetch_history(env, monkeypatch):  # noqa: F811
    calls = _patch(monkeypatch, _hist())
    p = await cr.projection("t1", "abc", years=3)
    assert calls == [] and p["project_soc"] == []


def test_fifty_years_ensemble_stays_within_budget():
    ref = months_from_row(_row(2025))
    clim = _years([8.0 + 0.1 * i for i in range(30)])
    seqs = sample_sequences(30, N_TRAJ, 50, "p|2025|1996|2025")
    t0 = time.perf_counter()
    trajs = project_soc_ensemble(START, clim, ref, 20.0, 30.0, 50, seqs)
    elapsed = time.perf_counter() - t0
    print(f"ensemble 50y x {N_TRAJ} traj: {elapsed:.3f}s")
    assert len(trajs) == N_TRAJ and len(trajs[0]) == 50
    assert elapsed < 1.0   # measured ~0.75 s; with the baseline the 50-year worst case is ~1.5 s


def _patch_real_server(monkeypatch, latest, last=2025):
    """Fake weather-api: 400 'end is after the latest available day' when end > latest."""
    data = _hist(n_years=40, last=last)
    calls = []

    async def fake(urn, tenant, start, end, client=None):
        calls.append((start, end))
        if end > latest:
            return HistoryResult(ready=False, status=400, end_after_latest=True,
                                 reason="weather-api answered 400")
        return HistoryResult(True, [d for d in data.days if start <= d.day <= end], "x", "Copernicus", latest)

    monkeypatch.setattr(cr, "fetch_climate_history", fake)
    return calls


@pytest.mark.asyncio
async def test_end_after_latest_400_retries_once_with_previous_year(env, monkeypatch):  # noqa: F811
    calls = _patch_real_server(monkeypatch, latest=date(2025, 11, 9))
    await cr.run_campaign("t1", "abc", 2025, today=date(2026, 10, 10))
    calls.clear()
    p = await cr.projection("t1", "abc", years=2)
    assert calls == [(date(1996, 1, 1), date(2025, 12, 31)), (date(1995, 1, 1), date(2024, 12, 31))]
    assert p["climate"]["years"] == "1995\u20132024" and p["climate"]["n_years"] == 30
    assert p["assumption_codes"][0] == {"code": "climate_history", "from": 1995, "to": 2024, "n": 30}
    assert not any(m["item"].startswith("climate_history") for m in p["missing"])


@pytest.mark.asyncio
async def test_second_400_is_not_retried_again(env, monkeypatch):  # noqa: F811
    calls = _patch_real_server(monkeypatch, latest=date(2020, 1, 1))
    await cr.run_campaign("t1", "abc", 2025, today=date(2026, 10, 10))
    calls.clear()
    p = await cr.projection("t1", "abc", years=2)
    assert len(calls) == 2
    assert p["climate"] == {"source": "reference_campaign"} and p["missing"][0]["item"].startswith("climate_history")


@pytest.mark.asyncio
async def test_start_is_clamped_to_1991(env, monkeypatch):  # noqa: F811
    store, _ = env
    calls = _patch(monkeypatch, _hist(n_years=26, last=2016))
    await cr.run_campaign("t1", "abc", 2016, today=date(2026, 10, 10))
    calls.clear()
    await cr.projection("t1", "abc", years=2)
    assert calls[0][2:] == (date(1991, 1, 1), date(2016, 12, 31))


@pytest.mark.asyncio
async def test_ready_history_is_cached_and_failures_are_not(env, monkeypatch):  # noqa: F811
    calls = _patch(monkeypatch, _hist())
    await cr.run_campaign("t1", "abc", 2025, today=date(2026, 10, 10))
    calls.clear()
    a = await cr.projection("t1", "abc", years=3)
    b = await cr.projection("t1", "abc", years=3)
    assert len(calls) == 1 and a == b            # cached, and same request -> identical numbers
    cr.clear_climate_cache()
    calls2 = _patch(monkeypatch, HistoryResult(ready=False, reason="x"))
    await cr.projection("t1", "abc", years=3)
    await cr.projection("t1", "abc", years=3)
    assert len(calls2) == 2                       # not-ready is retried each time


@pytest.mark.asyncio
async def test_cache_expires_after_24h_and_is_bounded(env, monkeypatch):  # noqa: F811
    calls = _patch(monkeypatch, _hist())
    await cr.run_campaign("t1", "abc", 2025, today=date(2026, 10, 10))
    calls.clear()
    clock = [1000.0]
    monkeypatch.setattr(cr, "_now", lambda: clock[0])
    await cr.projection("t1", "abc", years=2)
    clock[0] += 24 * 3600 - 1
    await cr.projection("t1", "abc", years=2)
    assert len(calls) == 1
    clock[0] += 2
    await cr.projection("t1", "abc", years=2)
    assert len(calls) == 2
    for i in range(cr.CLIMATE_CACHE_MAX + 20):
        cr._cache_put(("t", f"p{i}", 1, 2), object())
    assert len(cr._CLIMATE_CACHE) <= cr.CLIMATE_CACHE_MAX


@pytest.mark.asyncio
async def test_same_request_same_numbers_and_baseline_is_paired(env, monkeypatch):  # noqa: F811
    store, _ = env
    _patch(monkeypatch, _hist())
    await cr.run_campaign("t1", "abc", 2025, today=date(2026, 10, 10))
    store.entities[("t1", BASELINE["id"])] = BASELINE
    seen = []
    real = cr.project_soc_ensemble

    def spy(start, climate, inputs, clay, depth, years, sequences):
        seen.append(sequences)
        return real(start, climate, inputs, clay, depth, years, sequences)

    monkeypatch.setattr(cr, "project_soc_ensemble", spy)
    a = await cr.projection("t1", "abc", years=4)
    cr.clear_climate_cache()
    b = await cr.projection("t1", "abc", years=4)
    assert a == b
    assert len(seen) == 4 and seen[0] == seen[1] == seen[2] == seen[3]   # project and baseline share sequences
    assert len(seen[0]) == N_TRAJ


@pytest.mark.asyncio
async def test_ensemble_runs_off_the_event_loop(env, monkeypatch):  # noqa: F811
    import threading
    _patch(monkeypatch, _hist())
    await cr.run_campaign("t1", "abc", 2025, today=date(2026, 10, 10))
    main, threads = threading.get_ident(), []
    real = cr.project_soc_ensemble

    def spy(*a):
        threads.append(threading.get_ident())
        return real(*a)

    monkeypatch.setattr(cr, "project_soc_ensemble", spy)
    await cr.projection("t1", "abc", years=2)
    assert threads and all(t != main for t in threads)


@pytest.mark.asyncio
async def test_delta_band_is_median_of_per_trajectory_deltas(env, monkeypatch):  # noqa: F811
    store, _ = env
    _patch(monkeypatch, _hist())
    await cr.run_campaign("t1", "abc", 2025, today=date(2026, 10, 10))
    store.entities[("t1", BASELINE["id"])] = BASELINE
    sets = iter([[[0.0], [10.0], [20.0]], [[10.0], [0.0], [10.0]]])  # project, then baseline
    monkeypatch.setattr(cr, "project_soc_ensemble", lambda *a, **k: next(sets))
    p = await cr.projection("t1", "abc", years=1)
    # per-trajectory deltas -10, 10, 10 -> median 10; median(p) - median(b) would be 0
    assert p["project_soc"] == [10.0] and p["baseline_soc"] == [10.0]
    assert p["annual_delta_tC_ha_yr"] == [10.0]


@pytest.mark.asyncio
async def test_no_complete_campaign_still_labels_climate(env):  # noqa: F811
    p = await cr.projection("t1", "abc", years=3)
    assert p["climate"] == {"source": "reference_campaign"}


@pytest.mark.parametrize("hist", ["history", "fallback"])
@pytest.mark.asyncio
async def test_new_keys_reach_the_client_through_the_route(env, monkeypatch, hist):  # noqa: F811
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import assessments
    store, _ = env
    _patch(monkeypatch, _hist() if hist == "history" else HistoryResult(ready=False, reason="x"))
    await cr.run_campaign("tenant-one", "abc", 2025, today=date(2026, 10, 10))
    bid = "urn:ngsi-ld:BaselineScenario:tenant-one:abc"
    store.entities[("tenant-one", bid)] = dict(BASELINE, id=bid)
    app = FastAPI()
    app.include_router(assessments.router)
    r = TestClient(app).get("/api/carbon/parcels/abc/projection?years=3",
                            headers={"X-Tenant-ID": "tenant-one", "X-User-ID": "u1"})
    assert r.status_code == 200
    j = r.json()
    for k in ("project_soc_p025", "project_soc_p975", "baseline_soc_p025", "baseline_soc_p975",
              "annual_delta_p025", "annual_delta_p975", "climate", "assumption_codes", "missing"):
        assert k in j
    assert j["assumption_codes"][0]["code"] == ("climate_history" if hist == "history" else "repeat_reference")
    if hist == "history":
        assert j["climate"]["source"] == "history" and len(j["project_soc_p025"]) == 3
        assert len(j["annual_delta_p975"]) == 3
    else:
        assert j["climate"] == {"source": "reference_campaign"}
        assert j["missing"][0]["item"] == "climate_history" and j["project_soc_p025"] == []


@pytest.mark.asyncio
async def test_shorter_horizon_is_a_prefix_of_the_longer_one(env, monkeypatch):  # noqa: F811
    # The same parcel projected for 5 or 12 years must agree on the first 5 years.
    _patch(monkeypatch, _hist())
    await cr.run_campaign("t1", "abc", 2025, today=date(2026, 10, 10))
    cr._CLIMATE_CACHE.clear() if hasattr(cr, "_CLIMATE_CACHE") else None
    p5 = await cr.projection("t1", "abc", years=5)
    p12 = await cr.projection("t1", "abc", years=12)
    assert p5["project_soc"] == p12["project_soc"][:5]
    assert p5["project_soc_p975"] == p12["project_soc_p975"][:5]
