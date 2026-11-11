"""Monthly climate years from the parcel's daily history, for the SOC projection.

A year is usable only if every day of it has temperature, rain and ET0: nothing is
interpolated or filled. Months are calendar months 1-12 (campaigns run 1 Jan - 31 Dec).
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from typing import Sequence

from app.platform.weather_history_client import HistoryDay
from app.services.roth_c_model import pan_evap_from_et0

MIN_CLIMATE_YEARS = 25
WINDOW_YEARS = 30
MIN_HISTORY_YEAR = 1991   # weather-api rejects an earlier start

MonthClimate = tuple[float, float, float]  # temp_c, rain_mm, pan_evap_mm


def climate_years(days: Sequence[HistoryDay], first_year: int, last_year: int) -> dict[int, list[MonthClimate]]:
    """Complete years in [first_year, last_year] as 12 monthly (temp, rain, pan evaporation)."""
    by_year: dict[int, dict[object, HistoryDay]] = defaultdict(dict)
    for d in days:
        if first_year <= d.day.year <= last_year and d.complete:
            by_year[d.day.year][d.day] = d
    out: dict[int, list[MonthClimate]] = {}
    for year in range(first_year, last_year + 1):
        got = by_year.get(year, {})
        if len(got) != (366 if calendar.isleap(year) else 365):
            continue
        months: list[MonthClimate] = []
        for m in range(1, 13):
            ds = [d for day, d in got.items() if day.month == m]
            months.append((sum(d.tmean_c for d in ds) / len(ds), sum(d.precip_mm for d in ds),
                           pan_evap_from_et0(sum(d.et0_mm for d in ds))))
        out[year] = months
    return out


def usable(years: dict[int, list[MonthClimate]]) -> bool:
    return len(years) >= MIN_CLIMATE_YEARS
