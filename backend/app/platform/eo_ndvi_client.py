"""NDVI series of a parcel from the broker's EOProduct entities.

One EOProduct per optical acquisition carries an ``ndvi`` property and its
``sensingDate`` (the same source crop-health reads). SAR products share the type
without ``ndvi`` and are skipped.
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


async def fetch_ndvi_series(
    parcel_urn: str,
    tenant_id: str,
    start: date,
    end: date,
) -> list[tuple[date, float]]:
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

    out: list[tuple[date, float]] = []
    for e in entities:
        raw, sensed = _value(e.get("ndvi")), _value(e.get("sensingDate"))
        if raw is None or sensed is None:
            continue
        try:
            v, d = float(raw), date.fromisoformat(str(sensed)[:10])
        except (TypeError, ValueError):
            continue
        if -1.0 <= v <= 1.0 and lo <= d <= hi:
            out.append((d, v))
    out.sort()
    return out
