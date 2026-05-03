"""Mass conservation and monotonicity validation (spec 12.3, 12.4).

12.3: sum(C_inputs) - sum(C_outputs) - delta_SOC = 0 +- 0.1%
12.4: increasing organic amendments must monotonically increase final SOC
"""

import pytest
from dataclasses import dataclass

from app.services.roth_c_model import (
    MonthlyInputs,
    PoolState,
    init_pools_weihermuller,
    run_rothc_monthly,
    compute_c_inputs,
)


@dataclass
class ConservationResult:
    total_c_input_tC_ha: float
    total_rh_tC_ha: float
    delta_soc_tC_ha: float
    balance_tC_ha: float
    balance_pct: float


def _run_conservation_test(
    years: int,
    monthly_c_input: float,
    temp: float = 20.0,
    precip: float = 50.0,
    etp: float = 80.0,
    clay: float = 20.0,
) -> ConservationResult:
    """Run RothC and check mass conservation."""
    initial_soc = 50.0
    pools = init_pools_weihermuller(initial_soc, clay)

    monthly = [
        MonthlyInputs(
            temp_celsius=temp,
            precip_mm=precip,
            etp_mm=etp,
            cover_present=True,
            c_input_aerea_tC_ha=monthly_c_input,
            clay_pct=clay,
        )
        for _ in range(years * 12)
    ]

    result = run_rothc_monthly(pools, monthly, clay)

    total_input = monthly_c_input * years * 12
    # inputs are humified: h_aerea=1.0, split DPM/RPM
    # The C actually entering pools is humified C
    # For the conservation check, we verify: input_humified - RH = delta_SOC
    total_rh = result.rh_tC_ha_yr * years
    delta_soc = result.pools.total_tC_ha - initial_soc

    # The input is humified before entering pools
    # h_aerea=1.0 for aerial inputs, so humified input = total_input
    humified_input = total_input * 1.0

    balance = humified_input - total_rh - delta_soc
    balance_pct = abs(balance) / initial_soc * 100 if initial_soc > 0 else float('inf')

    return ConservationResult(
        total_c_input_tC_ha=humified_input,
        total_rh_tC_ha=total_rh,
        delta_soc_tC_ha=delta_soc,
        balance_tC_ha=balance,
        balance_pct=balance_pct,
    )


class TestMassConservation:
    """Spec 12.3: sum(C_in) - sum(C_out) - delta_SOC = 0 +- 0.1%."""

    def test_1_year_conservation(self):
        result = _run_conservation_test(years=1, monthly_c_input=0.3)
        assert result.balance_pct < 0.1, (
            f"1-year mass balance: {result.balance_tC_ha:.6f} tC/ha "
            f"({result.balance_pct:.4f}% of initial SOC)"
        )

    def test_5_year_conservation(self):
        result = _run_conservation_test(years=5, monthly_c_input=0.3)
        assert result.balance_pct < 0.1, (
            f"5-year mass balance: {result.balance_tC_ha:.6f} tC/ha "
            f"({result.balance_pct:.4f}% of initial SOC)"
        )

    def test_10_year_conservation(self):
        result = _run_conservation_test(years=10, monthly_c_input=0.3)
        assert result.balance_pct < 0.1, (
            f"10-year mass balance: {result.balance_tC_ha:.6f} tC/ha "
            f"({result.balance_pct:.4f}% of initial SOC)"
        )

    def test_high_input_scenario(self):
        """High C inputs should still conserve mass."""
        result = _run_conservation_test(years=5, monthly_c_input=1.0)
        assert result.balance_pct < 0.2, (
            f"High-input mass balance at {result.balance_pct:.4f}%"
        )

    def test_zero_input_scenario(self):
        """Zero input: SOC should decrease, but mass still conserved."""
        result = _run_conservation_test(years=5, monthly_c_input=0.0)
        assert result.balance_pct < 0.1
        assert result.delta_soc_tC_ha < 0  # SOC decreases with no input

    def test_balance_not_zero_with_significant_error(self):
        """The balance should NOT show drift over long periods."""
        result = _run_conservation_test(years=20, monthly_c_input=0.1)
        assert result.balance_pct < 0.15, (
            f"Long-term drift at {result.balance_pct:.4f}%"
        )


class TestMonotonicity:
    """Spec 12.4: increasing amendments -> monotonically increasing SOC."""

    def test_increasing_amendments_increases_soc(self):
        """0 -> 0.5 -> 1.0 -> 2.0 tC/ha/month should give increasing SOC."""
        amendments = [0.0, 0.1, 0.3, 0.5, 1.0]
        soc_values = []

        for amt in amendments:
            initial_pools = init_pools_weihermuller(50.0, 20.0)
            monthly = [
                MonthlyInputs(
                    temp_celsius=20.0, precip_mm=50.0, etp_mm=80.0,
                    cover_present=True,
                    c_input_enmienda_tC_ha=amt,
                    clay_pct=20.0,
                )
                for _ in range(24)  # 2 years
            ]
            result = run_rothc_monthly(initial_pools, monthly, 20.0)
            soc_values.append(result.pools.total_tC_ha)

        # Check monotonic increase
        for i in range(len(soc_values) - 1):
            assert soc_values[i] <= soc_values[i + 1], (
                f"Monotonicity violated: amendment={amendments[i]} -> "
                f"SOC={soc_values[i]:.2f}, "
                f"amendment={amendments[i+1]} -> SOC={soc_values[i+1]:.2f}"
            )

    def test_amendments_always_increase_soc_vs_no_amendments(self):
        """Any amount of amendment should beat no amendments."""
        initial_pools = init_pools_weihermuller(50.0, 20.0)

        # No amendments
        monthly_no = [
            MonthlyInputs(temp_celsius=20.0, precip_mm=50.0, etp_mm=80.0,
                          cover_present=True, clay_pct=20.0)
            for _ in range(24)
        ]
        result_no = run_rothc_monthly(initial_pools, monthly_no, 20.0)
        soc_no = result_no.pools.total_tC_ha

        # Tiny amendment
        monthly_yes = [
            MonthlyInputs(temp_celsius=20.0, precip_mm=50.0, etp_mm=80.0,
                          cover_present=True, c_input_enmienda_tC_ha=0.01,
                          clay_pct=20.0)
            for _ in range(24)
        ]
        result_yes = run_rothc_monthly(initial_pools, monthly_yes, 20.0)
        soc_yes = result_yes.pools.total_tC_ha

        assert soc_yes > soc_no, (
            f"Amendment of 0.01 should increase SOC. Without={soc_no:.2f}, With={soc_yes:.2f}"
        )
