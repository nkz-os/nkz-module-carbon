"""Tests for MRV reporter."""

import json
from app.services.mrv_reporter import (
    generate_vm0042_report,
    generate_gold_standard_report,
    report_to_dict,
    report_to_json,
    MRVReport,
    ENGINE_VERSION,
)


class TestVM0042Report:
    def test_generates_report_with_all_fields(self):
        report = generate_vm0042_report(
            project_name="Test Olive Carbon Project",
            parcel_id="parcela-42",
            tenant_id="testtenant",
            reporting_period_start="2025-01-01",
            reporting_period_end="2025-12-31",
            baseline_scenario_id="urn:ngsi-ld:BaselineScenario:testtenant:parcela-42",
            project_scenario_id="urn:ngsi-ld:ProjectScenario:testtenant:parcela-42",
            baseline_calculation_run_id="urn:ngsi-ld:CarbonCalculationRun:testtenant:abc123",
            project_calculation_run_id="urn:ngsi-ld:CarbonCalculationRun:testtenant:def456",
            baseline_nee_tCO2_ha_yr=0.5,
            project_nee_tCO2_ha_yr=-2.0,
            tier=2,
            confidence=0.78,
            confidence_interval_pct=22.5,
            data_sources=["vegetation-prime", "bioorchestrator"],
            baseline_management={"tillage": "conventional"},
            project_management={"tillage": "no_till", "cover_crop": True},
            input_snapshot={"ndvi": 0.72},
            output_snapshot={"gpp_gC_m2_day": 11.5},
        )
        assert report.standard == "VM0042"
        assert report.tier == 2
        assert report.confidence == 0.78

    def test_net_reductions_calculation(self):
        """Net reductions = baseline - project. If baseline emits 0.5 and project sequesters -2.0, net = 2.5."""
        report = generate_vm0042_report(
            project_name="Test",
            parcel_id="p1",
            tenant_id="t1",
            reporting_period_start="2025-01-01",
            reporting_period_end="2025-12-31",
            baseline_scenario_id="urn:b",
            project_scenario_id="urn:p",
            baseline_calculation_run_id="urn:cr1",
            project_calculation_run_id="urn:cr2",
            baseline_nee_tCO2_ha_yr=0.5,
            project_nee_tCO2_ha_yr=-2.0,
            tier=1,
            confidence=0.6,
            confidence_interval_pct=40.0,
            data_sources=[],
            baseline_management={},
            project_management={},
            input_snapshot={},
            output_snapshot={},
        )
        assert report.net_emission_reductions_tCO2eq_ha_yr == 2.5

    def test_buffer_pool_applied(self):
        """Verified credits = net_reductions * (1 - buffer). 2.5 * 0.80 = 2.0."""
        report = generate_vm0042_report(
            project_name="Test",
            parcel_id="p1", tenant_id="t1",
            reporting_period_start="2025-01-01", reporting_period_end="2025-12-31",
            baseline_scenario_id="urn:b", project_scenario_id="urn:p",
            baseline_calculation_run_id="urn:cr1", project_calculation_run_id="urn:cr2",
            baseline_nee_tCO2_ha_yr=0.5, project_nee_tCO2_ha_yr=-2.0,
            tier=1, confidence=0.6, confidence_interval_pct=40.0,
            data_sources=[], baseline_management={}, project_management={},
            input_snapshot={}, output_snapshot={},
        )
        assert report.verified_credits_tCO2eq_ha_yr == 2.0

    def test_inputs_hash_is_stable(self):
        """Same inputs must produce same hash (deterministic)."""
        common = dict(
            project_name="Test", parcel_id="p1", tenant_id="t1",
            reporting_period_start="2025-01-01", reporting_period_end="2025-12-31",
            baseline_scenario_id="urn:b", project_scenario_id="urn:p",
            baseline_calculation_run_id="urn:cr1", project_calculation_run_id="urn:cr2",
            baseline_nee_tCO2_ha_yr=0.5, project_nee_tCO2_ha_yr=-2.0,
            tier=1, confidence=0.6, confidence_interval_pct=40.0,
            data_sources=[], baseline_management={"tillage": "conv"},
            project_management={"tillage": "no_till"},
            input_snapshot={"ndvi": 0.7}, output_snapshot={},
        )
        r1 = generate_vm0042_report(**common)
        r2 = generate_vm0042_report(**common)
        assert r1.inputs_hash == r2.inputs_hash

    def test_inputs_hash_changes_with_different_inputs(self):
        """Different inputs must produce different hash."""
        def make_report(mgmt):
            return generate_vm0042_report(
                project_name="Test", parcel_id="p1", tenant_id="t1",
                reporting_period_start="2025-01-01", reporting_period_end="2025-12-31",
                baseline_scenario_id="urn:b", project_scenario_id="urn:p",
                baseline_calculation_run_id="urn:cr1", project_calculation_run_id="urn:cr2",
                baseline_nee_tCO2_ha_yr=0.5, project_nee_tCO2_ha_yr=-2.0,
                tier=1, confidence=0.6, confidence_interval_pct=40.0,
                data_sources=[], baseline_management=mgmt, project_management={},
                input_snapshot={}, output_snapshot={},
            )
        r1 = make_report({"tillage": "conventional"})
        r2 = make_report({"tillage": "no_till"})
        assert r1.inputs_hash != r2.inputs_hash


class TestGoldStandard:
    def test_generates_gs_report(self):
        report = generate_gold_standard_report(
            project_name="Test GS Project",
            parcel_id="p1", tenant_id="t1",
            reporting_period_start="2025-01-01", reporting_period_end="2025-12-31",
            baseline_scenario_id="urn:b", project_scenario_id="urn:p",
            baseline_calculation_run_id="urn:cr1", project_calculation_run_id="urn:cr2",
            baseline_nee_tCO2_ha_yr=0.5, project_nee_tCO2_ha_yr=-2.0,
            tier=2, confidence=0.78, confidence_interval_pct=22.5,
            data_sources=[], baseline_management={}, project_management={},
            input_snapshot={}, output_snapshot={},
        )
        assert report.standard == "GOLD_STANDARD_SOC"
        assert "GS-SOC" in report.report_id


class TestSerialization:
    def test_report_to_dict(self):
        report = generate_vm0042_report(
            project_name="Test", parcel_id="p1", tenant_id="t1",
            reporting_period_start="2025-01-01", reporting_period_end="2025-12-31",
            baseline_scenario_id="urn:b", project_scenario_id="urn:p",
            baseline_calculation_run_id="urn:cr1", project_calculation_run_id="urn:cr2",
            baseline_nee_tCO2_ha_yr=0.5, project_nee_tCO2_ha_yr=-2.0,
            tier=1, confidence=0.6, confidence_interval_pct=40.0,
            data_sources=[], baseline_management={}, project_management={},
            input_snapshot={}, output_snapshot={},
        )
        d = report_to_dict(report)
        assert d["standard"] == "VM0042"
        assert d["tier"] == 1

    def test_report_to_json(self):
        report = generate_vm0042_report(
            project_name="Test", parcel_id="p1", tenant_id="t1",
            reporting_period_start="2025-01-01", reporting_period_end="2025-12-31",
            baseline_scenario_id="urn:b", project_scenario_id="urn:p",
            baseline_calculation_run_id="urn:cr1", project_calculation_run_id="urn:cr2",
            baseline_nee_tCO2_ha_yr=0.5, project_nee_tCO2_ha_yr=-2.0,
            tier=1, confidence=0.6, confidence_interval_pct=40.0,
            data_sources=[], baseline_management={}, project_management={},
            input_snapshot={}, output_snapshot={},
        )
        json_str = report_to_json(report)
        parsed = json.loads(json_str)
        assert parsed["standard"] == "VM0042"
