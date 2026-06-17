"""Shared FastAPI auth dependencies for carbon module.

User-facing endpoints: require_auth() from nkz-platform-sdk
  (reads X-Tenant-ID, X-User-ID, X-User-Roles injected by api-gateway)

Internal endpoints: require_tenant_header()
  (reads NGSILD-Tenant for service-to-service calls: DataHub, webhooks)
"""

import re
from typing import Optional

from fastapi import Depends, Header, HTTPException
from nkz_platform_sdk.auth import AuthContext, require_auth as sdk_require_auth
from app.common.tenant_utils import normalize_tenant_id

__all__ = ["AuthContext", "require_auth", "require_tenant_header"]


def require_auth(roles: Optional[list[str]] = None):
    """FastAPI dependency for user-facing endpoints.

    Uses the api-gateway injected headers: X-Tenant-ID, X-User-ID, X-User-Roles.
    Optionally enforces role membership.
    """
    return sdk_require_auth(roles=roles)


async def require_tenant_header(
    ngsild_tenant: str = Header(default="", alias="NGSILD-Tenant"),
    fiware_service: str = Header(default="", alias="Fiware-Service"),
) -> str:
    """FastAPI dependency for internal service-to-service endpoints.

    Reads NGSILD-Tenant (preferred) or Fiware-Service (legacy) header.
    Does NOT validate JWT — only checks header presence and format.

    Raises 400 if no valid tenant header is present.
    """
    raw = ngsild_tenant or fiware_service
    if not raw:
        raise HTTPException(
            status_code=400,
            detail="NGSILD-Tenant or Fiware-Service header is required",
        )

    # Normalize via platform canonical
    normalized = normalize_tenant_id(raw)
    if len(normalized) < 3:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tenant ID: {raw}",
        )
    return normalized
