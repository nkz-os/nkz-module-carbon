"""One-off backfill: ask vegetation for continuous monitoring of every parcel with a carbon campaign.

  python -m app.jobs.request_continuous_monitoring [--tenant T ...] [--apply]

Without --apply it only prints ``tenant  parcel`` and calls nothing.
"""

import argparse
import asyncio
import logging
import sys

from app.common.orion import get_orion_client
from app.db.database import close_pool, list_tenants_with_module
from app.platform.vegetation_client import request_continuous

logger = logging.getLogger(__name__)

_PAGE = 100
# The relationship arrives short, legacy, or as a full IRI depending on the broker's context.
_PARCEL_KEYS = (
    "hasAgriParcel",
    "refAgriParcel",
    "https://nkz-os.org/ns/hasAgriParcel",
    "https://uri.etsi.org/ngsi-ld/default-context/hasAgriParcel",
)


async def list_carbon_parcels(tenant_id: str) -> list[str]:
    """Distinct AgriParcel URNs that have a stored CarbonAssessment."""
    parcels: set[str] = set()
    offset = 0
    while True:
        page = await get_orion_client().query_entities(
            entity_type="CarbonAssessment", tenant_id=tenant_id, limit=_PAGE, offset=offset)
        for entity in page or []:
            rel = next((entity[k] for k in _PARCEL_KEYS if k in entity), None)
            target = rel.get("object", rel.get("value")) if isinstance(rel, dict) else rel
            if target:
                parcels.add(str(target))
        if not page or len(page) < _PAGE:
            return sorted(parcels)
        offset += _PAGE


async def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", action="append", default=None, help="limit to this tenant (repeatable)")
    parser.add_argument("--apply", action="store_true", help="call vegetation; without it only list")
    args = parser.parse_args(argv)
    tenants = args.tenant or await list_tenants_with_module("carbon")
    failed = 0
    for tenant in tenants:
        try:
            parcels = await list_carbon_parcels(tenant)
        except Exception as exc:  # noqa: BLE001 — report and go on with the next tenant
            logger.warning("carbon parcels unavailable tenant=%s: %s", tenant, exc)
            failed += 1
            continue
        for parcel in parcels:
            if not args.apply:
                print(f"{tenant}  {parcel}")
                continue
            ok = await request_continuous(tenant, parcel)
            failed += 0 if ok else 1
            print(f"{tenant}  {parcel}  {'ok' if ok else 'failed'}")
    return 1 if failed else 0


async def _main() -> int:
    try:
        return await run()
    finally:
        await close_pool()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(asyncio.run(_main()))
