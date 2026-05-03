import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    internal_router,
    assessments_router,
    management_router,
    scenarios_router,
    timeseries_router,
    webhooks_router,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Carbon module starting")
    yield
    logger.info("Carbon module shutting down")


app = FastAPI(
    title="NKZ Module Carbon",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://nekazari.robotika.cloud"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "NGSILD-Tenant"],
)

# Internal / health
app.include_router(internal_router)

# Core carbon endpoints
app.include_router(assessments_router)
app.include_router(management_router)
app.include_router(scenarios_router)
app.include_router(timeseries_router)
app.include_router(webhooks_router)
