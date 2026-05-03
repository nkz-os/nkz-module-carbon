"""HTTP client for BioOrchestrator API."""

import logging
import os
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BIOORCHESTRATOR_URL = os.getenv(
    "BIOORCHESTRATOR_URL", "http://bioorchestrator-api-service:8420"
)


@dataclass
class PhenologyParams:
    """Crop phenology parameters from BioOrchestrator."""
    species: str
    scientific_name: str = ""
    stage: str = ""
    kc: float = 0.0
    lue_gC_per_MJ: Optional[float] = None
    fapar_a: Optional[float] = None
    fapar_b: Optional[float] = None
    fapar_vi_type: str = "NDVI"
    root_fraction: float = 0.22
    photosynthetic_type: str = "C3"
    morphological_type: str = "herbaceous"
    match_level: str = "none"  # "exact" | "generic" | "none"


@dataclass
class SoilData:
    """Soil properties from BioOrchestrator (SoilGrids proxy)."""
    clay_pct: float = 20.0
    sand_pct: float = 30.0
    silt_pct: float = 50.0
    ph: float = 7.0
    soc_tC_ha: Optional[float] = None  # 0-30cm
    bulk_density_kg_m3: Optional[float] = None


async def fetch_phenology_params(
    species: str,
    gdd: float | None = None,
    lat: float | None = None,
    lon: float | None = None,
    client: httpx.AsyncClient | None = None,
) -> PhenologyParams | None:
    """Fetch crop phenology parameters. Returns None if species not found."""
    async with (client or httpx.AsyncClient()) as c:
        try:
            params = {"species": species}
            if gdd is not None:
                params["gdd"] = gdd
            if lat is not None:
                params["lat"] = lat
            if lon is not None:
                params["lon"] = lon

            resp = await c.get(
                f"{BIOORCHESTRATOR_URL}/api/graph/phenology-params",
                params=params,
                timeout=10,
            )
            if resp.status_code == 404:
                logger.info("Species '%s' not found in BioOrchestrator", species)
                return None
            resp.raise_for_status()
            data = resp.json()

            return PhenologyParams(
                species=data.get("species", species),
                scientific_name=data.get("scientific_name", ""),
                stage=data.get("stage", ""),
                kc=float(data.get("kc", 0.7)),
                lue_gC_per_MJ=data.get("lue_gC_per_MJ"),
                fapar_a=data.get("fapar_a"),
                fapar_b=data.get("fapar_b"),
                fapar_vi_type=data.get("fapar_vi_type", "NDVI"),
                root_fraction=float(data.get("root_fraction", 0.22)),
                photosynthetic_type=data.get("photosynthetic_type", "C3"),
                morphological_type=data.get("morphological_type", "herbaceous"),
                match_level=data.get("match_level", "generic"),
            )
        except Exception as exc:
            logger.warning("BioOrchestrator phenology fetch failed: %s", exc)
            return None


async def fetch_soil_data(
    lat: float,
    lon: float,
    client: httpx.AsyncClient | None = None,
) -> SoilData | None:
    """Fetch soil properties from BioOrchestrator (SoilGrids 2.0 proxy)."""
    async with (client or httpx.AsyncClient()) as c:
        try:
            resp = await c.get(
                f"{BIOORCHESTRATOR_URL}/api/graph/soil-data",
                params={"lat": lat, "lon": lon},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            return SoilData(
                clay_pct=float(data.get("clay_pct", 20.0)),
                sand_pct=float(data.get("sand_pct", 30.0)),
                silt_pct=float(data.get("silt_pct", 50.0)),
                ph=float(data.get("ph", 7.0)),
                soc_tC_ha=data.get("soc_tC_ha"),
                bulk_density_kg_m3=data.get("bulk_density_kg_m3"),
            )
        except Exception as exc:
            logger.warning("BioOrchestrator soil data fetch failed: %s", exc)
            return None
