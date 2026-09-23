"""Phase 11 real integration test: a real ACE-Step generation, then a real EXTRACT
(track separation) of that generation's audio -- through the actual Tunora HTTP stack, not a
direct ACE-Step call. Verifies the EXTRACT operation end to end: real REST reachability, real
base-tier inference, a real new immutable Version, real lineage, and the original Version
untouched. Skipped unless the ACE-Step API server is reachable.
"""

from __future__ import annotations

import os

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
def test_a_real_extract_creates_a_new_version_and_leaves_the_source_untouched(tmp_path):
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
    app.include_router(jobs_router)
    app.include_router(songs_router)
    app.state.job_service = service

    with TestClient(app) as client:
        # ---- Version 1: a real generation with vocals ----
        r1 = client.post(
            "/api/jobs",
            json={
                "prompt": "an upbeat pop song with clear female lead vocals, drums, bass and synth",
                "instrumental": False,
                "duration": 15.0,
                "seed": 601,
            },
        )
        assert r1.status_code == 200
        job1 = client.get(f"/api/jobs/{r1.json()['id']}").json()
        assert job1["status"] == "COMPLETED", job1["status"]
        song_id = job1["song_id"]
        v1_key_before = repository.get_version(job1["version_id"]).audio.key
        v1_path = storage.get_path(v1_key_before)
        v1_bytes_before = v1_path.read_bytes()

        # ---- Real EXTRACT: pull the vocals track out of Version 1 ----
        extract = client.post(
            f"/api/songs/{song_id}/versions/{job1['version_id']}/extract",
            json={"track_name": "vocals"},
        )
        assert extract.status_code == 200, extract.text
        extract_job = extract.json()

        completed = client.get(f"/api/jobs/{extract_job['id']}")
        assert completed.status_code == 200 and completed.json()["status"] == "COMPLETED", completed.json()

        # ---- The extracted result is a real, new, playable Version ----
        details = client.get(f"/api/songs/{song_id}").json()
        versions_by_number = {v["version_number"]: v for v in details["versions"]}
        assert set(versions_by_number) == {1, 2}
        v2 = versions_by_number[2]
        assert v2["operation"] == "EXTRACT" and v2["extracted_track"] == "vocals"
        assert v2["source_version_number"] == 1
        assert v2["audio"] is not None

        v2_version = repository.get_version(extract_job["version_id"])
        v2_path = storage.get_path(v2_version.audio.key)
        assert v2_path.exists() and v2_path.stat().st_size > 0
        assert v2_path.read_bytes() != v1_bytes_before  # a real, distinct transformation

        audio_response = client.get(v2["audio"]["audio_url"])
        assert audio_response.status_code == 200 and len(audio_response.content) == v2_path.stat().st_size

        # ---- The original Version 1 is completely untouched ----
        assert versions_by_number[1]["operation"] == "ORIGINAL"
        assert versions_by_number[1]["extracted_track"] is None
        assert v1_path.read_bytes() == v1_bytes_before
        assert repository.get_version(job1["version_id"]).audio.key == v1_key_before

        # ---- Nothing internal leaks ----
        text = str(details) + completed.text + extract.text
        for leaked in (str(tmp_path), "acestep-v15-base", "/v1/audio", BASE_URL.replace("http://", "")):
            assert leaked not in text
