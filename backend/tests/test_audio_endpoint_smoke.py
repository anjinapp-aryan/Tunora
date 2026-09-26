"""Step 16 real integration test: POST /api/jobs -> real ACE-Step generation ->
COMPLETED -> GET /api/jobs/{id}/audio. Skipped unless the ACE-Step API server is
reachable. Run with: uv run pytest tests -m smoke
"""

from __future__ import annotations

import json
import os

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


@pytest.mark.skipif(not _server_reachable(), reason=f"ACE-Step API server not reachable at {BASE_URL}")
def test_real_generation_then_audio_endpoint(tmp_path):
    provider = AceStepMusicGenerationProvider(base_url=BASE_URL, request_timeout=60.0)
    storage = LocalAudioStorage(tmp_path / "audio")
    service = JobService(
        repository=SqliteJobRepository(tmp_path / "tunora.db"),
        provider=provider,
        storage=storage,
        poll_interval_seconds=2.0,
    )
    app = FastAPI()
    app.include_router(jobs_router)
    app.state.job_service = service

    with TestClient(app) as client:
        created = client.post(
            "/api/jobs", json={"prompt": "short upbeat instrumental synth loop", "instrumental": True, "duration": 10.0}
        )
        assert created.status_code == 200
        job_id = created.json()["id"]

        # TestClient runs the BackgroundTask to completion before returning.
        job = client.get(f"/api/jobs/{job_id}").json()
        assert job["status"] == "COMPLETED", f"job ended {job['status']}"

        # Only the Tunora job id is needed to get the audio.
        audio = client.get(f"/api/jobs/{job_id}/audio")
        assert audio.status_code == 200
        assert audio.headers["content-type"] == job["result"]["audio"]["media_type"] == "audio/flac"  # FLAC is the canonical format since Phase 17
        assert int(audio.headers["content-length"]) > 0
        assert len(audio.content) == int(audio.headers["content-length"]) == job["result"]["audio"]["size_bytes"]

        # The body is exactly the Tunora-stored artifact.
        stored_file = storage.get_path(job["result"]["audio"]["key"])
        assert stored_file.read_bytes() == audio.content

        # Range support (what a future <audio> element will use).
        ranged = client.get(f"/api/jobs/{job_id}/audio", headers={"Range": "bytes=0-99"})
        assert ranged.status_code == 206
        assert ranged.content == audio.content[:100]

        # Nothing internal leaks through the API (job JSON, headers, or error bodies).
        exposed = json.dumps(job) + str(dict(audio.headers)) + client.get("/api/jobs").text
        assert str(tmp_path) not in exposed
        assert "/v1/audio" not in exposed
        assert "8001" not in exposed
        assert "absolute_path" not in exposed
        assert job["result"]["audio"]["audio_url"] == f"/api/jobs/{job_id}/audio"

        # A client-supplied path is ignored: same bytes, never the requested file.
        smuggled = client.get(f"/api/jobs/{job_id}/audio", params={"path": str(tmp_path / "tunora.db")})
        assert smuggled.content == audio.content
