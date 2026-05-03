from app.services.ghg_model import (
    N2OInputs,
    compute_n2o,
    NEEInputs,
    compute_nee,
    compute_co2eq_net,
    GWP100_AR6,
)


class TestGWP:
    def test_ar6_not_ar5(self):
        """Verify AR6 values, not AR5."""
        assert GWP100_AR6["N2O"] == 273  # AR5 was 298
        assert GWP100_AR6["CH4_non_fossil"] == 27  # AR5 was 34


class TestN2O:
    def test_dry_synthetic(self):
        result = compute_n2o(N2OInputs(
            n_applied_synthetic_kgN_ha_yr=100.0,
            precip_annual_mm=400.0,
            etp_annual_mm=500.0,
            irrigated=False,
        ))
        # N2O direct: 100 x 0.005 x 44/28 ~ 0.786
        assert 0.5 < result.n2o_direct_kgN2O_ha_yr < 1.5
        # Indirect should add to total
        assert result.n2o_total_kgN2O_ha_yr > result.n2o_direct_kgN2O_ha_yr

    def test_humid_synthetic(self):
        result = compute_n2o(N2OInputs(
            n_applied_synthetic_kgN_ha_yr=100.0,
            precip_annual_mm=1200.0,
            etp_annual_mm=500.0,
            irrigated=False,
        ))
        # Humid EF1 should be higher (0.016 vs 0.005)
        assert result.n2o_direct_kgN2O_ha_yr > 1.0

    def test_irrigated_counts_as_humid(self):
        result = compute_n2o(N2OInputs(
            n_applied_synthetic_kgN_ha_yr=100.0,
            precip_annual_mm=400.0,
            irrigated=True,
        ))
        # Should use humid EF1=0.016 even with low precip
        assert result.n2o_direct_kgN2O_ha_yr > 1.0

    def test_no_input_is_zero(self):
        result = compute_n2o(N2OInputs())
        assert result.n2o_total_kgN2O_ha_yr == 0.0

    def test_co2eq_uses_ar6_gwp(self):
        result = compute_n2o(N2OInputs(
            n_applied_synthetic_kgN_ha_yr=100.0,
            precip_annual_mm=400.0,
            irrigated=False,
        ))
        expected_co2eq = result.n2o_total_kgN2O_ha_yr * 273 / 1000.0
        assert abs(result.n2o_co2eq_tCO2eq_ha_yr - expected_co2eq) < 0.01


class TestNEE:
    def test_negative_nee_is_sink(self):
        """When NPP > Rh, NEE is negative (carbon sink)."""
        result = compute_nee(NEEInputs(
            gpp_gC_m2_yr=1000.0,
            npp_total_gC_m2_yr=500.0,
            rh_tC_ha_yr=2.0,
        ))
        # npp_tC_ha_yr = 500 x 0.01 = 5.0
        # nee = -(5.0 - 2.0) = -3.0 tC/ha/yr (sink)
        assert result.nee_tC_ha_yr < 0

    def test_positive_nee_is_source(self):
        """When Rh > NPP, NEE is positive (carbon source)."""
        result = compute_nee(NEEInputs(
            gpp_gC_m2_yr=200.0,
            npp_total_gC_m2_yr=100.0,
            rh_tC_ha_yr=3.0,
        ))
        # npp_tC_ha_yr = 1.0, nee = -(1.0 - 3.0) = +2.0 (source)
        assert result.nee_tC_ha_yr > 0

    def test_necb_includes_harvest_and_amendments(self):
        result = compute_nee(NEEInputs(
            gpp_gC_m2_yr=1000.0,
            npp_total_gC_m2_yr=500.0,
            rh_tC_ha_yr=2.0,
            c_exported_harvest_tC_ha_yr=1.0,
            c_amendments_imported_tC_ha_yr=0.5,
        ))
        assert result.necb_tC_ha_yr == result.nee_tC_ha_yr - 1.0 + 0.5

    def test_autotrophic_respiration_is_gpp_minus_npp(self):
        result = compute_nee(NEEInputs(
            gpp_gC_m2_yr=1000.0,
            npp_total_gC_m2_yr=500.0,
            rh_tC_ha_yr=2.0,
        ))
        # Ra = GPP - NPP = 1000 - 500 = 500 gC/m2/yr
        assert abs(result.ra_gC_m2_yr - 500.0) < 0.01


class TestCO2eqNet:
    def test_sink_with_emissions(self):
        """A field sequestering -5 tCO2/ha/yr but emitting 0.5 tN2O-CO2eq has net -4.5."""
        net = compute_co2eq_net(
            nee_tCO2_ha_yr=-5.0,  # sink
            n2o_tCO2eq_ha_yr=0.5,
            ch4_tCO2eq_ha_yr=0.0,
        )
        # NEE + N2O = -5.0 + 0.5 = -4.5 (sink reduced by N2O)
        assert net == -4.5

    def test_net_with_methane(self):
        """With both N2O and CH4 emissions."""
        net = compute_co2eq_net(
            nee_tCO2_ha_yr=-3.0,
            n2o_tCO2eq_ha_yr=0.3,
            ch4_tCO2eq_ha_yr=0.1,
        )
        # NEE + N2O + CH4 = -3.0 + 0.3 + 0.1 = -2.6
        assert net == -2.6

    def test_emissions_exceed_sink(self):
        """When GHG emissions exceed sequestration, net is positive (source)."""
        net = compute_co2eq_net(
            nee_tCO2_ha_yr=-0.5,  # small sink
            n2o_tCO2eq_ha_yr=2.0,
        )
        assert net > 0
