import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_campaign_balance import _inp  # noqa: E402

from app.ngsild.campaign_entities import (  # noqa: E402
    build_campaign_assessment, build_campaign_stock, stock_state,
)
from app.platform.crop_client import canonical_parcel_urn, parcel_short  # noqa: E402
from app.services.campaign_balance import compute_campaign_balance  # noqa: E402
from app.services.roth_c_model import RothCPools, RothCState  # noqa: E402


def test_parcel_urn_forms():
    assert canonical_parcel_urn("abc") == "urn:ngsi-ld:AgriParcel:abc"
    assert canonical_parcel_urn("urn:ngsi-ld:AgriParcel:abc") == "urn:ngsi-ld:AgriParcel:abc"
    assert canonical_parcel_urn("urn:ngsi-ld:AgriParcel:t1:abc") == "urn:ngsi-ld:AgriParcel:abc"
    assert parcel_short("urn:ngsi-ld:AgriParcel:abc") == "abc"


def test_stock_round_trip():
    st = RothCState(RothCPools(0.1, 5.0, 0.7, 27.0, 3.0), -12.5)
    e = build_campaign_stock("t1", "abc", 2026, st, date(2026, 9, 30))
    assert e["id"] == "urn:ngsi-ld:CarbonStock:t1:abc:2026"
    assert e["hasAgriParcel"]["object"] == "urn:ngsi-ld:AgriParcel:abc"
    back, when = stock_state(e)
    assert back == st and when == date(2026, 9, 30)
    flat = {k: (v["value"] if isinstance(v, dict) and "value" in v else v) for k, v in e.items()}
    assert stock_state(flat)[0] == st  # keyValues form too


def test_assessment_entity_shape():
    b = compute_campaign_balance(_inp())
    e = build_campaign_assessment("t1", "urn:ngsi-ld:AgriParcel:abc", b, ["weather_daily"])
    assert e["id"] == "urn:ngsi-ld:CarbonAssessment:t1:abc:2026" and e["type"] == "CarbonAssessment"
    assert e["hasAgriParcel"]["object"] == "urn:ngsi-ld:AgriParcel:abc"
    assert e["campaignLabel"]["value"] == 2026 and e["computedThrough"]["value"] == "2026-09-30"
    assert e["dataTier"]["value"] == b.tier
    assert e["cycleBreakdown"]["value"][0]["start"] == "2026-01-01"
    m0 = e["monthlyBalance"]["value"][0]
    assert set(m0) >= {"month", "temp_c", "rain_mm", "et0_mm", "covered", "plant_c_tC_ha", "fym_c_tC_ha", "co2_c_tC_ha"}
    assert "nee" not in e  # tier 2: absent values are not written
    assert e["missing"]["value"] == [m.to_dict() for m in b.missing]
    assert "soilClayPct" not in e
    from app.services.campaign_types import SoilInit
    e2 = build_campaign_assessment("t1", "abc", b, [], soil=SoilInit(40.0, 21.0, 30.0, "soilgrids"))
    assert e2["soilClayPct"]["value"] == 21.0 and e2["soilDepthCm"]["value"] == 30.0
