"""Phase 4 real integration test: two REAL ACE-Step generations of the SAME Song.

POST /api/jobs (new Song, Version 1) -> real generation -> COMPLETED, then
POST /api/jobs with that song_id (Version 2) -> real generation. Verifies the
domain rows in the SQLite file and that Version 1 is untouched by Version 2.
Skipped unless the ACE-Step API server is reachable.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router as jobs_router
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


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.skipif(not _server_reachable(), reason=f"ACE-Step API server not reachable at {BASE_URL}")
def test_real_generation_creates_song_version_1_then_version_2_without_touching_version_1(tmp_path):
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
    app.state.job_service = service

    with TestClient(app) as client:
        # ---- Version 1 of a brand-new Song ----
        r1 = client.post("/api/jobs", json={"prompt": "short upbeat instrumental synth loop", "instrumental": True, "duration": 10.0, "seed": 11})
        assert r1.status_code == 200
        j1 = client.get(f"/api/jobs/{r1.json()['id']}").json()  # TestClient ran the background poll to completion
        assert j1["status"] == "COMPLETED", j1["status"]
        assert (j1["version_number"], j1["song_id"].startswith("song-"), j1["version_id"].startswith("ver-")) == (1, True, True)

        v1 = repository.get_version(j1["version_id"])
        v1_path = storage.get_path(v1.audio.key)
        v1_hash, v1_size = _sha(v1_path), v1_path.stat().st_size
        assert v1_size > 0 and v1.audio.size_bytes == v1_size and v1.audio.media_type == "audio/flac"  # FLAC since Phase 17
        assert v1.spec.seed == 11 and v1.spec.instrumental is True and v1.provider == "ace-step"
        assert client.get(f"/api/jobs/{j1['id']}/audio").content == v1_path.read_bytes()

        # ---- Version 2 of the SAME Song (a different take) ----
        r2 = client.post("/api/jobs", json={"prompt": "short mellow instrumental piano loop", "instrumental": True, "duration": 10.0, "seed": 22, "song_id": j1["song_id"]})
        assert r2.status_code == 200
        j2 = client.get(f"/api/jobs/{r2.json()['id']}").json()
        assert j2["status"] == "COMPLETED", j2["status"]
        assert j2["song_id"] == j1["song_id"] and j2["version_number"] == 2 and j2["version_id"] != j1["version_id"]
        assert j2["title"] == j1["title"]

        v2 = repository.get_version(j2["version_id"])
        v2_path = storage.get_path(v2.audio.key)
        assert v2.audio.key != v1.audio.key and v2_path.stat().st_size > 0
        assert v2.spec.seed == 22 and v2.spec.prompt == "short mellow instrumental piano loop"

        # ---- Version 1 is exactly as it was ----
        assert repository.get_version(j1["version_id"]) == v1
        assert _sha(v1_path) == v1_hash and v1_path.stat().st_size == v1_size
        assert client.get(f"/api/jobs/{j1['id']}/audio").content == v1_path.read_bytes()
        assert client.get(f"/api/jobs/{j2['id']}/audio").content == v2_path.read_bytes()
        assert [v.version_number for v in repository.list_versions(j1["song_id"])] == [1, 2]

        # ---- The domain rows, straight from SQLite ----
        conn = sqlite3.connect(db)
        try:
            assert conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM versions").fetchone()[0] == 2
            assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 2
            assert conn.execute("SELECT COUNT(*) FROM jobs WHERE version_id IS NULL").fetchone()[0] == 0
        finally:
            conn.close()

        # ---- Nothing internal leaks through the API ----
        exposed = json.dumps([j1, j2]) + client.get("/api/jobs").text
        for leaked in (str(tmp_path), "absolute_path", "/v1/audio", "8001", "provider_job_id"):
            assert leaked not in exposed
