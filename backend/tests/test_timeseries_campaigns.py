from unittest.mock import AsyncMock

import pyarrow as pa
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import timeseries
from app.platform.errors import SourceUnavailable

H = {"NGSILD-Tenant": "tenant-one"}


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(timeseries.router)
    return TestClient(app)


def _read(resp):
    return pa.ipc.open_stream(resp.content).read_all().to_pydict()


def test_one_point_per_campaign_and_none_skipped(client, monkeypatch):
    rows = [{"campaign_label": 2025, "computed_through": "2025-12-31", "soil_carbon_delta": 0.4},
            {"campaign_label": 2026, "computed_through": "2026-09-30", "soil_carbon_delta": None},
            {"campaign_label": 2024, "computed_through": None, "soil_carbon_delta": 0.1}]
    lc = AsyncMock(return_value=rows)
    monkeypatch.setattr(timeseries, "list_campaigns", lc)
    r = client.get("/api/carbon/timeseries/entities/abc/data?attribute=soilCarbonDelta", headers=H)
    assert r.status_code == 200
    data = _read(r)
    assert data["value"] == [0.4]  # absent values are not turned into 0
    assert lc.await_args.args == ("tenant-one", "abc")


def test_unknown_attribute_is_422(client, monkeypatch):
    monkeypatch.setattr(timeseries, "list_campaigns", AsyncMock(return_value=[]))
    assert client.get("/api/carbon/timeseries/entities/abc/data?attribute=gppDaily", headers=H).status_code == 422


def test_tenant_header_required(client):
    assert client.get("/api/carbon/timeseries/entities/abc/data").status_code == 400


def test_source_down_is_503(client, monkeypatch):
    monkeypatch.setattr(timeseries, "list_campaigns", AsyncMock(side_effect=SourceUnavailable("down")))
    assert client.get("/api/carbon/timeseries/entities/abc/data", headers=H).status_code == 503
