import math
from datetime import date

from app.services.solar_geometry import (
    extraterrestrial_solar_MJ_m2_day,
    clear_sky_par_MJ_m2_day,
    doy_from_date,
)


class TestDOY:
    def test_jan_1(self):
        assert doy_from_date(date(2026, 1, 1)) == 1

    def test_dec_31_non_leap(self):
        assert doy_from_date(date(2025, 12, 31)) == 365

    def test_june_15(self):
        assert doy_from_date(date(2026, 6, 15)) == 166


class TestExtraterrestrialSolar:
    def test_equator_summer_solstice(self):
        """At equator on summer solstice, Ra ~40 MJ/m²/day (FAO-56 Annex 2 Table 2.6)."""
        ra = extraterrestrial_solar_MJ_m2_day(lat_deg=0.0, doy=172)
        assert 30 < ra < 36, f"Expected ~33, got {ra}"

    def test_45n_winter_solstice(self):
        """At 45N on Dec 21, Ra is low."""
        ra = extraterrestrial_solar_MJ_m2_day(lat_deg=45.0, doy=355)
        assert ra < 15, f"Expected <15, got {ra}"

    def test_seville_summer(self):
        """Seville (37.4N) mid-summer should have Ra ~42."""
        ra = extraterrestrial_solar_MJ_m2_day(lat_deg=37.4, doy=182)
        assert 40 < ra < 44, f"Expected ~42, got {ra}"

    def test_pole_winter_is_zero(self):
        """At 90N in winter, Ra = 0 (polar night)."""
        ra = extraterrestrial_solar_MJ_m2_day(lat_deg=90.0, doy=1)
        assert ra < 0.01, f"Expected ~0, got {ra}"


class TestClearSkyPAR:
    def test_seville_summer_par(self):
        """Seville summer clear-sky PAR should be ~15 MJ/m²/day."""
        par = clear_sky_par_MJ_m2_day(lat_deg=37.4, doy=182)
        assert 12 < par < 18, f"Expected ~15, got {par}"

    def test_returns_positive_for_all_latitudes(self):
        for lat in [-60, -30, 0, 30, 60]:
            par = clear_sky_par_MJ_m2_day(lat_deg=lat, doy=180)
            assert par >= 0, f"PAR negative for lat={lat}: {par}"
