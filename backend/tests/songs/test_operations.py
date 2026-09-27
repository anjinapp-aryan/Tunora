"""Phase 5B: Extend / Remix / Repaint create NEW versions; the source version is never touched."""

from __future__ import annotations

import asyncio
import hashlib
import math
import sqlite3
import threading

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router as jobs_router
from app.api.routes_songs import router as songs_router
from app.jobs import migrations
from app.jobs.models import JobStatus
from app.jobs.repository import SqliteJobRepository
from app.providers.ace_step import AceStepMusicGenerationProvider
from app.providers.base import GenerationJob, GenerationRequest, GenerationResult, GenerationStatus, JobState
from app.providers.errors import ProviderUnavailableError, UnsupportedOperationError
from app.songs.errors import (
    InvalidIdError,
    InvalidOperationError,
    SongNotFoundError,
    SourceAudioUnavailableError,
    SourceVersionNotFoundError,
)
from app.storage.errors import StorageWriteError
from tests.jobs.fakes import FakeAudioStorage
from tests.songs.test_domain import new_generation
from tests.songs.test_service_versions import ACE_ID, Harness

ALL_OPS = frozenset({"ORIGINAL", "EXTEND", "REMIX", "REPAINT"})


@pytest.fixture
def h(tmp_path):
    harness = Harness(tmp_path)
    harness.provider.supported_operations = ALL_OPS
    return harness


def sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def complete(h: Harness, job, *, duration=12.5, content=b"NEW-AUDIO-BYTES"):
    h.provider.status_responses = [GenerationStatus(job_id=ACE_ID, status=JobState.SUCCEEDED)]
    h.provider.result_response = GenerationResult(
        job_id=ACE_ID, audio_path=h.source_audio(f"out-{job.id}.mp3", content), duration=duration, metadata={}
    )
    return await h.service.poll_once(job.id)


async def first_version(h: Harness, prompt="warm piano ballad", *, duration=12.5, **spec):
    """A completed ORIGINAL version whose stored audio is 12.5 s long."""

    job = await h.service.create_and_submit(GenerationRequest(prompt=prompt, **spec), title="I Will Rise")
    job = await complete(h, job, duration=duration, content=b"SOURCE-AUDIO" * 100)
    version = h.repository.get_version(job.version_id)
    return job, version


# -- the operations create NEW versions and read the source --------------------------------------------


@pytest.mark.asyncio
async def test_extend_creates_version_2_from_version_1_without_touching_version_1(h):
    j1, v1 = await first_version(h, seed=5)
    src_path = h.storage.get_path(v1.audio.key)
    before = (sha(src_path), src_path.stat().st_size, h.repository.get_version(v1.id))

    job = await h.service.create_version_from_operation(v1.song_id, v1.id, "EXTEND", extend_seconds=20)

    v2 = h.repository.get_version(job.version_id)
    assert (v2.version_number, v2.song_id, v2.operation, v2.source_version_id) == (2, v1.song_id, "EXTEND", v1.id)
    assert v2.operation_params == {"extend_seconds": 20.0}
    assert job.status == JobStatus.SUBMITTED and job.id != j1.id
    # The provider was given the source audio and the extension, in provider-neutral terms.
    request = h.provider.generate_calls[-1]
    assert (request.operation, request.extend_seconds, request.source_duration) == ("EXTEND", 20.0, 12.5)
    assert request.duration == 32.5 and request.source_audio_path == str(src_path)
    assert request.prompt == "warm piano ballad" and request.seed == 5  # inherited from the source
    # Nothing internal is persisted: no source path in the job or the version snapshot.
    assert h.repository.get(job.id).request.source_audio_path is None
    assert v2.spec == GenerationRequest(prompt="warm piano ballad", duration=32.5, seed=5)

    done = await complete(h, job, duration=32.5, content=b"EXTENDED" * 200)
    v2 = h.repository.get_version(done.version_id)
    assert v2.audio.key != v1.audio.key and v2.audio.key == f"{done.id}/{done.id}.mp3"
    assert v2.audio.duration == 32.5 and h.storage.get_path(v2.audio.key).read_bytes() == b"EXTENDED" * 200
    # Version 1: same record, same file, same bytes, same key.
    assert h.repository.get_version(v1.id) == before[2]
    assert (sha(src_path), src_path.stat().st_size) == before[:2]


@pytest.mark.asyncio
async def test_remix_uses_the_new_description_and_source_settings(h):
    _, v1 = await first_version(h, lyrics="[Verse] hello", language="kn", seed=9)
    job = await h.service.create_version_from_operation(
        v1.song_id, v1.id, "REMIX", prompt="  more acoustic and intimate ", remix_strength=0.85
    )

    v2 = h.repository.get_version(job.version_id)
    assert (v2.operation, v2.source_version_id, v2.version_number) == ("REMIX", v1.id, 2)
    assert v2.operation_params == {"remix_strength": 0.85}
    request = h.provider.generate_calls[-1]
    assert (request.operation, request.remix_strength) == ("REMIX", 0.85)
    assert request.prompt == "more acoustic and intimate"
    assert (request.lyrics, request.language, request.seed) == ("[Verse] hello", "kn", 9)
    assert request.source_audio_path == str(h.storage.get_path(v1.audio.key))
    assert v2.spec.prompt == "more acoustic and intimate" and v1.spec.prompt == "warm piano ballad"


@pytest.mark.asyncio
async def test_remix_defaults_the_strength_and_keeps_the_source_length_when_the_provider_reports_none(h):
    _, v1 = await first_version(h)
    job = await h.service.create_version_from_operation(v1.song_id, v1.id, "REMIX", prompt="darker")
    assert h.repository.get_version(job.version_id).operation_params == {"remix_strength": 0.7}
    done = await complete(h, job, duration=None)  # ACE-Step reports "N/A" for cover results
    assert h.repository.get_version(done.version_id).audio.duration == 12.5
    assert done.result["duration"] == 12.5


@pytest.mark.asyncio
async def test_repaint_records_the_region_and_preserves_the_source(h):
    _, v1 = await first_version(h)
    src_path = h.storage.get_path(v1.audio.key)
    src_hash = sha(src_path)

    job = await h.service.create_version_from_operation(
        v1.song_id, v1.id, "REPAINT", prompt="sudden drums", lyrics="new words", repaint_start=4, repaint_end=8
    )

    v2 = h.repository.get_version(job.version_id)
    assert (v2.operation, v2.source_version_id) == ("REPAINT", v1.id)
    assert v2.operation_params == {"repaint_start": 4.0, "repaint_end": 8.0}
    request = h.provider.generate_calls[-1]
    assert (request.repaint_start, request.repaint_end, request.lyrics) == (4.0, 8.0, "new words")
    done = await complete(h, job, duration=None)
    assert h.repository.get_version(done.version_id).audio.duration == 12.5  # repaint keeps the length
    assert sha(src_path) == src_hash


@pytest.mark.asyncio
async def test_lineage_can_branch_and_chain(h):
    _, v1 = await first_version(h)
    j2 = await h.service.create_version_from_operation(v1.song_id, v1.id, "EXTEND", extend_seconds=10)
    j2 = await complete(h, j2, duration=22.5)
    j3 = await h.service.create_version_from_operation(v1.song_id, v1.id, "REMIX", prompt="darker")  # branch from v1
    j3 = await complete(h, j3, duration=12.5)
    j4 = await h.service.create_version_from_operation(v1.song_id, j2.version_id, "REPAINT", prompt="x", repaint_start=1, repaint_end=5)

    versions = {v.version_number: v for v in h.repository.list_versions(v1.song_id)}
    assert [versions[n].operation for n in (1, 2, 3, 4)] == ["ORIGINAL", "EXTEND", "REMIX", "REPAINT"]
    assert [versions[n].source_version_id for n in (1, 2, 3, 4)] == [None, v1.id, v1.id, j2.version_id]
    assert h.repository.get_version(j4.version_id).version_number == 4


# -- validation -----------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("seconds", [None, 0, 4.9, 90.1, -5, math.nan, math.inf, "10", True])
async def test_extend_rejects_bad_lengths_and_creates_nothing(h, seconds):
    _, v1 = await first_version(h)
    jobs_before = len(h.repository.list())
    with pytest.raises(InvalidOperationError):
        await h.service.create_version_from_operation(v1.song_id, v1.id, "EXTEND", extend_seconds=seconds)
    assert len(h.repository.list()) == jobs_before and len(h.repository.list_versions(v1.song_id)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "start,end",
    [(None, 5), (2, None), (5, 5), (6, 5), (-1, 4), (0, 2.9), (0, 13), (0, 91), (math.nan, 5), (0, math.inf), ("1", 5)],
)
async def test_repaint_rejects_bad_regions(h, start, end):
    _, v1 = await first_version(h)
    with pytest.raises(InvalidOperationError):
        await h.service.create_version_from_operation(v1.song_id, v1.id, "REPAINT", prompt="x", repaint_start=start, repaint_end=end)
    assert len(h.repository.list_versions(v1.song_id)) == 1


@pytest.mark.asyncio
async def test_remix_and_repaint_require_a_description_and_a_valid_strength(h):
    _, v1 = await first_version(h)
    for prompt in (None, "", "   "):
        with pytest.raises(InvalidOperationError):
            await h.service.create_version_from_operation(v1.song_id, v1.id, "REMIX", prompt=prompt)
        with pytest.raises(InvalidOperationError):
            await h.service.create_version_from_operation(v1.song_id, v1.id, "REPAINT", prompt=prompt, repaint_start=1, repaint_end=5)
    for strength in (-0.1, 1.5, math.nan, "high"):
        with pytest.raises(InvalidOperationError):
            await h.service.create_version_from_operation(v1.song_id, v1.id, "REMIX", prompt="x", remix_strength=strength)
    with pytest.raises(InvalidOperationError):
        await h.service.create_version_from_operation(v1.song_id, v1.id, "DELETE", prompt="x")
    assert len(h.repository.list_versions(v1.song_id)) == 1


@pytest.mark.asyncio
async def test_a_source_of_unknown_length_cannot_be_extended_or_repainted(h):
    job = await h.service.create_and_submit(GenerationRequest(prompt="p"))
    job = await complete(h, job, duration=None)
    v1 = h.repository.get_version(job.version_id)
    assert v1.audio.duration is None
    with pytest.raises(InvalidOperationError, match="duration"):
        await h.service.create_version_from_operation(v1.song_id, v1.id, "EXTEND", extend_seconds=10)
    with pytest.raises(InvalidOperationError, match="duration"):
        await h.service.create_version_from_operation(v1.song_id, v1.id, "REPAINT", prompt="x", repaint_start=1, repaint_end=5)
    remix = await h.service.create_version_from_operation(v1.song_id, v1.id, "REMIX", prompt="x")  # remix needs no length
    assert h.repository.get_version(remix.version_id).version_number == 2


# -- ids, relationships, source availability ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_source_from_another_song_or_an_unknown_one_is_refused_and_creates_nothing(h):
    _, a1 = await first_version(h, "song a")
    _, b1 = await first_version(h, "song b")
    for song_id, version_id, error in [
        (a1.song_id, b1.id, SourceVersionNotFoundError),  # Song B's version through Song A
        (b1.song_id, a1.id, SourceVersionNotFoundError),
        (a1.song_id, "ver-does-not-exist", SourceVersionNotFoundError),
        ("song-does-not-exist", a1.id, SongNotFoundError),
    ]:
        with pytest.raises(error):
            await h.service.create_version_from_operation(song_id, version_id, "EXTEND", extend_seconds=10)
    for bad in ("../../etc/passwd", "..\\x", "a/b", "C:\\x", "ver-1' OR '1'='1", "x" * 81, "", "a b"):
        with pytest.raises(InvalidIdError):
            await h.service.create_version_from_operation(a1.song_id, bad, "EXTEND", extend_seconds=10)
        with pytest.raises(InvalidIdError):
            await h.service.create_version_from_operation(bad, a1.id, "EXTEND", extend_seconds=10)
    assert len(h.repository.list_versions(a1.song_id)) == 1 and len(h.repository.list_versions(b1.song_id)) == 1


@pytest.mark.asyncio
async def test_the_database_refuses_a_cross_song_source_even_if_the_service_were_bypassed(h, tmp_path):
    _, a1 = await first_version(h, "song a")
    _, b1 = await first_version(h, "song b")
    conn = sqlite3.connect(h.db)
    with pytest.raises(sqlite3.IntegrityError, match="same song"):
        conn.execute(
            "INSERT INTO versions (id, song_id, version_number, prompt, lyrics, language, instrumental, provider, "
            "created_at, source_version_id, operation) VALUES ('ver-x', ?, 9, 'p', '', 'en', 0, 'fake', "
            "'2026-01-01T00:00:00+00:00', ?, 'EXTEND')",
            (a1.song_id, b1.id),
        )
    conn.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("column,value", [("operation", "REMIX"), ("source_version_id", None), ("operation_params", "{}")])
async def test_lineage_is_immutable_in_the_database(h, column, value):
    _, v1 = await first_version(h)
    job = await h.service.create_version_from_operation(v1.song_id, v1.id, "EXTEND", extend_seconds=10)
    conn = sqlite3.connect(h.db)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute(f"UPDATE versions SET {column} = ? WHERE id = ?", (value, job.version_id))
    conn.close()


@pytest.mark.asyncio
async def test_a_source_without_audio_or_with_a_missing_file_is_refused(h):
    h.provider.generate_response = GenerationJob(job_id=ACE_ID, provider="ace-step", status=JobState.QUEUED)
    pending = await h.service.create_and_submit(GenerationRequest(prompt="p"))  # never completed: no audio
    pv = h.repository.get_version(pending.version_id)
    with pytest.raises(SourceAudioUnavailableError):
        await h.service.create_version_from_operation(pv.song_id, pv.id, "REMIX", prompt="x")

    _, v1 = await first_version(h)
    h.storage.get_path(v1.audio.key).unlink()  # the file disappeared after completion
    with pytest.raises(SourceAudioUnavailableError):
        await h.service.create_version_from_operation(v1.song_id, v1.id, "REMIX", prompt="x")
    assert len(h.repository.list_versions(v1.song_id)) == 1  # nothing was created


@pytest.mark.asyncio
async def test_a_provider_that_does_not_support_the_operation_is_refused_without_side_effects(tmp_path):
    h = Harness(tmp_path)  # default FakeProvider supports ORIGINAL only
    job = await h.service.create_and_submit(GenerationRequest(prompt="p"))
    job = await complete(h, job)
    v1 = h.repository.get_version(job.version_id)
    with pytest.raises(UnsupportedOperationError):
        await h.service.create_version_from_operation(v1.song_id, v1.id, "EXTEND", extend_seconds=10)
    assert len(h.repository.list_versions(v1.song_id)) == 1 and len(h.provider.generate_calls) == 1


# -- failure behaviour ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failed_operation_leaves_the_source_intact_and_the_new_version_without_audio(h):
    _, v1 = await first_version(h)
    src = h.storage.get_path(v1.audio.key)
    before = (sha(src), h.repository.get_version(v1.id))

    h.provider.generate_response = ProviderUnavailableError("ACE-Step down C:\\secret")
    job = await h.service.create_version_from_operation(v1.song_id, v1.id, "EXTEND", extend_seconds=10)

    assert job.status == JobStatus.FAILED
    failed = h.repository.get_version(job.version_id)
    assert failed.audio is None and failed.version_number == 2 and failed.operation == "EXTEND"
    assert (sha(src), h.repository.get_version(v1.id)) == before


@pytest.mark.asyncio
async def test_a_storage_failure_after_generation_fails_the_job_and_attaches_no_audio(tmp_path):
    h = Harness(tmp_path)
    h.provider.supported_operations = ALL_OPS
    _, v1 = await first_version(h)
    h.service._storage = FakeAudioStorage()  # noqa: SLF001 - swap storage AFTER the source exists on disk
    h.service._storage.get_path = lambda key: h.storage.get_path(key)  # source still readable
    h.service._storage.save_response = StorageWriteError("disk full")
    job = await h.service.create_version_from_operation(v1.song_id, v1.id, "REMIX", prompt="darker")
    job = await complete(h, job)
    assert job.status == JobStatus.FAILED and h.repository.get_version(job.version_id).audio is None
    assert h.repository.get_version(v1.id).audio is not None


@pytest.mark.asyncio
async def test_a_new_version_only_becomes_latest_once_it_has_audio(h):
    _, v1 = await first_version(h)
    job = await h.service.create_version_from_operation(v1.song_id, v1.id, "EXTEND", extend_seconds=10)
    (top,) = [e for e in h.service.song_details(v1.song_id)[1] if e.version.version_number == 2]
    assert top.version.audio is None  # generating: the API will not mark it Latest (see the API tests)
    await complete(h, job, duration=22.5)
    assert h.repository.get_version(job.version_id).audio is not None


# -- concurrency -------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_operations_on_one_song_never_produce_duplicate_version_numbers(h):
    _, v1 = await first_version(h)
    jobs = await asyncio.gather(
        *[h.service.create_version_from_operation(v1.song_id, v1.id, "REMIX", prompt=f"take {i}") for i in range(8)]
    )
    numbers = sorted(h.repository.get_version(j.version_id).version_number for j in jobs)
    assert numbers == list(range(2, 10))


def test_threaded_operation_creation_serializes_on_the_write_lock(tmp_path):
    repo = SqliteJobRepository(tmp_path / "tunora.db")
    song, v1, _ = new_generation(repo)
    numbers, errors = [], []
    barrier = threading.Barrier(10)

    def worker():
        try:
            barrier.wait()
            from app.songs.ids import new_version_id
            from app.songs.models import Version
            from app.jobs.models import Job

            version = Version(
                id=new_version_id(), song_id=song.id, spec=GenerationRequest(prompt="x"), provider="fake",
                operation="EXTEND", source_version_id=v1.id, operation_params={"extend_seconds": 10.0},
            )
            job = Job(id=f"tunora-{version.id}", provider="fake", status=JobStatus.CREATED, request=GenerationRequest(prompt="x"))
            numbers.append(repo.create_generation(new_song=None, version=version, job=job).version_number)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == [] and sorted(numbers) == list(range(2, 12))


# -- migration v3 ----------------------------------------------------------------------------------------------------


def test_version_lineage_migration_is_additive_and_repeat_safe(tmp_path):
    db = tmp_path / "v2.db"
    conn = sqlite3.connect(db)
    for target, step in ((1, migrations._to_v1), (2, migrations._to_v2)):  # noqa: SLF001
        migrations._run_step(conn, target, step)  # noqa: SLF001
    conn.execute(
        "INSERT INTO songs VALUES ('song-a', 'Old Song', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO versions (id, song_id, version_number, prompt, lyrics, language, instrumental, provider, created_at,"
        " audio_key, audio_filename, audio_media_type, audio_size_bytes) VALUES ('ver-a', 'song-a', 1, 'old', '', 'en', 0,"
        " 'ace-step', '2026-01-01T00:00:00+00:00', 'k/k.mp3', 'k.mp3', 'audio/mpeg', 5)"
    )
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    conn.close()

    repo = SqliteJobRepository(db)  # applies v3
    old = repo.get_version("ver-a")
    assert (old.operation, old.source_version_id, old.operation_params) == ("ORIGINAL", None, None)
    assert old.audio.key == "k/k.mp3" and old.spec.prompt == "old"  # nothing lost

    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(versions)")}
    assert {"operation", "source_version_id", "operation_params"} <= cols
    conn.execute("PRAGMA user_version = 2")  # even with the marker lost, re-running must not fail or duplicate
    conn.commit()
    migrations.migrate(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == migrations.LATEST_VERSION
    assert conn.execute("SELECT COUNT(*) FROM versions").fetchone()[0] == 1
    conn.close()


# -- HTTP API -------------------------------------------------------------------------------------------------------------


@pytest.fixture
def client(h):
    app = FastAPI()
    app.include_router(jobs_router)
    app.include_router(songs_router)
    app.state.job_service = h.service
    return TestClient(app)


def api_source(client, h):
    h.provider.generate_response = GenerationJob(job_id=ACE_ID, provider="ace-step", status=JobState.QUEUED)
    h.provider.status_responses = [GenerationStatus(job_id=ACE_ID, status=JobState.SUCCEEDED)]
    h.provider.result_response = GenerationResult(
        job_id=ACE_ID, audio_path=h.source_audio("api-src.mp3", b"API-SOURCE" * 100), duration=20.0, metadata={}
    )
    return client.post("/api/jobs", json={"prompt": "quiet piano", "title": "I Will Rise"}).json()


def op_url(job, op):
    return f"/api/songs/{job['song_id']}/versions/{job['version_id']}/{op}"


def queue_result(h, content, duration):
    h.provider.status_responses = [GenerationStatus(job_id=ACE_ID, status=JobState.SUCCEEDED)]
    h.provider.result_response = GenerationResult(
        job_id=ACE_ID, audio_path=h.source_audio(f"r{len(list(h.tmp_path.iterdir()))}.mp3", content), duration=duration, metadata={}
    )


def test_api_extend_remix_and_repaint_each_create_a_new_version_of_the_same_song(client, h):
    v1 = api_source(client, h)
    v1_bytes = client.get(f"/api/jobs/{v1['id']}/audio").content

    queue_result(h, b"EXT" * 300, 30.0)
    ext = client.post(op_url(v1, "extend"), json={"extend_seconds": 10}).json()
    queue_result(h, b"RMX" * 300, None)
    rmx = client.post(op_url(v1, "remix"), json={"prompt": "acoustic", "remix_strength": 0.6}).json()
    queue_result(h, b"RPT" * 300, None)
    rpt = client.post(op_url(v1, "repaint"), json={"prompt": "drums", "repaint_start": 5, "repaint_end": 10}).json()

    assert [j["version_number"] for j in (ext, rmx, rpt)] == [2, 3, 4]
    assert {j["song_id"] for j in (ext, rmx, rpt)} == {v1["song_id"]}
    assert len({v1["version_id"], ext["version_id"], rmx["version_id"], rpt["version_id"]}) == 4

    versions = client.get(f"/api/songs/{v1['song_id']}").json()["versions"]
    by_number = {v["version_number"]: v for v in versions}
    assert [v["version_number"] for v in versions] == [4, 3, 2, 1]
    assert [(by_number[n]["operation"], by_number[n]["source_version_number"]) for n in (1, 2, 3, 4)] == [
        ("ORIGINAL", None), ("EXTEND", 1), ("REMIX", 1), ("REPAINT", 1)
    ]
    assert [v["is_latest"] for v in versions] == [True, False, False, False]
    assert by_number[2]["duration"] == 30.0 and by_number[3]["duration"] == 20.0 and by_number[4]["duration"] == 20.0
    audio_bytes = {n: client.get(by_number[n]["audio"]["audio_url"]).content for n in (1, 2, 3, 4)}
    assert audio_bytes[1] == v1_bytes and len(set(audio_bytes.values())) == 4  # source unchanged, all distinct
    listing = client.get("/api/songs").json()["items"]
    assert len(listing) == 1 and listing[0]["version_count"] == 4 and listing[0]["latest_version"]["version_number"] == 4


def test_api_a_version_that_is_still_generating_or_failed_is_never_latest(client, h):
    v1 = api_source(client, h)
    h.provider.generate_response = ProviderUnavailableError("down")
    failed = client.post(op_url(v1, "remix"), json={"prompt": "x"}).json()
    assert failed["status"] == "FAILED"
    versions = client.get(f"/api/songs/{v1['song_id']}").json()["versions"]
    assert [(v["version_number"], v["is_latest"], v["audio"] is None) for v in versions] == [(2, False, True), (1, True, False)]
    assert versions[0]["operation"] == "REMIX" and versions[0]["source_version_number"] == 1


def test_api_errors_are_safe_and_specific(client, h):
    v1 = api_source(client, h)
    other = api_source(client, h)

    assert client.post(f"/api/songs/{v1['song_id']}/versions/{other['version_id']}/extend", json={"extend_seconds": 10}).status_code == 404
    assert client.post(f"/api/songs/song-nope/versions/{v1['version_id']}/extend", json={"extend_seconds": 10}).status_code == 404
    assert client.post(f"/api/songs/{v1['song_id']}/versions/ver-nope/extend", json={"extend_seconds": 10}).status_code == 404
    assert client.post(op_url(v1, "delete"), json={}).status_code == 422  # not an operation
    for bad_id in ("a'b", "a b", "x" * 81, "-x", "..%2F..%2Fetc"):
        assert client.post(f"/api/songs/{v1['song_id']}/versions/{bad_id}/extend", json={"extend_seconds": 10}).status_code in (404, 422), bad_id
        assert client.post(f"/api/songs/{bad_id}/versions/{v1['version_id']}/extend", json={"extend_seconds": 10}).status_code in (404, 422), bad_id
    for body, message in [
        ({}, "Extension length"),
        ({"extend_seconds": 1}, "Extend by between"),
        ({"extend_seconds": 1000}, "Extend by between"),
    ]:
        r = client.post(op_url(v1, "extend"), json=body)
        assert r.status_code == 422 and message in r.text
    assert client.post(op_url(v1, "remix"), json={}).status_code == 422
    assert client.post(op_url(v1, "repaint"), json={"prompt": "x", "repaint_start": 1, "repaint_end": 99}).status_code == 422
    assert client.post(op_url(v1, "extend"), json={"extend_seconds": "NaN"}).status_code == 422
    assert client.post(op_url(v1, "extend"), json={"extend_seconds": 10, "prompt": "x" * 1001}).status_code == 422
    (h.tmp_path / "audio" / v1["id"] / f"{v1['id']}.mp3").unlink()
    r = client.post(op_url(v1, "extend"), json={"extend_seconds": 10})
    assert r.status_code == 409 and r.json() == {"detail": "The source audio is unavailable."}
    assert len(client.get(f"/api/songs/{v1['song_id']}").json()["versions"]) == 1  # nothing was created


def test_api_unsupported_provider_operation_is_refused(tmp_path):
    h = Harness(tmp_path)  # ORIGINAL only
    app = FastAPI()
    app.include_router(jobs_router)
    app.include_router(songs_router)
    app.state.job_service = h.service
    client = TestClient(app)
    v1 = api_source(client, h)
    r = client.post(op_url(v1, "extend"), json={"extend_seconds": 10})
    assert r.status_code == 422 and "not supported" in r.text
    assert len(client.get(f"/api/songs/{v1['song_id']}").json()["versions"]) == 1


def test_api_responses_never_leak_the_source_path_or_provider_details(client, h):
    v1 = api_source(client, h)
    queue_result(h, b"EXT" * 100, 30.0)
    ext = client.post(op_url(v1, "extend"), json={"extend_seconds": 10})
    text = ext.text + client.get(f"/api/songs/{v1['song_id']}").text + client.get("/api/jobs").text + client.get("/api/songs").text
    for leaked in (str(h.tmp_path), "source_audio_path", "absolute_path", ACE_ID, "/v1/audio", "api-src.mp3"):
        assert leaked not in text, leaked
    songs_text = client.get(f"/api/songs/{v1['song_id']}").text + client.get("/api/songs").text
    assert "provider" not in songs_text and "fake" not in songs_text


# -- provider mapping (ACE-Step) -------------------------------------------------------------------------------------------


def wrap(data):
    return {"data": data, "code": 200, "error": None, "timestamp": 0, "extra": None}


def ace_request(tmp_path, **fields):
    src = tmp_path / "source.mp3"
    src.write_bytes(b"ID3-SOURCE-BYTES")
    return GenerationRequest(prompt="new take", source_audio_path=str(src), **fields)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields,expected",
    [
        (
            dict(operation="EXTEND", source_duration=10.0, extend_seconds=20.0, duration=30.0),
            {"task_type": "repaint", "audio_duration": "30.0", "repainting_start": "10.0", "repainting_end": "30.0", "chunk_mask_mode": "explicit"},
        ),
        (dict(operation="REMIX", source_duration=10.0, remix_strength=0.6), {"task_type": "cover", "audio_cover_strength": "0.6"}),
        (
            dict(operation="REPAINT", source_duration=10.0, repaint_start=4.0, repaint_end=7.0),
            {"task_type": "repaint", "repainting_start": "4.0", "repainting_end": "7.0", "chunk_mask_mode": "explicit"},
        ),
    ],
)
async def test_ace_step_maps_each_operation_to_the_verified_task_parameters_and_uploads_the_source(tmp_path, fields, expected):
    provider = AceStepMusicGenerationProvider(base_url="http://127.0.0.1:8001")
    with respx.mock(base_url="http://127.0.0.1:8001") as mock:
        route = mock.post("/release_task").mock(return_value=httpx.Response(200, json=wrap({"task_id": "t1"})))
        job = await provider.generate(ace_request(tmp_path, **fields))
    assert job.job_id == "t1"
    request = route.calls.last.request
    assert request.headers["content-type"].startswith("multipart/form-data")
    body = request.content
    assert b"ID3-SOURCE-BYTES" in body and b'name="src_audio"' in body  # uploaded, not referenced by path
    assert str(tmp_path).encode() not in body  # the local path is never sent to ACE-Step
    for key, value in expected.items():
        assert f'name="{key}"\r\n\r\n{value}\r\n'.encode() in body, key
    if fields["operation"] != "ORIGINAL" and fields["operation"] != "EXTEND":
        assert b'name="audio_duration"' not in body  # remix/repaint never force a duration


@pytest.mark.asyncio
async def test_ace_step_original_generation_is_unchanged_json_and_operations_need_their_inputs(tmp_path):
    provider = AceStepMusicGenerationProvider(base_url="http://127.0.0.1:8001")
    with respx.mock(base_url="http://127.0.0.1:8001") as mock:
        route = mock.post("/release_task").mock(return_value=httpx.Response(200, json=wrap({"task_id": "t1"})))
        await provider.generate(GenerationRequest(prompt="p", duration=10.0))
    assert route.calls.last.request.headers["content-type"] == "application/json"
    assert "task_type" not in route.calls.last.request.content.decode()

    from app.providers.errors import ProviderResponseError

    for bad in (
        GenerationRequest(prompt="p", operation="EXTEND", source_duration=10.0, extend_seconds=5.0),  # no source audio
        ace_request(tmp_path, operation="EXTEND", extend_seconds=5.0),  # no source duration
        ace_request(tmp_path, operation="REPAINT", repaint_start=1.0),  # no end
    ):
        with pytest.raises(ProviderResponseError):
            await provider.generate(bad)
    with pytest.raises(UnsupportedOperationError):
        await provider.generate(ace_request(tmp_path, operation="LEGO"))


def test_ace_step_reports_na_durations_as_unknown():
    assert AceStepMusicGenerationProvider._as_seconds("N/A") is None
    assert AceStepMusicGenerationProvider._as_seconds(None) is None
    assert AceStepMusicGenerationProvider._as_seconds(0) is None
    assert AceStepMusicGenerationProvider._as_seconds(True) is None
    assert AceStepMusicGenerationProvider._as_seconds(10) == 10.0
