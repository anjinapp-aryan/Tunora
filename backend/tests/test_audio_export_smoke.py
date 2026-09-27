"""Phase 21 real integration test: a real ACE-Step FLAC Version, then MP3 and WAV export of it.
Skipped unless the ACE-Step API server is reachable. Run with: uv run pytest tests -m smoke
"""

from __future__ import annotations

import io
import os
import time

import httpx
import pytest
import soundfile as sf
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
@pytest.mark.parametrize("duration", [10.0, 60.0, 180.0])
def test_real_export_of_a_real_flac_version_to_mp3_and_wav(tmp_path, duration):
    repository = SqliteJobRepository(tmp_path / "tunora.db")
    storage = LocalAudioStorage(tmp_path / "audio")
    service = JobService(
        repository=repository,
        provider=AceStepMusicGenerationProvider(base_url=BASE_URL, request_timeout=120.0),
        storage=storage,
        poll_interval_seconds=2.0,
    )
    app = FastAPI()
    app.include_router(jobs_router)
    app.state.job_service = service

    with TestClient(app) as client:
        r = client.post("/api/jobs", json={"prompt": "short upbeat instrumental synth loop", "instrumental": True, "duration": duration})
        job = client.get(f"/api/jobs/{r.json()['id']}").json()
        assert job["status"] == "COMPLETED", job["status"]
        source_bytes = client.get(f"/api/jobs/{job['id']}/audio").content
        source_info = sf.info(io.BytesIO(source_bytes))
        assert source_info.format == "FLAC"

        results = {}
        for fmt in ("mp3", "wav"):
            t0 = time.time()
            resp = client.get(f"/api/jobs/{job['id']}/audio", params={"format": fmt})
            elapsed = time.time() - t0
            assert resp.status_code == 200, resp.text
            assert resp.headers["content-type"] == {"mp3": "audio/mpeg", "wav": "audio/wav"}[fmt]
            assert "attachment" in resp.headers["content-disposition"]
            info = sf.info(io.BytesIO(resp.content))
            assert info.format == fmt.upper()
            assert abs(info.duration - source_info.duration) < 0.2  # not byte-equal across formats, but the same song
            results[fmt] = (elapsed, len(resp.content), info.samplerate, info.channels, info.duration)

        # The canonical file is untouched by exporting it twice.
        assert client.get(f"/api/jobs/{job['id']}/audio").content == source_bytes

        print(f"\nREAL EXPORT duration={duration}s source_bytes={len(source_bytes)} mp3={results['mp3']} wav={results['wav']}")
