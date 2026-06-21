"""Tests for Orion crop assignment reader."""

import pytest
from unittest.mock import AsyncMock, patch

from app.platform.crop_client import (
    AssignedCrop,
    carbon_species_key,
    fetch_assigned_crop,
    fetch_parcel_coordinates,
    normalize_parcel_short_id,
    parcel_urn,
    phenology_species_param,
)


def test_normalize_parcel_short_id():
    assert normalize_parcel_short_id("mont_2") == "mont_2"
    assert normalize_parcel_short_id("urn:ngsi-ld:AgriParcel:t:mont_2") == "mont_2"


def test_carbon_species_key_eppo_and_common():
    assert carbon_species_key("TRZAX") == "wheat"
    assert carbon_species_key("olive") == "olive"


def test_phenology_species_param():
    assert phenology_species_param("TRZAX") == "TRZAX"
    assert phenology_species_param("wheat") == "wheat"


@pytest.mark.asyncio
async def test_fetch_assigned_crop_from_has_agri_crop():
    parcel = {
        "id": "urn:ngsi-ld:AgriParcel:tenant1:parcel-a",
        "type": "AgriParcel",
        "hasAgriCrop": {
            "type": "Relationship",
            "object": "urn:ngsi-ld:AgriCrop:tenant1:parcel-a:2026",
        },
    }
    crop = {
        "id": "urn:ngsi-ld:AgriCrop:tenant1:parcel-a:2026",
        "type": "AgriCrop",
        "species": {"type": "Property", "value": "TRZAX"},
        "plantingDate": {
            "type": "Property",
            "value": {"@type": "Date", "@value": "2026-03-01"},
        },
        "status": {"type": "Property", "value": "active"},
    }

    mock_orion = AsyncMock()
    mock_orion.get_entity = AsyncMock(side_effect=[parcel, crop])

    with patch("app.platform.crop_client.get_orion_client", return_value=mock_orion):
        result = await fetch_assigned_crop("parcel-a", "tenant1")

    assert result == AssignedCrop(
        species_raw="TRZAX",
        species_key="wheat",
        planting_date="2026-03-01",
        variety=None,
        crop_entity_id="urn:ngsi-ld:AgriCrop:tenant1:parcel-a:2026",
        status="active",
    )


@pytest.mark.asyncio
async def test_fetch_assigned_crop_missing_returns_none():
    mock_orion = AsyncMock()
    mock_orion.get_entity = AsyncMock(return_value=None)
    mock_orion.query_entities = AsyncMock(return_value=[])

    with patch("app.platform.crop_client.get_orion_client", return_value=mock_orion):
        result = await fetch_assigned_crop("parcel-a", "tenant1")

    assert result is None


@pytest.mark.asyncio
async def test_fetch_parcel_coordinates_point():
    parcel = {
        "id": parcel_urn("tenant1", "p1"),
        "location": {
            "type": "GeoProperty",
            "value": {"type": "Point", "coordinates": [-2.0, 42.5]},
        },
    }
    mock_orion = AsyncMock()
    mock_orion.get_entity = AsyncMock(return_value=parcel)

    with patch("app.platform.crop_client.get_orion_client", return_value=mock_orion):
        coords = await fetch_parcel_coordinates("p1", "tenant1")

    assert coords == (42.5, -2.0)
