"""NGSI-LD entity builders for CarbonAssessment and CarbonStock."""

from datetime import date, datetime, timezone

NGSI_LD_CONTEXT = [
    "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
]


def _context() -> list[str]:
    return list(NGSI_LD_CONTEXT)


def build_carbon_assessment(
    tenant_id: str,
    parcel_id: str,
    assessment_date: date,
    tier: int,
    methodology: str,
    confidence: float,
    confidence_interval_pct: float,
    gpp_daily: float,
    npp_daily: float,
    co2_sequestered_daily: float,
    co2_sequestered_cumulative: float,
    agb_dry: float,
    bgb_dry: float,
    soil_carbon_delta: float | None,
    carbon_stock_total: float | None,
    data_sources: list[str],
    missing_for_next_tier: list[str],
    co2eq_net_daily: float | None = None,
    co2eq_net_cumulative: float | None = None,
    gwp_standard: str = "AR6",
    vegetation_index_id: str | None = None,
) -> dict:
    """Build a CarbonAssessment NGSI-LD entity (spec 7.1)."""
    date_str = assessment_date.isoformat()
    entity_id = f"urn:ngsi-ld:CarbonAssessment:{tenant_id}:{parcel_id}-{date_str}"

    entity = {
        "id": entity_id,
        "type": "CarbonAssessment",
        "@context": _context(),
        "refAgriParcel": {
            "type": "Relationship",
            "object": f"urn:ngsi-ld:AgriParcel:{tenant_id}:{parcel_id}",
        },
        "assessmentDate": {
            "type": "Property",
            "value": date_str,
        },
        "gppDaily": {"type": "Property", "value": gpp_daily, "unitCode": "GCM"},
        "nppDaily": {"type": "Property", "value": npp_daily, "unitCode": "GCM"},
        "co2SequesteredDaily": {
            "type": "Property",
            "value": co2_sequestered_daily,
            "unitCode": "KGM",
        },
        "co2SequesteredCumulative": {
            "type": "Property",
            "value": co2_sequestered_cumulative,
            "unitCode": "TNE",
        },
        "agbDry": {"type": "Property", "value": agb_dry, "unitCode": "TNE"},
        "bgbDry": {"type": "Property", "value": bgb_dry, "unitCode": "TNE"},
        "dataTier": {"type": "Property", "value": tier},
        "confidence": {"type": "Property", "value": round(confidence, 3)},
        "confidenceIntervalPct": {
            "type": "Property",
            "value": round(confidence_interval_pct, 1),
        },
        "methodology": {"type": "Property", "value": methodology},
        "dataSources": {"type": "Property", "value": data_sources},
        "missingForNextTier": {"type": "Property", "value": missing_for_next_tier},
        "gwpStandard": {"type": "Property", "value": gwp_standard},
        "source": {"type": "Property", "value": "carbon"},
    }

    if vegetation_index_id:
        entity["refVegetationIndex"] = {
            "type": "Relationship",
            "object": vegetation_index_id,
        }

    if soil_carbon_delta is not None:
        entity["soilCarbonDelta"] = {
            "type": "Property",
            "value": soil_carbon_delta,
            "unitCode": "TNE",
        }

    if carbon_stock_total is not None:
        entity["carbonStockTotal"] = {
            "type": "Property",
            "value": carbon_stock_total,
            "unitCode": "TNE",
        }

    if co2eq_net_daily is not None:
        entity["co2eqNetDaily"] = {
            "type": "Property",
            "value": co2eq_net_daily,
            "unitCode": "KGM",
        }

    if co2eq_net_cumulative is not None:
        entity["co2eqNetCumulative"] = {
            "type": "Property",
            "value": co2eq_net_cumulative,
            "unitCode": "TNE",
        }

    return entity


def build_carbon_stock(
    tenant_id: str,
    parcel_id: str,
    pools: dict[str, float],  # {"DPM": 2.1, "RPM": 8.7, ...}
    total_soc: float,
) -> dict:
    """Build a CarbonStock NGSI-LD entity (spec 7.2)."""
    entity_id = f"urn:ngsi-ld:CarbonStock:{tenant_id}:{parcel_id}"

    return {
        "id": entity_id,
        "type": "CarbonStock",
        "@context": _context(),
        "refAgriParcel": {
            "type": "Relationship",
            "object": f"urn:ngsi-ld:AgriParcel:{tenant_id}:{parcel_id}",
        },
        "dpmPool": {"type": "Property", "value": pools.get("DPM", 0.0), "unitCode": "TNE"},
        "rpmPool": {"type": "Property", "value": pools.get("RPM", 0.0), "unitCode": "TNE"},
        "bioPool": {"type": "Property", "value": pools.get("BIO", 0.0), "unitCode": "TNE"},
        "humPool": {"type": "Property", "value": pools.get("HUM", 0.0), "unitCode": "TNE"},
        "iomPool": {"type": "Property", "value": pools.get("IOM", 0.0), "unitCode": "TNE"},
        "totalSOC": {"type": "Property", "value": total_soc, "unitCode": "TNE"},
        "lastUpdated": {
            "type": "Property",
            "value": datetime.now(timezone.utc).isoformat(),
        },
        "source": {"type": "Property", "value": "carbon"},
    }
