import pytest

from app.platform.bioorchestrator_client import PhenologyParams
from app.services import crop_params as cp


async def _none(*a, **k):
    return None


@pytest.mark.asyncio
async def test_table_params_when_bioorch_has_none(monkeypatch):
    monkeypatch.setattr(cp, "fetch_phenology_params", _none)
    params, missing = await cp.resolve_crop_params("TRZAX", 42.0, -1.6)
    assert (params.lue_gC_MJ, params.fapar_a, params.vi_type, params.root_fraction, params.source) == \
        (1.1, 1.24, "NDVI", 0.22, "table")
    assert missing == []


@pytest.mark.asyncio
async def test_bioorch_complete_params_win(monkeypatch):
    async def bio(*a, **k):
        return PhenologyParams(species="TRZAX", lue_gC_per_MJ=1.3, fapar_a=1.1, fapar_b=-0.1,
                               fapar_vi_type="NDVI", root_fraction=0.25)
    monkeypatch.setattr(cp, "fetch_phenology_params", bio)
    params, _ = await cp.resolve_crop_params("TRZAX", None, None)
    assert params.lue_gC_MJ == 1.3 and params.root_fraction == 0.25 and params.source == "bioorchestrator"


@pytest.mark.asyncio
async def test_bioorch_partial_params_fall_back_to_table(monkeypatch):
    async def bio(*a, **k):
        return PhenologyParams(species="TRZAX", lue_gC_per_MJ=1.3, fapar_a=None, fapar_b=None, root_fraction=None)
    monkeypatch.setattr(cp, "fetch_phenology_params", bio)
    params, _ = await cp.resolve_crop_params("TRZAX", None, None)
    assert params.source == "table" and params.lue_gC_MJ == 1.1


@pytest.mark.asyncio
async def test_woody_needs_osavi(monkeypatch):
    monkeypatch.setattr(cp, "fetch_phenology_params", _none)
    params, missing = await cp.resolve_crop_params("OLVEU", 42.0, -1.6)
    assert params is None and [m.item for m in missing] == ["vi_type"]


@pytest.mark.asyncio
async def test_unknown_species_is_missing(monkeypatch):
    monkeypatch.setattr(cp, "fetch_phenology_params", _none)
    params, missing = await cp.resolve_crop_params("XXXXX", None, None)
    assert params is None and [m.item for m in missing] == ["crop_params"]


def test_phenology_parser_does_not_invent_root_fraction():
    assert PhenologyParams(species="x").root_fraction is None
