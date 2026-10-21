"""Sentinel-2 historical connector (spec 11.2).

Strategy: use CDSE STAC API or Sentinel Hub to extract parcel-level
timeseries. Avoids downloading full tiles.

S2 (2015+) covers 10-yr pre-project in 2026. Landsat deferred to V2.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class S2Observation:
    date: str       # YYYY-MM-DD
    ndvi_mean: float
    ndvi_std: float
    osavi_mean: float | None = None
    cloud_pct: float = 0.0
    valid_pixels: int = 0


async def fetch_s2_timeseries(
    geometry_wkt: str,
    date_from: str,
    date_to: str,
    indices: list[str] | None = None,
) -> list[S2Observation]:
    """Fetch Sentinel-2 timeseries. Returns empty list if unreachable."""
    logger.info("Sentinel-2 fetch %s to %s (not yet connected)", date_from, date_to)
    return []


def composite_monthly(
    observations: list[S2Observation],
    method: str = "max_ndvi",
    min_valid_obs: int = 2,
) -> list[dict]:
    """Aggregate S2 observations to monthly composites.

    - max_ndvi: use max NDVI in month (standard for biomass estimation)
    - weighted_mean: weight by inverse cloud score
    """
    if not observations:
        return []

    from collections import defaultdict
    monthly = defaultdict(list)

    for obs in observations:
        month_key = obs.date[:7]  # YYYY-MM
        monthly[month_key].append(obs)

    results = []
    for month_key in sorted(monthly.keys()):
        month_obs = monthly[month_key]
        if len(month_obs) < min_valid_obs:
            continue

        if method == "max_ndvi":
            best = max(month_obs, key=lambda o: o.ndvi_mean)
            results.append({
                "month": month_key,
                "ndvi_mean": best.ndvi_mean,
                "ndvi_std": best.ndvi_std,
                "osavi_mean": best.osavi_mean,
                "valid_obs": len(month_obs),
            })
        elif method == "weighted_mean":
            weights = [max(0, 100 - o.cloud_pct) for o in month_obs]
            total_w = sum(weights) or 1
            results.append({
                "month": month_key,
                "ndvi_mean": sum(o.ndvi_mean * w for o, w in zip(month_obs, weights)) / total_w,
                "ndvi_std": sum(o.ndvi_std * w for o, w in zip(month_obs, weights)) / total_w,
                "valid_obs": len(month_obs),
            })

    return results
