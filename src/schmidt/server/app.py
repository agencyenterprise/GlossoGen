"""FastAPI application definition with CORS middleware and route registration."""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from schmidt.server.response_models import HealthResponse, HealthStatus
from schmidt.server.runs_router import router as runs_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Store the configured runs directory on app state at startup."""
    runs_dir_str = os.environ.get("SCHMIDT_RUNS_DIR")
    if not runs_dir_str:
        raise RuntimeError("SCHMIDT_RUNS_DIR environment variable is required")
    app.state.runs_dir = Path(runs_dir_str)
    logger.info("Serving runs from: %s", app.state.runs_dir)
    yield


app = FastAPI(title="Schmidt Simulation Server", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs_router)


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status=HealthStatus.OK)
