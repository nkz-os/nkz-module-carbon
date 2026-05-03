"""ERA5-Land climate reanalysis connector (spec 11.2)."""

import logging
import math
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Era5Monthly:
    year: int
    month: int
    temp_air_celsius: float
    precip_mm: float
    etp_mm: float
    solar_rad_MJ_m2_day: float


async def fetch_era5_monthly(
    lat: float,
    lon: float,
    year_from: int,
    year_to: int,
) -> list[Era5Monthly]:
    """Fetch ERA5-Land monthly aggregates. Uses synthetic data as fallback."""
    logger.info("ERA5-Land fetch %d-%d (using synthetic fallback)", year_from, year_to)
    return _synthetic_monthly(lat, year_from, year_to)


def _synthetic_monthly(lat: float, year_from: int, year_to: int) -> list[Era5Monthly]:
    """Generate synthetic monthly climate from solar geometry + seasonal model."""
    from app.services.solar_geometry import clear_sky_par_MJ_m2_day

    results = []
    for year in range(year_from, year_to + 1):
        for month in range(1, 13):
            doy = min(15 + 30 * (month - 1), 365)
            par_MJ_m2_day = clear_sky_par_MJ_m2_day(lat, doy)
            rs_MJ_m2_day = par_MJ_m2_day / 0.48

            temp = 15.0 - 10.0 * math.cos(2 * math.pi * (doy - 20) / 365)
            is_wet_season = month in [10, 11, 12, 1, 2, 3]
            precip = 60.0 if is_wet_season else 15.0
            etp = rs_MJ_m2_day * 0.30

            results.append(Era5Monthly(
                year=year, month=month,
                temp_air_celsius=round(temp, 1),
                precip_mm=round(precip, 1),
                etp_mm=round(etp, 1),
                solar_rad_MJ_m2_day=round(rs_MJ_m2_day, 1),
            ))
    return results
