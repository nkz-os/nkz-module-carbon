"""Cache layer -- Redis L1 + S3/MinIO L2 (spec 8.5)."""

import hashlib
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def cache_key(parcel_id: str, year: int, product: str) -> str:
    """Deterministic cache key: sha256(parcel_id:year:product)[:16]."""
    raw = f"{parcel_id}:{year}:{product}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def get_cached(key: str, redis_client=None) -> Optional[dict]:
    """Get from L1 (Redis). Returns None on miss or unavailable."""
    if redis_client is None:
        return None
    try:
        data = await redis_client.get(key)
        return json.loads(data) if data else None
    except Exception:
        return None


async def set_cache(key: str, data: dict, ttl_seconds: int, redis_client=None):
    """Set L1 cache with TTL. No-op if Redis unavailable."""
    if redis_client is None:
        return
    try:
        await redis_client.setex(key, ttl_seconds, json.dumps(data, default=str))
    except Exception:
        pass


def is_closed_year(year: int, current_year: int = 2026) -> bool:
    """Closed years (≤ current - 1) have permanent cache."""
    return year <= current_year - 1
