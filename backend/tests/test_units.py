from app.services import units


class TestConversionConstants:
    def test_c_to_co2_is_44_over_12(self):
        assert units.C_TO_CO2 == 44.0 / 12.0

    def test_carbon_in_dry_matter_is_45_percent(self):
        assert units.C_IN_DM == 0.45

    def test_g_per_m2_to_t_per_ha_is_correct(self):
        # 100 g/m² = 1 t/ha
        assert 100 * units.G_PER_M2_TO_T_PER_HA == 1.0

    def test_n_to_n2o_conversion(self):
        # 28 g N → 44 g N₂O
        assert units.N_TO_N2O == 44.0 / 28.0

    def test_par_fraction_in_range(self):
        assert 0.4 < units.PAR_FRACTION < 0.6
