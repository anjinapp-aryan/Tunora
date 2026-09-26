"""Real end-to-end smoke test for Step 12: POST /api/jobs -> ... -> COMPLETED
against a real, locally running ACE-Step API server.

Skipped automatically if the server isn't reachable. Uses the shortest
practical duration to minimize GPU time. Run explicitly with:
    uv run pytest tests -m smoke
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
def test_real_job_lifecycle_end_to_end(tmp_path):
    provider = AceStepMusicGenerationProvider(base_url=BASE_URL, request_timeout=60.0)
    repository = SqliteJobRepository(tmp_path / "tunora.db")
    storage = LocalAudioStorage(tmp_path / "audio")
    service = JobService(repository=repository, provider=provider, storage=storage, poll_interval_seconds=2.0)

    app = FastAPI()
    app.include_router(jobs_router)
    app.state.job_service = service

    with TestClient(app) as client:
        create_response = client.post(
            "/api/jobs",
            json={
                "prompt": "short upbeat instrumental synth loop",
                "instrumental": True,
                "duration": 10.0,
            },
        )
        assert create_response.status_code == 200
        created_body = create_response.json()
        assert created_body["status"] in ("SUBMITTED", "QUEUED", "RUNNING")
        job_id = created_body["id"]

        # By the time TestClient returns from the POST above, the scheduled
        # BackgroundTask (JobService.run_until_terminal) has already run to
        # completion in-process -- TestClient blocks on the full ASGI cycle,
        # background tasks included. So the job should already be terminal.
        final = client.get(f"/api/jobs/{job_id}").json()

        assert final["status"] == "COMPLETED", (
            f"Job did not complete: status={final['status']}, error={final.get('error')!r}"
        )
        assert final["result"] is not None
        audio = final["result"]["audio"]
        # The API exposes a storage key, never a filesystem path.
        assert "absolute_path" not in audio
        assert audio["key"] == f"{job_id}/{job_id}.flac"  # FLAC is the canonical format since Phase 17

        resolved_path = storage.get_path(audio["key"])
        assert os.path.isfile(resolved_path), f"Audio file does not exist on disk: {resolved_path}"
        assert os.path.getsize(resolved_path) > 0
        assert os.path.getsize(resolved_path) == audio["size_bytes"]
        # Storage root containment: the resolved file must live under tmp_path/audio.
        assert str(resolved_path).startswith(str((tmp_path / "audio").resolve()))

        # No ACE-Step-specific structure (its wrap_response envelope, task_id
        # field name, "/v1/audio?path=" route strings, its own temp filename,
        # etc.) should leak through Tunora's own API shape.
        assert "task_id" not in final
        assert "/v1/audio" not in create_response.text
        assert "/v1/audio" not in json.dumps(final)
