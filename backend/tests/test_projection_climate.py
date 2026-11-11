from datetime import date, timedelta

import pytest

from app.platform.weather_history_client import HistoryDay
from app.services.projection_climate import MIN_CLIMATE_YEARS, climate_years, usable
from app.services.roth_c_model import pan_evap_from_et0


def _year(y, t=10.0, p=1.0, e=2.0, skip=None, null=None):
    d, out = date(y, 1, 1), []
    while d.year == y:
        if d != skip:
            out.append(HistoryDay(d, None if d == null else t, p, e))
        d += timedelta(days=1)
    return out


def test_monthly_aggregation_and_leap_february():
    cy = climate_years(_year(2024, t=10.0, p=1.0, e=2.0), 2024, 2024)
    months = cy[2024]
    assert len(months) == 12
    jan, feb = months[0], months[1]
    assert jan == (10.0, 31.0, pan_evap_from_et0(62.0))
    assert feb == (10.0, 29.0, pan_evap_from_et0(58.0))  # leap year: 29 days


def test_months_are_in_calendar_order():
    days = []
    for d in _year(2023):
        days.append(HistoryDay(d.day, float(d.day.month), 1.0, 1.0))
    cy = climate_years(days, 2023, 2023)[2023]
    assert [m[0] for m in cy] == [float(m) for m in range(1, 13)]


def test_year_with_one_missing_day_is_excluded():
    days = _year(2020) + _year(2021, skip=date(2021, 6, 1)) + _year(2022)
    assert sorted(climate_years(days, 2020, 2022)) == [2020, 2022]


def test_year_with_one_null_variable_is_excluded():
    days = _year(2020, null=date(2020, 3, 3)) + _year(2021)
    assert sorted(climate_years(days, 2020, 2021)) == [2021]


def test_years_outside_range_are_ignored():
    days = _year(2018) + _year(2020)
    assert sorted(climate_years(days, 2019, 2020)) == [2020]


def test_fewer_than_25_years_is_not_usable():
    days = [d for y in range(2000, 2000 + MIN_CLIMATE_YEARS - 1) for d in _year(y)]
    assert not usable(climate_years(days, 2000, 2030))
    days += _year(2000 + MIN_CLIMATE_YEARS - 1)
    assert usable(climate_years(days, 2000, 2030))
