"""HTTP client for vegetation-prime API."""

import logging
import os
from dataclasses import dataclass

import httpx

from app.services.spectral import MorphologicalType, select_index

logger = logging.getLogger(__name__)

VEGETATION_PRIME_URL = os.getenv(
    "VEGETATION_PRIME_URL", "http://vegetation-prime-api-service:8000"
)


@dataclass
class IndexResult:
    index_type: str
    mean_value: float
    min_value: float
    max_value: float
    std_dev: float
    pixel_count: int
    calculated_at: str | None


async def fetch_latest_indices(
    entity_id: str, tenant_id: str, client: httpx.AsyncClient | None = None
) -> list[IndexResult]:
    """Fetch latest vegetation index results for a parcel."""
    async with (client or httpx.AsyncClient()) as c:
        try:
            resp = await c.get(
                f"{VEGETATION_PRIME_URL}/api/vegetation/scenes/results/{entity_id}",
                headers={"NGSILD-Tenant": tenant_id},
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            return [
                IndexResult(
                    index_type=r["index_type"],
                    mean_value=float(r["mean_value"]),
                    min_value=float(r["min_value"]),
                    max_value=float(r["max_value"]),
                    std_dev=float(r.get("std_dev", 0)),
                    pixel_count=int(r.get("pixel_count", 0)),
                    calculated_at=r.get("calculated_at"),
                )
                for r in results
            ]
        except Exception as exc:
            logger.warning("Vegetation index fetch failed for %s: %s", entity_id, exc)
            return []


async def resolve_vi_for_parcel(
    entity_id: str,
    tenant_id: str,
    species: str,
    client: httpx.AsyncClient | None = None,
) -> tuple[float, str, str]:
    """Resolve the best vegetation index value for a parcel's crop species.

    Returns (vi_value, vi_type, data_quality).
    data_quality: "measured" | "simulated"
    """
    indices = await fetch_latest_indices(entity_id, tenant_id, client)

    if not indices:
        logger.info("No VI data for %s, using simulated 0.7 NDVI", entity_id)
        return (0.7, "NDVI", "simulated")

    # Determine which VI type is optimal for the crop morphological type
    woody_crops = {"olive", "vineyard", "almond", "citrus", "apple", "pear",
                   "peach", "plum", "cherry", "orange", "lemon", "forest",
                   "walnut", "pistachio"}
    morph = MorphologicalType.WOODY if species.lower() in woody_crops else MorphologicalType.HERBACEOUS
    preferred_vi = select_index(morph)

    # Find the best matching index
    preferred_name = preferred_vi.value
    for idx in indices:
        if idx.index_type.upper() == preferred_name.upper():
            return (idx.mean_value, idx.index_type, "measured")

    # Fall back: use whichever index is available
    logger.info("Preferred VI %s not found for %s, using %s", preferred_name, entity_id, indices[0].index_type)
    return (indices[0].mean_value, indices[0].index_type, "measured")
