"""Phase 23 real end-to-end: a real ACE-Step vocal Version -> real local alignment -> real
LGPL FFmpeg/libass render -> a playable 1080x1920 MP4. Nothing is mocked.

Skipped unless the ACE-Step API server is reachable and an approved FFmpeg is installed.
Run with: uv run pytest tests -m smoke
"""

from __future__ import annotations

import json
import os
import subprocess
import time

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router as jobs_router
from app.api.routes_music_videos import router as music_videos_router
from app.jobs.repository import SqliteJobRepository
from app.jobs.service import JobService
from app.music_videos import ffmpeg as policy
from app.music_videos.repository import SqliteMusicVideoRepository
from app.music_videos.service import MusicVideoService
from app.music_videos.storage import MusicVideoStorage
from app.providers.ace_step import AceStepMusicGenerationProvider
from app.storage.local import LocalAudioStorage

BASE_URL = os.environ.get("ACE_STEP_BASE_URL", "http://127.0.0.1:8001")
pytestmark = pytest.mark.smoke

LYRICS = """[Verse]
I wake up to a brand new day
With every fear I walk away
The road ahead is calling me
A chance to become who I can be

[Chorus]
I will rise, I will fly
I will reach the open sky"""


VOCAL_PROMPT = ("Uplifting cinematic pop ballad with warm piano, soft acoustic guitar, subtle strings, modern drums, "
                "expressive female lead vocal, emotional verses, a memorable catchy chorus. Keep the lead vocal clear, "
                "natural, and prominent throughout the song with emotional English singing and clear pronunciation.")


def _ready() -> bool:
    try:
        policy.resolve()
        return httpx.get(f"{BASE_URL}/health", timeout=3.0).status_code == 200
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _ready(), reason="ACE-Step not reachable or no approved FFmpeg installed")
def test_real_vocal_version_becomes_a_real_music_video(tmp_path):
    tools = policy.resolve()
    repository = SqliteJobRepository(tmp_path / "tunora.db")
    jobs = JobService(repository=repository, provider=AceStepMusicGenerationProvider(base_url=BASE_URL, request_timeout=120.0),
                      storage=LocalAudioStorage(tmp_path / "audio"), poll_interval_seconds=2.0)
    app = FastAPI()
    app.include_router(jobs_router)
    app.include_router(music_videos_router)
    app.state.job_service = jobs
    app.state.music_video_service = MusicVideoService(
        repository=SqliteMusicVideoRepository(tmp_path / "tunora.db"), jobs=jobs,
        storage=MusicVideoStorage(tmp_path / "music-videos"))
    background = tmp_path / "bg.mp4"
    subprocess.run([str(tools.ffmpeg), "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "gradients=s=1280x720:r=30:d=3:speed=0.02", "-c:v", "libopenh264", str(background)], check=True)

    with TestClient(app) as client:
        # The prompt that reliably produced clear vocals in Phase 22A/22B. ACE-Step can still return
        # a near-instrumental take for sung lyrics (a documented provider limitation); a 30 s
        # "clear female vocal" prompt did exactly that once, and Tunora then correctly failed with
        # "no lyrics matched" instead of inventing timings.
        r = client.post("/api/jobs", json={"prompt": VOCAL_PROMPT, "lyrics": LYRICS,
                                           "language": "en", "duration": 60.0, "instrumental": False})
        job = client.get(f"/api/jobs/{r.json()['id']}").json()
        assert job["status"] == "COMPLETED", job["status"]
        song_id, version_id = job["song_id"], job["version_id"]

        started = time.monotonic()
        created = client.post(f"/api/songs/{song_id}/music-videos", params={"source_version_id": version_id},
                              content=background.read_bytes(), headers={"Content-Type": "video/mp4"})
        assert created.status_code == 202, created.text
        video = client.get(f"/api/music-videos/{created.json()['id']}").json()
        elapsed = time.monotonic() - started
        assert video["status"] == "COMPLETED", (video["status"], video["error"], video["unmatched_lines"])
        mp4 = client.get(video["video_url"]).content

    out = tmp_path / "out.mp4"
    out.write_bytes(mp4)
    info = json.loads(subprocess.run([str(tools.ffprobe), "-v", "error", "-show_entries",
                                      "stream=codec_name,width,height:format=duration", "-of", "json", str(out)],
                                     capture_output=True, text=True, check=True).stdout)
    codecs = {s["codec_name"] for s in info["streams"]}
    v = next(s for s in info["streams"] if s["codec_name"] == "h264")
    assert codecs == {"h264", "aac"} and (v["width"], v["height"]) == (1080, 1920)
    assert abs(float(info["format"]["duration"]) - video["duration"]) < 0.2
    assert video["matched_line_count"] >= 1
    print(f"\nREAL MUSIC VIDEO: {video['duration']:.1f}s audio, align+render {elapsed:.1f}s, "
          f"{len(mp4)} bytes, matched={video['matched_line_count']} unmatched={len(video['unmatched_lines'])}")
