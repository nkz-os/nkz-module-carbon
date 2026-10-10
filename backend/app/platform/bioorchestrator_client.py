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
    kc: Optional[float] = None
    lue_gC_per_MJ: Optional[float] = None
    fapar_a: Optional[float] = None
    fapar_b: Optional[float] = None
    fapar_vi_type: str = "NDVI"
    root_fraction: Optional[float] = None
    photosynthetic_type: str = "C3"
    morphological_type: str = "herbaceous"
    match_level: str = "none"  # "exact" | "generic" | "none"


def _opt_float(v) -> Optional[float]:
    """A number the source gave, or None — never a generic default."""
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


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
                kc=_opt_float(data.get("kc")),
                lue_gC_per_MJ=data.get("lue_gC_per_MJ"),
                fapar_a=data.get("fapar_a"),
                fapar_b=data.get("fapar_b"),
                fapar_vi_type=data.get("fapar_vi_type", "NDVI"),
                root_fraction=_opt_float(data.get("root_fraction")),
                photosynthetic_type=data.get("photosynthetic_type", "C3"),
                morphological_type=data.get("morphological_type", "herbaceous"),
                match_level=data.get("match_level", "generic"),
            )
        except Exception as exc:
            logger.warning("BioOrchestrator phenology fetch failed: %s", exc)
            return None
