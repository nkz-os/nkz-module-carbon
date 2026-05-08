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


def _make_headers(tenant_id: str, accept: bool = True, content_type: bool = False) -> dict:
    """Build Orion-LD request headers with normalized tenant ID.

    Uses BOTH NGSILD-Tenant (ETSI standard) AND Fiware-Service (legacy)
    for compatibility with entity-manager writes. Includes Link @context
    header for NGSI-LD compliance.
    """
    from app.common.tenant_utils import normalize_tenant_id

    normalized = normalize_tenant_id(tenant_id)
    headers = {
        "NGSILD-Tenant": normalized,
        "Fiware-Service": normalized,
        "Fiware-ServicePath": "/",
    }
    if accept:
        headers["Accept"] = "application/ld+json"
    if content_type:
        headers["Content-Type"] = "application/ld+json"
    if CONTEXT_URL:
        headers["Link"] = (
            f'<{CONTEXT_URL}>; rel="http://www.w3.org/ns/json-ld#context";'
            f' type="application/ld+json"'
        )
    return headers


async def upsert_entity(
    entity: dict,
    tenant_id: str,
    client: httpx.AsyncClient | None = None,
) -> dict:
    """Create or update an NGSI-LD entity. Returns the entity as stored."""
    headers = _make_headers(tenant_id, accept=False, content_type=True)
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
    headers = _make_headers(tenant_id) if not local else {"Accept": "application/ld+json"}
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
    headers = _make_headers(tenant_id)
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
