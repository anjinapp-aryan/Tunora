"""Song -> Version -> Job persistence: numbering, immutability, atomicity, concurrency.

Runs against both repository implementations where the behavior is common;
the SQL-specific guarantees (constraints, triggers, rollback, locking) are
SQLite-only tests.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

import pytest

from app.jobs.models import Job, JobStatus
from app.jobs.repository import InMemoryJobRepository, SqliteJobRepository
from app.providers.base import GenerationRequest
from app.songs.errors import ImmutableVersionError, SongNotFoundError
from app.songs.ids import is_valid_id, new_song_id, new_version_id
from app.songs.models import Song, Version, VersionAudio


@pytest.fixture(params=["memory", "sqlite"])
def repo(request, tmp_path):
    if request.param == "memory":
        return InMemoryJobRepository()
    return SqliteJobRepository(tmp_path / "tunora.db")


@pytest.fixture
def sqlite_repo(tmp_path):
    return SqliteJobRepository(tmp_path / "tunora.db")


def make_job(job_id: str, prompt: str = "a song") -> Job:
    return Job(id=job_id, provider="fake", status=JobStatus.CREATED, request=GenerationRequest(prompt=prompt))


def new_generation(repo, *, song: Song | None = None, prompt: str = "a song", job_id: str | None = None, **spec):
    """Create one generation; a new Song unless `song` (an existing one) is passed."""

    new_song = None if song else Song(id=new_song_id(), title="T")
    song_id = song.id if song else new_song.id
    request = GenerationRequest(prompt=prompt, **spec)
    job = make_job(job_id or f"tunora-{new_version_id()}", prompt)
    version = repo.create_generation(
        new_song=new_song,
        version=Version(id=new_version_id(), song_id=song_id, spec=request, provider="fake"),
        job=job,
    )
    return (new_song or song), version, job


AUDIO = VersionAudio(key="j/j.mp3", filename="j.mp3", media_type="audio/mpeg", size_bytes=10, duration=5.0)


# -- creation, numbering, relationships ---------------------------------------------------


def test_creating_a_generation_creates_song_version_1_and_a_linked_job(repo):
    song, version, job = new_generation(repo, prompt="hello", lyrics="la", language="kn", duration=30.0, seed=7, instrumental=True)

    assert repo.get_song(song.id).title == "T"
    assert version.version_number == 1 and version.song_id == song.id
    stored = repo.get_version(version.id)
    assert stored.spec == GenerationRequest(prompt="hello", lyrics="la", language="kn", duration=30.0, seed=7, instrumental=True)
    assert stored.provider == "fake" and stored.audio is None
    assert job.version_id == version.id
    assert repo.get(job.id).version_id == version.id


def test_versions_of_one_song_number_1_2_3_and_songs_are_independent(repo):
    song_a, v1, _ = new_generation(repo)
    _, v2, _ = new_generation(repo, song=song_a)
    _, v3, _ = new_generation(repo, song=song_a)
    song_b, b1, _ = new_generation(repo)

    assert [v1.version_number, v2.version_number, v3.version_number] == [1, 2, 3]
    assert b1.version_number == 1  # not global numbering
    assert [v.version_number for v in repo.list_versions(song_a.id)] == [1, 2, 3]
    assert [v.id for v in repo.list_versions(song_b.id)] == [b1.id]


def test_a_version_of_song_a_is_never_listed_under_song_b(repo):
    song_a, va, _ = new_generation(repo)
    song_b, vb, _ = new_generation(repo)
    assert repo.get_version(va.id).song_id == song_a.id != song_b.id
    assert va.id not in {v.id for v in repo.list_versions(song_b.id)}


def test_get_versions_bulk_lookup_ignores_unknown_ids(repo):
    _, v1, _ = new_generation(repo)
    found = repo.get_versions([v1.id, "ver-does-not-exist", v1.id])
    assert list(found) == [v1.id]
    assert repo.get_versions([]) == {}


def test_unknown_song_raises_and_writes_nothing(repo):
    version = Version(id=new_version_id(), song_id="song-missing", spec=GenerationRequest(prompt="p"), provider="fake")
    job = make_job("tunora-orphan")
    with pytest.raises(SongNotFoundError):
        repo.create_generation(new_song=None, version=version, job=job)
    assert repo.get("tunora-orphan") is None
    assert repo.get_version(version.id) is None
    assert job.version_id is None


def test_regenerating_never_touches_version_1(repo):
    song, v1, j1 = new_generation(repo, prompt="original", seed=1)
    j1.status = JobStatus.COMPLETED
    repo.complete_job(j1, AUDIO)
    before = repo.get_version(v1.id)

    _, v2, _ = new_generation(repo, song=song, prompt="changed", seed=2)

    assert v2.version_number == 2
    assert repo.get_version(v1.id) == before
    assert repo.get_version(v1.id).spec.prompt == "original"
    assert repo.get_version(v1.id).audio == AUDIO
    assert repo.get_version(v2.id).audio is None


# -- audio + immutability -------------------------------------------------------------------


def test_complete_job_attaches_audio_and_persists_the_job(repo):
    _, version, job = new_generation(repo)
    job.status = JobStatus.COMPLETED
    job.result = {"audio": {"key": "k"}}
    repo.complete_job(job, AUDIO)

    assert repo.get_version(version.id).audio == AUDIO
    assert repo.get(job.id).status == JobStatus.COMPLETED


def test_attaching_the_same_audio_twice_is_idempotent_but_different_audio_is_refused(repo):
    _, version, job = new_generation(repo)
    repo.complete_job(job, AUDIO)
    repo.complete_job(job, AUDIO)  # retry after a crash: harmless

    other = VersionAudio(key="x/x.mp3", filename="x.mp3", media_type="audio/mpeg", size_bytes=99, duration=1.0)
    with pytest.raises(ImmutableVersionError):
        repo.complete_job(job, other)
    assert repo.get_version(version.id).audio == AUDIO


@pytest.mark.parametrize(
    "column,value",
    [
        ("prompt", "rewritten"),
        ("lyrics", "rewritten"),
        ("language", "hi"),
        ("duration", 999.0),
        ("seed", 12345),
        ("instrumental", 1),
        ("batch_size", 4),
        ("provider", "other"),
        ("version_number", 9),
        ("song_id", "song-other"),
        ("created_at", "2000-01-01T00:00:00+00:00"),
    ],
)
def test_the_database_itself_refuses_to_rewrite_a_generation_snapshot(sqlite_repo, tmp_path, column, value):
    _, version, _ = new_generation(sqlite_repo, prompt="original")
    conn = sqlite3.connect(tmp_path / "tunora.db")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute(f"UPDATE versions SET {column} = ? WHERE id = ?", (value, version.id))
    conn.close()
    assert sqlite_repo.get_version(version.id).spec.prompt == "original"


def test_the_database_itself_makes_attached_audio_write_once(sqlite_repo, tmp_path):
    _, version, job = new_generation(sqlite_repo)
    sqlite_repo.complete_job(job, AUDIO)
    conn = sqlite3.connect(tmp_path / "tunora.db")
    with pytest.raises(sqlite3.IntegrityError, match="write-once"):
        conn.execute("UPDATE versions SET audio_key = 'elsewhere/x.mp3' WHERE id = ?", (version.id,))
    conn.close()
    assert sqlite_repo.get_version(version.id).audio.key == "j/j.mp3"


# -- constraints ----------------------------------------------------------------------------


def test_unique_song_id_version_number_is_enforced_by_the_database(sqlite_repo, tmp_path):
    song, v1, _ = new_generation(sqlite_repo)
    conn = sqlite3.connect(tmp_path / "tunora.db")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        conn.execute(
            "INSERT INTO versions (id, song_id, version_number, prompt, lyrics, language, instrumental, provider, created_at)"
            " VALUES ('ver-dup', ?, 1, 'p', '', 'en', 0, 'fake', '2026-01-01T00:00:00+00:00')",
            (song.id,),
        )
    conn.close()


def test_a_version_needs_a_real_song_and_a_positive_number(sqlite_repo, tmp_path):
    conn = sqlite3.connect(tmp_path / "tunora.db")
    conn.execute("PRAGMA foreign_keys = ON")
    insert = (
        "INSERT INTO versions (id, song_id, version_number, prompt, lyrics, language, instrumental, provider, created_at)"
        " VALUES (?, ?, ?, 'p', '', 'en', 0, 'fake', '2026-01-01T00:00:00+00:00')"
    )
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        conn.execute(insert, ("ver-a", "song-missing", 1))
    conn.rollback()
    song, _, _ = new_generation(sqlite_repo)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        conn.execute(insert, ("ver-b", song.id, 0))
    conn.close()


# -- transactions ---------------------------------------------------------------------------


def test_a_failure_while_creating_the_job_rolls_back_the_song_and_version(sqlite_repo):
    sqlite_repo.create(make_job("tunora-taken"))  # so the job insert below violates the primary key
    new_song = Song(id=new_song_id(), title="Ghost")
    version = Version(id=new_version_id(), song_id=new_song.id, spec=GenerationRequest(prompt="p"), provider="fake")
    job = make_job("tunora-taken")

    with pytest.raises(sqlite3.IntegrityError):
        sqlite_repo.create_generation(new_song=new_song, version=version, job=job)

    assert sqlite_repo.get_song(new_song.id) is None
    assert sqlite_repo.get_version(version.id) is None
    assert sqlite_repo.list_versions(new_song.id) == []
    assert job.version_id is None


def test_a_failed_attempt_does_not_burn_a_version_number(sqlite_repo):
    song, v1, _ = new_generation(sqlite_repo)
    sqlite_repo.create(make_job("tunora-taken"))
    with pytest.raises(sqlite3.IntegrityError):
        new_generation(sqlite_repo, song=song, job_id="tunora-taken")
    _, v2, _ = new_generation(sqlite_repo, song=song)
    assert (v1.version_number, v2.version_number) == (1, 2)


def test_data_survives_a_restart(tmp_path):
    db = tmp_path / "tunora.db"
    first = SqliteJobRepository(db)
    song, version, job = new_generation(first, prompt="persist me")
    job.status = JobStatus.COMPLETED
    first.complete_job(job, AUDIO)
    del first

    second = SqliteJobRepository(db)
    assert second.get_song(song.id).title == "T"
    assert second.get_version(version.id).audio == AUDIO
    assert second.get(job.id).version_id == version.id


def test_concurrent_version_creation_never_produces_duplicate_numbers(tmp_path):
    repo = SqliteJobRepository(tmp_path / "tunora.db")
    song, _, _ = new_generation(repo)
    numbers: list[int] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(12)

    def worker() -> None:
        try:
            barrier.wait()
            _, version, _ = new_generation(repo, song=song)
            numbers.append(version.version_number)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert sorted(numbers) == list(range(2, 14))  # version 1 already existed
    assert [v.version_number for v in repo.list_versions(song.id)] == list(range(1, 14))


# -- ids ------------------------------------------------------------------------------------


def test_generated_ids_are_unique_opaque_and_valid():
    songs = {new_song_id() for _ in range(500)}
    versions = {new_version_id() for _ in range(500)}
    assert len(songs) == len(versions) == 500
    assert all(s.startswith("song-") and is_valid_id(s) for s in songs)
    assert all(v.startswith("ver-") and is_valid_id(v) for v in versions)
    assert not re.search(r"[\\/:.]", next(iter(songs)))


@pytest.mark.parametrize(
    "bad",
    ["", "../etc/passwd", "..\\x", "a/b", "a b", "a.b", "song-1' OR '1'='1", "-leading", "x" * 81, "C:\\x", "id\r\n", None, 5],
)
def test_malformed_ids_are_rejected(bad):
    assert not is_valid_id(bad)


# -- provider independence ------------------------------------------------------------------


def test_the_song_domain_does_not_depend_on_any_provider():
    root = Path(__file__).resolve().parents[2] / "app" / "songs"
    source = "\n".join(p.read_text(encoding="utf-8") for p in root.glob("*.py"))
    assert not re.search(r"ace_?step|acestep", source, re.IGNORECASE)
    assert "app.providers.ace_step" not in source
    assert "httpx" not in source
    version = Version(id="v", song_id="s", spec=GenerationRequest(prompt="p"), provider="anything")
    assert isinstance(version.spec, GenerationRequest)  # provider-neutral spec
