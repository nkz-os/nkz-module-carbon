"""Vegetation index series of a parcel from the broker's EOProduct entities.

One EOProduct per optical acquisition carries one property per index (``ndvi``,
``osavi``, ...) and its ``sensingDate`` (the same source crop-health reads). SAR
products share the type without optical indices and are skipped.
"""

import logging
from datetime import date, timedelta
from typing import Any

from app.common.orion import get_orion_client
from app.platform.errors import SourceUnavailable

logger = logging.getLogger(__name__)

_PAGE = 500
# Scenes just outside the period still bracket its first and last days.
_EDGE_DAYS = 60


def _value(attr: Any) -> Any:
    if isinstance(attr, dict):
        return attr.get("value", attr.get("@value"))
    return attr


# Indices read per acquisition: EOProduct attribute -> index name.
_INDEX_ATTRS = {"ndvi": "NDVI", "osavi": "OSAVI"}


async def fetch_vi_series(
    parcel_urn: str,
    tenant_id: str,
    start: date,
    end: date,
) -> dict[str, list[tuple[date, float]]]:
    """NDVI and OSAVI series of the parcel (one broker pass), keyed by index name."""
    lo, hi = start - timedelta(days=_EDGE_DAYS), end + timedelta(days=_EDGE_DAYS)
    orion = get_orion_client()
    entities: list[dict] = []
    offset = 0
    try:
        while True:
            page = await orion.query_entities(
                entity_type="EOProduct",
                tenant_id=tenant_id,
                query=f'hasAgriParcel=="{parcel_urn}"',
                limit=_PAGE,
                offset=offset,
            )
            entities.extend(page or [])
            if not page or len(page) < _PAGE:
                break
            offset += _PAGE
    except Exception as exc:  # noqa: BLE001 — any broker failure means unknown, not empty
        logger.warning("EOProduct query failed tenant=%s parcel=%s: %s", tenant_id, parcel_urn, exc)
        raise SourceUnavailable(f"EOProduct query failed: {exc}") from exc

    out: dict[str, list[tuple[date, float]]] = {name: [] for name in _INDEX_ATTRS.values()}
    for e in entities:
        sensed = _value(e.get("sensingDate"))
        try:
            d = date.fromisoformat(str(sensed)[:10]) if sensed is not None else None
        except ValueError:
            d = None
        if d is None or not lo <= d <= hi:
            continue
        for attr, name in _INDEX_ATTRS.items():
            raw = _value(e.get(attr))
            if raw is None:
                continue
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue
            if -1.0 <= v <= 1.0:
                out[name].append((d, v))
    for series in out.values():
        series.sort()
    return out
