"""replace_entity must leave exactly the new entity: Orion's PATCH /attrs only
touches attributes that already exist, so a merge would keep stale values and
drop new ones."""
import httpx
import pytest

from app.common import orion as orion_mod


class OrionLike:
    """Create = 409 if present; PATCH /attrs updates existing attributes only."""

    def __init__(self):
        self.store = {}

    async def create_entity(self, entity):
        if entity["id"] in self.store:
            raise httpx.HTTPStatusError("conflict", request=httpx.Request("POST", "http://o"),
                                        response=httpx.Response(409))
        self.store[entity["id"]] = dict(entity)
        return entity

    async def update_entity_attrs(self, entity_id, attrs):
        cur = self.store[entity_id]
        for k, v in attrs.items():
            if k in cur:
                cur[k] = v

    async def delete_entity(self, entity_id):
        self.store.pop(entity_id, None)


@pytest.mark.asyncio
async def test_replace_drops_stale_and_adds_new_attributes(monkeypatch):
    fake = OrionLike()
    monkeypatch.setattr(orion_mod, "_client_for", lambda tenant: fake)
    monkeypatch.setattr(orion_mod, "_initialized", True)
    w = orion_mod.get_orion_client()
    first = {"id": "urn:x", "type": "CarbonAssessment", "dataTier": {"type": "Property", "value": 0},
             "missing": {"type": "Property", "value": [{"item": "weather"}]}}
    second = {"id": "urn:x", "type": "CarbonAssessment", "dataTier": {"type": "Property", "value": 2},
              "computedThrough": {"type": "Property", "value": "2027-09-30"}}
    await w.replace_entity(first, "t1")
    await w.replace_entity(second, "t1")
    assert fake.store["urn:x"] == second


@pytest.mark.asyncio
async def test_upsert_merge_is_what_loses_attributes(monkeypatch):
    fake = OrionLike()
    monkeypatch.setattr(orion_mod, "_client_for", lambda tenant: fake)
    monkeypatch.setattr(orion_mod, "_initialized", True)
    w = orion_mod.get_orion_client()
    await w.upsert_entity({"id": "urn:y", "type": "T", "a": {"value": 1}}, "t1")
    await w.upsert_entity({"id": "urn:y", "type": "T", "b": {"value": 2}}, "t1")
    assert "b" not in fake.store["urn:y"]  # documents why campaigns use replace_entity
