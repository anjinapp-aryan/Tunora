"""Phase 6 real integration test: a Project over a REAL ACE-Step generation.

Projects are organizational metadata only, so this reuses ONE real generation
(no reason to spend more GPU time) and checks, against the real backend, that
adding/removing a song from a project never creates, moves or deletes a Song,
Version or audio file. Skipped unless the ACE-Step API server is reachable.
"""

from __future__ import annotations

import hashlib
import json
import os

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router as jobs_router
from app.api.routes_projects import router as projects_router
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


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.skipif(not _server_reachable(), reason=f"ACE-Step API server not reachable at {BASE_URL}")
def test_a_project_over_one_real_song_never_touches_its_audio_or_versions(tmp_path):
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
    app.include_router(projects_router)
    app.state.job_service = service

    with TestClient(app) as client:
        # ---- One real generation (the only GPU work this test needs) ----
        r = client.post("/api/jobs", json={"prompt": "short upbeat instrumental synth loop", "instrumental": True, "duration": 10.0, "seed": 7})
        assert r.status_code == 200
        job = client.get(f"/api/jobs/{r.json()['id']}").json()
        assert job["status"] == "COMPLETED", job["status"]
        song_id = job["song_id"]

        version = repository.get_version(job["version_id"])
        audio_path = storage.get_path(version.audio.key)
        audio_hash, audio_size = _sha(audio_path), audio_path.stat().st_size

        # ---- Create a Project and add the real song to it ----
        project = client.post("/api/projects", json={"name": "My Movie Album", "description": "Real GPU song"}).json()
        added = client.post(f"/api/projects/{project['id']}/songs", json={"song_id": song_id})
        assert added.status_code == 200, added.text
        assert added.json() == {
            "id": song_id, "title": job["title"], "version_count": 1, "latest_version_number": 1,
            "created_at": added.json()["created_at"], "updated_at": added.json()["updated_at"],
        }

        details = client.get(f"/api/projects/{project['id']}").json()
        assert [s["id"] for s in details["songs"]] == [song_id]
        song_details = client.get(f"/api/songs/{song_id}").json()
        assert song_details["project"] == {"id": project["id"], "name": "My Movie Album"}

        # ---- The real audio is byte-identical: nothing was copied, moved or regenerated ----
        assert repository.get_version(job["version_id"]) == version
        assert (_sha(audio_path), audio_path.stat().st_size) == (audio_hash, audio_size)
        assert client.get(f"/api/jobs/{job['id']}/audio").content == audio_path.read_bytes()

        # ---- Remove from the project: the song, its version and its audio survive ----
        removed = client.delete(f"/api/projects/{project['id']}/songs/{song_id}")
        assert removed.status_code == 204
        assert client.get(f"/api/songs/{song_id}").json()["project"] is None
        assert repository.get_version(job["version_id"]) == version
        assert (_sha(audio_path), audio_path.stat().st_size) == (audio_hash, audio_size)

        # ---- Re-add, then delete the PROJECT itself: song/version/audio all survive ----
        client.post(f"/api/projects/{project['id']}/songs", json={"song_id": song_id})
        assert client.delete(f"/api/projects/{project['id']}").status_code == 204
        assert client.get(f"/api/projects/{project['id']}").status_code == 404
        after = client.get(f"/api/songs/{song_id}").json()
        assert after["project"] is None and after["versions"][0]["id"] == version.id
        assert repository.get_version(job["version_id"]) == version
        assert (_sha(audio_path), audio_path.stat().st_size) == (audio_hash, audio_size)
        assert client.get(f"/api/jobs/{job['id']}/audio").content == audio_path.read_bytes()

        exposed = json.dumps([job, project, details, song_details, after])
        for leaked in (str(tmp_path), "absolute_path", "/v1/audio", "8001", "source_audio_path"):
            assert leaked not in exposed
