"""API routers for carbon module."""
from app.api.internal import router as internal_router
from app.api.assessments import router as assessments_router
from app.api.management import router as management_router
from app.api.mrv import router as mrv_router
from app.api.scenarios import router as scenarios_router
from app.api.timeseries import router as timeseries_router
from app.api.webhooks import router as webhooks_router

__all__ = [
    "internal_router",
    "assessments_router",
    "management_router",
    "mrv_router",
    "scenarios_router",
    "timeseries_router",
    "webhooks_router",
]
