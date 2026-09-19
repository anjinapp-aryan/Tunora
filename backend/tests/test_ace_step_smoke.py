"""Real, end-to-end smoke test against a locally running ACE-Step API server.

Skipped automatically if the server is not reachable at ACE_STEP_BASE_URL
(default http://127.0.0.1:8001) — this test uses real GPU time, so it is
excluded from the default test run (see pyproject.toml's `smoke` marker) and
uses the shortest practical duration to keep GPU usage minimal.

Run explicitly with:
    uv run pytest tests -m smoke
"""

from __future__ import annotations

import asyncio
import os

import httpx
import pytest

from app.providers.ace_step import AceStepMusicGenerationProvider
from app.providers.base import GenerationRequest, JobState

BASE_URL = os.environ.get("ACE_STEP_BASE_URL", "http://127.0.0.1:8001")
POLL_INTERVAL_SECONDS = 3.0
MAX_WAIT_SECONDS = 300.0


def _server_reachable() -> bool:
    try:
        response = httpx.get(f"{BASE_URL}/health", timeout=3.0)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.smoke


@pytest.mark.skipif(not _server_reachable(), reason=f"ACE-Step API server not reachable at {BASE_URL}")
@pytest.mark.asyncio
async def test_real_short_generation_end_to_end():
    provider = AceStepMusicGenerationProvider(base_url=BASE_URL, request_timeout=60.0)
    try:
        job = await provider.generate(
            GenerationRequest(
                prompt="short upbeat instrumental synth loop",
                instrumental=True,
                duration=10.0,
            )
        )
        assert job.status == JobState.QUEUED

        elapsed = 0.0
        status = await provider.get_status(job.job_id)
        while status.status in (JobState.QUEUED, JobState.RUNNING):
            if elapsed >= MAX_WAIT_SECONDS:
                pytest.fail(
                    f"ACE-Step job {job.job_id} did not finish within {MAX_WAIT_SECONDS}s "
                    f"(last status={status.status.value})"
                )
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            elapsed += POLL_INTERVAL_SECONDS
            status = await provider.get_status(job.job_id)

        assert status.status == JobState.SUCCEEDED, (
            f"ACE-Step job {job.job_id} ended with status={status.status.value}, "
            f"message={status.message!r}"
        )

        result = await provider.get_result(job.job_id)
        assert result.audio_path, "get_result() returned an empty audio_path"
        assert os.path.isfile(result.audio_path), f"Audio file does not exist on disk: {result.audio_path}"
        assert os.path.getsize(result.audio_path) > 0, "Audio file exists but is empty"
    finally:
        await provider.aclose()
