"""RothC spin-up driver -- run model from t=-N to t=0 (spec 11.3)."""

import logging

from app.services.roth_c_model import RothCMonth, RothCPools, RothCState, run_months, weihermuller_pools

logger = logging.getLogger(__name__)


async def run_spinup(
    monthly_inputs: list[RothCMonth],
    soc_initial_estimate_tC_ha: float,
    clay_pct: float,
    years: int = 10,
    depth_cm: float = 30.0,
) -> RothCPools:
    """Run RothC from t=-years to t=0 starting from the Weihermüller partition."""
    start = RothCState(weihermuller_pools(soc_initial_estimate_tC_ha, clay_pct), 0.0)
    if not monthly_inputs:
        logger.warning("No monthly inputs for spin-up, using the Weihermüller partition directly")
        return start.pools
    final = run_months(start, monthly_inputs, clay_pct, depth_cm).final
    logger.info("Spin-up complete: SOC %.1f -> %.1f tC/ha over %d years",
                soc_initial_estimate_tC_ha, final.pools.total, years)
    return final.pools
