import pytest

from app.platform import soil_client as sc
from app.platform.errors import SourceUnavailable


def H(a, b, oc, bd, clay, cf=0.0):
    return {"depthFrom": a, "depthTo": b, "organicCarbon": oc, "bulkDensity": bd,
            "clay": clay, "coarseFragments": cf}


class FakeOrion:
    def __init__(self, ents, fail=False):
        self.ents, self.fail, self.queries = ents, fail, []

    async def query_entities(self, entity_type, tenant_id, query=None, attrs=None, limit=100, offset=0):
        if self.fail:
            raise RuntimeError("down")
        self.queries.append((entity_type, query))
        return self.ents if entity_type == "AgriSoilExtended" else []


def _soil(horizons):
    return [{"id": "s", "horizons": {"type": "Property", "value": horizons},
             "dataSource": {"type": "Property", "value": "soilgrids"}}]


@pytest.mark.asyncio
async def test_soc_stock_from_horizons(monkeypatch):
    fake = FakeOrion(_soil([H(0, 5, 2.0, 1.2, 20), H(5, 15, 1.0, 1.3, 30, 10),
                            H(15, 30, 0.5, 1.4, 30), H(30, 60, 0.3, 1.5, 40)]))
    monkeypatch.setattr(sc, "get_orion_client", lambda: fake)
    soil, missing = await sc.fetch_soil_init("urn:ngsi-ld:AgriParcel:p", "t")
    # 2.0*1.2*5 + 1.0*1.3*10*0.9 + 0.5*1.4*15 = 12 + 11.7 + 10.5
    assert soil.soc_tC_ha == pytest.approx(34.2)
    assert soil.clay_pct == pytest.approx((20 * 5 + 30 * 10 + 30 * 15) / 30)
    assert soil.depth_cm == 30 and soil.source == "soilgrids" and missing == []
    assert fake.queries[0] == ("AgriSoilExtended",
                               'refAgriParcel=="urn:ngsi-ld:AgriParcel:p"|hasAgriParcel=="urn:ngsi-ld:AgriParcel:p"')


@pytest.mark.asyncio
async def test_horizon_straddling_30cm_is_clipped(monkeypatch):
    monkeypatch.setattr(sc, "get_orion_client", lambda: FakeOrion(_soil([H(0, 15, 1.0, 1.0, 10), H(15, 60, 1.0, 1.0, 40)])))
    soil, _ = await sc.fetch_soil_init("urn:ngsi-ld:AgriParcel:p", "t")
    assert soil.soc_tC_ha == pytest.approx(30.0) and soil.clay_pct == pytest.approx(25.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("bd", [-3276.8, 0.0, 2.5, None])
async def test_bad_bulk_density_is_missing_not_default(monkeypatch, bd):
    monkeypatch.setattr(sc, "get_orion_client", lambda: FakeOrion(_soil([H(0, 30, 1.0, bd, 20)])))
    soil, missing = await sc.fetch_soil_init("urn:ngsi-ld:AgriParcel:p", "t")
    assert soil is None and [m.item for m in missing] == ["soil_soc"]


@pytest.mark.asyncio
async def test_missing_clay_is_missing(monkeypatch):
    monkeypatch.setattr(sc, "get_orion_client", lambda: FakeOrion(_soil([H(0, 30, 1.0, 1.3, None)])))
    soil, missing = await sc.fetch_soil_init("urn:ngsi-ld:AgriParcel:p", "t")
    assert soil is None and [m.item for m in missing] == ["soil_clay"]


@pytest.mark.asyncio
async def test_no_entity_is_missing(monkeypatch):
    monkeypatch.setattr(sc, "get_orion_client", lambda: FakeOrion([]))
    soil, missing = await sc.fetch_soil_init("urn:ngsi-ld:AgriParcel:p", "t")
    assert soil is None and [m.item for m in missing] == ["soil"]


@pytest.mark.asyncio
async def test_lab_values_override(monkeypatch):
    monkeypatch.setattr(sc, "get_orion_client", lambda: FakeOrion([]))
    soil, missing = await sc.fetch_soil_init("urn:ngsi-ld:AgriParcel:p", "t", lab=(41.0, 22.0))
    assert (soil.soc_tC_ha, soil.clay_pct, soil.depth_cm, soil.source) == (41.0, 22.0, 30.0, "lab")


@pytest.mark.asyncio
async def test_partial_lab_completes_from_horizons(monkeypatch):
    monkeypatch.setattr(sc, "get_orion_client", lambda: FakeOrion(_soil([H(0, 30, 1.0, 1.3, 20)])))
    soil, missing = await sc.fetch_soil_init("urn:ngsi-ld:AgriParcel:p", "t", lab=(41.0, None))
    assert soil.soc_tC_ha == 41.0 and soil.clay_pct == 20.0 and soil.source == "lab+soilgrids"


@pytest.mark.asyncio
async def test_orion_failure_is_source_unavailable(monkeypatch):
    monkeypatch.setattr(sc, "get_orion_client", lambda: FakeOrion([], fail=True))
    with pytest.raises(SourceUnavailable):
        await sc.fetch_soil_init("urn:ngsi-ld:AgriParcel:p", "t")


@pytest.mark.asyncio
async def test_organic_carbon_in_g_per_kg_on_mineral_soil_is_missing(monkeypatch):
    # 15 "%" OC with mineral bulk density is a g/kg value written in a % field.
    monkeypatch.setattr(sc, "get_orion_client", lambda: FakeOrion(_soil([H(0, 30, 15.0, 1.3, 20)])))
    soil, missing = await sc.fetch_soil_init("urn:ngsi-ld:AgriParcel:p", "t")
    assert soil is None and [m.item for m in missing] == ["soil_soc"]
