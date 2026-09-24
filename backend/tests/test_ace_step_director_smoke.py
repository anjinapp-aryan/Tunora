"""Phase 7 real integration test: natural language -> AceStepSongDirector -> a real
ACE-Step generation, through Tunora's own API end to end (no mocks).

Verifies the full documented flow: POST /api/songs/plan (real 5Hz-LM call) produces
a plan, and POST /api/jobs (existing, unchanged) with that plan's own fields as its
body produces a real Song/Version with real audio. Skipped unless the ACE-Step API
server is reachable.
"""

from __future__ import annotations

import os

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_director import router as director_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_songs import router as songs_router
from app.director.ace_step import AceStepSongDirector
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
def test_a_natural_language_request_becomes_a_plan_and_then_a_real_song(tmp_path):
    db = tmp_path / "tunora.db"
    storage = LocalAudioStorage(tmp_path / "audio")
    repository = SqliteJobRepository(db)
    service = JobService(
        repository=repository,
        provider=AceStepMusicGenerationProvider(base_url=BASE_URL, request_timeout=120.0),
        storage=storage,
        poll_interval_seconds=2.0,
    )
    app = FastAPI()
    app.include_router(director_router)
    app.include_router(jobs_router)
    app.include_router(songs_router)
    app.state.job_service = service
    app.state.song_director = AceStepSongDirector(base_url=BASE_URL, request_timeout=180.0)

    with TestClient(app) as client:
        # ---- Natural language -> a real AI-produced plan ----
        plan_response = client.post(
            "/api/songs/plan",
            json={
                "query": "a short upbeat instrumental synth loop for a video game menu",
                "instrumental": True,
            },
        )
        assert plan_response.status_code == 200, plan_response.text
        plan = plan_response.json()
        assert plan["instrumental"] is True and plan["lyrics"] == ""  # explicit user choice honoured
        assert plan["prompt"] and len(plan["prompt"]) > 10  # a real, non-trivial AI description
        assert plan["title"]
        for leaked in ("8001", "task_id", "/v1/", "create_sample", str(tmp_path)):
            assert leaked not in plan_response.text

        # ---- The plan's OWN fields become the body of the EXISTING, unchanged /api/jobs ----
        job_payload = {
            "title": plan["title"],
            "prompt": plan["prompt"],
            "lyrics": plan["lyrics"],
            "language": plan["language"] or "en",
            "duration": min(plan["duration"] or 10.0, 15.0),  # keep the real generation short
            "instrumental": plan["instrumental"],
        }
        created = client.post("/api/jobs", json=job_payload)
        assert created.status_code == 200, created.text
        job = client.get(f"/api/jobs/{created.json()['id']}").json()
        assert job["status"] == "COMPLETED", job["status"]
        assert job["result"]["audio"]["size_bytes"] > 0

        version = repository.get_version(job["version_id"])
        assert version.spec.prompt == plan["prompt"] and version.spec.instrumental is True
        audio_path = storage.get_path(version.audio.key)
        assert audio_path.stat().st_size > 0
        assert client.get(f"/api/jobs/{job['id']}/audio").content == audio_path.read_bytes()
