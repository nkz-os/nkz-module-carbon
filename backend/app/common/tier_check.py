"""Tier/plan validation for carbon module endpoints.

Requires premium tier for carbon calculations (per manifest.json).

Resolves the tenant's plan_level from the shared Postgres DB — the platform
convention is that each service reads tenant context itself; modules are
self-contained and never depend on core adding a per-module header.
"""

import logging

from fastapi import HTTPException, Request

from app.common.tenant_utils import normalize_tenant_id
from app.db.database import get_pool

logger = logging.getLogger(__name__)

# Module requirement from manifest.json: premium (plan_level 2) or above.
REQUIRED_PLAN_LEVEL = 2


async def check_tier(request: Request):
    """Verify the tenant's plan allows carbon calculations.

    Raises 402 Payment Required if the tenant is below premium. Fail-open on
    DB errors (platform convention): an infrastructure hiccup must not lock
    paying tenants out.
    """
    tenant_id = (
        normalize_tenant_id(request.headers.get("X-Tenant-ID") or "") or "default"
    )

    # Fail-open default: an unresolvable plan is treated as allowed.
    plan_level = REQUIRED_PLAN_LEVEL
    try:
        pool = await get_pool()
        row = await pool.fetchrow(
            "SELECT plan_level FROM tenants WHERE tenant_id = $1", tenant_id
        )
        if row is not None and row["plan_level"] is not None:
            plan_level = int(row["plan_level"])
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to resolve tenant plan for %s — failing open: %s",
            tenant_id, exc,
        )

    if plan_level < REQUIRED_PLAN_LEVEL:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Carbon module requires premium plan. "
                f"Current plan level: {plan_level}. "
                f"Upgrade at https://nekazari.robotika.cloud/billing"
            ),
        )
