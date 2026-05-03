import math

from app.services.roth_c_model import (
    a_temp,
    b_humedad,
    tsmd_max,
    compute_monthly_tsmd,
    init_pools_weihermuller,
    compute_c_inputs,
    step_month,
    run_rothc_monthly,
    PoolState,
    MonthlyInputs,
)


class TestATemp:
    def test_20c_about_2_8(self):
        """a_temp(20C) should be ~2.82 (RothC canonical)."""
        result = a_temp(20.0)
        assert 2.5 < result < 3.0, f"Expected ~2.82, got {result}"

    def test_0c_is_low(self):
        result = a_temp(0.0)
        assert 0.1 < result < 0.2, f"Expected ~0.144, got {result}"

    def test_below_minus_18_clamped(self):
        assert a_temp(-20.0) == 0.0
        assert a_temp(-18.0) == 0.0

    def test_monotonic(self):
        """a_temp must be monotonically increasing."""
        vals = [a_temp(t) for t in [-10, 0, 10, 20, 30]]
        for i in range(len(vals) - 1):
            assert vals[i] <= vals[i + 1] + 1e-10


class TestTSMD:
    def test_tsmd_max_20pct_clay(self):
        """TSMD_max for 20% clay ~42mm."""
        tsmax = tsmd_max(20.0)
        assert 40 < tsmax < 46

    def test_tsmd_monthly_accumulation(self):
        precip = [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10]
        etp = [40, 40, 40, 40, 40, 40, 40, 40, 40, 40, 40, 40]
        covers = [0.8] * 12
        tsmd = compute_monthly_tsmd(precip, etp, covers, 20.0)
        # With moderate ETP > precip but not saturating immediately
        assert tsmd[-1] > tsmd[0]

    def test_b_humedad_no_stress(self):
        """When TSMD below threshold, b=1.0."""
        assert b_humedad(0.0, 100.0) == 1.0

    def test_b_humedad_full_stress(self):
        """When TSMD at max, b approaches 0.2."""
        tsmax = 100.0
        b = b_humedad(tsmax, tsmax)
        assert 0.19 < b < 0.25, f"Expected ~0.2, got {b}"


class TestWeihermuller:
    def test_pools_sum_to_total(self):
        pools = init_pools_weihermuller(soc_total_tC_ha=50.0, clay_pct=20.0)
        assert abs(pools.total_tC_ha - 50.0) < 0.01

    def test_iom_is_positive(self):
        pools = init_pools_weihermuller(soc_total_tC_ha=40.0, clay_pct=15.0)
        assert pools.iom_tC_ha > 0.0

    def test_hum_is_largest_pool(self):
        pools = init_pools_weihermuller(soc_total_tC_ha=50.0, clay_pct=20.0)
        assert pools.hum_tC_ha > pools.dpm_tC_ha
        assert pools.hum_tC_ha > pools.rpm_tC_ha
        assert pools.hum_tC_ha > pools.bio_tC_ha


class TestCarbonInputs:
    def test_no_inputs_return_zero(self):
        mi = MonthlyInputs(temp_celsius=20.0, precip_mm=50.0, etp_mm=80.0)
        dpm, rpm, hum = compute_c_inputs(mi)
        assert dpm == 0.0
        assert rpm == 0.0
        assert hum == 0.0

    def test_aerial_input_split(self):
        mi = MonthlyInputs(
            temp_celsius=20.0, precip_mm=50.0, etp_mm=80.0,
            c_input_aerea_tC_ha=1.0,
        )
        dpm, rpm, hum = compute_c_inputs(mi)
        # 1.0 * h=1.0 = 1.0, split 1.44:1 -> dpm=0.59, rpm=0.41
        assert dpm > 0.0
        assert rpm > 0.0
        assert dpm > rpm  # DPM fraction should be larger for annual crops
        assert hum == 0.0


class TestMonthlyEvolution:
    def test_one_month_no_input_soc_decreases(self):
        pools = init_pools_weihermuller(soc_total_tC_ha=50.0, clay_pct=20.0)
        monthly = MonthlyInputs(
            temp_celsius=20.0,
            precip_mm=50.0,
            etp_mm=80.0,
            cover_present=True,
            clay_pct=20.0,
        )
        tsmd_val = 10.0
        new_pools, rh = step_month(pools, monthly, tsmd_val)
        # With no input, SOC should decrease slightly (respiration)
        assert new_pools.total_tC_ha <= pools.total_tC_ha + 1e-10
        assert rh > 0

    def test_one_month_with_high_input_dpm_increases(self):
        pools = init_pools_weihermuller(soc_total_tC_ha=50.0, clay_pct=20.0)
        monthly = MonthlyInputs(
            temp_celsius=20.0,
            precip_mm=50.0,
            etp_mm=80.0,
            cover_present=True,
            c_input_aerea_tC_ha=1.0,
            c_input_raices_tC_ha=0.5,
            c_input_exudados_tC_ha=0.1,
            clay_pct=20.0,
        )
        tsmd_val = 10.0
        new_pools, rh = step_month(pools, monthly, tsmd_val)
        # With high input, DPM should increase
        assert new_pools.dpm_tC_ha > pools.dpm_tC_ha

    def test_run_rothc_12_months_mass_conservation(self):
        """Mass conservation over 12 months: sum(in) - Rh ~ delta_SOC."""
        initial_pools = init_pools_weihermuller(soc_total_tC_ha=50.0, clay_pct=20.0)
        total_input = 0.0
        monthly_inputs = []
        for m in range(12):
            mi = MonthlyInputs(
                temp_celsius=20.0,
                precip_mm=50.0,
                etp_mm=60.0,
                cover_present=True,
                c_input_aerea_tC_ha=0.3,
                c_input_raices_tC_ha=0.15,
                clay_pct=20.0,
            )
            total_input += 0.3 + 0.15  # raw C input before humification
            monthly_inputs.append(mi)

        result = run_rothc_monthly(initial_pools, monthly_inputs, 20.0)
        delta_soc = result.pools.total_tC_ha - initial_pools.total_tC_ha
        rh_total = result.rh_tC_ha_yr

        # sum(in) * humification - Rh ~ delta_SOC
        # h_aerea=1.0 so aerial input = 0.3*12=3.6, h_root=2.3 so root input = 0.15*12*2.3=4.14
        expected_input_humified = 3.6 * 1.0 + 1.8 * 2.3
        balance = expected_input_humified - rh_total - delta_soc
        assert abs(balance) < 0.5, (
            f"Mass balance: input_hum={expected_input_humified:.4f}, "
            f"rh={rh_total:.4f}, delta_soc={delta_soc:.4f}, balance={balance:.4f}"
        )

    def test_length_of_tsmd_matches_inputs(self):
        """TSMD series length should match number of months."""
        monthly_inputs = []
        for m in range(24):
            monthly_inputs.append(MonthlyInputs(
                temp_celsius=20.0, precip_mm=50.0, etp_mm=60.0, cover_present=True,
            ))
        initial_pools = init_pools_weihermuller(soc_total_tC_ha=50.0, clay_pct=20.0)
        result = run_rothc_monthly(initial_pools, monthly_inputs, 20.0)
        assert len(result.monthly_tsmd) == 24
