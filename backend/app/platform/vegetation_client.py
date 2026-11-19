"""Ask vegetation to keep a parcel's satellite monitoring continuous.

Carbon reads the NDVI of the days without a crop, so a parcel with carbon active must
not be paused after its harvest. Both calls are idempotent on vegetation's side, never
raise, and do nothing when ``VEGETATION_INTERNAL_URL`` is empty (no default: the URL is
a property of each installation).
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

MODULE_ID = "carbon"
_TIMEOUT = 10.0


def _url(parcel_urn: str) -> str | None:
    base = os.getenv("VEGETATION_INTERNAL_URL", "").rstrip("/")
    if not base:
        return None
    return f"{base}/api/internal/vegetation/parcels/{parcel_urn}/continuous"


async def _call(method: str, tenant_id: str, parcel_urn: str, client: httpx.AsyncClient | None) -> bool:
    url = _url(parcel_urn)
    if url is None:
        return False
    headers = {"X-Internal-Service-Secret": os.getenv("INTERNAL_SERVICE_SECRET", "")}
    payload = {"tenant_id": tenant_id, "module_id": MODULE_ID}
    kwargs = {"json": payload} if method == "POST" else {"params": payload}
    try:
        if client is not None:
            resp = await client.request(method, url, headers=headers, timeout=_TIMEOUT, **kwargs)
        else:
            async with httpx.AsyncClient() as c:
                resp = await c.request(method, url, headers=headers, timeout=_TIMEOUT, **kwargs)
        resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 — vegetation must never break carbon
        logger.warning("vegetation %s continuous failed tenant=%s parcel=%s: %s", method, tenant_id, parcel_urn, exc)
        return False


async def request_continuous(tenant_id: str, parcel_urn: str, client: httpx.AsyncClient | None = None) -> bool:
    """True when vegetation recorded the request."""
    return await _call("POST", tenant_id, parcel_urn, client)


async def release_continuous(tenant_id: str, parcel_urn: str, client: httpx.AsyncClient | None = None) -> bool:
    """True when vegetation recorded the withdrawal."""
    return await _call("DELETE", tenant_id, parcel_urn, client)
