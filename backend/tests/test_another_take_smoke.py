"""Phase 13 real integration test: Another Take through Tunora against REAL ACE-Step (GPU).

A 10 s source Version with a FIXED seed, then two REAL takes of it. Objective facts only: jobs
COMPLETED, new audio with its own key/bytes/checksum, same Song, consecutive Version numbers,
lineage rows, the source's row/audio untouched, the take's seed left to the provider (None).
Musical quality/difference needs a human listener. Skipped unless the ACE-Step server is reachable.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess

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


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _probe(path):
    """(codec, duration seconds) from the file itself via ffprobe, or None when ffprobe is absent."""

    if not shutil.which("ffprobe"):
        return None
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name:format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    return out


@pytest.mark.skipif(not _server_reachable(), reason=f"ACE-Step API server not reachable at {BASE_URL}")
def test_real_another_take_creates_new_versions_and_leaves_the_source_untouched(tmp_path, capsys):
    storage = LocalAudioStorage(tmp_path / "audio")
    repository = SqliteJobRepository(tmp_path / "tunora.db")
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
        r = client.post(
            "/api/jobs",
            json={"prompt": "short upbeat instrumental synth loop", "instrumental": True, "duration": 10.0, "seed": 11},
        )
        j1 = client.get(f"/api/jobs/{r.json()['id']}").json()
        assert j1["status"] == "COMPLETED", j1["status"]
        v1 = repository.get_version(j1["version_id"])
        assert v1.spec.seed == 11
        v1_path = storage.get_path(v1.audio.key)
        v1_hash, v1_size = _sha(v1_path), v1_path.stat().st_size

        record = [("V1 ORIGINAL", v1.id, v1.spec.seed, v1.audio.duration, v1_size, v1_hash[:16], _probe(v1_path))]
        hashes = {v1_hash}
        take_versions = []
        for number in (2, 3):
            resp = client.post(f"/api/songs/{j1['song_id']}/versions/{v1.id}/another_take", json={})
            assert resp.status_code == 200, resp.text
            job = client.get(f"/api/jobs/{resp.json()['id']}").json()  # the background poll ran to completion
            assert job["status"] == "COMPLETED", job
            assert (job["song_id"], job["version_number"]) == (j1["song_id"], number)
            assert job["id"] != j1["id"]

            version = repository.get_version(job["version_id"])
            assert (version.operation, version.source_version_id, version.song_id) == ("ANOTHER_TAKE", v1.id, v1.song_id)
            assert version.spec.seed is None  # left to the provider, never the source's fixed seed
            assert (version.spec.prompt, version.spec.instrumental) == (v1.spec.prompt, v1.spec.instrumental)
            path = storage.get_path(version.audio.key)
            assert path.stat().st_size > 0 and version.audio.key != v1.audio.key
            digest = _sha(path)
            assert digest not in hashes  # genuinely new audio, not a copy of any earlier version
            hashes.add(digest)
            assert client.get(f"/api/jobs/{job['id']}/audio").content == path.read_bytes()
            record.append((f"V{number} ANOTHER_TAKE", version.id, version.spec.seed, version.audio.duration,
                           path.stat().st_size, digest[:16], _probe(path)))
            take_versions.append(version)

            # The source is exactly as it was after every take.
            assert repository.get_version(v1.id) == v1
            assert (_sha(v1_path), v1_path.stat().st_size) == (v1_hash, v1_size)

        versions = client.get(f"/api/songs/{j1['song_id']}").json()["versions"]
        assert sorted(v["version_number"] for v in versions) == [1, 2, 3]
        assert take_versions[0].id != take_versions[1].id

    with capsys.disabled():
        for row in record:
            print("\nREAL-GPU", row)
