"""Tunora backend FastAPI app assembly.

Wires the concrete JobRepository and MusicGenerationProvider implementations
at startup (the composition root) — nothing below this module should know
which repository or provider is actually in use.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes_jobs import router as jobs_router
from app.jobs.repository import SqliteJobRepository
from app.jobs.service import JobService
from app.providers.ace_step import AceStepMusicGenerationProvider
from app.storage.local import LocalAudioStorage

DB_PATH = os.environ.get("TUNORA_DB_PATH", "tunora.db")
ACE_STEP_BASE_URL = os.environ.get("ACE_STEP_BASE_URL", "http://127.0.0.1:8001")
STORAGE_ROOT = os.environ.get("TUNORA_STORAGE_ROOT", "./data/audio")


@asynccontextmanager
async def lifespan(app: FastAPI):
    provider = AceStepMusicGenerationProvider(base_url=ACE_STEP_BASE_URL)
    repository = SqliteJobRepository(DB_PATH)
    storage = LocalAudioStorage(STORAGE_ROOT)
    app.state.job_service = JobService(repository=repository, provider=provider, storage=storage)
    app.state.provider = provider
    try:
        yield
    finally:
        await provider.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="Tunora Backend", lifespan=lifespan)
    app.include_router(jobs_router)
    return app


app = create_app()
