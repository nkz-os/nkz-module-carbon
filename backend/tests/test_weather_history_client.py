from datetime import date

import httpx
import pytest

from app.platform.weather_history_client import fetch_climate_history

URN = "urn:ngsi-ld:AgriParcel:p1"


def _day(d, t=10.0, p=1.0, e=2.0):
    return {"date": d, "tmean_c": t, "precip_mm": p, "et0_mm": e}


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_ready_history_parses_days_and_signs_request(monkeypatch):
    monkeypatch.setenv("HMAC_SECRET", "s3cret")
    seen = {}

    def handler(req):
        seen["h"], seen["url"] = req.headers, str(req.url)
        return httpx.Response(200, json={
            "days": [_day("1996-01-01"), _day("1997-01-01", t=None)], "latest_available": "2026-11-09",
            "provenance": {}, "validation": {}, "attribution": "Copernicus"})

    async with _client(handler) as c:
        r = await fetch_climate_history(URN, "t1", date(1996, 1, 1), date(2025, 12, 31), c)
    assert r.ready and r.attribution == "Copernicus" and r.years_label == "1996–1997"
    assert r.latest_available == date(2026, 11, 9)
    assert r.days[0].complete and not r.days[1].complete
    assert seen["h"]["x-tenant-id"] == "t1" and seen["h"]["x-user-id"] == "carbon-worker"
    assert seen["h"]["x-auth-signature"]
    assert "/api/weather/parcel/p1/history" in seen["url"]
    assert "resolution=daily" in seen["url"] and "vars=tmean_c%2Cprecip_mm%2Cet0_mm" in seen["url"]
    assert "start=1996-01-01" in seen["url"] and "end=2025-12-31" in seen["url"]


@pytest.mark.asyncio
async def test_incomplete_years_is_not_ready():
    def handler(req):
        return httpx.Response(200, json={"days": [_day("2025-01-01")], "incomplete_years": [1996, 1997]})

    async with _client(handler) as c:
        r = await fetch_climate_history(URN, "t1", date(1996, 1, 1), date(2025, 12, 31), c)
    assert not r.ready and "incomplete" in r.reason


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 404, 500, 503])
async def test_http_errors_are_not_ready_and_raise_nothing(status):
    async with _client(lambda r: httpx.Response(status)) as c:
        r = await fetch_climate_history(URN, "t1", date(1996, 1, 1), date(2025, 12, 31), c)
    assert not r.ready and str(status) in r.reason and r.days == []


@pytest.mark.asyncio
async def test_unreachable_is_not_ready():
    def handler(req):
        raise httpx.ConnectError("down")

    async with _client(handler) as c:
        r = await fetch_climate_history(URN, "t1", date(1996, 1, 1), date(2025, 12, 31), c)
    assert not r.ready and "unreachable" in r.reason


@pytest.mark.asyncio
async def test_garbage_body_is_not_ready():
    async with _client(lambda r: httpx.Response(200, json={"days": [{"date": "nope"}]})) as c:
        r = await fetch_climate_history(URN, "t1", date(1996, 1, 1), date(2025, 12, 31), c)
    assert not r.ready
