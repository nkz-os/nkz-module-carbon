"""Shared OrionClient wrapper for carbon module.

Thin wrapper around nkz_platform_sdk's OrionClient that adds:
- upsert_entity() convenience (create-or-update)
- Module-level singleton via get_orion_client()
- Auto-tenant from request context
"""

import logging
from typing import Any

from nkz_platform_sdk.orion import OrionClient as SDKOrionClient

logger = logging.getLogger(__name__)

_global_client: SDKOrionClient | None = None


def get_orion_client() -> "OrionClientWrapper":
    """Get the global OrionClientWrapper instance.

    Must be initialized first via init_orion_client() in app lifespan.
    """
    if _global_client is None:
        raise RuntimeError("OrionClient not initialized — call init_orion_client() first")
    return OrionClientWrapper(_global_client)


def init_orion_client(tenant_id: str | None = None):
    """Initialize the global OrionClient singleton.

    Called from app lifespan. For tenant-scoped operations, the tenant_id
    is provided per-request via the wrapper.
    """
    global _global_client
    if _global_client is not None:
        return  # already initialized
    _global_client = SDKOrionClient(tenant_id=tenant_id or "default")


async def close_orion_client():
    """Close the global OrionClient singleton."""
    global _global_client
    if _global_client:
        await _global_client.close()
        _global_client = None


class OrionClientWrapper:
    """Scoped wrapper that pins tenant_id per operation."""

    def __init__(self, client: SDKOrionClient):
        self._client = client

    async def query_entities(
        self,
        entity_type: str,
        tenant_id: str,
        query: str | None = None,
        attrs: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query entities scoped to tenant."""
        self._client.tenant_id = tenant_id
        return await self._client.query_entities(
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
        """Get a single entity. Returns None on 404."""
        self._client.tenant_id = tenant_id
        try:
            return await self._client.get_entity(entity_id)
        except Exception:
            return None

    async def upsert_entity(
        self,
        entity: dict[str, Any],
        tenant_id: str,
    ) -> dict[str, Any]:
        """Create entity, or update if already exists (409)."""
        self._client.tenant_id = tenant_id
        try:
            return await self._client.create_entity(entity)
        except Exception as exc:
            if hasattr(exc, "response") and getattr(exc.response, "status_code", 0) == 409:
                entity_id = entity["id"]
                attrs = {k: v for k, v in entity.items()
                         if k not in ("id", "type", "@context")}
                await self._client.update_entity_attrs(entity_id, attrs)
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
