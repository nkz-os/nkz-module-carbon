"""RothC spin-up driver -- run model from t=-N to t=0 (spec 11.3)."""

import logging

from app.services.roth_c_model import (
    MonthlyInputs,
    PoolState,
    init_pools_weihermuller,
    run_rothc_monthly,
)

logger = logging.getLogger(__name__)


async def run_spinup(
    monthly_inputs: list[MonthlyInputs],
    soc_initial_estimate_tC_ha: float,
    clay_pct: float,
    years: int = 10,
) -> PoolState:
    """Run RothC spin-up from t=-years to t=0.

    1. Initialize pools from SOC estimate (Weihermuller 2013)
    2. Run RothC monthly for N years
    3. Return pool state at t=0 (project start)
    """
    if not monthly_inputs:
        logger.warning("No monthly inputs for spin-up, using Weihermuller directly")
        return init_pools_weihermuller(soc_initial_estimate_tC_ha, clay_pct)

    initial_pools = init_pools_weihermuller(soc_initial_estimate_tC_ha, clay_pct)
    result = run_rothc_monthly(initial_pools, monthly_inputs, clay_pct)

    logger.info(
        "Spin-up complete: SOC %.1f -> %.1f tC/ha over %d years",
        soc_initial_estimate_tC_ha,
        result.pools.total_tC_ha,
        years,
    )
    return result.pools
