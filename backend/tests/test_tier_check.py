"""check_tier resolves the tenant plan from Postgres and gates premium."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.common.tier_check import REQUIRED_PLAN_LEVEL, check_tier


def _request(tenant="montiko"):
    req = MagicMock()
    req.headers = {"X-Tenant-ID": tenant}
    return req


def _pool(plan_level):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={"plan_level": plan_level})
    return pool


@pytest.mark.asyncio
async def test_premium_or_above_passes():
    with patch("app.common.tier_check.get_pool", AsyncMock(return_value=_pool(3))):
        await check_tier(_request())  # enterprise → no raise


@pytest.mark.asyncio
async def test_basic_is_rejected():
    with patch("app.common.tier_check.get_pool", AsyncMock(return_value=_pool(1))):
        with pytest.raises(HTTPException) as exc:
            await check_tier(_request())
        assert exc.value.status_code == 402


@pytest.mark.asyncio
async def test_db_error_fails_open():
    async def boom():
        raise RuntimeError("db down")

    with patch("app.common.tier_check.get_pool", boom):
        await check_tier(_request())  # no raise → fail-open


@pytest.mark.asyncio
async def test_missing_tenant_row_fails_open():
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    with patch("app.common.tier_check.get_pool", AsyncMock(return_value=pool)):
        await check_tier(_request())  # no row → fail-open
