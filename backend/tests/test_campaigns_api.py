import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))

from test_campaign_balance import _inp  # noqa: E402

from app.api import campaigns as api  # noqa: E402
from app.api import internal  # noqa: E402
from app.platform.errors import SourceUnavailable  # noqa: E402
from app.services.campaign_balance import compute_campaign_balance  # noqa: E402

H = {"X-Tenant-ID": "tenant-one", "X-User-ID": "u1"}


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(api.router)
    app.include_router(internal.router)
    monkeypatch.setattr("app.common.tier_check.get_pool", AsyncMock(side_effect=RuntimeError("no db")))
    return TestClient(app)


def test_calculate_returns_balance(client, monkeypatch):
    b = compute_campaign_balance(_inp())
    monkeypatch.setattr(api, "run_campaign", AsyncMock(return_value=b))
    r = client.post("/api/carbon/parcels/abc/campaigns/2026/calculate", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["year"] == 2026 and body["tier"] == b.tier and body["computed_through"] == "2026-09-30"
    assert body["cycles"][0]["start"] == "2026-01-01" and isinstance(body["missing"], list)


def test_calculate_empty_balance_is_200(client, monkeypatch):
    from test_campaign_balance import _weather
    b = compute_campaign_balance(_inp(today=date(2026, 1, 20), weather=_weather(date(2026, 1, 1), date(2026, 1, 19))))
    monkeypatch.setattr(api, "run_campaign", AsyncMock(return_value=b))
    r = client.post("/api/carbon/parcels/abc/campaigns/2026/calculate", headers=H)
    assert r.status_code == 200 and r.json()["tier"] == 0 and r.json()["missing"][0]["item"] == "weather"


def test_calculate_source_down_is_503(client, monkeypatch):
    monkeypatch.setattr(api, "run_campaign", AsyncMock(side_effect=SourceUnavailable("weather down")))
    r = client.post("/api/carbon/parcels/abc/campaigns/2026/calculate", headers=H)
    assert r.status_code == 503 and r.json()["detail"]["error"] == "source_unavailable"


def test_calculate_future_year_is_422(client, monkeypatch):
    monkeypatch.setattr(api, "run_campaign", AsyncMock(side_effect=ValueError("campaign 2099 has not started")))
    assert client.post("/api/carbon/parcels/abc/campaigns/2099/calculate", headers=H).status_code == 422


def test_get_campaign_404_and_list(client, monkeypatch):
    monkeypatch.setattr(api, "get_campaign", AsyncMock(return_value=None))
    assert client.get("/api/carbon/parcels/abc/campaigns/2026", headers=H).status_code == 404
    monkeypatch.setattr(api, "list_campaigns", AsyncMock(return_value=[{"campaign_label": 2026}]))
    r = client.get("/api/carbon/parcels/abc/campaigns", headers=H)
    assert r.json() == {"parcel_id": "urn:ngsi-ld:AgriParcel:abc", "campaigns": [{"campaign_label": 2026}]}


def test_user_routes_need_gateway_headers(client):
    assert client.get("/api/carbon/parcels/abc/campaigns").status_code == 401


def test_recalculate_open_auth(client, monkeypatch):
    monkeypatch.setattr(api, "INTERNAL_SERVICE_SECRET", "")
    assert client.post("/api/carbon/internal/campaigns/recalculate-open",
                       headers={"X-Internal-Service-Secret": ""}).status_code == 401
    monkeypatch.setattr(api, "INTERNAL_SERVICE_SECRET", "s3")
    assert client.post("/api/carbon/internal/campaigns/recalculate-open").status_code == 401
    assert client.post("/api/carbon/internal/campaigns/recalculate-open",
                       headers={"X-Internal-Service-Secret": "bad"}).status_code == 401


def test_recalculate_open_counts_failures(client, monkeypatch):
    monkeypatch.setattr(api, "INTERNAL_SERVICE_SECRET", "s3")
    monkeypatch.setattr(api, "list_tenants_with_module", AsyncMock(return_value=["t1", "t2"]))
    monkeypatch.setattr(api, "list_parcel_ids", AsyncMock(side_effect=[["p1", "p2"], ["p3"]]))

    async def run(tenant, parcel, year, today=None, cascade=True):
        if parcel == "p2":
            raise SourceUnavailable("down")
        return compute_campaign_balance(_inp())
    monkeypatch.setattr(api, "run_campaign", run)
    r = client.post("/api/carbon/internal/campaigns/recalculate-open", headers={"X-Internal-Service-Secret": "s3"})
    assert r.status_code == 200
    assert r.json() == {"tenants": 2, "parcels": 3, "ok": 2, "failed": 1}


def test_setup_parcel_no_longer_writes_default_stock(client, monkeypatch):
    monkeypatch.setattr(internal, "INTERNAL_SERVICE_SECRET", "s3", raising=False)
    monkeypatch.setenv("INTERNAL_SERVICE_SECRET", "s3")
    upsert = AsyncMock()
    run = AsyncMock(return_value=compute_campaign_balance(_inp()))
    with patch("app.common.orion.upsert_entity", upsert), patch.object(internal, "run_campaign", run):
        r = client.post("/api/carbon/internal/setup-parcel", json={"parcel_id": "urn:ngsi-ld:AgriParcel:abc",
                                                                   "tenant_id": "t1"},
                        headers={"X-Internal-Service-Secret": "s3"})
    assert r.status_code == 200 and r.json()["scheduled"] is True
    upsert.assert_not_called()
    run.assert_awaited_once()


def test_projection_and_mrv_routes_use_stored_campaigns(monkeypatch):
    from app.api import assessments, mrv
    app = FastAPI()
    app.include_router(assessments.router)
    app.include_router(mrv.router)
    c = TestClient(app)
    proj = {"entity_id": "abc", "projection_years": 5, "reference_year": None, "baseline_soc": [],
            "project_soc": [], "annual_delta_tC_ha_yr": [], "assumptions": [],
            "missing": [{"item": "complete_campaign", "reason": "x", "effect": "no_projection"}]}
    monkeypatch.setattr(assessments, "projection", AsyncMock(return_value=proj))
    r = c.get("/api/carbon/parcels/abc/projection?years=5", headers=H)
    assert r.status_code == 200 and r.json()["missing"][0]["item"] == "complete_campaign"
    report = AsyncMock(return_value={"report_type": "monitoring_estimate"})
    monkeypatch.setattr(mrv, "monitoring_report", report)
    r = c.get("/api/carbon/parcels/abc/mrv/report?standard=VM0042&from_year=2025&to_year=2026", headers=H)
    assert r.status_code == 200 and r.json()["report_type"] == "monitoring_estimate"
    assert report.await_args.args[1:] == ("abc", "VM0042", 2025, 2026)


def test_scenario_recalculate_route_is_gone():
    from app.api import scenarios
    paths = {r.path for r in scenarios.router.routes}
    assert not any(p.endswith("/recalculate") for p in paths)
