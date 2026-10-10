from datetime import date

import httpx
import pytest

from app.platform.daily_weather_client import fetch_daily_weather
from app.platform.errors import SourceUnavailable

DAY = {"date": "2026-03-01", "tmin_c": 2.0, "tmax_c": 12.0, "precip_mm": 3.1,
       "et0_mm": 1.2, "radiation_mj_m2": 10.5, "source": "reanalysis"}
EMPTY = {"date": "2026-03-02", "tmin_c": None, "tmax_c": None, "precip_mm": None,
         "et0_mm": None, "radiation_mj_m2": None, "source": None}


@pytest.mark.asyncio
async def test_parses_days_and_sends_tenant_headers():
    seen = {}

    def handler(req):
        seen["headers"] = req.headers
        seen["url"] = str(req.url)
        return httpx.Response(200, json={"days": [DAY, EMPTY]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        days = await fetch_daily_weather("urn:ngsi-ld:AgriParcel:p1", "t1",
                                         date(2026, 3, 1), date(2026, 3, 2), c)
    assert seen["headers"]["x-tenant-id"] == "t1"
    assert seen["headers"]["x-user-id"] == "carbon-worker"
    assert "/api/weather/parcel/p1/daily" in seen["url"] and "fill=open_meteo" in seen["url"]
    assert days[0].complete and days[0].radiation_mj_m2 == 10.5 and days[0].day == date(2026, 3, 1)
    assert not days[1].complete


@pytest.mark.asyncio
async def test_parcel_unknown_is_empty():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as c:
        assert await fetch_daily_weather("urn:ngsi-ld:AgriParcel:p1", "t1",
                                         date(2026, 3, 1), date(2026, 3, 2), c) == []


@pytest.mark.asyncio
async def test_server_error_is_source_unavailable():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(502))) as c:
        with pytest.raises(SourceUnavailable):
            await fetch_daily_weather("urn:ngsi-ld:AgriParcel:p1", "t1",
                                      date(2026, 3, 1), date(2026, 3, 2), c)


@pytest.mark.asyncio
async def test_network_error_is_source_unavailable():
    def boom(req):
        raise httpx.ConnectError("refused")

    async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as c:
        with pytest.raises(SourceUnavailable):
            await fetch_daily_weather("urn:ngsi-ld:AgriParcel:p1", "t1",
                                      date(2026, 3, 1), date(2026, 3, 2), c)
