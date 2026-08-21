"""Shared OrionClient wrapper for carbon module.

Thin wrapper around nkz_platform_sdk's OrionClient that adds:
- upsert_entity() convenience (create-or-update)
- One cached SDK client per tenant
- Auto-tenant from request context

Tenant binding is per client, never per call. A single shared client whose
tenant_id is rebound on each request is not safe under asyncio: any await hands
the loop to another request, which rebinds it, and the write lands in the wrong
namespace. upsert_entity's 409 branch spans two awaits and hit exactly that.
"""

import logging
from typing import Any

import httpx
from nkz_platform_sdk.orion import OrionClient as SDKOrionClient

logger = logging.getLogger(__name__)

_clients: dict[str, SDKOrionClient] = {}
_initialized: bool = False


def _client_for(tenant_id: str) -> SDKOrionClient:
    """Return the client bound to this tenant, creating it on first use."""
    client = _clients.get(tenant_id)
    if client is None:
        client = SDKOrionClient(tenant_id=tenant_id)
        _clients[tenant_id] = client
    return client


def get_orion_client() -> "OrionClientWrapper":
    """Get the OrionClientWrapper.

    Must be initialized first via init_orion_client() in app lifespan.
    """
    if not _initialized:
        raise RuntimeError("OrionClient not initialized — call init_orion_client() first")
    return OrionClientWrapper()


def init_orion_client(tenant_id: str | None = None):
    """Enable Orion access for the process.

    Called from app lifespan. Clients are created lazily, one per tenant, so
    there is nothing to build here. ``tenant_id`` is accepted for call
    compatibility and ignored: every operation carries its own tenant.
    """
    global _initialized
    _initialized = True


async def close_orion_client():
    """Close every per-tenant client."""
    global _initialized
    for client in list(_clients.values()):
        await client.close()
    _clients.clear()
    _initialized = False


class OrionClientWrapper:
    """Tenant-scoped facade: each call resolves the client bound to its tenant."""

    async def query_entities(
        self,
        entity_type: str,
        tenant_id: str,
        query: str | None = None,
        attrs: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query entities scoped to tenant."""
        return await _client_for(tenant_id).query_entities(
            type=entity_type,
            q=query,
            limit=limit,
            attrs=attrs,
        )

    async def get_entity(
        self,
        entity_id: str,
        tenant_id: str,
    ) -> dict[str, Any] | None:
        """Get a single entity. Returns None on 404.

        Only 404 means absent. Swallowing every error here would report "no such
        entity" when Orion is unreachable — a false zero the platform forbids.
        """
        try:
            return await _client_for(tenant_id).get_entity(entity_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    async def upsert_entity(
        self,
        entity: dict[str, Any],
        tenant_id: str,
    ) -> dict[str, Any]:
        """Create entity, or update if already exists (409).

        Both calls go through the same tenant-bound client, so the retry cannot
        drift to another namespace while the first await is in flight.
        """
        client = _client_for(tenant_id)
        try:
            return await client.create_entity(entity)
        except Exception as exc:
            if getattr(getattr(exc, "response", None), "status_code", 0) == 409:
                entity_id = entity["id"]
                attrs = {k: v for k, v in entity.items()
                         if k not in ("id", "type", "@context")}
                await client.update_entity_attrs(entity_id, attrs)
                return entity
            raise


# ---------------------------------------------------------------------------
# Convenience functions — matching old ngsild/client.py API signature
# for minimal diff during migration.
# ---------------------------------------------------------------------------


async def query_entities(
    entity_type: str,
    tenant_id: str,
    query: str | None = None,
    attrs: str | None = None,
    limit: int = 100,
    local: bool = False,
) -> list[dict[str, Any]]:
    """Query NGSI-LD entities by type.

    NOTE: local=True is DEPRECATED — do NOT use in new code.
    """
    if local:
        logger.warning(
            "query_entities(local=True) called — tenant isolation bypassed. "
            "This is deprecated and should be removed."
        )
    client = get_orion_client()
    return await client.query_entities(
        entity_type=entity_type,
        tenant_id=tenant_id,
        query=query,
        attrs=attrs,
        limit=limit,
    )


async def upsert_entity(entity: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    """Create or update an NGSI-LD entity."""
    client = get_orion_client()
    return await client.upsert_entity(entity, tenant_id)


async def get_entity(entity_id: str, tenant_id: str) -> dict[str, Any] | None:
    """Get a single NGSI-LD entity by ID. Returns None if 404."""
    client = get_orion_client()
    return await client.get_entity(entity_id, tenant_id)
