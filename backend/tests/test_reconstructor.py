"""Tests for historical reconstructor."""

import pytest


class TestTemporalHarmonizer:
    def test_monthly_count_10_years(self):
        from app.reconstructor.temporal_harmonizer import harmonize_to_monthly
        records = harmonize_to_monthly([], [], [], year_from=2016, year_to=2025)
        assert len(records) == 120  # 10 years * 12 months

    def test_monthly_count_5_years(self):
        from app.reconstructor.temporal_harmonizer import harmonize_to_monthly
        records = harmonize_to_monthly([], [], [], year_from=2021, year_to=2025)
        assert len(records) == 60

    def test_crop_active_olive_all_year(self):
        from app.reconstructor.temporal_harmonizer import _crop_active_in_month
        for month in range(1, 13):
            assert _crop_active_in_month("olive", month) is True

    def test_crop_active_cereal_winter(self):
        from app.reconstructor.temporal_harmonizer import _crop_active_in_month
        assert _crop_active_in_month("cereal", 3) is True    # March: active
        assert _crop_active_in_month("cereal", 7) is False   # July: harvested

    def test_crop_active_fallow_never(self):
        from app.reconstructor.temporal_harmonizer import _crop_active_in_month
        for month in range(1, 13):
            assert _crop_active_in_month("fallow", month) is False

    def test_cover_present_in_output(self):
        from app.reconstructor.temporal_harmonizer import harmonize_to_monthly
        records = harmonize_to_monthly([], [], [], year_from=2025, year_to=2025)
        jan = records[0]
        assert isinstance(jan.cover_present, bool)

    def test_outputs_have_required_fields(self):
        from app.reconstructor.temporal_harmonizer import harmonize_to_monthly
        records = harmonize_to_monthly([], [], [], year_from=2025, year_to=2025)
        r = records[0]
        assert hasattr(r, 'temp_celsius')
        assert hasattr(r, 'precip_mm')
        assert hasattr(r, 'etp_mm')
        assert hasattr(r, 'crop_type')
        assert hasattr(r, 'ndvi_mean')


class TestSpinupDriver:
    @pytest.mark.asyncio
    async def test_spinup_returns_pool_state(self):
        from app.reconstructor.spinup_driver import run_spinup
        from app.services.roth_c_model import MonthlyInputs

        monthly = [
            MonthlyInputs(temp_celsius=20.0, precip_mm=50.0, etp_mm=80.0, cover_present=True)
            for _ in range(12)
        ]
        pools = await run_spinup(monthly, soc_initial_estimate_tC_ha=50.0, clay_pct=20.0, years=1)
        assert pools.total_tC_ha > 0

    @pytest.mark.asyncio
    async def test_spinup_empty_inputs(self):
        from app.reconstructor.spinup_driver import run_spinup
        pools = await run_spinup([], soc_initial_estimate_tC_ha=50.0, clay_pct=20.0, years=1)
        assert pools.total_tC_ha > 0


class TestCacheLayer:
    def test_cache_key_deterministic(self):
        from app.reconstructor.cache_layer import cache_key
        assert cache_key("p42", 2020, "sigpac") == cache_key("p42", 2020, "sigpac")

    def test_cache_key_different_per_product(self):
        from app.reconstructor.cache_layer import cache_key
        assert cache_key("p42", 2020, "sigpac") != cache_key("p42", 2020, "sentinel2")

    def test_cache_key_different_per_year(self):
        from app.reconstructor.cache_layer import cache_key
        assert cache_key("p42", 2019, "sigpac") != cache_key("p42", 2020, "sigpac")

    def test_is_closed_year(self):
        from app.reconstructor.cache_layer import is_closed_year
        assert is_closed_year(2020, current_year=2026) is True
        assert is_closed_year(2026, current_year=2026) is False
        assert is_closed_year(2025, current_year=2026) is True


class TestERA5Connector:
    @pytest.mark.asyncio
    async def test_synthetic_returns_120_for_10_years(self):
        from app.reconstructor.era5_connector import fetch_era5_monthly
        records = await fetch_era5_monthly(37.4, -4.5, 2016, 2025)
        assert len(records) == 120

    @pytest.mark.asyncio
    async def test_seville_summer_dry(self):
        from app.reconstructor.era5_connector import fetch_era5_monthly
        records = await fetch_era5_monthly(37.4, -4.5, 2020, 2020)
        july = [r for r in records if r.month == 7][0]
        assert july.temp_air_celsius > 20
        assert july.precip_mm < 20

    @pytest.mark.asyncio
    async def test_winter_wetter(self):
        from app.reconstructor.era5_connector import fetch_era5_monthly
        records = await fetch_era5_monthly(37.4, -4.5, 2020, 2020)
        jan = [r for r in records if r.month == 1][0]
        jul = [r for r in records if r.month == 7][0]
        assert jan.precip_mm > jul.precip_mm


class TestS2Composite:
    def test_empty_returns_empty(self):
        from app.reconstructor.sentinel2_connector import composite_monthly
        assert composite_monthly([]) == []

    def test_max_ndvi_method(self):
        from app.reconstructor.sentinel2_connector import S2Observation, composite_monthly
        obs = [
            S2Observation(date="2025-01-05", ndvi_mean=0.3, ndvi_std=0.05, cloud_pct=10, valid_pixels=100),
            S2Observation(date="2025-01-15", ndvi_mean=0.5, ndvi_std=0.04, cloud_pct=5, valid_pixels=100),
            S2Observation(date="2025-01-25", ndvi_mean=0.4, ndvi_std=0.06, cloud_pct=20, valid_pixels=100),
        ]
        result = composite_monthly(obs, method="max_ndvi", min_valid_obs=2)
        assert len(result) == 1
        assert result[0]["ndvi_mean"] == 0.5  # max NDVI


class TestSIGPACMapping:
    def test_olive_code(self):
        from app.reconstructor.sigpac_connector import sigpac_to_nkz_crop
        assert sigpac_to_nkz_crop("OV") == "olive"

    def test_cereal_code(self):
        from app.reconstructor.sigpac_connector import sigpac_to_nkz_crop
        assert sigpac_to_nkz_crop("TA") == "cereal"

    def test_unknown_code_fallback(self):
        from app.reconstructor.sigpac_connector import sigpac_to_nkz_crop
        assert sigpac_to_nkz_crop("XX") == "fallow"


class TestOnboardingPipeline:
    @pytest.mark.asyncio
    async def test_onboard_with_synthetic_data(self):
        from app.reconstructor.onboarding import onboard_parcela

        result = await onboard_parcela(
            parcela_id="test-parcela-1",
            lat=37.4, lon=-4.5,
            years_back=2,
            clay_pct=20.0,
            soc_initial_tC_ha=50.0,
        )
        assert result.parcela_id == "test-parcela-1"
        assert result.years_processed == 2
        assert "era5_land" in result.sources_used
        assert len(result.pools_t0) == 5  # DPM, RPM, BIO, HUM, IOM
        assert result.latency_ms >= 0  # may be 0 with synthetic data

    @pytest.mark.asyncio
    async def test_onboard_warns_about_missing_sources(self):
        from app.reconstructor.onboarding import onboard_parcela

        result = await onboard_parcela(
            parcela_id="test-parcela-2",
            lat=37.4, lon=-4.5,
            years_back=1,
        )
        assert len(result.warnings) >= 2  # SIGPAC + S2 unavailable
