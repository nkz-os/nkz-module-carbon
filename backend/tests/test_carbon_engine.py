import math

from app.services.carbon_engine import (
    Tier1Input,
    compute_fapar_frac,
    calculate_tier1,
)
from app.services.units import C_IN_DM, C_TO_CO2, G_PER_M2_TO_T_PER_HA


class TestFAPAR:
    def test_herbaceous_default(self):
        """NDVI=0.7, a=1.24, b=-0.168 -> fAPAR ~0.70."""
        fapar = compute_fapar_frac(vi_value=0.7, a=1.24, b=-0.168)
        assert 0.6 < fapar < 0.8

    def test_olive_default(self):
        """OSAVI=0.5, a=1.40, b=-0.240 -> fAPAR ~0.46."""
        fapar = compute_fapar_frac(vi_value=0.5, a=1.40, b=-0.240)
        assert 0.4 < fapar < 0.55

    def test_clamped_to_zero(self):
        fapar = compute_fapar_frac(vi_value=0.0, a=1.24, b=-0.168)
        assert fapar == 0.0

    def test_clamped_to_0_95(self):
        fapar = compute_fapar_frac(vi_value=1.0, a=1.40, b=1.0)
        assert fapar == 0.95


class TestTier1Calculation:
    def test_typical_wheat_day(self):
        """Wheat, PAR=15, fAPAR=0.7, LUE=1.1, root=0.22."""
        result = calculate_tier1(Tier1Input(
            par_MJ_m2_day=15.0,
            fapar_frac=0.7,
            lue_gC_per_MJ=1.1,
            root_fraction=0.22,
            species="wheat",
        ))
        # GPP = 15 x 0.7 x 1.1 = 11.55
        assert abs(result.gpp_gC_m2_day - 11.55) < 0.01
        # NPP = GPP x 0.5 = 5.775
        assert abs(result.npp_total_gC_m2_day - 5.775) < 0.01
        # NPP_aerea = 5.775 x 0.78 = 4.5045
        assert abs(result.npp_aerea_gC_m2_day - 4.5045) < 0.01
        # AGB = (4.5045 / 0.45) x 0.01 = 0.1001
        assert abs(result.agb_dry_tDM_ha - 0.1001) < 0.001

    def test_co2_calculation(self):
        """Verify CO2 conversion chain."""
        result = calculate_tier1(Tier1Input(
            par_MJ_m2_day=10.0,
            fapar_frac=0.5,
            lue_gC_per_MJ=1.0,
            root_fraction=0.25,
        ))
        # GPP = 10 x 0.5 x 1.0 = 5.0
        # NPP = 5.0 x 0.5 = 2.5
        # CO2 = 2.5 x 3.6667 x 10 = 91.6675
        expected_co2 = 2.5 * C_TO_CO2 * 10.0
        assert abs(result.co2_seq_kgCO2_ha_day - expected_co2) < 0.01

    def test_units_not_kg_per_m2(self):
        """AGB must be ~0.1 for a typical day (tDM/ha), not ~0.001 (kg/m2)."""
        result = calculate_tier1(Tier1Input(
            par_MJ_m2_day=15.0,
            fapar_frac=0.7,
            lue_gC_per_MJ=1.1,
            root_fraction=0.22,
        ))
        agb = result.agb_dry_tDM_ha
        assert 0.05 < agb < 0.20, (
            f"AGB={agb} tDM/ha/day is outside expected range for typical day. "
            f"Check unit conversion -- should be tDM/ha."
        )

    def test_data_quality_flags_propagated(self):
        result = calculate_tier1(Tier1Input(
            par_MJ_m2_day=10.0,
            fapar_frac=0.5,
            lue_gC_per_MJ=1.0,
            root_fraction=0.25,
            data_quality_flags=["synthetic_par"],
        ))
        assert "synthetic_par" in result.data_quality_flags
