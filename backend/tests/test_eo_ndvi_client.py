from datetime import date

import pytest

from app.platform import eo_ndvi_client as eo
from app.platform.errors import SourceUnavailable


class FakeOrion:
    def __init__(self, pages, fail=False):
        self.pages, self.calls, self.fail, self.queries = pages, [], fail, []

    async def query_entities(self, entity_type, tenant_id, query=None, attrs=None, limit=100, offset=0):
        if self.fail:
            raise RuntimeError("orion down")
        self.calls.append(offset)
        self.queries.append((entity_type, query))
        i = offset // limit
        return self.pages[i] if i < len(self.pages) else []


def _e(d, ndvi):
    e = {"id": f"urn:ngsi-ld:EOProduct:x:{d}", "sensingDate": {"type": "Property", "value": d}}
    if ndvi is not None:
        e["ndvi"] = {"type": "Property", "value": ndvi}
    return e


@pytest.mark.asyncio
async def test_pages_filters_sar_and_out_of_range(monkeypatch):
    page1 = [_e("2026-05-01", 0.4)] * 499 + [_e("2026-05-03", None)]
    page2 = [_e("2026-05-05", 1.8), _e("2026-05-07", 0.6), _e("2025-01-01", 0.3)]
    fake = FakeOrion([page1, page2])
    monkeypatch.setattr(eo, "get_orion_client", lambda: fake)
    out = (await eo.fetch_vi_series("urn:ngsi-ld:AgriParcel:p1", "t1", date(2026, 1, 1), date(2026, 12, 31)))["NDVI"]
    assert fake.calls == [0, 500]
    assert fake.queries[0] == ("EOProduct", 'hasAgriParcel=="urn:ngsi-ld:AgriParcel:p1"')
    assert (date(2026, 5, 7), 0.6) in out
    assert all(-1 <= v <= 1 for _, v in out)
    assert all(d.year == 2026 for d, _ in out)
    assert date(2026, 5, 3) not in {d for d, _ in out}


@pytest.mark.asyncio
async def test_window_includes_scenes_shortly_outside(monkeypatch):
    fake = FakeOrion([[_e("2025-12-10", 0.3), _e("2025-10-01", 0.3)]])
    monkeypatch.setattr(eo, "get_orion_client", lambda: fake)
    out = (await eo.fetch_vi_series("urn:ngsi-ld:AgriParcel:p1", "t1", date(2026, 1, 1), date(2026, 12, 31)))["NDVI"]
    assert out == [(date(2025, 12, 10), 0.3)]


@pytest.mark.asyncio
async def test_orion_failure_is_source_unavailable(monkeypatch):
    monkeypatch.setattr(eo, "get_orion_client", lambda: FakeOrion([], fail=True))
    with pytest.raises(SourceUnavailable):
        await eo.fetch_vi_series("urn:ngsi-ld:AgriParcel:p1", "t1", date(2026, 1, 1), date(2026, 12, 31))


@pytest.mark.asyncio
async def test_vi_series_returns_ndvi_and_osavi(monkeypatch):
    e1 = _e("2026-05-01", 0.5); e1["osavi"] = {"type": "Property", "value": 0.42}
    e2 = _e("2026-05-11", None); e2["osavi"] = {"type": "Property", "value": 0.44}
    monkeypatch.setattr(eo, "get_orion_client", lambda: FakeOrion([[e1, e2]]))
    out = await eo.fetch_vi_series("urn:ngsi-ld:AgriParcel:p1", "t1", date(2026, 1, 1), date(2026, 12, 31))
    assert out["NDVI"] == [(date(2026, 5, 1), 0.5)]
    assert out["OSAVI"] == [(date(2026, 5, 1), 0.42), (date(2026, 5, 11), 0.44)]
