"""NGSI-LD entities of the per-campaign carbon balance."""

from datetime import date, datetime, timezone
from typing import Any, Optional

from app.ngsild.entities import _context
from app.platform.crop_client import canonical_parcel_urn, parcel_short
from app.services.campaign_balance import ENGINE_VERSION
from app.services.campaign_types import CampaignBalance, CycleResult, MonthResult, SoilInit
from app.services.roth_c_model import RothCPools, RothCState


def _p(value: Any, unit: Optional[str] = None) -> dict:
    prop = {"type": "Property", "value": value}
    if unit:
        prop["unitCode"] = unit
    return prop


def _iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def _cycle(c: CycleResult) -> dict:
    return {
        "crop_id": c.crop_id, "species": c.species, "role": c.role, "start": _iso(c.start), "end": _iso(c.end),
        "start_provenance": c.start_provenance, "end_provenance": c.end_provenance,
        "campaign_label": c.campaign_label, "days_in_period": c.days_in_period, "days_computed": c.days_computed,
        "npp_tC_ha": c.npp_tC_ha, "c_to_soil_tC_ha": c.c_to_soil_tC_ha, "exported_c_tC_ha": c.exported_c_tC_ha,
    }


def _month(m: MonthResult) -> dict:
    return {
        "month": m.month, "temp_c": m.temp_c, "rain_mm": m.rain_mm, "et0_mm": m.et0_mm, "covered": m.covered,
        "cover_days": m.cover_days, "plant_c_tC_ha": m.plant_c_tC_ha, "fym_c_tC_ha": m.fym_c_tC_ha,
        "co2_c_tC_ha": m.co2_c_tC_ha,
    }


def build_campaign_assessment(tenant_id: str, parcel_id: str, b: CampaignBalance, sources: list[str],
                              soil: Optional[SoilInit] = None) -> dict:
    short = parcel_short(parcel_id)
    entity: dict[str, Any] = {
        "id": f"urn:ngsi-ld:CarbonAssessment:{tenant_id}:{short}:{b.year}",
        "type": "CarbonAssessment",
        "@context": _context(),
        "hasAgriParcel": {"type": "Relationship", "object": canonical_parcel_urn(parcel_id)},
        "campaignLabel": _p(b.year),
        "periodStart": _p(_iso(b.period_start)),
        "periodEnd": _p(_iso(b.period_end)),
        "dataTier": _p(b.tier),
        "coverDays": _p(b.cover_days),
        "bareDays": _p(b.bare_days),
        "tier1Coverage": _p(round(b.tier1_coverage, 4)),
        "cycleBreakdown": _p([_cycle(c) for c in b.cycles]),
        "monthlyBalance": _p([_month(m) for m in b.months]),
        "missing": _p([m.to_dict() for m in b.missing]),
        "assumptions": _p(list(b.assumptions)),
        "initialStateSource": _p(b.initial_state_source),
        "dataSources": _p(sources),
        "gwpStandard": _p("AR6"),
        "engineVersion": _p(ENGINE_VERSION),
        "calculatedAt": _p(datetime.now(timezone.utc).isoformat()),
        "source": _p("carbon"),
    }
    optional = {
        "computedThrough": (_iso(b.computed_through), None),
        "gppTotal": (b.gpp_tC_ha, "tC/ha"),
        "nppTotal": (b.npp_tC_ha, "tC/ha"),
        "co2SequesteredGross": (b.co2_gross_tCO2_ha, "tCO2/ha"),
        "heterotrophicRespiration": (b.rh_tC_ha, "tC/ha"),
        "socStart": (b.soc_start_tC_ha, "tC/ha"),
        "socEnd": (b.soc_end_tC_ha, "tC/ha"),
        "soilCarbonDelta": (b.delta_soc_tC_ha, "tC/ha"),
        "soilCarbonDeltaCi95": (b.delta_soc_ci95_tC_ha, "tC/ha"),
        "nee": (b.nee_tCO2_ha, "tCO2/ha"),
        "necb": (b.necb_tC_ha, "tC/ha"),
        "n2oEmissions": (b.n2o_tCO2eq_ha, "tCO2eq/ha"),
        "co2eqNet": (b.co2eq_net_tCO2eq_ha, "tCO2eq/ha"),
        "gppCi95Pct": (b.gpp_ci95_pct, None),
        "soilClayPct": (soil.clay_pct if soil else None, "%"),
        "soilDepthCm": (soil.depth_cm if soil else None, "cm"),
        "soilSource": (soil.source if soil else None, None),
    }
    # Units are fixed per attribute (see the API models and METHODOLOGY.md); there is
    # no UN/CEFACT code for tC/ha, so none is attached.
    for name, (value, _unit) in optional.items():
        if value is not None:
            entity[name] = _p(value)
    return entity


def build_campaign_stock(tenant_id: str, parcel_id: str, year: int, state: RothCState, state_date: date) -> dict:
    p = state.pools
    return {
        "id": f"urn:ngsi-ld:CarbonStock:{tenant_id}:{parcel_short(parcel_id)}:{year}",
        "type": "CarbonStock",
        "@context": _context(),
        "hasAgriParcel": {"type": "Relationship", "object": canonical_parcel_urn(parcel_id)},
        "campaignLabel": _p(year),
        "dpmPool": _p(p.dpm), "rpmPool": _p(p.rpm), "bioPool": _p(p.bio), "humPool": _p(p.hum),
        "iomPool": _p(p.iom),
        "totalSOC": _p(p.total),
        "soilWaterDeficit": _p(state.swc_mm),
        "stateDate": _p(state_date.isoformat()),
        "source": _p("carbon"),
    }


def _v(entity: dict, name: str) -> Any:
    v = entity[name]
    return v.get("value") if isinstance(v, dict) else v


def stock_state(entity: dict) -> tuple[RothCState, date]:
    pools = RothCPools(float(_v(entity, "dpmPool")), float(_v(entity, "rpmPool")), float(_v(entity, "bioPool")),
                       float(_v(entity, "humPool")), float(_v(entity, "iomPool")))
    return RothCState(pools, float(_v(entity, "soilWaterDeficit"))), date.fromisoformat(str(_v(entity, "stateDate"))[:10])
