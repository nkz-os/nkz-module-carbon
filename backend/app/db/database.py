"""asyncpg database connection for audit log (spec 1.2)."""

import logging
import os

import asyncpg

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Get or create the asyncpg connection pool."""
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL environment variable is not set")
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
        )
        logger.info("Database pool created")
    return _pool


async def close_pool():
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")


async def insert_carbon_calculation(
    tenant_id: str,
    entity_id: str,
    tier: int,
    methodology: str,
    data_sources: list[str],
    input_params: dict,
    results: dict,
    confidence: float,
    confidence_interval_pct: float,
    calculated_by: str = "scheduler",
) -> str:
    """Insert an audit log entry. Returns the UUID of the new row."""
    pool = await get_pool()
    import json
    row = await pool.fetchrow(
        """
        INSERT INTO admin_platform.carbon_calculations (
            tenant_id, entity_id, tier, methodology,
            data_sources, input_params, results,
            confidence, confidence_interval_pct, calculated_by
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING id
        """,
        tenant_id,
        entity_id,
        tier,
        methodology,
        json.dumps(data_sources),
        json.dumps(input_params),
        json.dumps(results),
        confidence,
        confidence_interval_pct,
        calculated_by,
    )
    return str(row["id"])
