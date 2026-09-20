"""JobService + Song/Version: creation flow, regeneration, failure paths, transaction boundaries, API."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router
from app.jobs.models import JobStatus
from app.jobs.repository import SqliteJobRepository
from app.jobs.service import JobService
from app.providers.base import (
    GenerationJob,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
    JobState,
)
from app.providers.errors import ProviderUnavailableError
from app.songs.errors import InvalidIdError, SongNotFoundError
from app.storage.errors import StorageWriteError
from app.storage.local import LocalAudioStorage
from tests.jobs.fakes import FakeAudioStorage, FakeProvider

ACE_ID = "8741640e-ace-step-task-id"


class Harness:
    def __init__(self, tmp_path, storage=None):
        self.db = tmp_path / "tunora.db"
        self.tmp_path = tmp_path
        self.repository = SqliteJobRepository(self.db)
        self.provider = FakeProvider()
        self.provider.generate_response = GenerationJob(job_id=ACE_ID, provider="ace-step", status=JobState.QUEUED)
        self.storage = storage or LocalAudioStorage(tmp_path / "audio")
        self.service = JobService(
            repository=self.repository, provider=self.provider, storage=self.storage, poll_interval_seconds=0.0
        )

    def source_audio(self, name: str, content: bytes) -> str:
        path = self.tmp_path / name
        path.write_bytes(content)
        return str(path)

    async def generate_to_completion(self, prompt="a song", *, song_id=None, content=b"ID3-audio-bytes", **spec):
        job = await self.service.create_and_submit(GenerationRequest(prompt=prompt, **spec), song_id=song_id)
        self.provider.status_responses = [GenerationStatus(job_id=ACE_ID, status=JobState.SUCCEEDED)]
        self.provider.result_response = GenerationResult(
            job_id=ACE_ID, audio_path=self.source_audio(f"out-{job.id}.mp3", content), duration=12.5,
            metadata={"bpm": 100},
        )
        return await self.service.poll_once(job.id)


@pytest.fixture
def h(tmp_path):
    return Harness(tmp_path)


# -- creation and completion ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_new_generation_creates_song_version_1_and_a_submitted_job(h):
    job = await h.service.create_and_submit(
        GenerationRequest(prompt="warm cinematic ballad", lyrics="la", language="kn", duration=60.0, seed=3),
        title="  Evening  Rain ",
    )

    assert job.status == JobStatus.SUBMITTED and job.version_id
    version = h.repository.get_version(job.version_id)
    song = h.repository.get_song(version.song_id)
    assert (song.title, job.title) == ("Evening Rain", "Evening Rain")
    assert version.version_number == 1 and version.provider == "fake"
    assert version.spec == GenerationRequest(prompt="warm cinematic ballad", lyrics="la", language="kn", duration=60.0, seed=3)
    assert version.audio is None


@pytest.mark.asyncio
async def test_completion_attaches_the_stored_audio_to_the_version(h):
    job = await h.generate_to_completion("hello world", content=b"A" * 3000)

    assert job.status == JobStatus.COMPLETED
    audio = h.repository.get_version(job.version_id).audio
    assert audio.key == job.result["audio"]["key"] == f"{job.id}/{job.id}.mp3"
    assert (audio.media_type, audio.size_bytes, audio.duration) == ("audio/mpeg", 3000, 12.5)
    assert h.storage.get_path(audio.key).read_bytes() == b"A" * 3000
    # The existing audio contract still resolves from the job.
    assert h.service.resolve_audio(job.id).size_bytes == 3000


@pytest.mark.asyncio
async def test_a_second_generation_for_the_same_song_is_version_2_and_leaves_version_1_intact(h):
    first = await h.generate_to_completion("original idea", content=b"ONE" * 500, seed=1)
    v1_id = first.version_id
    song_id = h.repository.get_version(v1_id).song_id
    snapshot = h.repository.get_version(v1_id)
    v1_bytes = h.storage.get_path(snapshot.audio.key).read_bytes()

    second = await h.generate_to_completion("a different take", song_id=song_id, content=b"TWO" * 700, seed=2)

    v2 = h.repository.get_version(second.version_id)
    assert (snapshot.version_number, v2.version_number) == (1, 2)  # not 1, 1
    assert v2.song_id == song_id and second.id != first.id and v2.id != v1_id
    assert second.title == first.title  # a version of the same song keeps the song's title
    # Version 1: same record, same spec, same audio reference, same bytes on disk.
    assert h.repository.get_version(v1_id) == snapshot
    assert h.repository.get_version(v1_id).spec.prompt == "original idea"
    assert h.storage.get_path(snapshot.audio.key).read_bytes() == v1_bytes == b"ONE" * 500
    assert h.storage.get_path(v2.audio.key).read_bytes() == b"TWO" * 700
    assert v2.audio.key != snapshot.audio.key
    assert [v.version_number for v in h.service.list_versions(song_id)] == [1, 2]
    assert len({s for s in [h.repository.get_version(v).song_id for v in (v1_id, v2.id)]}) == 1  # one song, not two


@pytest.mark.asyncio
async def test_regenerating_an_unknown_or_malformed_song_is_refused_and_creates_nothing(h):
    with pytest.raises(SongNotFoundError):
        await h.service.create_and_submit(GenerationRequest(prompt="p"), song_id="song-does-not-exist")
    for bad in ("../../etc/passwd", "song-1' OR '1'='1", "a/b", "C:\\x", "x" * 200, ""):
        with pytest.raises(InvalidIdError):
            await h.service.create_and_submit(GenerationRequest(prompt="p"), song_id=bad)
    assert h.repository.list() == []
    assert h.provider.generate_calls == []  # never reached the provider


# -- provider independence + failure paths ---------------------------------------------------------


@pytest.mark.asyncio
async def test_the_provider_receives_only_the_provider_neutral_request(h):
    await h.service.create_and_submit(GenerationRequest(prompt="p", seed=5))
    (received,) = h.provider.generate_calls
    assert type(received) is GenerationRequest
    assert received == GenerationRequest(prompt="p", seed=5)  # no song or version ids leak to a provider


@pytest.mark.asyncio
async def test_provider_submission_failure_keeps_the_version_but_fails_the_job(h):
    h.provider.generate_response = ProviderUnavailableError("connection refused C:\\secret")

    job = await h.service.create_and_submit(GenerationRequest(prompt="p"))

    assert job.status == JobStatus.FAILED
    version = h.repository.get_version(job.version_id)
    assert version is not None and version.version_number == 1 and version.audio is None
    assert h.repository.get_song(version.song_id) is not None


@pytest.mark.asyncio
async def test_a_failed_version_still_consumes_its_number_and_the_next_one_continues(h):
    h.provider.generate_response = ProviderUnavailableError("down")
    failed = await h.service.create_and_submit(GenerationRequest(prompt="p"))
    song_id = h.repository.get_version(failed.version_id).song_id

    h.provider.generate_response = GenerationJob(job_id=ACE_ID, provider="ace-step", status=JobState.QUEUED)
    retry = await h.service.create_and_submit(GenerationRequest(prompt="p"), song_id=song_id)

    assert h.repository.get_version(retry.version_id).version_number == 2
    assert h.repository.get_version(failed.version_id).version_number == 1


@pytest.mark.asyncio
async def test_a_storage_failure_fails_the_job_and_attaches_no_audio(tmp_path):
    fake_storage = FakeAudioStorage()
    fake_storage.save_response = StorageWriteError("disk full C:\\x")
    h = Harness(tmp_path, storage=fake_storage)

    job = await h.generate_to_completion("p")

    assert job.status == JobStatus.FAILED and job.result is None
    assert h.repository.get_version(job.version_id).audio is None


@pytest.mark.asyncio
async def test_job_and_version_survive_an_application_restart_mid_generation(h):
    job = await h.service.create_and_submit(GenerationRequest(prompt="restart me", seed=9))
    del h.service, h.repository  # process exit after submission

    repository = SqliteJobRepository(h.db)
    restored = repository.get(job.id)
    assert restored.status == JobStatus.SUBMITTED and restored.provider_job_id == ACE_ID
    version = repository.get_version(restored.version_id)
    assert version.spec.seed == 9 and version.version_number == 1

    # The restarted service can finish it and the audio lands on the same version.
    service = JobService(repository=repository, provider=h.provider, storage=h.storage, poll_interval_seconds=0.0)
    h.provider.status_responses = [GenerationStatus(job_id=ACE_ID, status=JobState.SUCCEEDED)]
    h.provider.result_response = GenerationResult(
        job_id=ACE_ID, audio_path=h.source_audio("late.mp3", b"late-audio"), duration=3.0, metadata={}
    )
    done = await service.poll_once(job.id)
    assert done.status == JobStatus.COMPLETED
    assert repository.get_version(version.id).audio.key == f"{job.id}/{job.id}.mp3"


@pytest.mark.asyncio
async def test_no_database_transaction_is_held_open_while_waiting_for_the_provider(tmp_path):
    """The domain rows commit BEFORE the (slow) provider call: another writer can get in during it."""

    seen: dict[str, object] = {}

    class LockProbingProvider(FakeProvider):
        async def generate(self, request):
            probe = sqlite3.connect(tmp_path / "tunora.db", timeout=0.2)
            try:
                probe.execute("BEGIN IMMEDIATE")  # would raise "database is locked" if we still held a write lock
                seen["writer_got_in"] = True
                seen["rows_already_committed"] = probe.execute("SELECT COUNT(*) FROM versions").fetchone()[0]
                probe.rollback()
            finally:
                probe.close()
            return await super().generate(request)

    h = Harness(tmp_path)
    provider = LockProbingProvider()
    provider.generate_response = GenerationJob(job_id=ACE_ID, provider="ace-step", status=JobState.QUEUED)
    service = JobService(repository=h.repository, provider=provider, storage=h.storage, poll_interval_seconds=0.0)

    await service.create_and_submit(GenerationRequest(prompt="p"))

    assert seen == {"writer_got_in": True, "rows_already_committed": 1}


# -- HTTP API ------------------------------------------------------------------------------------------


def make_client(h: Harness) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.state.job_service = h.service
    return TestClient(app)


def post(client, h, prompt="a song", **extra):
    h.provider.status_responses = [GenerationStatus(job_id=ACE_ID, status=JobState.SUCCEEDED)]
    h.provider.result_response = GenerationResult(
        job_id=ACE_ID, audio_path=h.source_audio(f"o{len(list(h.tmp_path.iterdir()))}.mp3", (prompt * 400).encode()),
        duration=8.0, metadata={},
    )
    return client.post("/api/jobs", json={"prompt": prompt, **extra})


def test_api_creates_song_version_1_then_version_2_of_the_same_song(h):
    client = make_client(h)

    first = post(client, h, "first idea").json()
    second = post(client, h, "second idea", song_id=first["song_id"]).json()
    other = post(client, h, "unrelated").json()

    assert first["song_id"].startswith("song-") and first["version_id"].startswith("ver-")
    assert (first["version_number"], second["version_number"]) == (1, 2)
    assert second["song_id"] == first["song_id"] and second["version_id"] != first["version_id"]
    assert other["song_id"] != first["song_id"] and other["version_number"] == 1
    # Both finished (the background task ran) and both audio endpoints still work, with different bytes.
    a1 = client.get(f"/api/jobs/{first['id']}/audio")
    a2 = client.get(f"/api/jobs/{second['id']}/audio")
    assert a1.status_code == a2.status_code == 200 and a1.content != a2.content
    listing = {j["id"]: j for j in client.get("/api/jobs?status=COMPLETED").json()}
    assert listing[first["id"]]["version_number"] == 1 and listing[second["id"]]["version_number"] == 2


def test_api_rejects_unknown_and_malformed_song_ids_without_creating_anything(h):
    client = make_client(h)
    assert post(client, h, song_id="song-nope").status_code == 404
    for bad in ("../../etc/passwd", "..\\..\\x", "a/b", "C:\\Windows", "song-1' OR '1'='1", "x" * 81, "-x", "a b"):
        assert post(client, h, song_id=bad).status_code == 422, bad
    assert h.repository.list() == []


def test_api_responses_expose_only_tunora_ids_never_paths_or_provider_ids(h):
    client = make_client(h)
    post(client, h, "leak check")
    text = client.get("/api/jobs").text + client.get(f"/api/jobs/{client.get('/api/jobs').json()[0]['id']}").text
    for leaked in (str(h.tmp_path), "absolute_path", ACE_ID, "provider_job_id", "/v1/audio", "8001"):
        assert leaked not in text


def test_a_song_id_is_not_a_way_to_reach_another_songs_audio(h):
    client = make_client(h)
    a = post(client, h, "song a").json()
    b = post(client, h, "song b").json()
    # There is no version/audio route by song; job audio stays bound to its own job, whatever song is named.
    resp = client.get(f"/api/jobs/{b['id']}/audio", params={"song_id": a["song_id"], "version_id": a["version_id"]})
    assert resp.status_code == 200 and resp.content == client.get(f"/api/jobs/{b['id']}/audio").content
    assert resp.content != client.get(f"/api/jobs/{a['id']}/audio").content
    assert h.repository.get_version(a["version_id"]).song_id != h.repository.get_version(b["version_id"]).song_id
