"""Temporal harmonizer -- align heterogeneous sources to monthly timestep (spec 8.4)."""

import logging
from dataclasses import dataclass, field

from app.reconstructor.sigpac_connector import SigpacRecord, sigpac_to_nkz_crop
from app.reconstructor.sentinel2_connector import S2Observation
from app.reconstructor.era5_connector import Era5Monthly

logger = logging.getLogger(__name__)


@dataclass
class MonthlyRecord:
    """One month of harmonized data ready for RothC."""
    year: int
    month: int
    temp_celsius: float
    precip_mm: float
    etp_mm: float
    cover_present: bool
    crop_type: str
    ndvi_mean: float = 0.5
    c_input_aerea_tC_ha: float = 0.0
    c_input_raices_tC_ha: float = 0.0
    c_input_exudados_tC_ha: float = 0.0


def harmonize_to_monthly(
    sigpac_records: list,
    s2_observations: list,
    era5_monthly: list,
    year_from: int,
    year_to: int,
) -> list[MonthlyRecord]:
    """Harmonize all sources to monthly timestep for RothC."""
    # Build lookup maps
    sigpac_by_year = {r.year: r for r in (sigpac_records or [])}
    s2_by_month = {}
    for obs in (s2_observations or []):
        month_key = obs.date[:7] if hasattr(obs, 'date') else ""
        s2_by_month[month_key] = obs
    era5_by_month = {(r.year, r.month): r for r in (era5_monthly or [])}

    records = []
    current_year = 2026
    years_back = current_year - year_from

    for year in range(year_from, year_to + 1):
        sigpac = sigpac_by_year.get(year)
        crop = sigpac_to_nkz_crop(sigpac.uso_sigpac) if sigpac else "fallow"

        for month in range(1, 13):
            era5 = era5_by_month.get((year, month))
            month_key = f"{year}-{month:02d}"
            s2 = s2_by_month.get(month_key)

            temp = era5.temp_air_celsius if era5 else 20.0
            precip = era5.precip_mm if era5 else 50.0
            etp = era5.etp_mm if era5 else 80.0
            ndvi = s2.ndvi_mean if s2 else 0.5
            cover = _crop_active_in_month(crop, month)

            c_inputs = _estimate_monthly_c_inputs(crop, ndvi, cover)

            records.append(MonthlyRecord(
                year=year, month=month,
                temp_celsius=temp,
                precip_mm=precip,
                etp_mm=etp,
                cover_present=cover,
                crop_type=crop,
                ndvi_mean=ndvi,
                c_input_aerea_tC_ha=c_inputs["aerea"],
                c_input_raices_tC_ha=c_inputs["raices"],
                c_input_exudados_tC_ha=c_inputs["exudados"],
            ))

    return records


def _crop_active_in_month(crop: str, month: int) -> bool:
    """Determine if crop is actively growing (Mediterranean calendar)."""
    if crop in ("olive", "vineyard", "fruit_tree", "almond", "citrus"):
        return True
    if crop in ("cereal", "wheat", "corn", "sunflower"):
        return month in [11, 12, 1, 2, 3, 4, 5, 6]
    if crop == "rice":
        return month in [4, 5, 6, 7, 8, 9]
    if crop == "pasture":
        return month in [3, 4, 5, 6, 10, 11]
    if crop == "fallow":
        return False
    return True


def _estimate_monthly_c_inputs(crop: str, ndvi: float, cover: bool) -> dict:
    """Estimate monthly C inputs from crop type + NDVI proxy."""
    if not cover or crop == "fallow":
        return {"aerea": 0.0, "raices": 0.0, "exudados": 0.0}

    # Rough GPP from NDVI proxy, then partition to soil inputs
    gpp_estimate = ndvi * 3.0   # gC/m2/month, rough estimate
    npp = gpp_estimate * 0.5     # CUE
    npp_tC_ha = npp * 0.01       # gC/m2 → tC/ha

    root_fractions = {
        "olive": 0.20, "almond": 0.20, "vineyard": 0.15,
        "cereal": 0.22, "wheat": 0.22, "corn": 0.18,
        "pasture": 0.55, "rice": 0.15,
    }
    root_frac = root_fractions.get(crop, 0.22)
    exudate_frac = 0.07

    return {
        "aerea": round(npp_tC_ha * 0.5, 4),           # ~50% stays as residue
        "raices": round(npp_tC_ha * root_frac, 4),
        "exudados": round(npp_tC_ha * exudate_frac, 4),
    }
