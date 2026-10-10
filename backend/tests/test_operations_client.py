from datetime import date

import pytest

from app.platform import operations_client as oc
from app.platform.errors import SourceUnavailable


def test_parse_n_percent():
    assert oc.parse_n_percent("15-15-15") == 15.0
    assert oc.parse_n_percent(" 46 ") == 46.0
    assert oc.parse_n_percent("27-0-0") == 27.0
    assert oc.parse_n_percent("NPK") is None
    assert oc.parse_n_percent(None) is None and oc.parse_n_percent("") is None


def test_polygon_area_hectares():
    # ~100 m x ~100 m square at 42 N
    ring = [[-2.0, 42.0], [-2.0 + 0.0012134, 42.0], [-2.0 + 0.0012134, 42.0009],
            [-2.0, 42.0009], [-2.0, 42.0]]
    assert oc.polygon_area_ha({"type": "Polygon", "coordinates": [ring]}) == pytest.approx(1.0, rel=0.01)
    assert oc.polygon_area_ha({"type": "Point", "coordinates": [-2.0, 42.0]}) is None


class FakeOrion:
    def __init__(self, ents, fail=False):
        self.ents, self.fail, self.queries = ents, fail, []

    async def query_entities(self, entity_type, tenant_id, query=None, attrs=None, limit=100, offset=0):
        if self.fail:
            raise RuntimeError("down")
        self.queries.append(query)
        return self.ents if offset == 0 else []


def _op(t, day, status="completed", **attrs):
    e = {"id": f"op-{t}-{day}", "operationType": {"value": t}, "status": {"value": status},
         "endedAt": {"type": "Property", "value": {"@type": "DateTime", "@value": f"{day}T10:00:00Z"}}}
    e.update({k: {"type": "Property", "value": v} for k, v in attrs.items()})
    return e


@pytest.mark.asyncio
async def test_harvest_and_fertilization(monkeypatch):
    ents = [_op("harvesting", "2026-07-01", harvestedWeight=30000, moisture=12),
            _op("harvesting", "2026-07-02", harvestedWeight=500),
            _op("fertilization", "2026-03-01", fertilizerRate=200, fertilizerComposition="27-0-0",
                organicFertilizer=False),
            _op("fertilization", "2026-03-02", fertilizerRate=200),
            _op("tillage", "2026-02-01", tillageType="ploughing"),
            _op("baling", "2026-07-05"),
            _op("sowing", "2026-01-10", status="planned"),
            _op("harvesting", "2025-07-01", harvestedWeight=1, moisture=1)]
    fake = FakeOrion(ents)
    monkeypatch.setattr(oc, "get_orion_client", lambda: fake)
    h, f, t, b, missing = await oc.fetch_operations("urn:ngsi-ld:AgriParcel:p", "t",
                                                    date(2026, 1, 1), date(2026, 12, 31), area_ha=10.0)
    assert fake.queries[0] == 'hasAgriParcel=="urn:ngsi-ld:AgriParcel:p";status=="completed"'
    assert len(h) == 2 and h[0].exported_c_tC_ha == pytest.approx(30000 * 0.88 * 0.45 / 1000 / 10)
    assert h[1].exported_c_tC_ha is None
    assert f[0].n_kg_ha == pytest.approx(54.0) and f[0].organic is False and f[1].n_kg_ha is None
    assert t[0].tillage_type == "ploughing" and b[0].day == date(2026, 7, 5)
    assert sorted(m.item for m in missing) == ["fertilizer_n", "harvest_export"]


@pytest.mark.asyncio
async def test_harvest_without_area_is_missing(monkeypatch):
    monkeypatch.setattr(oc, "get_orion_client",
                        lambda: FakeOrion([_op("harvesting", "2026-07-01", harvestedWeight=30000, moisture=12)]))
    h, f, t, b, missing = await oc.fetch_operations("urn:ngsi-ld:AgriParcel:p", "t",
                                                    date(2026, 1, 1), date(2026, 12, 31), area_ha=None)
    assert h[0].exported_c_tC_ha is None and missing[0].item == "harvest_export"


@pytest.mark.asyncio
async def test_orion_failure_is_source_unavailable(monkeypatch):
    monkeypatch.setattr(oc, "get_orion_client", lambda: FakeOrion([], fail=True))
    with pytest.raises(SourceUnavailable):
        await oc.fetch_operations("urn:ngsi-ld:AgriParcel:p", "t", date(2026, 1, 1), date(2026, 12, 31), 1.0)


@pytest.mark.asyncio
async def test_parcel_area_prefers_attribute_then_polygon(monkeypatch):
    class O:
        def __init__(self, e): self.e = e
        async def get_entity(self, entity_id, tenant_id): return self.e
    ring = [[-2.0, 42.0], [-1.9987866, 42.0], [-1.9987866, 42.0009], [-2.0, 42.0009], [-2.0, 42.0]]
    monkeypatch.setattr(oc, "get_orion_client", lambda: O({"area": {"value": 12.5}}))
    assert await oc.fetch_parcel_area_ha("urn:ngsi-ld:AgriParcel:p", "t") == 12.5
    monkeypatch.setattr(oc, "get_orion_client",
                        lambda: O({"location": {"value": {"type": "Polygon", "coordinates": [ring]}}}))
    assert await oc.fetch_parcel_area_ha("urn:ngsi-ld:AgriParcel:p", "t") == pytest.approx(1.0, rel=0.01)
    monkeypatch.setattr(oc, "get_orion_client", lambda: O(None))
    assert await oc.fetch_parcel_area_ha("urn:ngsi-ld:AgriParcel:p", "t") is None
