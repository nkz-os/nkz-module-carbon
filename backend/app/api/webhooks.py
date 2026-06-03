"""Webhook endpoints for NGSI-LD subscription notifications.

Mount at /api/carbon (handled by main.py include_router).

Endpoints:
  POST /webhooks/vegetation-index-updated
      Receives NGSI-LD notification from vegetation-prime when a new
      VegetationIndex entity is published. Triggers recalculation as
      a background task.
"""

import logging
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.models.schemas import ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/carbon", tags=["webhooks"])

WEBHOOK_API_KEY = os.getenv("CARBON_WEBHOOK_API_KEY", "")


def _verify_webhook_auth(request: Request):
    """Verify webhook call via shared API key."""
    if not WEBHOOK_API_KEY:
        logger.warning("CARBON_WEBHOOK_API_KEY not set — accepting all webhook calls")
        return
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = auth_header.split(" ", 1)[1]
    if token != WEBHOOK_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")


async def _recalculate_from_vi(entity_id: str, vi_value: float, tenant_id: str):
    """Background recalculation triggered by vegetation index update.

    Phase 6: wires into the full calculate pipeline. For now logs the event.
    """
    logger.info(
        "VI update received — would recalc entity=%s vi=%.4f tenant=%s",
        entity_id, vi_value, tenant_id,
    )


@router.post(
    "/webhooks/vegetation-index-updated",
    status_code=202,
    responses={400: {"model": ErrorResponse}},
)
async def vegetation_index_updated(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Receive NGSI-LD notification when vegetation-prime publishes a new index.

    Expected payload follows the NGSI-LD notification JSON format:
    {
      "id": "...",
      "type": "Notification",
      "data": [
        {
          "id": "urn:ngsi-ld:VegetationIndex:...",
          "type": "VegetationIndex",
          "refAgriParcel": {"type": "Relationship", "object": "urn:ngsi-ld:AgriParcel:..."},
          "indexValue": {"type": "Property", "value": 0.75}
        }
      ],
      "subscriptionId": "...",
      "notifiedAt": "..."
    }
    """
    _verify_webhook_auth(request)
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}")

    # Extract tenant from NGSILD-Tenant header
    tenant_id = request.headers.get("NGSILD-Tenant", "")

    # NGSI-LD subscription notifications carry the data array
    data = payload.get("data", [])
    if not data:
        logger.warning("VI webhook received empty data array")
        return {"status": "accepted", "processed": 0}

    processed = 0
    for entity_data in data:
        try:
            entity_id = entity_data.get("id", "")
            index_value = _extract_vi_value(entity_data)
            agri_parcel = _extract_ref_parcel(entity_data)

            if not entity_id or index_value is None:
                logger.warning("Skipping VI entity with missing fields: %s", entity_id)
                continue

            parcel_id = agri_parcel or entity_id

            # Schedule background recalculation
            background_tasks.add_task(
                _recalculate_from_vi,
                entity_id=parcel_id,
                vi_value=index_value,
                tenant_id=tenant_id,
            )
            processed += 1

        except Exception as exc:
            logger.error("Error processing VI notification entity: %s", exc)
            continue

    logger.info("VI webhook processed %d/%d entities", processed, len(data))

    return {"status": "accepted", "processed": processed}


def _extract_vi_value(entity_data: dict) -> float | None:
    """Extract the vegetation index value from an NGSI-LD entity."""
    raw = entity_data.get("indexValue", {})
    if isinstance(raw, dict):
        val = raw.get("value")
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
    # Fallback: direct numeric value
    if isinstance(raw, (int, float)):
        return float(raw)
    return None


def _extract_ref_parcel(entity_data: dict) -> str | None:
    """Extract the referenced AgriParcel entity ID from an NGSI-LD entity."""
    ref = entity_data.get("refAgriParcel", {})
    if isinstance(ref, dict):
        return ref.get("object") or ref.get("value")
    if isinstance(ref, str):
        return ref
    return None
