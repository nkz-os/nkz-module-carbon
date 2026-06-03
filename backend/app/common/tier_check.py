"""Tier/plan validation for carbon module endpoints.

Requires premium tier for carbon calculations (per manifest.json).
Uses services/common/tier_quotas.py canonical PLAN_LEVELS mapping.
"""

import logging

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

# Module requirement from manifest.json
REQUIRED_PLAN_LEVEL = 2  # "premium"

# Inline the plan levels for self-contained deployment.
# Mirrors services/common/tier_quotas.py
PLAN_LEVELS = {"basic": 0, "pro": 1, "premium": 2, "enterprise": 3}


async def check_tier(request: Request):
    """Verify the tenant's plan allows carbon calculations.

    Reads X-Tenant-Plan header injected by api-gateway.
    Raises 402 Payment Required if the tenant is below premium tier.
    """
    plan = request.headers.get("X-Tenant-Plan", "basic").strip().lower()
    plan_level = PLAN_LEVELS.get(plan, 0)

    if plan_level < REQUIRED_PLAN_LEVEL:
        raise HTTPException(
            status_code=402,
            detail=f"Carbon module requires premium plan. Current: {plan}. "
                   f"Upgrade at https://nekazari.robotika.cloud/billing",
        )
