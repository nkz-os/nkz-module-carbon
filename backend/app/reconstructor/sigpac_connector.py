"""SIGPAC connector -- Spanish agricultural parcel registry (spec 11.2)."""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# SIGPAC crop code → NKZ crop name mapping
SIGPAC_CROP_MAP = {
    "OV": "olive",
    "TA": "cereal",
    "TH": "cereal",
    "VI": "vineyard",
    "FR": "fruit_tree",
    "FS": "fruit_tree",
    "IM": "fallow",
    "PR": "pasture",
    "PS": "pasture",
    "AR": "rice",
    "CI": "citrus",
    "AL": "almond",
    "AV": "wheat",
    "OL": "olive",
}


@dataclass
class SigpacRecord:
    """One year of SIGPAC data for a parcel."""
    year: int
    uso_sigpac: str
    superficie_ha: float
    pendiente_pct: float
    geometry_wkt: str


def sigpac_to_nkz_crop(uso_sigpac: str) -> str:
    """Convert SIGPAC land use code to NKZ crop name."""
    return SIGPAC_CROP_MAP.get(uso_sigpac.upper(), "fallow")


async def fetch_sigpac_history(
    parcela_id: str,
    provincia: str = "",
    municipio: str = "",
    years_back: int = 10,
) -> list[SigpacRecord]:
    """Fetch historical SIGPAC records. Returns empty list if unreachable."""
    logger.info("SIGPAC fetch for %s (not yet connected)", parcela_id)
    return []
