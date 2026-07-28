"""AppForge AI FastAPI application."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from appforge.config import get_settings
from appforge.db import init_db
from appforge.routers import apps, pipeline, projects
from appforge.routers.deps import require_operator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s")
logger = logging.getLogger("appforge.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db()
    try:
        Path(settings.storage_root).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("Could not create artifact storage %s: %s",
                     settings.storage_root, exc)
    logger.info("AppForge API ready (offline_mode=%s)", settings.offline_mode)
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="AppForge AI",
        version="1.0.0",
        description=(
            "Autonomous platform that discovers viral Google Play apps, mines their "
            "weaknesses, and builds improved clones through eight coordinated AI agents."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_prefix = "/api"
    app.include_router(apps.router, prefix=api_prefix)
    app.include_router(projects.router, prefix=api_prefix)
    app.include_router(pipeline.router, prefix=api_prefix)

    @app.get("/api/health", tags=["system"])
    def health():
        return {
            "status": "ok",
            "service": "appforge-api",
            "version": "1.0.0",
            "offline_mode": settings.offline_mode,
            "environment": settings.environment,
        }

    @app.post("/api/seed", tags=["system"], dependencies=[Depends(require_operator)])
    def seed_endpoint(run_pipeline: bool = True):
        """Seed niches and (optionally) run a full demo pipeline."""
        from appforge.seed import seed

        return seed(run_pipeline=run_pipeline)

    # Serve generated artifacts (logos, screenshots, generated repos).
    # A non-writable storage root must not prevent the API from starting:
    # health and read endpoints stay useful, and the failure is logged loudly.
    storage = Path(settings.storage_root)
    try:
        storage.mkdir(parents=True, exist_ok=True)
        app.mount("/artifacts", StaticFiles(directory=str(storage)), name="artifacts")
    except OSError as exc:
        logger.error(
            "Artifact storage %s is not writable (%s). Generated assets will not be "
            "served; check the volume mount and its ownership.",
            storage, exc,
        )

    return app


app = create_app()
