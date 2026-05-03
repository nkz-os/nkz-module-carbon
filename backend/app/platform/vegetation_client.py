"""HTTP client for vegetation-prime API."""

import logging
import os
from dataclasses import dataclass

import httpx

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
