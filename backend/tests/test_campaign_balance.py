from dataclasses import replace
from datetime import date, timedelta

import pytest

from app.services.campaign_balance import compute_campaign_balance
from app.services.campaign_types import (
    NO_DECLARED_MANAGEMENT, BalingEvent, CampaignInputs, CropParams, CycleSpan,
    FertilizationEvent, HarvestEvent, Missing, SoilInit, WeatherDay,
)

P = CropParams(lue_gC_MJ=1.1, fapar_a=1.24, fapar_b=-0.168, vi_type="NDVI", root_fraction=0.22, source="table")
SOIL = SoilInit(40.0, 20.0, 30.0, "soilgrids")


def _weather(first, last):
    d, out = first, []
    while d <= last:
        out.append(WeatherDay(d, 2.0, 14.0, 1.5, 2.0, 12.0))
        d += timedelta(days=1)
    return tuple(out)


def _ndvi(first, last, value=0.6):
    out, d = [], first
    while d <= last:
        out.append((d, value))
        d += timedelta(days=10)
    return tuple(out)


def _cycle(start, end, role="main_crop", params=P, lifecycle="annual", prov="actual", crop_id="c1"):
    return CycleSpan(crop_id, "TRZAX", role, lifecycle, start, end, prov, "actual" if end else None, 2026, params)


def _inp(**kw):
    base = dict(
        year=2026, today=date(2026, 10, 10),
        weather=_weather(date(2026, 1, 1), date(2026, 10, 9)),
        ndvi=_ndvi(date(2026, 1, 1), date(2026, 12, 31)),
        cycles=(_cycle(date(2026, 1, 1), date(2026, 6, 30)),),
        soil=SOIL, initial_state=None, initial_state_source="soil",
        harvests=(HarvestEvent(date(2026, 7, 1), 1.2, "operation"),),
        fertilizations=(), tillages=(), balings=(),
        declared=NO_DECLARED_MANAGEMENT, missing_in=(),
    )
    base.update(kw)
    return CampaignInputs(**base)


def _items(b):
    return {m.item for m in b.missing}


def test_computed_through_is_last_complete_month():
    assert compute_campaign_balance(_inp()).computed_through == date(2026, 9, 30)


def test_gap_in_weather_stops_at_previous_month():
    w = tuple(d for d in _weather(date(2026, 1, 1), date(2026, 10, 9)) if d.day != date(2026, 5, 15))
    assert compute_campaign_balance(_inp(weather=w)).computed_through == date(2026, 4, 30)


def test_january_without_complete_month_returns_empty_balance():
    b = compute_campaign_balance(_inp(today=date(2026, 1, 20), weather=_weather(date(2026, 1, 1), date(2026, 1, 19))))
    assert b.tier == 0 and b.computed_through is None and "weather" in _items(b)
    assert b.months == () and b.gpp_tC_ha is None


def test_closed_year_runs_through_december():
    b = compute_campaign_balance(_inp(year=2025, today=date(2026, 10, 10),
                                      weather=_weather(date(2025, 1, 1), date(2025, 12, 31)),
                                      ndvi=_ndvi(date(2025, 1, 1), date(2025, 12, 31)),
                                      cycles=(), harvests=()))
    assert b.computed_through == date(2025, 12, 31) and len(b.months) == 12


def test_cover_days_inclusive_end_and_bare_days():
    b = compute_campaign_balance(_inp())
    assert b.cover_days == (date(2026, 6, 30) - date(2026, 1, 1)).days + 1
    assert b.cover_days + b.bare_days == (date(2026, 9, 30) - date(2026, 1, 1)).days + 1


def test_future_planned_cycle_is_not_cover():
    b = compute_campaign_balance(_inp(cycles=(_cycle(date(2026, 10, 15), None, prov="planned"),), harvests=()))
    assert b.cover_days == 0 and b.cycles == ()


def test_past_planned_start_is_flagged():
    b = compute_campaign_balance(_inp(cycles=(_cycle(date(2026, 3, 1), date(2026, 6, 30), prov="planned"),)))
    assert "cycle_start" in _items(b) and b.cover_days > 0


def test_inverted_cycle_is_ignored():
    b = compute_campaign_balance(_inp(cycles=(_cycle(date(2026, 6, 1), date(2026, 5, 1)),), harvests=()))
    assert b.cover_days == 0 and "cycle" in _items(b)


def test_tier2_runs_and_conserves_mass():
    b = compute_campaign_balance(_inp())
    assert b.tier == 2 and b.tier1_coverage == 1.0
    c_in = sum(m.plant_c_tC_ha + m.fym_c_tC_ha for m in b.months)
    assert b.soc_end_tC_ha == pytest.approx(b.soc_start_tC_ha + c_in - b.rh_tC_ha, abs=1e-9)
    assert b.delta_soc_tC_ha == pytest.approx(b.soc_end_tC_ha - b.soc_start_tC_ha)
    assert b.end_state is not None and b.delta_soc_ci95_tC_ha is not None


def test_npp_split_reaches_soil_at_closure_minus_export():
    b = compute_campaign_balance(_inp(harvests=(HarvestEvent(date(2026, 7, 1), 0.0, "operation"),)))
    cyc = b.cycles[0]
    # without export, everything produced (shoot + root + exudates) reaches the soil
    assert cyc.c_to_soil_tC_ha == pytest.approx(cyc.npp_tC_ha)
    june = b.months[5]
    assert june.plant_c_tC_ha > b.months[4].plant_c_tC_ha  # closure lands in the end month


def test_harvest_export_reduces_soil_input():
    full = compute_campaign_balance(_inp(harvests=(HarvestEvent(date(2026, 7, 1), 0.0, "operation"),)))
    exp = compute_campaign_balance(_inp())
    assert exp.cycles[0].c_to_soil_tC_ha == pytest.approx(full.cycles[0].c_to_soil_tC_ha - 1.2, abs=1e-9)
    assert exp.cycles[0].exported_c_tC_ha == pytest.approx(1.2)


def test_unknown_export_blocks_tier2_but_keeps_tier1():
    b = compute_campaign_balance(_inp(harvests=(HarvestEvent(date(2026, 7, 1), None, "operation"),)))
    assert b.tier == 1 and b.delta_soc_tC_ha is None and "harvest_export" in _items(b)


def test_declared_export_fraction_used_when_weight_unknown():
    decl = replace(NO_DECLARED_MANAGEMENT, harvest_export_fraction=0.5)
    b = compute_campaign_balance(_inp(harvests=(HarvestEvent(date(2026, 7, 1), None, "operation"),), declared=decl))
    assert b.tier == 2 and b.cycles[0].exported_c_tC_ha > 0


def test_main_crop_end_without_harvest_record_is_missing():
    b = compute_campaign_balance(_inp(harvests=()))
    assert b.tier == 1 and "harvest_export" in _items(b)


def test_cover_crop_without_harvest_returns_everything():
    b = compute_campaign_balance(_inp(cycles=(_cycle(date(2026, 1, 1), date(2026, 4, 30), role="cover_crop"),),
                                      harvests=()))
    assert b.tier == 2 and b.cycles[0].exported_c_tC_ha == 0.0


def test_baling_needs_declared_removal_fraction():
    b = compute_campaign_balance(_inp(balings=(BalingEvent(date(2026, 7, 3)),)))
    assert b.tier == 1 and "residue_removal" in _items(b)
    decl = replace(NO_DECLARED_MANAGEMENT, residue_removal_fraction=0.5)
    b2 = compute_campaign_balance(_inp(balings=(BalingEvent(date(2026, 7, 3)),), declared=decl))
    plain = compute_campaign_balance(_inp())
    assert b2.tier == 2 and b2.cycles[0].c_to_soil_tC_ha < plain.cycles[0].c_to_soil_tC_ha


def test_missing_ndvi_gives_partial_tier1_and_no_tier2():
    b = compute_campaign_balance(_inp(ndvi=((date(2026, 5, 1), 0.6), (date(2026, 5, 31), 0.6))))
    assert 0 < b.tier1_coverage < 1 and b.tier == 1 and b.delta_soc_tC_ha is None and "ndvi" in _items(b)


def test_cycle_without_params_is_not_computed():
    b = compute_campaign_balance(_inp(cycles=(_cycle(date(2026, 1, 1), date(2026, 6, 30), params=None),)))
    assert b.tier1_coverage == 0.0 and b.tier == 0 and b.gpp_tC_ha is None


def test_no_cycle_means_no_production_and_bare_soil():
    b = compute_campaign_balance(_inp(cycles=(), harvests=()))
    assert b.gpp_tC_ha == 0.0 and b.cover_days == 0 and "cycles" in _items(b)
    assert b.tier == 2 and all(m.plant_c_tC_ha == 0.0 for m in b.months)


def test_perennial_blocks_tier2():
    b = compute_campaign_balance(_inp(cycles=(_cycle(date(2026, 1, 1), None, lifecycle="perennial"),), harvests=()))
    assert b.tier == 1 and "perennial_litter" in _items(b)


def test_no_soil_no_tier2():
    b = compute_campaign_balance(_inp(soil=None, missing_in=(Missing("soil", "none", "tier2_unavailable"),)))
    assert b.tier == 1 and b.soc_end_tC_ha is None and "soil" in _items(b)


def test_cycle_crossing_years_closes_with_its_whole_biomass():
    weather = _weather(date(2025, 10, 1), date(2026, 10, 9))
    ndvi = _ndvi(date(2025, 10, 1), date(2026, 12, 31))
    crossing = compute_campaign_balance(_inp(weather=weather, ndvi=ndvi,
                                             cycles=(_cycle(date(2025, 10, 1), date(2026, 6, 30)),)))
    in_year = compute_campaign_balance(_inp(weather=weather, ndvi=ndvi))
    # same days in the campaign, so same GPP reported for 2026...
    assert crossing.gpp_tC_ha == pytest.approx(in_year.gpp_tC_ha)
    # ...but the closure returns the biomass grown since October 2025 too
    assert crossing.cycles[0].c_to_soil_tC_ha > in_year.cycles[0].c_to_soil_tC_ha


def test_crossing_cycle_without_previous_year_data_blocks_tier2():
    b = compute_campaign_balance(_inp(cycles=(_cycle(date(2025, 10, 1), date(2026, 6, 30)),)))
    assert b.tier == 1 and "cycle_biomass" in _items(b)


def test_overlapping_cycles_do_not_double_count_production():
    one = compute_campaign_balance(_inp())
    two = compute_campaign_balance(_inp(cycles=(_cycle(date(2026, 1, 1), date(2026, 6, 30)),
                                                _cycle(date(2026, 3, 1), date(2026, 4, 30), role="cover_crop",
                                                       crop_id="c2"))))
    assert two.gpp_tC_ha == pytest.approx(one.gpp_tC_ha)


def test_tier3_needs_real_nitrogen():
    b = compute_campaign_balance(_inp())
    assert b.tier == 2 and b.n2o_tCO2eq_ha is None and "fertilizer_n" in _items(b)
    fert = (FertilizationEvent(date(2026, 3, 1), 54.0, False, "operation"),)
    b3 = compute_campaign_balance(_inp(fertilizations=fert))
    assert b3.tier == 3 and b3.n2o_tCO2eq_ha > 0
    exported = sum(c.exported_c_tC_ha or 0.0 for c in b3.cycles)
    assert b3.necb_tC_ha == pytest.approx(b3.npp_tC_ha - b3.rh_tC_ha - exported)
    # exported harvest is not sequestration: the net balance uses NECB, not NEE
    assert b3.co2eq_net_tCO2eq_ha == pytest.approx(-b3.necb_tC_ha * 44 / 12 + b3.n2o_tCO2eq_ha)


def test_organic_fertilization_needs_declared_carbon():
    fert = (FertilizationEvent(date(2026, 3, 1), 20.0, True, "operation"),)
    b = compute_campaign_balance(_inp(fertilizations=fert))
    assert b.tier == 1 and "organic_c" in _items(b)
    decl = replace(NO_DECLARED_MANAGEMENT, organic_amendments_tC_ha_yr=1.2)
    b2 = compute_campaign_balance(_inp(fertilizations=fert, declared=decl))
    assert b2.tier == 3 and b2.months[2].fym_c_tC_ha == pytest.approx(1.2)


def test_previous_state_is_used_as_start():
    first = compute_campaign_balance(_inp())
    chained = compute_campaign_balance(_inp(initial_state=first.end_state, initial_state_source="previous_campaign"))
    assert chained.soc_start_tC_ha == pytest.approx(first.soc_end_tC_ha)
    assert chained.initial_state_source == "previous_campaign"


def test_deterministic():
    assert compute_campaign_balance(_inp()) == compute_campaign_balance(_inp())


def test_green_ndvi_on_bare_days_is_flagged():
    b = compute_campaign_balance(_inp(cycles=(), harvests=()))  # NDVI 0.6 all year, no cycle
    flags = [m for m in b.missing if m.item == "cover_mismatch"]
    assert flags and flags[0].effect == "cover_uncertain"
    assert b.tier == 2  # a warning, not a block (spec D2)


def test_low_ndvi_on_bare_days_is_not_flagged():
    b = compute_campaign_balance(_inp(cycles=(), harvests=(), ndvi=_ndvi(date(2026, 1, 1), date(2026, 12, 31), 0.15)))
    assert "cover_mismatch" not in _items(b)
