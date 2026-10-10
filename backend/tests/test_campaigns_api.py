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


def test_calculate_returns_the_stored_row(client, monkeypatch):
    b = compute_campaign_balance(_inp())
    monkeypatch.setattr(api, "run_campaign", AsyncMock(return_value=b))
    monkeypatch.setattr(api, "get_campaign", AsyncMock(return_value={"campaign_label": 2026, "data_tier": b.tier}))
    monkeypatch.setattr(api, "get_campaign_stock", AsyncMock(return_value={
        "dpmPool": {"value": 0.1}, "rpmPool": {"value": 5.0}, "bioPool": {"value": 0.7},
        "humPool": {"value": 27.0}, "iomPool": {"value": 3.0}, "soilWaterDeficit": {"value": 0.0},
        "stateDate": {"value": "2026-09-30"}}))
    r = client.post("/api/carbon/parcels/abc/campaigns/2026/calculate", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["campaign_label"] == 2026 and body["data_tier"] == b.tier
    assert body["pools_end"]["HUM"] == 27.0 and body["pools_state_date"] == "2026-09-30"


def test_calculate_empty_balance_is_200(client, monkeypatch):
    from test_campaign_balance import _weather
    b = compute_campaign_balance(_inp(today=date(2026, 1, 20), weather=_weather(date(2026, 1, 1), date(2026, 1, 19))))
    monkeypatch.setattr(api, "run_campaign", AsyncMock(return_value=b))
    monkeypatch.setattr(api, "get_campaign", AsyncMock(return_value={
        "campaign_label": 2026, "data_tier": 0, "missing": [m.to_dict() for m in b.missing]}))
    monkeypatch.setattr(api, "get_campaign_stock", AsyncMock(return_value=None))
    r = client.post("/api/carbon/parcels/abc/campaigns/2026/calculate", headers=H)
    assert r.status_code == 200 and r.json()["data_tier"] == 0 and r.json()["missing"][0]["item"] == "weather"
    assert r.json()["pools_end"] is None


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


def test_management_save_stores_only_what_was_declared(monkeypatch):
    from app.api import management
    app = FastAPI()
    app.include_router(management.router)
    saved = {}

    class O:
        async def replace_entity(self, entity, tenant_id):
            saved.update(entity)
            return entity
    monkeypatch.setattr("app.common.orion.get_orion_client", lambda: O())
    r = TestClient(app).post("/api/carbon/parcels/abc/management", json={"irrigated": True}, headers=H)
    assert r.status_code == 201
    keys = set(saved) - {"id", "type", "@context", "hasAgriParcel", "lastUpdated", "source"}
    assert keys == {"irrigated"}


def test_management_form_declares_only_what_the_platform_does_not_record():
    from app.models.management import ManagementInput
    assert set(ManagementInput.model_fields) == {
        "harvest_export_fraction", "residue_removal_fraction", "organic_amendments_tC_ha_yr",
        "n_synthetic_kgN_ha_yr", "n_organic_kgN_ha_yr", "irrigated", "soil_lab_soc_tC_ha", "soil_lab_clay_pct",
    }
    # old clients sending removed fields are not rejected
    assert ManagementInput(weather_source="sensor", tillage_type="no_till").model_dump(exclude_none=True) == {}


def test_sensor_listing_route_is_gone():
    from app.api import assessments
    assert not any(r.path.endswith("/sensors/available") for r in assessments.router.routes)


def test_calculate_unknown_parcel_is_404(client, monkeypatch):
    from app.services.campaign_runner import ParcelNotFound
    monkeypatch.setattr(api, "run_campaign", AsyncMock(side_effect=ParcelNotFound("no AgriParcel x")))
    r = client.post("/api/carbon/parcels/x/campaigns/2026/calculate", headers=H)
    assert r.status_code == 404
