"""Step 16: GET /api/jobs/{job_id}/audio and the public job result contract.

Real LocalAudioStorage over tmp_path + FakeProvider: no network, no GPU.
Jobs are placed directly in the repository so each state can be tested
without running the lifecycle.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router as jobs_router
from app.jobs.models import Job, JobStatus
from app.jobs.repository import InMemoryJobRepository
from app.jobs.service import JobService
from app.providers.base import GenerationRequest
from app.storage.errors import StorageWriteError
from app.storage.local import LocalAudioStorage
from tests.jobs.fakes import FakeProvider

AUDIO_BYTES = b"ID3" + bytes(range(256)) * 8  # 2051 bytes, non-trivial content
SECRET = b"TOP-SECRET-OUTSIDE-STORAGE-ROOT"


class Env:
    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        self.storage_root = tmp_path / "storage"
        self.storage = LocalAudioStorage(self.storage_root)
        self.repository = InMemoryJobRepository()
        self.service = JobService(
            repository=self.repository, provider=FakeProvider(), storage=self.storage, poll_interval_seconds=0.0
        )
        app = FastAPI()
        app.include_router(jobs_router)
        app.state.job_service = self.service
        self.client = TestClient(app)
        self.secret_file = tmp_path / "secret.txt"
        self.secret_file.write_bytes(SECRET)

    def add_job(self, job_id: str, status: JobStatus, **overrides) -> Job:
        job = Job(id=job_id, provider="ace-step", status=status, request=GenerationRequest(prompt="p"))
        job.provider_job_id = "8741640e-ace-step-task-id"
        for name, value in overrides.items():
            setattr(job, name, value)
        self.repository.create(job)
        return job

    def add_completed_job(self, job_id: str = "tunora-a", content: bytes = AUDIO_BYTES, **audio_overrides) -> Job:
        source = self.tmp_path / f"{job_id}-source.mp3"
        source.write_bytes(content)
        stored = self.storage.save(source, job_id=job_id, media_type="audio/mpeg") if content else None
        audio = {
            "key": f"{job_id}/{job_id}.mp3",
            "absolute_path": str(self.storage_root / job_id / f"{job_id}.mp3"),
            "filename": f"{job_id}.mp3",
            "media_type": "audio/mpeg",
            "size_bytes": stored.size_bytes if stored else 0,
        }
        audio.update(audio_overrides)
        return self.add_job(
            job_id,
            JobStatus.COMPLETED,
            result={
                "audio": audio,
                "duration": 10.0,
                "metadata": {
                    "bpm": 120,
                    "prompt": "p",
                    "audio_url": "http://127.0.0.1:8001/v1/audio?path=/tmp/x.mp3",
                    "audio_paths": ["/tmp/x.mp3"],
                },
            },
        )


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


# -- success ---------------------------------------------------------------


def test_completed_job_serves_audio(env):
    env.add_completed_job("tunora-a")
    response = env.client.get("/api/jobs/tunora-a/audio")

    assert response.status_code == 200
    assert response.content == AUDIO_BYTES
    assert len(response.content) > 0


def test_content_type_and_length_come_from_the_stored_artifact(env):
    env.add_completed_job("tunora-a")
    response = env.client.get("/api/jobs/tunora-a/audio")

    assert response.headers["content-type"] == "audio/mpeg"
    assert int(response.headers["content-length"]) == len(AUDIO_BYTES)
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"].startswith("inline")
    assert "tunora-a.mp3" in response.headers["content-disposition"]


def test_wav_artifact_uses_its_own_media_type(env):
    job = env.add_completed_job("tunora-w")
    job.result["audio"]["media_type"] = "audio/wav"
    env.repository.update(job)

    assert env.client.get("/api/jobs/tunora-w/audio").headers["content-type"] == "audio/wav"


def test_range_requests_are_supported_by_the_existing_response_class(env):
    env.add_completed_job("tunora-a")
    response = env.client.get("/api/jobs/tunora-a/audio", headers={"Range": "bytes=10-19"})

    assert response.status_code == 206
    assert response.content == AUDIO_BYTES[10:20]
    assert response.headers["content-range"] == f"bytes 10-19/{len(AUDIO_BYTES)}"
    assert response.headers["accept-ranges"] == "bytes"


def test_client_supplied_path_parameters_are_ignored(env):
    env.add_completed_job("tunora-a")
    for query in (
        f"?path={env.secret_file}",
        "?path=../../secret.txt",
        "?file=C:\\Windows\\win.ini",
        "?key=../secret.txt",
    ):
        response = env.client.get(f"/api/jobs/tunora-a/audio{query}")
        assert response.status_code == 200
        assert response.content == AUDIO_BYTES
        assert SECRET not in response.content


# -- state behaviour ------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [JobStatus.CREATED, JobStatus.SUBMITTED, JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.FAILED],
)
def test_non_completed_jobs_have_no_audio(env, status):
    env.add_job("tunora-x", status, error="Failed to store: C:\\secret\\path.mp3")
    response = env.client.get("/api/jobs/tunora-x/audio")

    assert response.status_code == 409
    assert "C:\\" not in response.text
    assert "secret" not in response.text


def test_unknown_job_is_404(env):
    assert env.client.get("/api/jobs/tunora-nope/audio").status_code == 404


def test_completed_job_without_a_result_is_a_safe_integrity_error(env):
    env.add_job("tunora-x", JobStatus.COMPLETED, result=None)
    response = env.client.get("/api/jobs/tunora-x/audio")
    assert response.status_code == 500
    assert response.json() == {"detail": "Audio is unavailable."}


def test_completed_job_with_deleted_file_is_a_safe_integrity_error(env):
    env.add_completed_job("tunora-a")
    (env.storage_root / "tunora-a" / "tunora-a.mp3").unlink()

    response = env.client.get("/api/jobs/tunora-a/audio")

    assert response.status_code == 500
    assert response.json() == {"detail": "Audio is unavailable."}
    assert str(env.storage_root) not in response.text


def test_completed_job_with_empty_file_is_a_safe_integrity_error(env):
    env.add_completed_job("tunora-a")
    (env.storage_root / "tunora-a" / "tunora-a.mp3").write_bytes(b"")
    assert env.client.get("/api/jobs/tunora-a/audio").status_code == 500


@pytest.mark.parametrize("error", [StorageWriteError("disk exploded at C:\\x"), OSError("permission denied /root/x")])
def test_storage_read_failure_is_a_safe_error(env, monkeypatch, error):
    env.add_completed_job("tunora-a")

    def boom(key):
        raise error

    monkeypatch.setattr(env.storage, "get_path", boom)
    response = env.client.get("/api/jobs/tunora-a/audio")

    assert response.status_code == 500
    assert response.json() == {"detail": "Audio is unavailable."}


def test_non_audio_media_type_in_the_record_is_never_served(env):
    job = env.add_completed_job("tunora-a")
    job.result["audio"]["media_type"] = "text/html"
    env.repository.update(job)
    assert env.client.get("/api/jobs/tunora-a/audio").status_code == 500


# -- security -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "tampered_key",
    [
        "../secret.txt",
        "../../secret.txt",
        "tunora-a/../../secret.txt",
        "tunora-a/../../../secret.txt",
        "..%2f..%2fsecret.txt",
        "%2e%2e/%2e%2e/secret.txt",
        "C:\\Windows\\win.ini",
        "C:/Windows/win.ini",
        "\\\\server\\share\\x.mp3",
        "//server/share/x.mp3",
        "/etc/passwd",
        "",
    ],
)
def test_tampered_artifact_keys_are_never_served(env, tampered_key):
    job = env.add_completed_job("tunora-a")
    job.result["audio"]["key"] = tampered_key
    env.repository.update(job)

    response = env.client.get("/api/jobs/tunora-a/audio")

    assert response.status_code == 500
    assert SECRET not in response.content
    assert AUDIO_BYTES not in response.content
    assert response.json() == {"detail": "Audio is unavailable."}


def test_a_job_can_not_serve_another_jobs_artifact(env):
    env.add_completed_job("tunora-a", content=b"A-AUDIO-BYTES" * 50)
    job_b = env.add_completed_job("tunora-b", content=b"B-AUDIO-BYTES" * 50)
    job_b.result["audio"]["key"] = "tunora-a/tunora-a.mp3"
    env.repository.update(job_b)

    response = env.client.get("/api/jobs/tunora-b/audio")

    assert response.status_code == 500
    assert b"A-AUDIO-BYTES" not in response.content


@pytest.mark.parametrize(
    "job_id",
    ["..%2f..%2fsecret", "%2e%2e%2f%2e%2e%2fsecret.txt", "..%5c..%5csecret", "C%3A%5CWindows%5Cwin.ini", "%2Fetc%2Fpasswd"],
)
def test_traversal_in_the_job_id_never_reaches_the_filesystem(env, job_id):
    env.add_completed_job("tunora-a")
    response = env.client.get(f"/api/jobs/{job_id}/audio")

    assert response.status_code in (404, 405)
    assert SECRET not in response.content
    assert AUDIO_BYTES not in response.content


# -- public contract ------------------------------------------------------------------


def test_public_job_result_is_an_allowlist_of_safe_fields(env):
    env.add_completed_job("tunora-a")
    body = env.client.get("/api/jobs/tunora-a").json()

    assert body["status"] == "COMPLETED"
    assert set(body["result"].keys()) == {"audio", "duration", "metadata"}
    assert set(body["result"]["audio"].keys()) == {"key", "filename", "media_type", "size_bytes", "audio_url"}
    assert body["result"]["audio"]["audio_url"] == "/api/jobs/tunora-a/audio"
    assert body["result"]["audio"]["key"] == "tunora-a/tunora-a.mp3"
    assert body["result"]["audio"]["size_bytes"] == len(AUDIO_BYTES)
    assert set(body["result"]["metadata"].keys()) <= {"bpm", "genres", "key_scale", "time_signature", "prompt", "lyrics"}


def test_public_response_never_exposes_paths_provider_ids_or_ace_step_urls(env):
    env.add_completed_job("tunora-a")
    for url in ("/api/jobs/tunora-a", "/api/jobs"):
        text = env.client.get(url).text
        assert str(env.tmp_path) not in text
        assert str(env.storage_root) not in text
        assert "absolute_path" not in text
        assert "/v1/audio" not in text
        assert "8001" not in text
        assert "8741640e" not in text
        assert "audio_paths" not in text
        assert "/tmp/x.mp3" not in text
        assert "provider_job_id" not in text


def test_failed_job_returns_a_fixed_message_and_no_result(env):
    env.add_job("tunora-f", JobStatus.FAILED, error="Failed to store generated audio: C:\\Users\\x\\.cache\\a.mp3")
    body = env.client.get("/api/jobs/tunora-f").json()

    assert body["error"] == "Generation failed."
    assert body["result"] is None
    assert "C:\\" not in json.dumps(body)


@pytest.mark.parametrize("status", [JobStatus.CREATED, JobStatus.SUBMITTED, JobStatus.QUEUED, JobStatus.RUNNING])
def test_in_progress_jobs_have_no_result_and_no_error(env, status):
    env.add_job("tunora-p", status)
    body = env.client.get("/api/jobs/tunora-p").json()
    assert body["result"] is None
    assert body["error"] is None


# -- Step 18: user-facing filename is sanitized at the boundary ----------------------

_SAFE_DISPOSITION = re.compile(r'^inline; filename="[A-Za-z0-9][A-Za-z0-9._-]*\.(mp3|wav|flac|ogg|opus|aac)"$')


@pytest.mark.parametrize(
    "stored_filename",
    [
        "../../secret.mp3",
        "..\..\secret.mp3",
        "song\r\nSet-Cookie: pwned=1.mp3",
        "song\rinjected.mp3",
        "song\ninjected.mp3",
        'x"; filename="evil.exe.mp3',
        "C:\Windows\win.ini",
        "/etc/passwd",
        "sóng ✓ 歌.mp3",
        "a" * 400 + ".mp3",
    ],
)
def test_content_disposition_and_public_filename_are_safe_for_any_stored_filename(env, stored_filename):
    job = env.add_completed_job("tunora-a")
    job.result["audio"]["filename"] = stored_filename
    env.repository.update(job)

    response = env.client.get("/api/jobs/tunora-a/audio")
    public = env.client.get("/api/jobs/tunora-a").json()["result"]["audio"]["filename"]

    assert response.status_code == 200
    assert response.content == AUDIO_BYTES  # bytes unchanged
    disposition = response.headers["content-disposition"]
    assert _SAFE_DISPOSITION.match(disposition), disposition
    assert "\r" not in disposition and "\n" not in disposition
    assert "set-cookie" not in {k.lower() for k in response.headers}
    assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.(mp3|wav|flac|ogg|opus|aac)", public), public
    assert public in disposition  # one filename contract for the header and the API


def test_range_and_headers_still_work_with_a_sanitized_filename(env):
    job = env.add_completed_job("tunora-a")
    job.result["audio"]["filename"] = "../../evil\r\n.mp3"
    env.repository.update(job)

    ranged = env.client.get("/api/jobs/tunora-a/audio", headers={"Range": "bytes=0-99"})

    assert ranged.status_code == 206
    assert ranged.content == AUDIO_BYTES[:100]
    assert ranged.headers["content-range"] == f"bytes 0-99/{len(AUDIO_BYTES)}"
    assert ranged.headers["content-length"] == "100"
    assert ranged.headers["content-type"] == "audio/mpeg"
    assert ranged.headers["etag"]
    assert ranged.headers["accept-ranges"] == "bytes"
    assert ranged.headers["x-content-type-options"] == "nosniff"


def test_a_client_can_not_choose_the_filename_or_the_disposition(env):
    env.add_completed_job("tunora-a")
    for query in (
        "?filename=evil.exe",
        "?filename=../../etc/passwd",
        "?download=1&filename=%0d%0aSet-Cookie:x=1",
        "?disposition=attachment",
        "?name=evil.mp3",
    ):
        response = env.client.get(f"/api/jobs/tunora-a/audio{query}")
        assert response.status_code == 200
        assert response.headers["content-disposition"] == 'inline; filename="tunora-a.mp3"'
        assert response.content == AUDIO_BYTES


def test_download_by_a_completed_job_is_the_same_trusted_route_and_bytes(env):
    env.add_completed_job("tunora-a")
    body = env.client.get("/api/jobs/tunora-a").json()["result"]["audio"]
    saved = env.client.get(body["audio_url"])

    assert saved.status_code == 200
    assert saved.content == AUDIO_BYTES
    assert len(saved.content) == body["size_bytes"] == int(saved.headers["content-length"])
    assert body["filename"] == "tunora-a.mp3"


# -- Milestone: titles + library query -------------------------------------------------------


def _completed(env, job_id, prompt, title="", minutes_ago=0):
    from datetime import datetime, timedelta, timezone

    job = env.add_completed_job(job_id)
    job.request = GenerationRequest(prompt=prompt)
    job.title = title
    job.created_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    env.repository.update(job)
    return job


def test_response_title_is_provided_or_derived_never_the_job_id(env):
    _completed(env, "tunora-a", "warm cinematic piano ballad with strings", title="")
    _completed(env, "tunora-b", "ignored", title="My Anthem")
    a = env.client.get("/api/jobs/tunora-a").json()
    b = env.client.get("/api/jobs/tunora-b").json()
    assert a["title"] == "Warm cinematic piano ballad with strings"
    assert b["title"] == "My Anthem"
    assert "tunora-a" not in a["title"]


def test_library_query_filters_by_status_search_and_sort(env):
    _completed(env, "tunora-1", "sad piano ballad", "Rainy Day", minutes_ago=30)
    _completed(env, "tunora-2", "upbeat dance", "Aurora", minutes_ago=10)
    _completed(env, "tunora-3", "cinematic theme", "Zenith", minutes_ago=20)
    env.add_job("tunora-run", JobStatus.RUNNING)

    def ids(query):
        return [j["id"] for j in env.client.get(f"/api/jobs?{query}").json()]

    assert ids("status=COMPLETED") == ["tunora-2", "tunora-3", "tunora-1"]  # newest first
    assert ids("status=completed&sort=oldest") == ["tunora-1", "tunora-3", "tunora-2"]
    assert ids("status=COMPLETED&sort=title") == ["tunora-2", "tunora-1", "tunora-3"]
    assert ids("status=COMPLETED&q=piano") == ["tunora-1"]  # matches the prompt
    assert ids("status=COMPLETED&q=AURORA") == ["tunora-2"]  # case-insensitive title
    assert ids("status=COMPLETED&q=nothing-matches") == []
    assert "tunora-run" in ids("")  # no filter -> everything


def test_library_query_rejects_bad_parameters_without_touching_the_filesystem(env):
    assert env.client.get("/api/jobs?status=BOGUS").status_code == 422
    assert env.client.get("/api/jobs?sort=../../etc/passwd").status_code == 422
    assert env.client.get("/api/jobs?limit=0").status_code == 422
    assert env.client.get("/api/jobs?limit=9999").status_code == 422
    assert env.client.get("/api/jobs?q=" + "x" * 101).status_code == 422


def test_library_listing_never_exposes_paths_or_provider_ids(env):
    _completed(env, "tunora-1", "p", "T")
    text = env.client.get("/api/jobs?status=COMPLETED").text
    assert str(env.tmp_path) not in text
    for leaked in ("absolute_path", "/v1/audio", "8741640e", "provider_job_id", "8001"):
        assert leaked not in text
