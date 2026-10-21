from datetime import date, timedelta

import pytest

from app.services.ndvi_series import interpolate_daily

D = date(2026, 5, 1)


def _days(n):
    return [D + timedelta(days=i) for i in range(n)]


def test_linear_between_scenes():
    out = interpolate_daily([(D, 0.2), (D + timedelta(days=10), 0.7)], _days(11))
    assert out[D + timedelta(days=5)] == pytest.approx(0.45)
    assert out[D] == 0.2 and out[D + timedelta(days=10)] == 0.7


def test_no_extrapolation_outside_series():
    out = interpolate_daily([(D + timedelta(days=2), 0.5), (D + timedelta(days=4), 0.5)], _days(6))
    assert out[D] is None and out[D + timedelta(days=5)] is None


def test_gap_longer_than_max_is_unknown():
    out = interpolate_daily([(D, 0.3), (D + timedelta(days=61), 0.6)], _days(62), max_gap_days=60)
    assert out[D + timedelta(days=30)] is None
    assert out[D] == 0.3 and out[D + timedelta(days=61)] == 0.6


def test_invalid_values_and_duplicates_ignored():
    series = [(D, 1.7), (D, 0.4), (D + timedelta(days=2), None), (D + timedelta(days=4), 0.4)]
    out = interpolate_daily(series, _days(5))
    assert out[D] == 0.4 and out[D + timedelta(days=2)] == pytest.approx(0.4)


def test_single_scene_only_its_day():
    out = interpolate_daily([(D + timedelta(days=1), 0.5)], _days(3))
    assert out == {D: None, D + timedelta(days=1): 0.5, D + timedelta(days=2): None}
