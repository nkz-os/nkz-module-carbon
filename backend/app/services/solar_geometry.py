"""Solar geometry for clear-sky PAR calculation (FAO-56, Allen et al. 1998)."""

import math
from datetime import date

from app.services.units import PAR_FRACTION, CLEAR_SKY_FRACTION

SOLAR_CONSTANT = 0.0820  # MJ/m²/min


def extraterrestrial_solar_MJ_m2_day(lat_deg: float, doy: int) -> float:
    """Extraterrestrial solar radiation Ra [MJ/m²/day] (FAO-56 Eq. 21)."""
    lat_rad = math.radians(lat_deg)
    solar_decl_rad = 0.409 * math.sin(2 * math.pi / 365 * doy - 1.39)
    cos_sunset = -math.tan(lat_rad) * math.tan(solar_decl_rad)
    cos_sunset = max(-1.0, min(1.0, cos_sunset))
    sunset_hour_angle = math.acos(cos_sunset)
    d_r = 1 + 0.033 * math.cos(2 * math.pi / 365 * doy)
    ra = (
        24 * 60 / math.pi
        * SOLAR_CONSTANT
        * d_r
        * (
            sunset_hour_angle * math.sin(lat_rad) * math.sin(solar_decl_rad)
            + math.cos(lat_rad) * math.cos(solar_decl_rad) * math.sin(sunset_hour_angle)
        )
    )
    return ra


def doy_from_date(d: date) -> int:
    """Day of year from date."""
    return d.timetuple().tm_yday


def clear_sky_par_MJ_m2_day(lat_deg: float, doy: int) -> float:
    """Clear-sky PAR [MJ/m²/day] from latitude and day of year.

    Ra       = extraterrestrial solar radiation
    Rs_clear = 0.75 x Ra       (clear-sky global radiation)
    PAR      = 0.48 x Rs_clear (PAR fraction)
    """
    ra_MJ_m2_day = extraterrestrial_solar_MJ_m2_day(lat_deg, doy)
    rs_clear_MJ_m2_day = CLEAR_SKY_FRACTION * ra_MJ_m2_day
    return PAR_FRACTION * rs_clear_MJ_m2_day
