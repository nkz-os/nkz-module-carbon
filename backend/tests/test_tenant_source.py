"""The module reads platform tenant data through the views, never the core tables."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.common.tier_check import check_tier
from app.db import database


@pytest.mark.asyncio
async def test_tier_reads_the_plan_view():
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={"plan_level": 3})
    req = MagicMock()
    req.headers = {"X-Tenant-ID": "acmefarm"}
    with patch("app.common.tier_check.get_pool", AsyncMock(return_value=pool)):
        await check_tier(req)
    assert "FROM module_tenant_plan" in pool.fetchrow.call_args.args[0]


@pytest.mark.asyncio
async def test_installed_tenants_read_the_installations_view():
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[{"tenant_id": "t1"}])
    with patch.object(database, "get_pool", AsyncMock(return_value=pool)):
        assert await database.list_tenants_with_module("carbon") == ["t1"]
    assert "FROM module_installations" in pool.fetch.call_args.args[0]
