"""
Carbon Capture Engine — LUE (Light Use Efficiency) Model.

Extracted from nekazari-module-vegetation-health/backend/app/jobs/carbon_calculator.py.
This module is responsible for all carbon calculations; vegetation-health only
provides spectral indices.

Formula:
  GPP  = PAR × fAPAR × LUE                   [gC/m²/day]
  fAPAR ≈ (NDVI - 0.2) / 0.8, clamped [0, 0.95]
  NPP  = GPP × 0.5  (autotrophic respiration discount)
  CO2  = NPP × 3.664  [gCO2/m²/day]
  CO2_parcel = CO2 × area_m² / 1000          [kgCO2/day]

PAR source (priority order):
  1. Weather-worker API  (/api/weather/par?lat=…&lon=…&date=…)
  2. Fallback constant 20 MJ/m²/day (summer midlatitude average)

NGSI-LD properties published to AgriParcel:
  carbonFixationRateDaily   [gC/m²/day]   — source: "carbon"
  co2SequesteredCumulative  [kgCO2]       — source: "carbon"
  gppDaily                  [gC/m²/day]
  nppDaily                  [gC/m²/day]
"""

import logging
import os
from datetime import date, datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# LUE constants per crop type [gC/MJ]
LUE_VALUES: dict[str, float] = {
    "olive":    1.2,
    "vineyard": 1.0,
    "wheat":    1.5,
    "corn":     1.7,
    "rice":     1.4,
    "sunflower": 1.3,
    "default":  1.1,
}

# Molar mass ratio CO2/C = 44/12
_GC_TO_GCO2 = 3.6667
_PAR_FALLBACK_MJ = 20.0


def _get_par_from_weather(lat: float, lon: float, obs_date: date) -> float:
    """Fetch PAR from weather-worker. Falls back to constant on error."""
    url = os.getenv("WEATHER_WORKER_URL", "http://weather-worker-service:8000")
    try:
        resp = requests.get(
            f"{url}/api/weather/par",
            params={"lat": lat, "lon": lon, "date": obs_date.isoformat()},
            timeout=5,
        )
        resp.raise_for_status()
        return float(resp.json()["par_mj_m2"])
    except Exception as exc:
        logger.warning("PAR fetch failed (%s), using fallback %.1f MJ/m²", exc, _PAR_FALLBACK_MJ)
        return _PAR_FALLBACK_MJ


def calculate_carbon(
    ndvi: float,
    area_m2: float,
    crop_species: str = "default",
    par: Optional[float] = None,
) -> dict:
    """
    Calculate carbon metrics from NDVI and parcel area.

    Args:
        ndvi:         Mean NDVI value for the parcel (from vegetation_indices_cache).
        area_m2:      Parcel area in square metres.
        crop_species: Crop type for LUE lookup.
        par:          Photosynthetically Active Radiation [MJ/m²/day].
                      If None, uses fallback constant.
    Returns:
        dict with keys: gpp, npp, co2_g_m2, co2_kg_parcel, fapar, lue, par
    """
    lue   = LUE_VALUES.get(crop_species.lower(), LUE_VALUES["default"])
    fapar = max(0.0, min(0.95, (ndvi - 0.2) * 1.25))
    par   = par if par is not None else _PAR_FALLBACK_MJ

    gpp           = par * fapar * lue           # gC/m²/day
    npp           = gpp * 0.5                   # gC/m²/day (respiration)
    co2_g_m2      = npp * _GC_TO_GCO2           # gCO2/m²/day
    co2_kg_parcel = co2_g_m2 * area_m2 / 1000  # kgCO2/day for whole parcel

    return {
        "gpp":           round(gpp,           6),
        "npp":           round(npp,           6),
        "co2_g_m2":      round(co2_g_m2,      6),
        "co2_kg_parcel": round(co2_kg_parcel, 4),
        "fapar":         round(fapar,         6),
        "lue":           lue,
        "par":           par,
    }
