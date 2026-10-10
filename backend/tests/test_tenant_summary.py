from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import assessments

H = {"X-Tenant-ID": "tenant-one", "X-User-ID": "u1"}


def _row(year, gross, delta, tier=2, species="TRZAX", coverage=1.0):
    return {"campaign_label": year, "computed_through": f"{year}-09-30", "data_tier": tier,
            "co2_sequestered_gross": gross, "soil_carbon_delta": delta, "co2eq_net": None,
            "tier1_coverage": coverage, "cycle_breakdown": [{"species": species}]}


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(assessments.router)
    parcels = [{"id": "urn:ngsi-ld:AgriParcel:p1", "name": {"value": "North"}},
               {"id": "urn:ngsi-ld:AgriParcel:p2", "name": {"value": "South"}},
               {"id": "urn:ngsi-ld:AgriParcel:p3"}]
    monkeypatch.setattr(assessments, "_tenant_parcels", AsyncMock(return_value=parcels))
    by_parcel = {"p1": [_row(2025, 10.0, 0.5), _row(2026, 12.0, None, tier=1)],
                 "p2": [_row(2026, 8.0, 0.3)], "p3": []}
    monkeypatch.setattr(assessments, "list_campaigns",
                        AsyncMock(side_effect=lambda t, pid: by_parcel[pid.rsplit(":", 1)[-1]]))
    return TestClient(app)


def test_summary_for_a_campaign(client):
    r = client.get("/api/carbon/tenant/summary?year=2026", headers=H).json()
    rows = {p["parcel_id"]: p for p in r["parcels"]}
    assert r["year"] == 2026
    assert rows["p1"]["delta_soc_tC_ha"] is None and rows["p1"]["co2_gross_tCO2_ha"] == 12.0
    assert rows["p1"]["crop_species"] == "TRZAX" and rows["p1"]["parcel_name"] == "North"
    assert rows["p3"]["tier"] == 0 and rows["p3"]["co2_gross_tCO2_ha"] is None  # not 0.0
    agg = {a["year"]: a for a in r["yearly_aggregations"]}
    assert agg[2026]["parcel_count"] == 2 and agg[2026]["co2_gross_tCO2_ha_mean"] == pytest.approx(10.0)
    assert agg[2026]["delta_soc_tC_ha_mean"] == pytest.approx(0.3)  # only non-null values
    assert agg[2025]["parcel_count"] == 1


def test_partial_production_is_flagged_and_not_averaged(monkeypatch):
    app = FastAPI()
    app.include_router(assessments.router)
    monkeypatch.setattr(assessments, "_tenant_parcels", AsyncMock(return_value=[{"id": "urn:ngsi-ld:AgriParcel:p1"},
                                                                               {"id": "urn:ngsi-ld:AgriParcel:p2"}]))
    rows = {"p1": [_row(2026, 2.0, None, tier=1, coverage=0.25)], "p2": [_row(2026, 8.0, 0.3)]}
    monkeypatch.setattr(assessments, "list_campaigns", AsyncMock(side_effect=lambda t, pid: rows[pid.rsplit(":", 1)[-1]]))
    r = TestClient(app).get("/api/carbon/tenant/summary?year=2026", headers=H).json()
    p1 = next(p for p in r["parcels"] if p["parcel_id"] == "p1")
    assert p1["tier1_coverage"] == 0.25
    assert r["yearly_aggregations"][0]["co2_gross_tCO2_ha_mean"] == pytest.approx(8.0)  # partial p1 excluded
