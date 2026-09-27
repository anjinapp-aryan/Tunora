"""Phase 9: Song management -- rename, favorite/filter, and safe whole-song delete.

Delete strategy under test (see docs/PHASE-9-SONG-MANAGEMENT.md): the database rows
(Jobs, Versions, Song) are removed first, in one transaction; the audio files are
only deleted afterwards, best-effort. This suite proves both halves independently:
the DB cascade (with real SQLite constraints/triggers) and the real filesystem
cleanup (with a real LocalAudioStorage over tmp_path) -- never mocking the one
thing this phase is actually about.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router as jobs_router
from app.api.routes_projects import router as projects_router
from app.api.routes_songs import router as songs_router
from app.jobs import migrations
from app.jobs.repository import SqliteJobRepository
from app.songs.errors import InvalidIdError, InvalidSongUpdateError, SongNotFoundError
from app.storage.errors import PathTraversalError
from tests.songs.test_service_versions import Harness

# -- service / repository ------------------------------------------------------------------------


@pytest.fixture
def h(tmp_path):
    return Harness(tmp_path)


@pytest.mark.asyncio
async def test_rename_persists_and_does_not_touch_versions_jobs_or_audio(h):
    job = await h.generate_to_completion("a song")
    song_id = h.repository.get_version(job.version_id).song_id
    before_versions = h.repository.list_versions(song_id)
    jobs_before = len(h.repository.list())

    updated = h.service.update_song(song_id, title="  My  Renamed   Song  ")

    assert updated.title == "My Renamed Song"  # collapsed/trimmed, same as clean_title elsewhere
    assert h.repository.get_song(song_id).title == "My Renamed Song"
    assert h.repository.list_versions(song_id) == before_versions
    assert len(h.repository.list()) == jobs_before


@pytest.mark.asyncio
async def test_favorite_toggles_and_persists_independently_of_rename(h):
    job = await h.generate_to_completion("a song")
    song_id = h.repository.get_version(job.version_id).song_id

    fav = h.service.update_song(song_id, is_favorite=True)
    assert fav.is_favorite is True and fav.title == h.repository.get_song(song_id).title

    unfav = h.service.update_song(song_id, is_favorite=False)
    assert unfav.is_favorite is False


@pytest.mark.asyncio
async def test_update_song_advances_updated_at(h):
    job = await h.generate_to_completion("a song")
    song_id = h.repository.get_version(job.version_id).song_id
    before = h.repository.get_song(song_id).updated_at
    updated = h.service.update_song(song_id, is_favorite=True)
    assert updated.updated_at >= before


@pytest.mark.asyncio
@pytest.mark.parametrize("title", ["", "   ", "\x00\x01"])
async def test_rename_rejects_empty_or_whitespace_only_titles(h, title):
    job = await h.generate_to_completion("a song")
    song_id = h.repository.get_version(job.version_id).song_id
    with pytest.raises(InvalidSongUpdateError):
        h.service.update_song(song_id, title=title)
    assert h.repository.get_song(song_id).title != ""


@pytest.mark.asyncio
async def test_rename_rejects_an_oversized_title(h):
    job = await h.generate_to_completion("a song")
    song_id = h.repository.get_version(job.version_id).song_id
    original = h.repository.get_song(song_id).title
    with pytest.raises(InvalidSongUpdateError):
        h.service.update_song(song_id, title="x" * 81)
    assert h.repository.get_song(song_id).title == original  # rejected, not silently truncated


@pytest.mark.asyncio
async def test_update_song_rejects_a_non_boolean_favorite(h):
    job = await h.generate_to_completion("a song")
    song_id = h.repository.get_version(job.version_id).song_id
    with pytest.raises(InvalidSongUpdateError):
        h.service.update_song(song_id, is_favorite="yes")  # type: ignore[arg-type]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_id", ["", "a b", "../../etc/passwd", "..\\x", "C:\\x", "song-1' OR '1'='1", "x" * 81])
async def test_update_song_rejects_malformed_ids(h, bad_id):
    with pytest.raises(InvalidIdError):
        h.service.update_song(bad_id, title="x")


@pytest.mark.asyncio
async def test_update_song_unknown_id_raises_not_found(h):
    with pytest.raises(SongNotFoundError):
        h.service.update_song("song-does-not-exist", title="x")


@pytest.mark.asyncio
async def test_favorite_filter_composes_with_project_and_search(h):
    project = h.service.create_project("Album")
    j1 = await h.generate_to_completion("alpha song")
    j2 = await h.generate_to_completion("beta song")
    j3 = await h.generate_to_completion("alpha instrumental")
    s1, s2, s3 = (h.repository.get_version(j.version_id).song_id for j in (j1, j2, j3))
    h.service.update_song(s1, is_favorite=True)
    h.service.update_song(s2, is_favorite=True)
    h.service.add_song_to_project(project.id, s1)

    assert {s.song.id for s in h.service.list_songs(favorite=True)} == {s1, s2}
    assert {s.song.id for s in h.service.list_songs(favorite=False)} == {s3}
    assert len(h.service.list_songs()) == 3  # no filter -> everyone

    assert {s.song.id for s in h.service.list_songs(favorite=True, query="alpha")} == {s1}
    assert {s.song.id for s in h.service.list_songs(favorite=True, project=project.id)} == {s1}


@pytest.mark.asyncio
async def test_existing_project_filter_is_unaffected_by_the_favorite_filter(h):
    project = h.service.create_project("Album")
    job = await h.generate_to_completion("a song")
    song_id = h.repository.get_version(job.version_id).song_id
    h.service.add_song_to_project(project.id, song_id)

    assert {s.song.id for s in h.service.list_songs(project=project.id)} == {song_id}
    assert {s.song.id for s in h.service.list_songs(project=project.id, favorite=False)} == {song_id}
    assert h.service.list_songs(project=project.id, favorite=True) == []


# -- delete: DB cascade -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_removes_song_all_versions_and_all_their_jobs(h):
    job1 = await h.generate_to_completion("v1")
    song_id = h.repository.get_version(job1.version_id).song_id
    job2 = await h.generate_to_completion("v2", song_id=song_id)
    job3 = await h.generate_to_completion("v3", song_id=song_id)
    version_ids = [job1.version_id, job2.version_id, job3.version_id]
    job_ids = [job1.id, job2.id, job3.id]

    h.service.delete_song(song_id)

    assert h.repository.get_song(song_id) is None
    for vid in version_ids:
        assert h.repository.get_version(vid) is None
    for jid in job_ids:
        assert h.repository.get(jid) is None


@pytest.mark.asyncio
async def test_delete_leaves_no_orphaned_rows_visible_through_any_read_path(h):
    job = await h.generate_to_completion("a song")
    song_id = h.repository.get_version(job.version_id).song_id
    h.service.delete_song(song_id)

    assert h.repository.list_versions(song_id) == []
    assert h.repository.list_version_entries(song_id) == []
    with pytest.raises(SongNotFoundError):
        h.service.get_song(song_id)
    with pytest.raises(SongNotFoundError):
        h.service.song_details(song_id)


@pytest.mark.asyncio
async def test_delete_removes_the_song_from_its_project_without_deleting_the_project(h):
    project = h.service.create_project("Album")
    job = await h.generate_to_completion("a song")
    song_id = h.repository.get_version(job.version_id).song_id
    h.service.add_song_to_project(project.id, song_id)

    h.service.delete_song(song_id)

    assert h.service.get_project(project.id) is not None
    assert h.service.project_details(project.id)[1] == []


@pytest.mark.asyncio
async def test_delete_unknown_song_raises_not_found(h):
    with pytest.raises(SongNotFoundError):
        h.service.delete_song("song-does-not-exist")


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_id", ["", "a b", "../../etc/passwd", "..\\x", "C:\\x", "song-1' OR '1'='1", "x" * 81])
async def test_delete_rejects_malformed_ids(h, bad_id):
    with pytest.raises(InvalidIdError):
        h.service.delete_song(bad_id)


@pytest.mark.asyncio
async def test_repeated_delete_is_safe_the_second_time_reports_not_found(h):
    job = await h.generate_to_completion("a song")
    song_id = h.repository.get_version(job.version_id).song_id
    h.service.delete_song(song_id)
    with pytest.raises(SongNotFoundError):
        h.service.delete_song(song_id)  # not a crash, not a silent success -- an honest 404-equivalent


@pytest.mark.asyncio
async def test_delete_rolls_back_completely_if_the_db_transaction_fails(h, monkeypatch):
    """Case B (audio deleted, DB fails) is impossible by construction: no file is ever
    touched until after the DB commit. This proves the DB side alone is all-or-nothing."""

    job = await h.generate_to_completion("a song")
    song_id = h.repository.get_version(job.version_id).song_id
    before = h.repository.get_song(song_id)

    real_connect = h.repository._connect  # noqa: SLF001

    class FailingConnection:
        """Wraps a real connection but fails the final DELETE, proving the earlier
        DELETEs in the same transaction are rolled back rather than left partial."""

        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, *args, **kwargs):
            if sql.startswith("DELETE FROM songs"):
                raise sqlite3.OperationalError("simulated failure")
            return self._conn.execute(sql, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._conn, name)

    monkeypatch.setattr(h.repository, "_connect", lambda: FailingConnection(real_connect()))
    with pytest.raises(sqlite3.OperationalError):
        h.repository.delete_song(song_id)

    monkeypatch.undo()
    assert h.repository.get_song(song_id) == before  # nothing was removed
    assert h.repository.list_versions(song_id) != []


# -- delete: real filesystem -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_removes_real_audio_files_for_every_version_from_disk(h):
    job1 = await h.generate_to_completion("v1", content=b"AUDIO-ONE" * 50)
    song_id = h.repository.get_version(job1.version_id).song_id
    job2 = await h.generate_to_completion("v2", song_id=song_id, content=b"AUDIO-TWO" * 50)
    job3 = await h.generate_to_completion("v3", song_id=song_id, content=b"AUDIO-THREE" * 50)
    paths = [h.storage.get_path(h.repository.get_version(j.version_id).audio.key) for j in (job1, job2, job3)]
    assert all(p.exists() for p in paths)

    h.service.delete_song(song_id)

    assert all(not p.exists() for p in paths)
    assert all(not p.parent.exists() for p in paths)  # each job's own directory is cleaned up too


@pytest.mark.asyncio
async def test_delete_never_touches_an_unrelated_songs_audio(h):
    job_a = await h.generate_to_completion("song a", content=b"SONG-A-BYTES" * 50)
    job_b = await h.generate_to_completion("song b", content=b"SONG-B-BYTES" * 50)
    song_a = h.repository.get_version(job_a.version_id).song_id
    song_b = h.repository.get_version(job_b.version_id).song_id
    path_b = h.storage.get_path(h.repository.get_version(job_b.version_id).audio.key)
    bytes_b = path_b.read_bytes()

    h.service.delete_song(song_a)

    assert h.repository.get_song(song_b) is not None
    assert path_b.exists() and path_b.read_bytes() == bytes_b


@pytest.mark.asyncio
async def test_delete_of_a_song_with_a_version_that_never_completed_is_safe(h):
    """A version with no audio yet (job still running/failed) has no file to delete."""

    from app.providers.base import GenerationJob, JobState

    h.provider.generate_response = GenerationJob(job_id="pending-task", provider="ace-step", status=JobState.QUEUED)
    pending = await h.service.create_and_submit(__import__("app.providers.base", fromlist=["GenerationRequest"]).GenerationRequest(prompt="p"))
    song_id = h.repository.get_version(pending.version_id).song_id

    h.service.delete_song(song_id)  # must not raise even though there is no audio file

    assert h.repository.get_song(song_id) is None


@pytest.mark.asyncio
async def test_a_storage_failure_deleting_one_file_does_not_fail_the_whole_delete(h, monkeypatch):
    """Case A (DB deleted, a file delete fails): the Song is already gone from Tunora's
    own data by the time any file is touched, so this is a logged leak, not an error the
    caller sees -- see JobService.delete_song's docstring."""

    job = await h.generate_to_completion("a song")
    song_id = h.repository.get_version(job.version_id).song_id
    key = h.repository.get_version(job.version_id).audio.key

    from app.storage.errors import StorageWriteError

    def failing_delete(k):
        raise StorageWriteError("simulated disk failure")

    monkeypatch.setattr(h.storage, "delete", failing_delete)

    h.service.delete_song(song_id)  # does not raise

    assert h.repository.get_song(song_id) is None  # the DB side still fully succeeded
    monkeypatch.undo()
    assert h.storage.get_path(key).exists()  # the file really is still there (best-effort, not silently lost)


# -- AudioStorage.delete: security / idempotency -----------------------------------------------------


def test_local_storage_delete_is_idempotent(h):
    h.storage.save(h.source_audio("a.mp3", b"bytes"), job_id="job-x", media_type="audio/mpeg")
    key = "job-x/job-x.mp3"
    assert h.storage.exists(key)
    h.storage.delete(key)
    assert not h.storage.exists(key)
    h.storage.delete(key)  # again -- must not raise


@pytest.mark.parametrize(
    "bad_key",
    ["../../etc/passwd", "..\\x", "/etc/passwd", "C:\\Windows\\x", "\\\\server\\share\\x", "a/../../b", ""],
)
def test_local_storage_delete_rejects_path_traversal_and_absolute_keys(h, bad_key):
    with pytest.raises(PathTraversalError):
        h.storage.delete(bad_key)


def test_local_storage_delete_cannot_reach_another_songs_directory_via_key_confusion(h):
    h.storage.save(h.source_audio("a.mp3", b"a-bytes"), job_id="job-a", media_type="audio/mpeg")
    h.storage.save(h.source_audio("b.mp3", b"b-bytes"), job_id="job-b", media_type="audio/mpeg")
    h.storage.delete("job-a/job-a.mp3")
    assert not h.storage.exists("job-a/job-a.mp3")
    assert h.storage.exists("job-b/job-b.mp3")  # untouched


# -- migration --------------------------------------------------------------------------------------


def test_favorite_migration_is_additive_defaults_false_and_repeat_safe(tmp_path):
    db = tmp_path / "v4.db"
    conn = sqlite3.connect(db)
    for target, step in ((1, migrations._to_v1), (2, migrations._to_v2), (3, migrations._to_v3), (4, migrations._to_v4)):  # noqa: SLF001
        migrations._run_step(conn, target, step)  # noqa: SLF001
    conn.execute("INSERT INTO songs (id, title, created_at, updated_at) VALUES ('song-a', 'Old Song', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')")
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
    conn.close()

    repo = SqliteJobRepository(db)  # applies v5
    old = repo.get_song("song-a")
    assert old.is_favorite is False
    assert old.title == "Old Song"

    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(songs)")}
    assert "is_favorite" in cols
    conn.execute("PRAGMA user_version = 4")  # simulate the version marker being lost
    conn.commit()
    migrations.migrate(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == migrations.LATEST_VERSION
    assert conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0] == 1
    conn.close()


# -- HTTP API -----------------------------------------------------------------------------------------


@pytest.fixture
def client(h):
    app = FastAPI()
    app.include_router(jobs_router)
    app.include_router(songs_router)
    app.include_router(projects_router)
    app.state.job_service = h.service
    return TestClient(app)


def create_song_via_api(client, h, prompt="a song", **extra):
    from app.providers.base import GenerationJob, GenerationResult, GenerationStatus, JobState
    from tests.songs.test_service_versions import ACE_ID

    h.provider.generate_response = GenerationJob(job_id=ACE_ID, provider="ace-step", status=JobState.QUEUED)
    h.provider.status_responses = [GenerationStatus(job_id=ACE_ID, status=JobState.SUCCEEDED)]
    seq = len(list(h.tmp_path.iterdir()))
    h.provider.result_response = GenerationResult(
        job_id=ACE_ID, audio_path=h.source_audio(f"o{seq}.mp3", f"{prompt}-{seq}".encode() * 50), duration=10.0, metadata={},
    )
    r = client.post("/api/jobs", json={"prompt": prompt, "instrumental": True, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_api_rename_and_favorite_via_patch(client, h):
    song = create_song_via_api(client, h, "Original Title")
    r = client.patch(f"/api/songs/{song['song_id']}", json={"title": "New Title", "is_favorite": True})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "New Title" and body["is_favorite"] is True

    r2 = client.get(f"/api/songs/{song['song_id']}")
    assert r2.json()["title"] == "New Title" and r2.json()["is_favorite"] is True

    library = client.get("/api/songs").json()["items"]
    row = next(i for i in library if i["id"] == song["song_id"])
    assert row["title"] == "New Title" and row["is_favorite"] is True


def test_api_patch_partial_updates_do_not_disturb_the_other_field(client, h):
    song = create_song_via_api(client, h)
    client.patch(f"/api/songs/{song['song_id']}", json={"is_favorite": True})
    r = client.patch(f"/api/songs/{song['song_id']}", json={"title": "Renamed"})
    assert r.json()["is_favorite"] is True and r.json()["title"] == "Renamed"


def test_api_patch_creates_no_job_or_version(client, h):
    song = create_song_via_api(client, h)
    jobs_before = len(client.get("/api/jobs").json())
    versions_before = len(client.get(f"/api/songs/{song['song_id']}").json()["versions"])
    client.patch(f"/api/songs/{song['song_id']}", json={"title": "Renamed", "is_favorite": True})
    assert len(client.get("/api/jobs").json()) == jobs_before
    assert len(client.get(f"/api/songs/{song['song_id']}").json()["versions"]) == versions_before


def test_api_patch_validation_errors(client, h):
    song = create_song_via_api(client, h)
    assert client.patch(f"/api/songs/{song['song_id']}", json={"title": ""}).status_code == 422
    assert client.patch(f"/api/songs/{song['song_id']}", json={"title": "   "}).status_code == 422
    assert client.patch(f"/api/songs/{song['song_id']}", json={"title": "x" * 81}).status_code == 422
    assert client.patch(f"/api/songs/{song['song_id']}", json={"is_favorite": "banana"}).status_code == 422
    assert client.patch(f"/api/songs/{song['song_id']}", json={"is_favorite": [1, 2]}).status_code == 422
    assert client.patch("/api/songs/song-does-not-exist", json={"title": "x"}).status_code == 404
    for bad_id in ("a'b", "a b", "x" * 81):
        assert client.patch(f"/api/songs/{bad_id}", json={"title": "x"}).status_code == 422, bad_id
    # A URL-encoded traversal id never even reaches our route pattern check -- Starlette
    # decodes %2F to a literal slash, which splits it into extra path segments with no
    # matching route, so it 404s instead of 422. Either way nothing traverses.
    assert client.patch("/api/songs/..%2F..%2Fetc", json={"title": "x"}).status_code == 404


def test_api_delete_removes_the_song_and_a_repeated_delete_is_a_safe_404(client, h):
    song = create_song_via_api(client, h)
    r = client.delete(f"/api/songs/{song['song_id']}")
    assert r.status_code == 204
    assert client.get(f"/api/songs/{song['song_id']}").status_code == 404
    assert client.delete(f"/api/songs/{song['song_id']}").status_code == 404  # already gone -- safe, not a crash


def test_api_delete_unknown_or_malformed_id(client, h):
    assert client.delete("/api/songs/song-does-not-exist").status_code == 404
    for bad_id in ("a'b", "a b", "x" * 81):
        assert client.delete(f"/api/songs/{bad_id}").status_code == 422, bad_id
    # See the matching PATCH test: a URL-encoded traversal id 404s (no matching route)
    # rather than 422, because Starlette decodes %2F before routing. Still safe.
    assert client.delete("/api/songs/..%2F..%2Fetc").status_code == 404


def test_api_delete_response_leaks_no_internal_detail(client, h):
    song = create_song_via_api(client, h)
    r = client.delete(f"/api/songs/{song['song_id']}")
    for leaked in (str(h.tmp_path), "provider", "fake", "/v1/audio", song["id"]):
        assert leaked not in r.text


def test_api_favorite_filter_query_param(client, h):
    a = create_song_via_api(client, h, "song a")
    b = create_song_via_api(client, h, "song b")
    client.patch(f"/api/songs/{a['song_id']}", json={"is_favorite": True})

    favorites = client.get("/api/songs?favorite=true").json()["items"]
    assert [i["id"] for i in favorites] == [a["song_id"]]

    non_favorites = client.get("/api/songs?favorite=false").json()["items"]
    assert [i["id"] for i in non_favorites] == [b["song_id"]]

    everyone = client.get("/api/songs").json()["items"]
    assert {i["id"] for i in everyone} == {a["song_id"], b["song_id"]}
    assert client.get("/api/songs?favorite=notabool").status_code == 422
