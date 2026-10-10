"""Daily NDVI from sparse acquisitions: linear between scenes, never extrapolated."""

from bisect import bisect_left
from datetime import date
from typing import Optional, Sequence


def interpolate_daily(
    series: Sequence[tuple[date, Optional[float]]],
    days: Sequence[date],
    max_gap_days: int = 60,
) -> dict[date, Optional[float]]:
    """Value per day, or None where no acquisition brackets the day closely enough.

    Values outside [-1, 1] are discarded; the first valid value of a date wins.
    Days before the first or after the last acquisition stay None.
    """
    clean: dict[date, float] = {}
    for d, v in series:
        if v is None:
            continue
        fv = float(v)
        if -1.0 <= fv <= 1.0:
            clean.setdefault(d, fv)
    dates = sorted(clean)
    out: dict[date, Optional[float]] = {}
    for day in days:
        i = bisect_left(dates, day)
        if i < len(dates) and dates[i] == day:
            out[day] = clean[day]
        elif 0 < i < len(dates):
            d0, d1 = dates[i - 1], dates[i]
            span = (d1 - d0).days
            if span <= max_gap_days:
                v0, v1 = clean[d0], clean[d1]
                out[day] = v0 + (v1 - v0) * ((day - d0).days / span)
            else:
                out[day] = None
        else:
            out[day] = None
    return out
