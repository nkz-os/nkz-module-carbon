"""Crop cycles come from the platform rule over the broker (SDK), not a core endpoint."""
from datetime import date

import pytest

from app.platform import crop_cycles_client as cc
from app.platform.errors import SourceUnavailable

P = "urn:ngsi-ld:AgriParcel:p1"
CROP = {"id": "urn:ngsi-ld:AgriCrop:t:a", "type": "AgriCrop", "hasAgriParcel": P, "status": "active",
        "plantingDate": "2026-03-01", "plantingDateSource": "manual", "harvestDate": "2026-07-15"}


class FakeOrion:
    def __init__(self, behaviour):
        self.behaviour, self.closed = behaviour, False

    async def close(self):
        self.closed = True


def _patch_load(monkeypatch, behaviour):
    fake = FakeOrion(behaviour)
    monkeypatch.setattr(cc, "OrionClient", lambda tenant_id, **kw: fake)

    async def load(client, urn):
        if behaviour == "missing":
            raise cc.ParcelNotFound(urn)
        if behaviour == "down":
            raise cc.CropDataUnavailable("broker down")
        return {"id": urn}, [dict(CROP)], []

    monkeypatch.setattr(cc, "load_crop_data", load)
    return fake


@pytest.mark.asyncio
async def test_returns_the_cycles_of_the_timeline_at_the_given_day(monkeypatch):
    fake = _patch_load(monkeypatch, "ok")
    out = await cc.fetch_cycles(P, "t1", date(2026, 12, 31))
    assert [c["crop_id"] for c in out] == [CROP["id"]] and out[0]["campaign_label"] == 2026
    assert fake.closed


@pytest.mark.asyncio
async def test_unknown_parcel_has_no_cycles(monkeypatch):
    _patch_load(monkeypatch, "missing")
    assert await cc.fetch_cycles(P, "t1", date(2026, 12, 31)) == []


@pytest.mark.asyncio
async def test_broker_failure_is_source_unavailable(monkeypatch):
    fake = _patch_load(monkeypatch, "down")
    with pytest.raises(SourceUnavailable):
        await cc.fetch_cycles(P, "t1", date(2026, 12, 31))
    assert fake.closed


def test_no_core_endpoint_left():
    import inspect

    assert "/crop-cycles" not in inspect.getsource(cc)
