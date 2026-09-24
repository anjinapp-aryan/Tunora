"""Phase 5B real integration test: Extend, Remix and Repaint through Tunora against REAL ACE-Step.

One 10 s source Version, then one REAL generation per operation. Checks objective facts only
(job COMPLETED, new audio exists with its own key/bytes, duration, lineage rows, source untouched).
Musical quality needs a human listener. Skipped unless the ACE-Step API server is reachable.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
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


def _probe_seconds(path):
    """Independent duration from the file itself (ffprobe), or None when ffprobe is absent."""

    if not shutil.which("ffprobe"):
        return None
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


@pytest.mark.skipif(not _server_reachable(), reason=f"ACE-Step API server not reachable at {BASE_URL}")
def test_real_extend_remix_and_repaint_each_create_a_new_version_and_leave_the_source_untouched(tmp_path):
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
        r = client.post("/api/jobs", json={"prompt": "short upbeat instrumental synth loop", "instrumental": True, "duration": 10.0, "seed": 11})
        j1 = client.get(f"/api/jobs/{r.json()['id']}").json()
        assert j1["status"] == "COMPLETED", j1["status"]
        v1 = repository.get_version(j1["version_id"])
        v1_path = storage.get_path(v1.audio.key)
        v1_hash, v1_size = _sha(v1_path), v1_path.stat().st_size
        base = f"/api/songs/{j1['song_id']}/versions/{j1['version_id']}"

        cases = [
            ("EXTEND", "extend", {"extend_seconds": 10}),
            ("REMIX", "remix", {"prompt": "slow warm acoustic piano version", "remix_strength": 0.7}),
            ("REPAINT", "repaint", {"prompt": "add a soft pad", "repaint_start": 3, "repaint_end": 7}),
        ]
        keys = {v1.audio.key}
        durations = {}
        for number, (operation, path, body) in enumerate(cases, start=2):
            resp = client.post(f"{base}/{path}", json=body)
            assert resp.status_code == 200, resp.text
            job = client.get(f"/api/jobs/{resp.json()['id']}").json()  # background poll ran to completion
            assert job["status"] == "COMPLETED", (operation, job)
            assert (job["song_id"], job["version_number"]) == (j1["song_id"], number)

            version = repository.get_version(job["version_id"])
            assert (version.operation, version.source_version_id) == (operation, v1.id)
            path_on_disk = storage.get_path(version.audio.key)
            assert path_on_disk.stat().st_size > 0 and version.audio.key not in keys
            keys.add(version.audio.key)
            assert path_on_disk.read_bytes() != v1_path.read_bytes()
            assert client.get(f"/api/jobs/{job['id']}/audio").content == path_on_disk.read_bytes()
            durations[operation] = (version.audio.duration, _probe_seconds(path_on_disk))

            # Source is exactly as it was after every operation.
            assert repository.get_version(v1.id) == v1
            assert (_sha(v1_path), v1_path.stat().st_size) == (v1_hash, v1_size)

        # Extend really is longer; remix/repaint keep roughly the source length (objective bounds only).
        ext_reported, ext_probed = durations["EXTEND"]
        assert ext_reported == pytest.approx(20.0, abs=1.0)
        if ext_probed is not None:
            assert 17.0 <= ext_probed <= 23.0
        for op in ("REMIX", "REPAINT"):
            reported, probed = durations[op]
            assert reported == pytest.approx(10.0, abs=1.0)
            if probed is not None:
                assert 8.0 <= probed <= 12.5
        print("OBJECTIVE-DURATIONS", json.dumps(durations))

        details = client.get(f"/api/songs/{j1['song_id']}").json()
        assert [(v["version_number"], v["operation"], v["source_version_number"]) for v in details["versions"]] == [
            (4, "REPAINT", 1), (3, "REMIX", 1), (2, "EXTEND", 1), (1, "ORIGINAL", None)
        ]
        assert details["versions"][0]["is_latest"] is True
        assert len(client.get("/api/songs").json()["items"]) == 1

        conn = sqlite3.connect(db)
        try:
            assert conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM versions").fetchone()[0] == 4
            assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 4
        finally:
            conn.close()
        exposed = json.dumps(details) + client.get("/api/songs").text
        for leaked in (str(tmp_path), "absolute_path", "/v1/audio", "8001", "source_audio_path"):
            assert leaked not in exposed
