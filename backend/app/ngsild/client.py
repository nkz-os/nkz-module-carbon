"""Orion-LD HTTP client for NGSI-LD operations."""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

ORION_URL = os.getenv("FIWARE_CONTEXT_BROKER_URL", "http://orion-ld-service:1026")
CONTEXT_URL = os.getenv(
    "CONTEXT_URL", "http://api-gateway-service:5000/ngsi-ld-context.json"
)
NGSI_LD_CONTEXT = [
    "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
    CONTEXT_URL,
]


async def upsert_entity(
    entity: dict,
    tenant_id: str,
    client: httpx.AsyncClient | None = None,
) -> dict:
    """Create or update an NGSI-LD entity. Returns the entity as stored."""
    headers = {
        "NGSILD-Tenant": tenant_id, "Fiware-Service": tenant_id, "Fiware-ServicePath": "/",
        "Content-Type": "application/ld+json",
    }
    entity_id = entity["id"]

    async with (client or httpx.AsyncClient()) as c:
        resp = await c.post(
            f"{ORION_URL}/ngsi-ld/v1/entities",
            json=entity,
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 201:
            return resp.json() if resp.text else entity

        if resp.status_code == 409:
            # Entity exists, update via PATCH /attrs
            attrs = {k: v for k, v in entity.items() if k not in ("id", "type", "@context")}
            resp = await c.patch(
                f"{ORION_URL}/ngsi-ld/v1/entities/{entity_id}/attrs",
                json=attrs,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            return entity

        resp.raise_for_status()
        return entity


async def query_entities(
    entity_type: str,
    tenant_id: str,
    query: str | None = None,
    attrs: str | None = None,
    limit: int = 100,
    client: httpx.AsyncClient | None = None,
    local: bool = False,
) -> list[dict]:
    """Query NGSI-LD entities by type.

    Set local=True to bypass tenant isolation (queries all entities
    regardless of tenant association).
    """
    headers = {"Accept": "application/ld+json"}
    if not local:
        headers["NGSILD-Tenant"] = tenant_id
        headers["Fiware-Service"] = tenant_id
        headers["Fiware-ServicePath"] = "/"
    params: dict = {"type": entity_type, "limit": limit}
    if local:
        params["local"] = "true"
    if query:
        params["q"] = query
    if attrs:
        params["attrs"] = attrs

    async with (client or httpx.AsyncClient()) as c:
        resp = await c.get(
            f"{ORION_URL}/ngsi-ld/v1/entities",
            params=params,
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()


async def get_entity(
    entity_id: str,
    tenant_id: str,
    client: httpx.AsyncClient | None = None,
) -> dict | None:
    """Get a single NGSI-LD entity by ID. Returns None if 404."""
    headers = {"NGSILD-Tenant": tenant_id, "Fiware-Service": tenant_id, "Fiware-ServicePath": "/", "Accept": "application/ld+json"}
    async with (client or httpx.AsyncClient()) as c:
        resp = await c.get(
            f"{ORION_URL}/ngsi-ld/v1/entities/{entity_id}",
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
