"""Onboarding pipeline -- reconstruct 10-year history + spin-up (spec 8.6).

Target: <30s end-to-end per parcel.
Steps run concurrently where possible.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field

from app.services.roth_c_model import MonthlyInputs

logger = logging.getLogger(__name__)


@dataclass
class OnboardingResult:
    parcela_id: str
    pools_t0: dict
    years_processed: int
    sources_used: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    latency_ms: int = 0


async def onboard_parcela(
    parcela_id: str,
    lat: float = 37.4,
    lon: float = -4.5,
    geometry_wkt: str = "",
    provincia: str = "",
    municipio: str = "",
    years_back: int = 10,
    clay_pct: float = 20.0,
    soc_initial_tC_ha: float = 50.0,
) -> OnboardingResult:
    """Onboard a new parcel: reconstruct history + spin-up RothC.

    Steps (concurrent where possible):
    1. SIGPAC + (SoilGrids would go here) in parallel
    2. Sentinel-2 + ERA5-Land in parallel
    3. Harmonize to monthly
    4. Run RothC spin-up
    5. Return t=0 state
    """
    t_start = time.monotonic()
    sources: list[str] = []
    warnings: list[str] = []

    current_year = 2026
    year_from = current_year - years_back

    # Step 1: SIGPAC
    sigpac_records = await _fetch_sigpac_safe(parcela_id, provincia, municipio, years_back)
    if sigpac_records:
        sources.append("sigpac")
    else:
        warnings.append("SIGPAC unavailable, using default crop assumptions")

    # Step 2-3: S2 + ERA5 concurrently
    s2_task = _fetch_s2_safe(geometry_wkt, year_from, current_year)
    era5_task = _fetch_era5_safe(lat, lon, year_from, current_year)

    s2_obs, era5_data = await asyncio.gather(s2_task, era5_task)

    if s2_obs:
        sources.append("sentinel2")
    else:
        warnings.append("Sentinel-2 unavailable, using default NDVI assumptions")

    if era5_data:
        sources.append("era5_land")
    else:
        warnings.append("ERA5-Land unavailable, using synthetic climate")

    # Step 4: Harmonize
    from app.reconstructor.temporal_harmonizer import harmonize_to_monthly

    monthly_records = harmonize_to_monthly(
        sigpac_records, s2_obs, era5_data,
        year_from=year_from, year_to=current_year,
    )

    # Convert to RothC MonthlyInputs
    monthly_inputs = [
        MonthlyInputs(
            temp_celsius=m.temp_celsius,
            precip_mm=m.precip_mm,
            etp_mm=m.etp_mm,
            cover_present=m.cover_present,
            c_input_aerea_tC_ha=m.c_input_aerea_tC_ha,
            c_input_raices_tC_ha=m.c_input_raices_tC_ha,
            c_input_exudados_tC_ha=m.c_input_exudados_tC_ha,
            clay_pct=clay_pct,
        )
        for m in monthly_records
    ]

    # Step 5: Spin-up
    from app.reconstructor.spinup_driver import run_spinup

    pools_t0 = await run_spinup(monthly_inputs, soc_initial_tC_ha, clay_pct, years_back)

    elapsed_ms = int((time.monotonic() - t_start) * 1000)
    logger.info("Onboarding %s complete in %d ms", parcela_id, elapsed_ms)

    return OnboardingResult(
        parcela_id=parcela_id,
        pools_t0=pools_t0.to_dict(),
        years_processed=years_back,
        sources_used=sources,
        warnings=warnings,
        latency_ms=elapsed_ms,
    )


async def _fetch_sigpac_safe(parcela_id: str, provincia: str, municipio: str, years_back: int):
    try:
        from app.reconstructor.sigpac_connector import fetch_sigpac_history
        return await fetch_sigpac_history(parcela_id, provincia, municipio, years_back)
    except Exception as e:
        logger.warning("SIGPAC fetch: %s", e)
        return []


async def _fetch_s2_safe(geometry_wkt: str, year_from: int, year_to: int):
    try:
        from app.reconstructor.sentinel2_connector import fetch_s2_timeseries
        return await fetch_s2_timeseries(
            geometry_wkt,
            date_from=f"{year_from}-01-01",
            date_to=f"{year_to}-12-31",
        )
    except Exception as e:
        logger.warning("S2 fetch: %s", e)
        return []


async def _fetch_era5_safe(lat: float, lon: float, year_from: int, year_to: int):
    try:
        from app.reconstructor.era5_connector import fetch_era5_monthly
        return await fetch_era5_monthly(lat, lon, year_from, year_to)
    except Exception as e:
        logger.warning("ERA5 fetch: %s", e)
        return []
