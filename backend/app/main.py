"""Tunora backend FastAPI app assembly.

Wires the concrete JobRepository and MusicGenerationProvider implementations
at startup (the composition root) — nothing below this module should know
which repository or provider is actually in use.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes_director import router as director_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_projects import router as projects_router
from app.api.routes_songs import router as songs_router
from app.director.ace_step import AceStepSongDirector
from app.jobs.repository import SqliteJobRepository
from app.jobs.service import JobService
from app.providers.ace_step import AceStepMusicGenerationProvider
from app.storage.local import LocalAudioStorage

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("TUNORA_DB_PATH", "tunora.db")
ACE_STEP_BASE_URL = os.environ.get("ACE_STEP_BASE_URL", "http://127.0.0.1:8001")
STORAGE_ROOT = os.environ.get("TUNORA_STORAGE_ROOT", "./data/audio")


async def _recover_jobs(service: JobService) -> None:
    """Run startup recovery; a failure here is logged and never stops the API or its shutdown."""

    try:
        await service.recover_unfinished_jobs()
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("job recovery failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    provider = AceStepMusicGenerationProvider(base_url=ACE_STEP_BASE_URL)
    repository = SqliteJobRepository(DB_PATH)
    storage = LocalAudioStorage(STORAGE_ROOT)
    app.state.job_service = JobService(repository=repository, provider=provider, storage=storage)
    # Resume jobs a previous process left in flight (Phase 16). Runs in the background so the API is
    # available immediately; it is cancelled on shutdown so no polling task is left behind.
    recovery = asyncio.create_task(_recover_jobs(app.state.job_service), name="job-recovery")
    app.state.provider = provider
    director = AceStepSongDirector(base_url=ACE_STEP_BASE_URL)
    app.state.song_director = director
    try:
        yield
    finally:
        recovery.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await recovery
        await provider.aclose()
        await director.aclose()


def _configure_app_logging() -> None:
    """Make Tunora's own log lines (job creation, restart recovery) visible under uvicorn, which
    only configures its own loggers. Idempotent; leaves other loggers alone."""

    app_logger = logging.getLogger("app")
    if app_logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)


def create_app() -> FastAPI:
    _configure_app_logging()
    app = FastAPI(title="Tunora Backend", lifespan=lifespan)
    app.include_router(jobs_router)
    # director_router owns the static "/api/songs/plan" path and must be registered
    # before songs_router's "/api/songs/{song_id}" -- otherwise the dynamic route can
    # shadow it (song_id="plan") and a POST there 405s instead of reaching the planner.
    app.include_router(director_router)
    app.include_router(songs_router)
    app.include_router(projects_router)
    return app


app = create_app()
