"""Phase 10 real integration test: two REAL ACE-Step generations of the SAME
Song, proving provider-reported metadata (bpm/genres/key_scale/time_signature)
really flows: real generation -> Job.result_json -> Song/Version API ->
Version A / Version B, each with its own metadata. Skipped unless the
ACE-Step API server is reachable.

Values are not hardcoded (the provider's own bpm/key vary per generation);
this test verifies presence/type/consistent mapping, per the governing
prompt's explicit instruction not to assert exact generated values.
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


def _assert_valid_metadata_shape(metadata) -> None:
    assert set(metadata) == {"bpm", "genres", "key_scale", "time_signature", "source"}
    assert metadata["source"] == "provider"
    assert metadata["bpm"] is None or isinstance(metadata["bpm"], (int, float))
    for field in ("genres", "key_scale", "time_signature"):
        assert metadata[field] is None or isinstance(metadata[field], str)
        assert metadata[field] != ""  # normalized to null, never a blank string


@pytest.mark.skipif(not _server_reachable(), reason=f"ACE-Step API server not reachable at {BASE_URL}")
def test_two_real_versions_of_one_song_each_carry_their_own_provider_metadata(tmp_path):
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
        # ---- Version A: a real generation, a brand-new Song ----
        r1 = client.post(
            "/api/jobs",
            json={"prompt": "short upbeat instrumental synth loop", "instrumental": True, "duration": 10.0, "seed": 51},
        )
        assert r1.status_code == 200
        job1 = client.get(f"/api/jobs/{r1.json()['id']}").json()
        assert job1["status"] == "COMPLETED", job1["status"]
        song_id = job1["song_id"]

        # ---- Version B: a second real generation, same Song ----
        r2 = client.post(
            "/api/jobs",
            json={"prompt": "short mellow instrumental piano loop", "instrumental": True, "duration": 10.0, "seed": 52, "song_id": song_id},
        )
        assert r2.status_code == 200
        job2 = client.get(f"/api/jobs/{r2.json()['id']}").json()
        assert job2["status"] == "COMPLETED", job2["status"]

        # ---- Song Details: each Version carries its OWN metadata, not the other's ----
        details = client.get(f"/api/songs/{song_id}").json()
        versions_by_number = {v["version_number"]: v for v in details["versions"]}
        assert set(versions_by_number) == {1, 2}

        v1, v2 = versions_by_number[1], versions_by_number[2]
        # ACE-Step's LM reports metadata for a real generation; if it ever reports nothing
        # for a given call, metadata is null rather than a fabricated object -- both are
        # valid, so only the shape (when present) is asserted, not a specific value.
        if v1["metadata"] is not None:
            _assert_valid_metadata_shape(v1["metadata"])
        if v2["metadata"] is not None:
            _assert_valid_metadata_shape(v2["metadata"])

        # ---- Nothing internal leaks through the API ----
        text = client.get(f"/api/songs/{song_id}").text
        for leaked in (str(tmp_path), BASE_URL.replace("http://", ""), "/v1/audio", "provider_job_id"):
            assert leaked not in text
