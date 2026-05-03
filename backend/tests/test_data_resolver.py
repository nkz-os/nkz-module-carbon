"""Tests for data resolver."""

from app.services.data_resolver import (
    DataAvailability,
    resolve_tier,
    Tier,
)


class TestResolveTier:
    def test_tier1_with_minimal_data(self):
        avail = DataAvailability(
            ndvi_available=True,
            meteo_available=True,
        )
        result = resolve_tier(avail)
        assert result.tier == Tier.ONE

    def test_tier2_with_soil_phenology_management(self):
        avail = DataAvailability(
            ndvi_available=True,
            meteo_available=True,
            soil_available=True,
            phenology_available=True,
            management_available=True,
        )
        result = resolve_tier(avail)
        assert result.tier == Tier.TWO
        assert "sensors_soil" not in " ".join(result.available_sources)

    def test_tier3_with_full_sensor_data(self):
        avail = DataAvailability(
            ndvi_available=True,
            meteo_available=True,
            soil_available=True,
            phenology_available=True,
            management_available=True,
            sensors_soil_available=True,
            sensors_plant_available=True,
            fertilization_available=True,
        )
        result = resolve_tier(avail)
        assert result.tier == Tier.THREE

    def test_tier2_shows_tier3_gaps(self):
        avail = DataAvailability(
            ndvi_available=True,
            meteo_available=True,
            soil_available=True,
            phenology_available=True,
            management_available=True,
        )
        result = resolve_tier(avail)
        assert result.tier == Tier.TWO
        assert len(result.missing_for_next_tier) > 0

    def test_lai_counts_as_ndvi(self):
        avail = DataAvailability(
            lai_available=True,
            meteo_available=True,
        )
        result = resolve_tier(avail)
        assert result.tier == Tier.ONE

    def test_confidence_from_ci_width(self):
        avail = DataAvailability(
            ndvi_available=True,
            meteo_available=True,
        )
        result = resolve_tier(avail, uncertainty_ci_width=0.25)
        assert result.confidence == 0.75

    def test_gap_details_populated(self):
        avail = DataAvailability(
            ndvi_available=True,
            meteo_available=True,
        )
        result = resolve_tier(avail)
        assert len(result.gap_details) > 0

    def test_soc_provenance_preserved(self):
        avail = DataAvailability(
            ndvi_available=True,
            meteo_available=True,
            soil_available=True,
            phenology_available=True,
            management_available=True,
            soc_provenance="soilgrids_250m_v2",
        )
        result = resolve_tier(avail)
        assert result.soc_provenance == "soilgrids_250m_v2"
