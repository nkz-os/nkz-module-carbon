import logging
from contextlib import asynccontextmanager

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.common.orion import init_orion_client, close_orion_client
from app.api import (
    internal_router,
    assessments_router,
    management_router,
    mrv_router,
    scenarios_router,
    timeseries_router,
    webhooks_router,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Carbon module starting")
    init_orion_client()
    yield
    await close_orion_client()
    logger.info("Carbon module shutting down")


app = FastAPI(
    title="NKZ Module Carbon",
    version="0.1.0",
    lifespan=lifespan,
)

cors_origin = os.getenv("CORS_ORIGIN", "https://nekazari.robotika.cloud")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[cors_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "NGSILD-Tenant",
                   "X-Tenant-ID", "X-User-ID", "X-User-Roles", "X-Request-ID"],
)

# Internal / health
app.include_router(internal_router)

# Core carbon endpoints
app.include_router(assessments_router)
app.include_router(management_router)
app.include_router(mrv_router)
app.include_router(scenarios_router)
app.include_router(timeseries_router)
app.include_router(webhooks_router)
