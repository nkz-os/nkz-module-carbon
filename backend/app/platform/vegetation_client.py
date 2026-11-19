"""Ask vegetation to keep a parcel's satellite monitoring continuous.

Carbon reads the NDVI of the days without a crop, so a parcel with carbon active must
not be paused after its harvest. Both calls are idempotent on vegetation's side, never
raise, and do nothing when ``VEGETATION_INTERNAL_URL`` is empty (no default: the URL is
a property of each installation).
"""

import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

MODULE_ID = "carbon"
_TIMEOUT = 10.0
_BATCH_TIMEOUT = 5.0


def _url(parcel_urn: str) -> str | None:
    base = os.getenv("VEGETATION_INTERNAL_URL", "").rstrip("/")
    if not base:
        return None
    return f"{base}/api/internal/vegetation/parcels/{parcel_urn}/continuous"


async def _send(method: str, tenant_id: str, parcel_urn: str, client: httpx.AsyncClient | None) -> tuple[bool, bool]:
    """(ok, transport_failed): transport_failed means vegetation is unreachable or too slow."""
    url = _url(parcel_urn)
    if url is None:
        return False, False
    headers = {"X-Internal-Service-Secret": os.getenv("INTERNAL_SERVICE_SECRET", "")}
    payload = {"tenant_id": tenant_id, "module_id": MODULE_ID}
    kwargs = {"json": payload} if method == "POST" else {"params": payload}
    try:
        if client is not None:
            resp = await client.request(method, url, headers=headers, **kwargs)
        else:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
                resp = await c.request(method, url, headers=headers, **kwargs)
        resp.raise_for_status()
        return True, False
    except Exception as exc:  # noqa: BLE001 — vegetation must never break carbon
        logger.warning("vegetation %s continuous failed tenant=%s parcel=%s: %s", method, tenant_id, parcel_urn, exc)
        return False, isinstance(exc, httpx.TransportError)


async def _call(method: str, tenant_id: str, parcel_urn: str, client: httpx.AsyncClient | None) -> bool:
    return (await _send(method, tenant_id, parcel_urn, client))[0]


async def request_continuous(tenant_id: str, parcel_urn: str, client: httpx.AsyncClient | None = None) -> bool:
    """True when vegetation recorded the request."""
    return await _call("POST", tenant_id, parcel_urn, client)


async def release_continuous(tenant_id: str, parcel_urn: str, client: httpx.AsyncClient | None = None) -> bool:
    """True when vegetation recorded the withdrawal."""
    return await _call("DELETE", tenant_id, parcel_urn, client)


async def request_continuous_batch(
    pairs: list[tuple[str, str]],
    concurrency: int = 5,
    timeout: float = _BATCH_TIMEOUT,
    client: httpx.AsyncClient | None = None,
) -> int:
    """Request continuity for (tenant, parcel urn) pairs; returns how many succeeded.

    One shared client, bounded concurrency, and a circuit breaker: after the first
    transport error or timeout the rest of the batch is skipped, so an unreachable
    vegetation costs one timeout, not one per parcel. Never raises.
    """
    if not pairs or _url("") is None:
        return 0
    state = {"open": False, "ok": 0}
    skipped: dict[str, int] = {}
    sem = asyncio.Semaphore(max(1, concurrency))
    own = client is None
    shared = httpx.AsyncClient(timeout=timeout) if own else client

    async def one(tenant_id: str, urn: str) -> None:
        async with sem:
            if state["open"]:
                skipped[tenant_id] = skipped.get(tenant_id, 0) + 1
                return
            ok, transport_failed = await _send("POST", tenant_id, urn, shared)
            if ok:
                state["ok"] += 1
            elif transport_failed:
                state["open"] = True

    try:
        await asyncio.gather(*(one(t, u) for t, u in pairs))
    except Exception as exc:  # noqa: BLE001 — never break the caller
        logger.warning("vegetation continuity batch failed: %s", exc)
    finally:
        if own:
            await shared.aclose()
    if skipped:
        logger.warning("vegetation continuity circuit open, skipped %s", skipped)
    return state["ok"]
