"""Phase 17: 16-bit FLAC is the canonical output for new Versions.

The provider asks ACE-Step for `audio_format=flac` on every generation path, uploads derived-operation
sources under their real extension/type, and Tunora normalizes the FLAC media type; existing MP3
Versions keep working (mixed lineages), Phase 14's Extract model check and Phase 16's restart recovery
are unaffected by the format.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router as jobs_router
from app.api.routes_songs import router as songs_router
from app.jobs.models import JobStatus
from app.jobs.service import JobService
from app.providers.ace_step import AceStepMusicGenerationProvider
from app.providers.base import GenerationRequest
from app.storage.filenames import safe_audio_filename
from app.storage.media_types import guess_media_type
from tests.songs.test_operations import complete, first_version, op_url, wrap
from tests.songs.test_service_versions import Harness

BASE_URL = "http://127.0.0.1:8001"
ALL_OPS = frozenset({"ORIGINAL", "EXTEND", "REMIX", "REPAINT", "EXTRACT", "ANOTHER_TAKE"})


def _source_request(path, operation: str, **fields) -> GenerationRequest:
    return GenerationRequest(prompt="p", operation=operation, source_audio_path=str(path), source_duration=10.0, **fields)


def _fields_for(operation: str) -> dict:
    return {
        "EXTEND": dict(extend_seconds=10.0, duration=20.0),
        "REMIX": dict(remix_strength=0.7),
        "REPAINT": dict(repaint_start=3.0, repaint_end=7.0),
        "EXTRACT": dict(track_name="vocals"),
    }[operation]


async def _sent(provider, request):
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.post("/release_task").mock(return_value=httpx.Response(200, json=wrap({"task_id": "t1"})))
        await provider.generate(request)
    return route.calls.last.request


def _form(body: bytes, key: str) -> bool:
    return f'name="{key}"'.encode() in body


# -- provider: the format is requested on every generation path -------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["ORIGINAL", "ANOTHER_TAKE"])
async def test_text_to_music_paths_request_flac(operation):
    sent = await _sent(AceStepMusicGenerationProvider(base_url=BASE_URL), GenerationRequest(prompt="p", operation=operation))
    assert json.loads(sent.content)["audio_format"] == "flac"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["EXTEND", "REMIX", "REPAINT", "EXTRACT"])
async def test_source_based_operations_request_flac(tmp_path, operation):
    source = tmp_path / "v.flac"
    source.write_bytes(b"fLaC-source")
    sent = await _sent(AceStepMusicGenerationProvider(base_url=BASE_URL), _source_request(source, operation, **_fields_for(operation)))
    assert b'name="audio_format"\r\n\r\nflac\r\n' in sent.content


@pytest.mark.asyncio
async def test_the_format_is_one_provider_setting_and_mp3_stays_selectable(tmp_path):
    provider = AceStepMusicGenerationProvider(base_url=BASE_URL, audio_format="mp3")
    assert json.loads((await _sent(provider, GenerationRequest(prompt="p"))).content)["audio_format"] == "mp3"
    assert AceStepMusicGenerationProvider.DEFAULT_AUDIO_FORMAT == "flac"


@pytest.mark.parametrize("bad", ["wav", "wav32", "opus", "aac", "ogg", "", "FLAC ", "../x"])
def test_only_verified_formats_can_be_configured(bad):
    with pytest.raises(ValueError):
        AceStepMusicGenerationProvider(base_url=BASE_URL, audio_format=bad)


# -- provider: derived-operation sources are uploaded under their real name and type -----------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored,name,mime",
    [("v.flac", "source.flac", "audio/flac"), ("v.FLAC", "source.flac", "audio/flac"), ("v.mp3", "source.mp3", "audio/mpeg"),
     ("v.wav", "source.wav", None), ("v.weird", "source.mp3", "audio/mpeg")],
)
async def test_the_source_upload_uses_the_stored_files_real_extension_and_type(tmp_path, stored, name, mime):
    source = tmp_path / stored
    source.write_bytes(b"SRC-BYTES")
    sent = await _sent(AceStepMusicGenerationProvider(base_url=BASE_URL), _source_request(source, "REMIX", remix_strength=0.7))
    assert f'name="src_audio"; filename="{name}"'.encode() in sent.content
    if mime:
        assert f"Content-Type: {mime}\r\n\r\nSRC-BYTES".encode() in sent.content
    assert b"SRC-BYTES" in sent.content


# -- media types ---------------------------------------------------------------------------------------


def test_flac_is_normalized_whatever_the_platform_table_says(monkeypatch):
    monkeypatch.setattr("app.storage.media_types.mimetypes.guess_type", lambda _p: ("audio/x-flac", None))
    assert guess_media_type("a/b/x.flac") == "audio/flac"
    monkeypatch.setattr("app.storage.media_types.mimetypes.guess_type", lambda _p: ("audio/flac", None))
    assert guess_media_type("x.flac") == "audio/flac"


def test_other_media_types_are_left_alone(monkeypatch):
    assert guess_media_type("x.mp3") == "audio/mpeg"
    monkeypatch.setattr("app.storage.media_types.mimetypes.guess_type", lambda _p: ("audio/x-wav", None))
    assert guess_media_type("x.wav") == "audio/x-wav"  # no broad rewriting
    monkeypatch.setattr("app.storage.media_types.mimetypes.guess_type", lambda _p: (None, None))
    assert guess_media_type("x.opus") == "audio/opus" and guess_media_type("x.bin") == "application/octet-stream"


def test_the_public_filename_allowlist_covers_flac():
    assert safe_audio_filename("tunora-1.flac", job_id="j", media_type="audio/flac") == "tunora-1.flac"
    assert safe_audio_filename("../../evil.exe", job_id="j", media_type="audio/flac").endswith(".flac")
    assert safe_audio_filename("x.flac\r\nX: y", job_id="j", media_type="audio/flac").count("\n") == 0


# -- service + API: FLAC storage, content type, Range, mixed lineages --------------------------------------


@pytest.fixture
def h(tmp_path):
    harness = Harness(tmp_path)
    harness.provider.supported_operations = ALL_OPS
    return harness


@pytest.fixture
def client(h):
    app = FastAPI()
    app.include_router(jobs_router)
    app.include_router(songs_router)
    app.state.job_service = h.service
    return TestClient(app)


async def _complete_as(h, job, name: str, content: bytes):
    """Complete `job` with an output file called `name` (its extension decides the stored format)."""
    from app.providers.base import GenerationResult, GenerationStatus, JobState
    from tests.songs.test_service_versions import ACE_ID

    h.provider.status_responses = [GenerationStatus(job_id=ACE_ID, status=JobState.SUCCEEDED)]
    h.provider.result_response = GenerationResult(job_id=ACE_ID, audio_path=h.source_audio(name, content), duration=10.0, metadata={})
    return await h.service.poll_once(job.id)


@pytest.mark.asyncio
async def test_a_flac_generation_is_stored_and_served_as_flac(h, client):
    job = await h.service.create_and_submit(GenerationRequest(prompt="p"))
    done = await _complete_as(h, job, "out.flac", b"fLaC" + b"\x00" * 3000)

    audio = done.result["audio"]
    assert audio["filename"].endswith(".flac") and audio["media_type"] == "audio/flac" and audio["size_bytes"] == 3004
    assert h.storage.get_path(audio["key"]).name == f"{job.id}.flac"

    body = client.get(f"/api/jobs/{job.id}").json()
    assert body["result"]["audio"]["media_type"] == "audio/flac" and body["result"]["audio"]["filename"].endswith(".flac")
    full = client.get(f"/api/jobs/{job.id}/audio")
    assert (full.status_code, full.headers["content-type"], full.headers["accept-ranges"]) == (200, "audio/flac", "bytes")
    assert "etag" in full.headers and int(full.headers["content-length"]) == 3004
    part = client.get(f"/api/jobs/{job.id}/audio", headers={"Range": "bytes=10-19"})
    assert (part.status_code, part.headers["content-range"], part.content) == (206, "bytes 10-19/3004", full.content[10:20])
    version = client.get(f"/api/songs/{body['song_id']}").json()["versions"][0]["audio"]
    assert version["media_type"] == "audio/flac" and version["filename"].endswith(".flac")
    assert str(h.tmp_path) not in json.dumps(body) + json.dumps(version)  # no paths leak


@pytest.mark.asyncio
async def test_an_existing_mp3_version_is_unchanged_and_still_served_as_mp3(h, client):
    job, v1 = await first_version(h)  # completed as MP3 by the shared helper
    assert v1.audio.filename.endswith(".mp3") and v1.audio.media_type == "audio/mpeg"
    r = client.get(f"/api/jobs/{job.id}/audio")
    assert (r.status_code, r.headers["content-type"]) == (200, "audio/mpeg")
    assert client.get(f"/api/jobs/{job.id}/audio", headers={"Range": "bytes=0-9"}).status_code == 206


@pytest.mark.asyncio
async def test_mixed_lineages_mp3_then_flac_then_flac_and_flac_all_the_way(h):
    _, v1 = await first_version(h)  # MP3
    j2 = await h.service.create_version_from_operation(v1.song_id, v1.id, "ANOTHER_TAKE")
    assert h.provider.generate_calls[-1].source_audio_path is None
    j2 = await _complete_as(h, j2, "two.flac", b"fLaC-2" * 100)
    j3 = await h.service.create_version_from_operation(v1.song_id, j2.version_id, "REMIX", prompt="darker")
    assert h.provider.generate_calls[-1].source_audio_path.endswith(".flac")  # the FLAC Version is the source
    j3 = await _complete_as(h, j3, "three.flac", b"fLaC-3" * 100)
    j4 = await h.service.create_version_from_operation(v1.song_id, v1.id, "REPAINT", prompt="pad", repaint_start=1, repaint_end=5)
    assert h.provider.generate_calls[-1].source_audio_path.endswith(".mp3")  # the old MP3 Version still works as a source
    j4 = await _complete_as(h, j4, "four.flac", b"fLaC-4" * 100)

    versions = {v.version_number: v for v in h.repository.list_versions(v1.song_id)}
    assert [versions[n].audio.filename.rsplit(".", 1)[-1] for n in (1, 2, 3, 4)] == ["mp3", "flac", "flac", "flac"]
    assert [versions[n].operation for n in (1, 2, 3, 4)] == ["ORIGINAL", "ANOTHER_TAKE", "REMIX", "REPAINT"]
    assert [versions[n].source_version_id for n in (1, 2, 3, 4)] == [None, v1.id, j2.version_id, v1.id]
    assert (j3.status, j4.status) == (JobStatus.COMPLETED, JobStatus.COMPLETED)


# -- Phase 14 / Phase 16: the format is orthogonal ------------------------------------------------------------


def _wrap(data):
    return wrap(data)


def _result(path: str, **item):
    entry = {"file": f"/v1/audio?path={path}", "status": 1, "stage": "succeeded", "metas": {}, **item}
    return wrap([{"task_id": "task-x", "result": json.dumps([entry]), "status": 1}])


def _real_service(h):
    return JobService(repository=h.repository, provider=AceStepMusicGenerationProvider(base_url=BASE_URL), storage=h.storage, poll_interval_seconds=0.0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields,expected",
    [({"dit_model": "acestep-v15-base"}, JobStatus.COMPLETED), ({"dit_model": "acestep-v15-turbo"}, JobStatus.FAILED), ({}, JobStatus.FAILED)],
)
async def test_extract_with_a_flac_result_still_needs_the_base_model(tmp_path, fields, expected):
    h = Harness(tmp_path)
    _, v1 = await first_version(h)
    service = _real_service(h)
    produced = tmp_path / "vocals.flac"
    produced.write_bytes(b"fLaC-stem" * 50)
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/release_task").mock(return_value=httpx.Response(200, json=wrap({"task_id": "task-x"})))
        job = await service.create_version_from_operation(v1.song_id, v1.id, "EXTRACT", track_name="vocals")
        mock.post("/query_result").mock(return_value=httpx.Response(200, json=_result(str(produced), **fields)))
        job = await service.poll_once(job.id)
    assert job.status is expected
    version = h.repository.get_version(job.version_id)
    assert (version.audio is not None) is (expected is JobStatus.COMPLETED)
    if version.audio:
        assert version.audio.filename.endswith(".flac") and version.audio.media_type == "audio/flac"


@pytest.mark.asyncio
async def test_a_flac_generation_recovers_after_a_backend_restart_without_a_second_submission(tmp_path):
    h = Harness(tmp_path)
    produced = tmp_path / "song.flac"
    produced.write_bytes(b"fLaC-song" * 80)
    with respx.mock(base_url=BASE_URL) as mock:
        submit = mock.post("/release_task").mock(return_value=httpx.Response(200, json=wrap({"task_id": "task-x"})))
        old = _real_service(h)
        job = await old.create_and_submit(GenerationRequest(prompt="restart me"))  # the process 'dies' here
        assert json.loads(submit.calls.last.request.content)["audio_format"] == "flac"

        restarted = _real_service(h)
        mock.post("/query_result").mock(return_value=httpx.Response(200, json=_result(str(produced))))
        summary = await restarted.recover_unfinished_jobs()
        await restarted.recover_unfinished_jobs()  # a second restart changes nothing

    done = h.repository.get(job.id)
    assert done.status is JobStatus.COMPLETED and summary["completed"] == 1
    assert submit.call_count == 1  # never resubmitted
    version = h.repository.get_version(done.version_id)
    assert version.audio.filename.endswith(".flac") and version.audio.media_type == "audio/flac"
    assert len(h.repository.list_versions(version.song_id)) == 1


@pytest.mark.asyncio
async def test_the_source_versions_lineage_and_bytes_are_untouched_by_a_flac_derivation(h):
    _, v1 = await first_version(h)
    before = (h.repository.get_version(v1.id), h.storage.get_path(v1.audio.key).read_bytes())
    job = await h.service.create_version_from_operation(v1.song_id, v1.id, "REMIX", prompt="warmer")
    await _complete_as(h, job, "r.flac", b"fLaC-r" * 50)
    assert (h.repository.get_version(v1.id), h.storage.get_path(v1.audio.key).read_bytes()) == before


def test_the_app_wires_the_configured_format_into_the_provider(monkeypatch, tmp_path):
    import app.main as main

    monkeypatch.setattr(main, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(main, "STORAGE_ROOT", str(tmp_path / "audio"))
    for configured in ("flac", "mp3"):
        monkeypatch.setattr(main, "AUDIO_FORMAT", configured)
        with TestClient(main.create_app()) as client:
            assert client.app.state.provider._audio_format == configured  # noqa: SLF001
    assert main.AceStepMusicGenerationProvider.DEFAULT_AUDIO_FORMAT == "flac"
