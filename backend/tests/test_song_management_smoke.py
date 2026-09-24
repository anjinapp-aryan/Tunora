"""Phase 9 real integration test: a real ACE-Step generation, then Song deletion.

POST /api/jobs -> real generation -> COMPLETED -> real audio file on disk ->
DELETE /api/songs/{song_id} -> verifies the DB rows are gone AND the real audio
file is physically gone from the filesystem. Skipped unless the ACE-Step API
server is reachable.
"""

from __future__ import annotations

import os
import sqlite3

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router as jobs_router
from app.api.routes_songs import router as songs_router
from app.jobs.repository import SqliteJobRepository
from app.jobs.service import JobService
from app.providers.ace_step import AceStepMusicGenerationProvider
from app.storage.local import LocalAudioStorage

BASE_URL = os.environ.get("ACE_STEP_BASE_URL", "http://127.0.0.1:8001")

pytestmark = pytest.mark.smoke


def _server_reachable() -> bool:
    try:
        return httpx.get(f"{BASE_URL}/health", timeout=3.0).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.mark.skipif(not _server_reachable(), reason=f"ACE-Step API server not reachable at {BASE_URL}")
def test_deleting_a_song_with_a_real_generation_removes_its_real_audio_file(tmp_path):
    db = tmp_path / "tunora.db"
    storage = LocalAudioStorage(tmp_path / "audio")
    repository = SqliteJobRepository(db)
    service = JobService(
        repository=repository,
        provider=AceStepMusicGenerationProvider(base_url=BASE_URL, request_timeout=60.0),
        storage=storage,
        poll_interval_seconds=2.0,
    )
    app = FastAPI()
    app.include_router(jobs_router)
    app.include_router(songs_router)
    app.state.job_service = service

    with TestClient(app) as client:
        r = client.post(
            "/api/jobs",
            json={"prompt": "short upbeat instrumental synth loop", "instrumental": True, "duration": 10.0, "seed": 91},
        )
        assert r.status_code == 200
        job = client.get(f"/api/jobs/{r.json()['id']}").json()
        assert job["status"] == "COMPLETED", job["status"]
        song_id = job["song_id"]

        version = repository.get_version(job["version_id"])
        audio_path = storage.get_path(version.audio.key)
        assert audio_path.exists() and audio_path.stat().st_size > 0
        assert client.get(f"/api/jobs/{job['id']}/audio").status_code == 200

        # ---- delete the real Song ----
        d = client.delete(f"/api/songs/{song_id}")
        assert d.status_code == 204

        # ---- the real file is physically gone ----
        assert not audio_path.exists()
        assert not audio_path.parent.exists()

        # ---- the database rows are gone ----
        assert client.get(f"/api/songs/{song_id}").status_code == 404
        assert client.get(f"/api/jobs/{job['id']}").status_code == 404
        conn = sqlite3.connect(db)
        try:
            assert conn.execute("SELECT COUNT(*) FROM songs WHERE id = ?", (song_id,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM versions WHERE song_id = ?", (song_id,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM jobs WHERE id = ?", (job["id"],)).fetchone()[0] == 0
        finally:
            conn.close()
