"""fetch_parcel_soil builds a tenant-less parcel URN and a single-pipe OR."""

from unittest.mock import AsyncMock, patch

import pytest

from app.platform.soil_client import fetch_parcel_soil


def _orion(entities_by_type):
    client = AsyncMock()

    async def q(entity_type=None, tenant_id=None, query=None, limit=None):
        return entities_by_type.get(entity_type, [])

    client.query_entities = q
    return client


SOIL_ENTITY = {
    "id": "urn:ngsi-ld:AgriSoilExtended:d2e55461",
    "type": "AgriSoilExtended",
    "hasAgriParcel": {"type": "Relationship", "object": "urn:ngsi-ld:AgriParcel:d2e55461"},
    "clayContent": {"value": 21.0},
    "sandContent": {"value": 31.0},
    "siltContent": {"value": 48.0},
    "socTotal": {"value": 55.0},
    "bulkDensity": {"value": 1350.0},
    "ph": {"value": 6.5},
    "availableWaterCapacityMm": {"value": 160.0},
}


@pytest.mark.asyncio
async def test_query_uses_tenantless_urn_and_single_pipe():
    captured = {}

    async def q(entity_type=None, tenant_id=None, query=None, limit=None):
        captured["entity_type"] = entity_type
        captured["query"] = query
        return []

    client = AsyncMock()
    client.query_entities = q
    with patch("app.platform.soil_client.get_orion_client", return_value=client):
        await fetch_parcel_soil("urn:ngsi-ld:AgriParcel:d2e55461", "montiko")

    # Tenant-less parcel URN, single-pipe OR (double pipe is an invalid Q-Filter).
    assert "urn:ngsi-ld:AgriParcel:d2e55461" in captured["query"]
    assert "montiko:d2e55461" not in captured["query"]
    assert "||" not in captured["query"]
    assert '|hasAgriParcel=="urn:ngsi-ld:AgriParcel:d2e55461"' in captured["query"]


@pytest.mark.asyncio
async def test_parses_agri_soil_extended():
    client = _orion({"AgriSoilExtended": [SOIL_ENTITY]})
    with patch("app.platform.soil_client.get_orion_client", return_value=client):
        snap = await fetch_parcel_soil("d2e55461", "montiko")
    assert snap.clay_pct == 21.0
    assert snap.soc_tC_ha == 55.0
    assert snap.ph == 6.5
    assert snap.source == "orion-ld"


@pytest.mark.asyncio
async def test_falls_back_to_agri_soil_then_defaults():
    # No AgriSoilExtended, no AgriSoil → defaults.
    client = _orion({})
    with patch("app.platform.soil_client.get_orion_client", return_value=client):
        snap = await fetch_parcel_soil("d2e55461", "montiko")
    assert snap.source == "default"
    assert snap.clay_pct == 20.0
