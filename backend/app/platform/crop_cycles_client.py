"""Crop cycles of a parcel: the platform rule (SDK ``crop_cycles``) over the broker.

The SDK reads the parcel, its crops and the operations that set cycle boundaries
and resolves the cycles here, so the module does not depend on a core service.
"""

import logging
from datetime import date

from nkz_platform_sdk.crop_cycles import resolve_crop_cycles
from nkz_platform_sdk.crop_timeline import CropDataUnavailable, ParcelNotFound, load_crop_data
from nkz_platform_sdk.orion import OrionClient

from app.platform.errors import SourceUnavailable

logger = logging.getLogger(__name__)


async def fetch_cycles(parcel_urn: str, tenant_id: str, at: date) -> list[dict]:
    """All cycles of the parcel at ``at`` (the timeline's ``cycles`` list).

    An unknown parcel has no cycles; a broker that cannot answer is
    ``SourceUnavailable`` (the campaign is then left incomplete, never invented).
    """
    client = OrionClient(tenant_id)
    try:
        parcel, crops, ops = await load_crop_data(client, parcel_urn)
    except ParcelNotFound:
        return []
    except CropDataUnavailable as exc:
        logger.warning("crop cycles unavailable tenant=%s parcel=%s: %s", tenant_id, parcel_urn, exc)
        raise SourceUnavailable(f"crop cycles unavailable: {exc}") from exc
    finally:
        await client.close()
    return list(resolve_crop_cycles(parcel_urn, crops, ops, at).to_dict()["cycles"])
