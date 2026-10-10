from datetime import date

import httpx
import pytest

from app.platform import crop_cycles_client as cc
from app.platform.errors import SourceUnavailable


@pytest.mark.asyncio
async def test_sends_internal_secret_and_returns_cycles(monkeypatch):
    monkeypatch.setattr(cc, "INTERNAL_SERVICE_SECRET", "s3")

    def handler(req):
        assert req.headers["x-internal-service-secret"] == "s3"
        assert req.url.params["tenant_id"] == "t1" and req.url.params["at"] == "2026-12-31"
        assert req.url.path.endswith("/api/internal/parcels/urn:ngsi-ld:AgriParcel:p1/crop-cycles")
        return httpx.Response(200, json={"cycles": [{"crop_id": "c1"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        out = await cc.fetch_cycles("urn:ngsi-ld:AgriParcel:p1", "t1", date(2026, 12, 31), c)
    assert out == [{"crop_id": "c1"}]


@pytest.mark.asyncio
async def test_unknown_parcel_has_no_cycles(monkeypatch):
    monkeypatch.setattr(cc, "INTERNAL_SERVICE_SECRET", "s3")
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as c:
        assert await cc.fetch_cycles("urn:ngsi-ld:AgriParcel:p1", "t1", date(2026, 12, 31), c) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 503])
async def test_auth_or_server_error_is_source_unavailable(monkeypatch, status):
    monkeypatch.setattr(cc, "INTERNAL_SERVICE_SECRET", "s3")
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(status))) as c:
        with pytest.raises(SourceUnavailable):
            await cc.fetch_cycles("urn:ngsi-ld:AgriParcel:p1", "t1", date(2026, 12, 31), c)
