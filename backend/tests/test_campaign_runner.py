import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from test_campaign_balance import P, SOIL, _ndvi, _weather  # noqa: E402

from app.ngsild.campaign_entities import build_campaign_stock  # noqa: E402
from app.platform.errors import SourceUnavailable  # noqa: E402
from app.services import campaign_runner as cr  # noqa: E402
from app.services.campaign_types import HarvestEvent, OperationsRead  # noqa: E402
from app.services.roth_c_model import RothCPools, RothCState  # noqa: E402

TODAY = date(2026, 10, 10)


class Store:
    def __init__(self):
        self.entities = {}

    async def get_entity(self, entity_id, tenant_id):
        return self.entities.get((tenant_id, entity_id))

    async def upsert_entity(self, entity, tenant_id):
        raise AssertionError("campaign results must be written with replace_entity")

    async def replace_entity(self, entity, tenant_id):
        self.entities[(tenant_id, entity["id"])] = entity
        return entity

    async def delete_entity(self, entity_id, tenant_id):
        self.entities.pop((tenant_id, entity_id), None)

    async def query_entities(self, entity_type, tenant_id, query=None, attrs=None, limit=100, offset=0):
        if offset:
            return []
        return [e for (t, _), e in self.entities.items() if t == tenant_id and e["type"] == entity_type
                and query and e["hasAgriParcel"]["object"] in query]


def _cycle_dict(start, end, species="TRZAX"):
    return {"crop_id": "urn:ngsi-ld:AgriCrop:c1", "role": "main_crop", "species": species, "status": "active",
            "lifecycle": "annual", "start": {"date": start, "provenance": "actual"},
            "end": {"date": end, "provenance": "actual" if end else None}, "campaign_label": 2026}


@pytest.fixture
def env(monkeypatch):
    store = Store()
    calls = {"weather": []}

    async def cycles(urn, tenant, at, client=None):
        return [_cycle_dict("2026-01-01", "2026-06-30")]

    async def weather(urn, tenant, start, end, client=None):
        calls["weather"].append((start, end))
        return list(_weather(start, min(end, TODAY - timedelta(days=1))))

    async def ndvi(urn, tenant, start, end):
        return {"NDVI": list(_ndvi(date(2025, 1, 1), date(2026, 12, 31))), "OSAVI": []}

    async def soil(urn, tenant, lab=(None, None)):
        return SOIL, []

    async def ops(urn, tenant, start, end, area):
        return OperationsRead((HarvestEvent(date(2026, 7, 1), 1.2, "operation"),), (), (), (), (), ())

    async def area(urn, tenant):
        return 10.0

    async def coords(pid, tenant):
        return (42.0, -1.6)

    async def params(species, lat, lon):
        return P, []

    for name, fn in [("fetch_cycles", cycles), ("fetch_daily_weather", weather), ("fetch_vi_series", ndvi),
                     ("fetch_soil_init", soil), ("fetch_operations", ops), ("fetch_parcel_area_ha", area),
                     ("fetch_parcel_coordinates", coords), ("resolve_crop_params", params)]:
        monkeypatch.setattr(cr, name, fn)
    monkeypatch.setattr(cr, "get_orion_client", lambda: store)
    return store, calls


@pytest.mark.asyncio
async def test_writes_assessment_and_stock(env):
    store, _ = env
    b = await cr.run_campaign("t1", "abc", 2026, today=TODAY)
    assert b.tier == 2 and b.initial_state_source == "soil"
    a = store.entities[("t1", "urn:ngsi-ld:CarbonAssessment:t1:abc:2026")]
    assert a["hasAgriParcel"]["object"] == "urn:ngsi-ld:AgriParcel:abc"
    s = store.entities[("t1", "urn:ngsi-ld:CarbonStock:t1:abc:2026")]
    assert s["stateDate"]["value"] == "2026-09-30"


@pytest.mark.asyncio
async def test_chains_from_complete_previous_stock(env):
    store, _ = env
    prev = RothCState(RothCPools(0.1, 5.0, 0.7, 30.0, 3.0), -5.0)
    e = build_campaign_stock("t1", "abc", 2025, prev, date(2025, 12, 31))
    store.entities[("t1", e["id"])] = e
    b = await cr.run_campaign("t1", "abc", 2026, today=TODAY)
    assert b.initial_state_source == "previous_campaign"
    assert b.soc_start_tC_ha == pytest.approx(prev.pools.total)


@pytest.mark.asyncio
async def test_incomplete_previous_campaign_is_finished_first(env):
    store, _ = env
    first = await cr.run_campaign("t1", "abc", 2025, today=date(2025, 12, 20))
    assert first.computed_through == date(2025, 11, 30)
    b = await cr.run_campaign("t1", "abc", 2026, today=TODAY)
    s25 = store.entities[("t1", "urn:ngsi-ld:CarbonStock:t1:abc:2025")]
    assert s25["stateDate"]["value"] == "2025-12-31" and b.initial_state_source == "previous_campaign"


@pytest.mark.asyncio
async def test_cascade_recomputes_following_campaign(env):
    store, _ = env
    await cr.run_campaign("t1", "abc", 2026, today=TODAY)
    before = store.entities[("t1", "urn:ngsi-ld:CarbonAssessment:t1:abc:2026")]["calculatedAt"]["value"]
    await cr.run_campaign("t1", "abc", 2025, today=TODAY)
    after = store.entities[("t1", "urn:ngsi-ld:CarbonAssessment:t1:abc:2026")]
    assert after["calculatedAt"]["value"] >= before
    assert after["initialStateSource"]["value"] == "previous_campaign"


@pytest.mark.asyncio
async def test_crossing_cycle_widens_weather_window(env, monkeypatch):
    store, calls = env

    async def cycles(urn, tenant, at, client=None):
        return [_cycle_dict("2025-10-15", "2026-06-30")]
    monkeypatch.setattr(cr, "fetch_cycles", cycles)
    await cr.run_campaign("t1", "abc", 2026, today=TODAY)
    assert min(s for s, _ in calls["weather"]) == date(2025, 10, 15)


@pytest.mark.asyncio
async def test_source_down_writes_nothing(env, monkeypatch):
    store, _ = env

    async def down(*a, **k):
        raise SourceUnavailable("weather down")
    monkeypatch.setattr(cr, "fetch_daily_weather", down)
    with pytest.raises(SourceUnavailable):
        await cr.run_campaign("t1", "abc", 2026, today=TODAY)
    assert store.entities == {}


@pytest.mark.asyncio
async def test_future_year_rejected(env):
    with pytest.raises(ValueError):
        await cr.run_campaign("t1", "abc", 2027, today=TODAY)


@pytest.mark.asyncio
async def test_list_and_get(env):
    store, _ = env
    await cr.run_campaign("t1", "abc", 2026, today=TODAY)
    listed = await cr.list_campaigns("t1", "abc")
    assert [c["campaign_label"] for c in listed] == [2026]
    one = await cr.get_campaign("t1", "abc", 2026)
    assert one["computed_through"] == "2026-09-30" and one["data_tier"] == 2
    assert await cr.get_campaign("t1", "abc", 2024) is None


@pytest.mark.asyncio
async def test_audit_row_written_best_effort(env, monkeypatch):
    from unittest.mock import AsyncMock
    audit = AsyncMock(side_effect=RuntimeError("db down"))
    monkeypatch.setattr(cr, "insert_carbon_calculation", audit)
    b = await cr.run_campaign("t1", "abc", 2026, today=TODAY)  # a failing audit does not fail the run
    kwargs = audit.await_args.kwargs
    assert kwargs["tier"] == b.tier and kwargs["entity_id"] == "urn:ngsi-ld:AgriParcel:abc"
    assert kwargs["results"]["computed_through"] == "2026-09-30"


@pytest.mark.asyncio
async def test_projection_needs_a_complete_campaign(env):
    await cr.run_campaign("t1", "abc", 2026, today=TODAY)  # open campaign only
    p = await cr.projection("t1", "abc", years=5)
    assert p["project_soc"] == [] and p["missing"][0]["item"] == "complete_campaign" and p["reference_year"] is None


@pytest.mark.asyncio
async def test_projection_repeats_last_complete_campaign(env):
    await cr.run_campaign("t1", "abc", 2025, today=TODAY)
    p = await cr.projection("t1", "abc", years=3)
    assert p["reference_year"] == 2025 and len(p["project_soc"]) == 3
    assert p["baseline_soc"] == [] and any("baseline" in a for a in p["assumptions"])


@pytest.mark.asyncio
async def test_projection_and_report_with_baseline(env):
    store, _ = env
    await cr.run_campaign("t1", "abc", 2025, today=TODAY)
    await cr.run_campaign("t1", "abc", 2026, today=TODAY)
    store.entities[("t1", "urn:ngsi-ld:BaselineScenario:t1:abc")] = {
        "id": "urn:ngsi-ld:BaselineScenario:t1:abc", "type": "BaselineScenario",
        "validFrom": {"type": "Property", "value": "2025-01-01"}}
    p = await cr.projection("t1", "abc", years=2)
    assert len(p["baseline_soc"]) == 2 and len(p["annual_delta_tC_ha_yr"]) == 2
    r = await cr.monitoring_report("t1", "abc", "VM0042", 2025, 2026)
    assert r["baseline_reference_year"] == 2025 and [c["year"] for c in r["campaigns"]] == [2025, 2026]
    # the reference campaign replayed under its own climate is itself: no reduction that year
    assert r["campaigns"][0]["baseline_delta_soc_tC_ha"] == pytest.approx(r["campaigns"][0]["delta_soc_tC_ha"])
    assert r["net_emission_reductions_tCO2eq_ha"] is not None


@pytest.mark.asyncio
async def test_report_without_campaigns_is_empty(env):
    r = await cr.monitoring_report("t1", "abc", "VM0042", None, None)
    assert r["campaigns"] == [] and r["net_emission_reductions_tCO2eq_ha"] is None


@pytest.mark.asyncio
async def test_future_cycle_does_not_report_its_params(env, monkeypatch):
    async def cycles(urn, tenant, at, client=None):
        return [_cycle_dict("2026-10-15", None, species="QUCHX")]

    async def no_params(species, lat, lon):
        from app.services.campaign_types import Missing
        return None, [Missing("crop_params", f"{species}: none", "tier1_unavailable")]
    monkeypatch.setattr(cr, "fetch_cycles", cycles)
    monkeypatch.setattr(cr, "resolve_crop_params", no_params)
    b = await cr.run_campaign("t1", "abc", 2026, today=TODAY)
    assert "crop_params" not in {m.item for m in b.missing}


def test_entity_view_reads_either_relationship_term():
    # Orion compacts the relationship to whichever term the context lists first;
    # both expand to the same IRI.
    e = {"id": "x", "type": "CarbonAssessment",
         "refAgriParcel": {"type": "Relationship", "object": "urn:ngsi-ld:AgriParcel:abc"},
         "campaignLabel": {"type": "Property", "value": 2026}}
    row = cr.entity_to_dict(e)
    assert row["parcel_id"] == "urn:ngsi-ld:AgriParcel:abc" and "ref_agri_parcel" not in row


@pytest.mark.asyncio
async def test_losing_tier2_removes_the_stock(env, monkeypatch):
    store, _ = env
    await cr.run_campaign("t1", "abc", 2025, today=TODAY)
    assert ("t1", "urn:ngsi-ld:CarbonStock:t1:abc:2025") in store.entities

    async def no_soil(urn, tenant, lab=(None, None)):
        from app.services.campaign_types import Missing
        return None, [Missing("soil", "none", "tier2_unavailable")]
    monkeypatch.setattr(cr, "fetch_soil_init", no_soil)
    b = await cr.run_campaign("t1", "abc", 2025, today=TODAY)
    assert b.tier == 1 and ("t1", "urn:ngsi-ld:CarbonStock:t1:abc:2025") not in store.entities


@pytest.mark.asyncio
async def test_chain_needs_a_tier2_previous_assessment(env):
    store, _ = env
    prev = RothCState(RothCPools(0.1, 5.0, 0.7, 30.0, 3.0), -5.0)
    e = build_campaign_stock("t1", "abc", 2025, prev, date(2025, 12, 31))
    store.entities[("t1", e["id"])] = e
    store.entities[("t1", "urn:ngsi-ld:CarbonAssessment:t1:abc:2025")] = {
        "id": "urn:ngsi-ld:CarbonAssessment:t1:abc:2025", "type": "CarbonAssessment",
        "hasAgriParcel": {"type": "Relationship", "object": "urn:ngsi-ld:AgriParcel:abc"},
        "campaignLabel": {"type": "Property", "value": 2025},
        "computedThrough": {"type": "Property", "value": "2025-12-31"},
        "dataTier": {"type": "Property", "value": 1}}
    b = await cr.run_campaign("t1", "abc", 2026, today=TODAY)
    assert b.initial_state_source == "soil"


def test_management_model_has_no_silent_defaults():
    from app.models.management import ManagementInput
    m = ManagementInput()
    assert all(v is None for v in m.model_dump().values())


@pytest.mark.asyncio
async def test_form_saved_for_irrigation_only_declares_nothing_else(env, monkeypatch):
    store, _ = env
    store.entities[("t1", "urn:ngsi-ld:ManagementPractice:t1:abc")] = {
        "id": "urn:ngsi-ld:ManagementPractice:t1:abc", "type": "ManagementPractice",
        "irrigated": {"type": "Property", "value": True}}

    b = await cr.run_campaign("t1", "abc", 2026, today=TODAY)   # harvest recorded: reaches Tier 2
    assert b.tier == 2 and "fertilizer_n" in {m.item for m in b.missing}   # no invented zero N

    async def ops(urn, tenant, start, end, area):
        return OperationsRead((), (), (), (), (), ())   # no harvest record
    monkeypatch.setattr(cr, "fetch_operations", ops)
    b = await cr.run_campaign("t1", "abc", 2026, today=TODAY)
    assert "harvest_export" in {m.item for m in b.missing}   # no invented 90 % export


@pytest.mark.asyncio
async def test_declared_export_fraction_unlocks_tier2_with_real_ops_missing(env, monkeypatch):
    store, _ = env
    from app.platform import operations_client as oc

    class O:
        async def query_entities(self, entity_type, tenant_id, query=None, attrs=None, limit=100, offset=0):
            if offset:
                return []
            return [{"id": "h", "operationType": {"value": "harvesting"}, "status": {"value": "completed"},
                     "endedAt": {"value": "2026-07-01T10:00:00Z"}, "harvestedWeight": {"value": 30000}}]
    monkeypatch.setattr(oc, "get_orion_client", lambda: O())
    monkeypatch.setattr(cr, "fetch_operations", oc.fetch_operations)   # the real client: weight without moisture
    store.entities[("t1", "urn:ngsi-ld:ManagementPractice:t1:abc")] = {
        "id": "urn:ngsi-ld:ManagementPractice:t1:abc", "type": "ManagementPractice",
        "harvest_export_fraction": {"type": "Property", "value": 0.5}}
    b = await cr.run_campaign("t1", "abc", 2026, today=TODAY)
    assert b.tier == 2 and b.cycles[0].exported_c_tC_ha > 0


def test_entity_view_restores_single_element_lists():
    # Orion-LD compacts a one-element array value to the element itself.
    e = {"id": "x", "type": "CarbonAssessment",
         "hasAgriParcel": {"type": "Relationship", "object": "urn:ngsi-ld:AgriParcel:abc"},
         "cycleBreakdown": {"type": "Property", "value": {"crop_id": "c1"}},
         "monthlyBalance": {"type": "Property", "value": {"month": 1}},
         "missing": {"type": "Property", "value": {"item": "soil"}},
         "assumptions": {"type": "Property", "value": "only one"},
         "dataSources": {"type": "Property", "value": "eo_ndvi"}}
    row = cr.entity_to_dict(e)
    assert row["cycle_breakdown"] == [{"crop_id": "c1"}] and row["monthly_balance"] == [{"month": 1}]
    assert row["missing"] == [{"item": "soil"}] and row["assumptions"] == ["only one"]
    assert row["data_sources"] == ["eo_ndvi"]
    assert cr.entity_to_dict({"id": "y", "type": "CarbonAssessment"})["missing"] == []



@pytest.mark.asyncio
async def test_woody_species_without_lifecycle_is_treated_as_perennial(env, monkeypatch):
    async def cycles(urn, tenant, at, client=None):
        c = _cycle_dict("2026-01-01", None, species="OLVEU")
        c["lifecycle"] = "unknown"
        return [c]
    monkeypatch.setattr(cr, "fetch_cycles", cycles)
    b = await cr.run_campaign("t1", "abc", 2026, today=TODAY)
    items = {m.item for m in b.missing}
    assert "perennial_litter" in items and "cycle_lifecycle" in items
    assert b.tier <= 1 and b.co2eq_net_tCO2eq_ha is None
