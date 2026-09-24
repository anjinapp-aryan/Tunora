"""Phase 6: Projects are organizational metadata over Songs only.

A Project owns no audio and no Version. Adding/removing a Song from a Project,
and deleting a Project, must never create, move, rewrite or delete a Song, a
Version or an audio file -- every test here checks that directly, not just
the HTTP status code.
"""

from __future__ import annotations

import asyncio
import hashlib
import sqlite3
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router as jobs_router
from app.api.routes_projects import router as projects_router
from app.api.routes_songs import router as songs_router
from app.jobs import migrations
from app.jobs.repository import SqliteJobRepository
from app.projects.errors import InvalidProjectError, ProjectNotFoundError
from app.providers.base import GenerationJob, GenerationResult, GenerationStatus, JobState
from app.songs.errors import InvalidIdError, SongNotFoundError
from tests.songs.test_service_versions import ACE_ID, Harness


def sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def h(tmp_path):
    return Harness(tmp_path)


@pytest.fixture
def client(h):
    app = FastAPI()
    app.include_router(jobs_router)
    app.include_router(songs_router)
    app.include_router(projects_router)
    app.state.job_service = h.service
    return TestClient(app)


# -- service / repository ------------------------------------------------------------------------


def test_create_list_get_update_delete_project(h):
    project = h.service.create_project("My Movie Album", "Songs for the film")
    assert project.id.startswith("proj-") and project.name == "My Movie Album"

    [summary] = h.service.list_projects()
    assert (summary.project.id, summary.song_count) == (project.id, 0)  # "6. Project with zero Songs"

    assert h.service.get_project(project.id) == project

    renamed = h.service.update_project(project.id, name="Movie Album", description="Updated")
    assert (renamed.name, renamed.description) == ("Movie Album", "Updated")
    assert renamed.updated_at >= project.updated_at

    h.service.delete_project(project.id)
    with pytest.raises(ProjectNotFoundError):
        h.service.get_project(project.id)
    assert h.service.list_projects() == []


def test_update_project_can_change_only_one_field(h):
    project = h.service.create_project("Album", "Original description")
    only_name = h.service.update_project(project.id, name="New Name")
    assert (only_name.name, only_name.description) == ("New Name", "Original description")
    only_description = h.service.update_project(project.id, description="New description")
    assert (only_description.name, only_description.description) == ("New Name", "New description")


@pytest.mark.parametrize("name", ["", "   ", "x" * 201])
def test_invalid_project_names_are_rejected_and_create_nothing(h, name):
    with pytest.raises(InvalidProjectError):
        h.service.create_project(name)
    assert h.service.list_projects() == []


def test_invalid_project_description_is_rejected(h):
    with pytest.raises(InvalidProjectError):
        h.service.create_project("Album", "x" * 2001)


def test_duplicate_project_names_are_allowed(h):
    """Documented decision (docs/PHASE-6-PROJECTS-WORKSPACES.md): no uniqueness constraint."""

    a = h.service.create_project("Singles")
    b = h.service.create_project("Singles")
    assert a.id != b.id
    assert {p.project.id for p in h.service.list_projects()} == {a.id, b.id}


# -- add / remove songs ---------------------------------------------------------------------------


async def _song(h, prompt="a song", **spec):
    job = await h.generate_to_completion(prompt, **spec)
    return h.repository.get_song(job.version_id and h.repository.get_version(job.version_id).song_id)


@pytest.mark.asyncio
async def test_add_and_remove_song_creates_or_deletes_nothing(h):
    project = h.service.create_project("My Movie Album")
    song = await _song(h, "Opening Theme")
    before_versions = h.repository.list_versions(song.id)
    before_audio = h.storage.get_path(before_versions[0].audio.key)
    before_hash = sha(before_audio)

    updated = h.service.add_song_to_project(project.id, song.id)
    assert updated.id == song.id and updated.project_id == project.id  # SAME id, now assigned
    _, entries = h.service.project_details(project.id)
    assert [e.song.id for e in entries] == [song.id]
    assert (entries[0].version_count, entries[0].latest_version_number) == (1, 1)
    assert h.service.list_projects()[0].song_count == 1

    # Nothing about the Song/Version/audio changed.
    after_versions = h.repository.list_versions(song.id)
    assert after_versions == before_versions
    assert sha(before_audio) == before_hash

    h.service.remove_song_from_project(project.id, song.id)
    assert h.repository.get_song(song.id).project_id is None
    assert h.service.project_details(project.id)[1] == []
    assert h.repository.list_versions(song.id) == before_versions  # still untouched
    assert sha(before_audio) == before_hash


@pytest.mark.asyncio
async def test_adding_an_existing_song_creates_no_job_version_or_audio_file(h):
    project = h.service.create_project("Album")
    song = await _song(h)
    jobs_before = len(h.repository.list())
    versions_before = len(h.repository.list_versions(song.id))
    files_before = sorted(p.name for p in h.tmp_path.rglob("*") if p.is_file())

    h.service.add_song_to_project(project.id, song.id)

    assert len(h.repository.list()) == jobs_before
    assert len(h.repository.list_versions(song.id)) == versions_before
    assert sorted(p.name for p in h.tmp_path.rglob("*") if p.is_file()) == files_before


@pytest.mark.asyncio
async def test_repeated_assignment_is_idempotent_and_moving_projects_works(h):
    a = h.service.create_project("A")
    b = h.service.create_project("B")
    song = await _song(h)

    h.service.add_song_to_project(a.id, song.id)
    h.service.add_song_to_project(a.id, song.id)  # "13. duplicate assignment" / "14. repeated assignment"
    assert h.service.list_projects()[0 if h.service.list_projects()[0].project.id == a.id else 1].song_count == 1
    assert len(h.service.project_details(a.id)[1]) == 1

    h.service.add_song_to_project(b.id, song.id)  # move
    assert h.repository.get_song(song.id).project_id == b.id
    assert h.service.project_details(a.id)[1] == []
    assert [e.song.id for e in h.service.project_details(b.id)[1]] == [song.id]


@pytest.mark.asyncio
async def test_removing_a_song_not_in_that_project_is_a_safe_no_op(h):
    a = h.service.create_project("A")
    b = h.service.create_project("B")
    song = await _song(h)
    h.service.add_song_to_project(a.id, song.id)

    h.service.remove_song_from_project(b.id, song.id)  # song is not in B
    assert h.repository.get_song(song.id).project_id == a.id  # A's assignment survives


@pytest.mark.asyncio
async def test_two_projects_with_their_own_songs_are_isolated(h):
    a = h.service.create_project("Project A")
    b = h.service.create_project("Project B")
    song1 = await _song(h, "Song 1")
    song2 = await _song(h, "Song 2")
    h.service.add_song_to_project(a.id, song1.id)
    h.service.add_song_to_project(b.id, song2.id)

    assert [e.song.id for e in h.service.project_details(a.id)[1]] == [song1.id]
    assert [e.song.id for e in h.service.project_details(b.id)[1]] == [song2.id]
    by_id = {s.project.id: s.song_count for s in h.service.list_projects()}
    assert by_id == {a.id: 1, b.id: 1}


# -- unknown / malformed ids ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_project_raises_not_found(h):
    song = await _song(h)
    with pytest.raises(ProjectNotFoundError):
        h.service.get_project("proj-does-not-exist")
    with pytest.raises(ProjectNotFoundError):
        h.service.add_song_to_project("proj-does-not-exist", song.id)
    with pytest.raises(ProjectNotFoundError):
        h.service.update_project("proj-does-not-exist", name="x")
    with pytest.raises(ProjectNotFoundError):
        h.service.delete_project("proj-does-not-exist")


@pytest.mark.asyncio
async def test_unknown_song_raises_not_found_and_assigns_nothing(h):
    project = h.service.create_project("Album")
    with pytest.raises(SongNotFoundError):
        h.service.add_song_to_project(project.id, "song-does-not-exist")
    assert h.service.project_details(project.id)[1] == []


@pytest.mark.parametrize(
    "bad_id",
    ["", "a b", "a/b", "../../etc/passwd", "..\\x", "C:\\x", "proj-1' OR '1'='1", "x" * 81, "proj-1;DROP TABLE projects;"],
)
def test_malformed_project_ids_are_rejected(h, bad_id):
    with pytest.raises(InvalidIdError):
        h.service.get_project(bad_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_id", ["", "a b", "../x", "song-1' OR '1'='1", "x" * 81])
async def test_malformed_song_ids_are_rejected(h, bad_id):
    project = h.service.create_project("Album")
    with pytest.raises(InvalidIdError):
        h.service.add_song_to_project(project.id, bad_id)
    assert h.service.project_details(project.id)[1] == []


def test_sql_injection_in_project_name_and_search_is_inert(h):
    project = h.service.create_project("Robert'); DROP TABLE projects;--")
    assert h.service.get_project(project.id).name == "Robert'); DROP TABLE projects;--"
    found = h.service.list_projects(query="' OR '1'='1")
    assert found == []  # treated as a literal substring, not SQL
    assert h.service.list_projects()[0].project.id == project.id  # table still exists


# -- deletion preserves everything ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deleting_a_project_deletes_only_the_project(h):
    project = h.service.create_project("Album")
    song = await _song(h)
    h.service.add_song_to_project(project.id, song.id)
    versions_before = h.repository.list_versions(song.id)
    audio_path = h.storage.get_path(versions_before[0].audio.key)
    audio_before = audio_path.read_bytes()

    h.service.delete_project(project.id)

    with pytest.raises(ProjectNotFoundError):
        h.service.get_project(project.id)
    assert h.repository.get_song(song.id) is not None  # 15. song survives
    assert h.repository.get_song(song.id).project_id is None  # unassigned, not deleted
    assert h.repository.list_versions(song.id) == versions_before  # 16. versions survive
    assert audio_path.exists() and audio_path.read_bytes() == audio_before  # 17. audio survives


# -- immutability: moving a song between projects touches nothing else -----------------------------


@pytest.mark.asyncio
async def test_moving_a_song_between_projects_leaves_its_versions_and_audio_untouched(h):
    a = h.service.create_project("A")
    b = h.service.create_project("B")
    job1 = await h.generate_to_completion("v1", content=b"AUDIO-ONE" * 50)
    song_id = h.repository.get_version(job1.version_id).song_id
    job2 = await h.generate_to_completion("v2", song_id=song_id, content=b"AUDIO-TWO" * 50)
    job3 = await h.generate_to_completion("v3", song_id=song_id, content=b"AUDIO-THREE" * 50)
    before = h.repository.list_versions(song_id)
    before_ids = [v.id for v in before]
    before_numbers = [v.version_number for v in before]
    before_keys = [v.audio.key for v in before]
    before_hashes = [sha(h.storage.get_path(v.audio.key)) for v in before]
    before_lineage = [(v.operation, v.source_version_id) for v in before]

    h.service.add_song_to_project(a.id, song_id)
    h.service.add_song_to_project(b.id, song_id)  # move A -> B
    h.service.remove_song_from_project(b.id, song_id)  # unassign entirely

    after = h.repository.list_versions(song_id)
    assert [v.id for v in after] == before_ids
    assert [v.version_number for v in after] == before_numbers
    assert [v.audio.key for v in after] == before_keys
    assert [sha(h.storage.get_path(v.audio.key)) for v in after] == before_hashes
    assert [(v.operation, v.source_version_id) for v in after] == before_lineage
    assert h.repository.get_song(song_id).id == song_id  # song id itself never changes


# -- concurrency ------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_add_of_many_songs_to_one_project_is_race_free(h):
    project = h.service.create_project("Album")
    songs = [await _song(h, f"song {i}") for i in range(8)]

    await asyncio.gather(*(asyncio.to_thread(h.service.add_song_to_project, project.id, s.id) for s in songs))

    entries = h.service.project_details(project.id)[1]
    assert {e.song.id for e in entries} == {s.id for s in songs}
    assert h.service.list_projects()[0].song_count == 8


def test_threaded_assignment_is_serialized_and_ends_in_a_consistent_state(h):
    project_a_id = h.service.create_project("A").id
    project_b_id = h.service.create_project("B").id

    async def make_song():
        job = await h.generate_to_completion("threaded song")
        return h.repository.get_version(job.version_id).song_id

    song_id = asyncio.run(make_song())
    errors = []
    barrier = threading.Barrier(10)

    def worker(target):
        try:
            barrier.wait()
            h.service.add_song_to_project(target, song_id)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(project_a_id if i % 2 == 0 else project_b_id,)) for i in range(10)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert errors == []
    final = h.repository.get_song(song_id).project_id
    assert final in (project_a_id, project_b_id)  # one clean winner, never corrupted/duplicated
    a_songs = [e.song.id for e in h.service.project_details(project_a_id)[1]]
    b_songs = [e.song.id for e in h.service.project_details(project_b_id)[1]]
    assert (song_id in a_songs) != (song_id in b_songs)  # in exactly one project, never both/neither


# -- migration --------------------------------------------------------------------------------------


def test_project_migration_is_additive_and_repeat_safe(tmp_path):
    db = tmp_path / "v3.db"
    conn = sqlite3.connect(db)
    for target, step in ((1, migrations._to_v1), (2, migrations._to_v2), (3, migrations._to_v3)):  # noqa: SLF001
        migrations._run_step(conn, target, step)  # noqa: SLF001
    conn.execute("INSERT INTO songs (id, title, created_at, updated_at) VALUES ('song-a', 'Old Song', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')")
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    conn.close()

    repo = SqliteJobRepository(db)  # applies v4
    old_song = repo.get_song("song-a")
    assert old_song.project_id is None  # "18. existing songs survive migration": unassigned, not deleted, not a fake project
    assert old_song.title == "Old Song"

    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(songs)")}
    assert "project_id" in cols
    assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0  # no fake project was created
    conn.execute("PRAGMA user_version = 3")  # simulate the version marker being lost
    conn.commit()
    migrations.migrate(conn)  # "19. migration repeat safety"
    assert conn.execute("PRAGMA user_version").fetchone()[0] == migrations.LATEST_VERSION
    assert conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0] == 1
    conn.close()


# -- HTTP API -----------------------------------------------------------------------------------------


def create_song_via_api(client, h, prompt="a song", **extra):
    """One completed generation through the real API path (FakeProvider + real storage)."""

    h.provider.generate_response = GenerationJob(job_id=ACE_ID, provider="ace-step", status=JobState.QUEUED)
    h.provider.status_responses = [GenerationStatus(job_id=ACE_ID, status=JobState.SUCCEEDED)]
    seq = len(list(h.tmp_path.iterdir()))
    h.provider.result_response = GenerationResult(
        job_id=ACE_ID, audio_path=h.source_audio(f"o{seq}.mp3", f"{prompt}-{seq}".encode() * 50),
        duration=30.0, metadata={},
    )
    r = client.post("/api/jobs", json={"prompt": prompt, "instrumental": True, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_api_full_lifecycle(client):
    created = client.post("/api/projects", json={"name": "My Movie Album", "description": "For the film"})
    assert created.status_code == 200
    project = created.json()
    assert (project["name"], project["description"]) == ("My Movie Album", "For the film")

    listed = client.get("/api/projects").json()["items"]
    assert listed == [{**project, "song_count": 0}]

    fetched = client.get(f"/api/projects/{project['id']}").json()
    assert fetched == {**project, "songs": []}

    renamed = client.patch(f"/api/projects/{project['id']}", json={"name": "Movie Album"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Movie Album"

    assert client.delete(f"/api/projects/{project['id']}").status_code == 204
    assert client.get(f"/api/projects/{project['id']}").status_code == 404
    assert client.get("/api/projects").json()["items"] == []


def test_api_add_remove_song_and_library_context(client, h):
    project = client.post("/api/projects", json={"name": "My Movie Album"}).json()
    song = create_song_via_api(client, h, "Opening Theme")

    added = client.post(f"/api/projects/{project['id']}/songs", json={"song_id": song["song_id"]})
    assert added.status_code == 200
    assert added.json() == {
        "id": song["song_id"], "title": song["title"], "version_count": 1,
        "latest_version_number": 1, "created_at": added.json()["created_at"], "updated_at": added.json()["updated_at"],
    }

    details = client.get(f"/api/projects/{project['id']}").json()
    assert [s["id"] for s in details["songs"]] == [song["song_id"]]

    # Library shows the project context (no N+1: see test below), and Song Details too.
    library = client.get("/api/songs").json()["items"]
    row = next(i for i in library if i["id"] == song["song_id"])
    assert row["project"] == {"id": project["id"], "name": "My Movie Album"}
    song_details = client.get(f"/api/songs/{song['song_id']}").json()
    assert song_details["project"] == {"id": project["id"], "name": "My Movie Album"}

    removed = client.delete(f"/api/projects/{project['id']}/songs/{song['song_id']}")
    assert removed.status_code == 204
    assert client.get(f"/api/projects/{project['id']}").json()["songs"] == []
    # Song still exists in the Library, now with no project.
    row = next(i for i in client.get("/api/songs").json()["items"] if i["id"] == song["song_id"])
    assert row["project"] is None
    assert client.get(f"/api/songs/{song['song_id']}").json()["project"] is None


def test_api_create_song_with_and_without_a_project(client, h):
    project = client.post("/api/projects", json={"name": "Album"}).json()
    with_project = create_song_via_api(client, h, "In Album", project_id=project["id"])
    assert client.get(f"/api/songs/{with_project['song_id']}").json()["project"]["id"] == project["id"]

    without_project = create_song_via_api(client, h, "No Project")  # unchanged existing behavior
    assert client.get(f"/api/songs/{without_project['song_id']}").json()["project"] is None

    bad = client.post("/api/jobs", json={"prompt": "x", "project_id": "proj-does-not-exist"})
    assert bad.status_code == 404
    assert client.get("/api/songs").json()["items"][-1]["title"] != "x"  # nothing created for the bad project


def test_api_library_project_filter(client, h):
    project = client.post("/api/projects", json={"name": "Album"}).json()
    in_project = create_song_via_api(client, h, "In Album", project_id=project["id"])
    outside = create_song_via_api(client, h, "Outside")

    only_project = client.get(f"/api/songs?project={project['id']}").json()["items"]
    assert [s["id"] for s in only_project] == [in_project["song_id"]]

    unassigned = client.get("/api/songs?project=none").json()["items"]
    assert outside["song_id"] in [s["id"] for s in unassigned]
    assert in_project["song_id"] not in [s["id"] for s in unassigned]

    assert client.get("/api/songs?project=not-a-real-id-but-shaped-ok").json()["items"] == []
    assert client.get("/api/songs?project=bad!id").status_code == 422


def test_api_errors_are_safe_and_specific(client, h):
    other_song = create_song_via_api(client, h, "Elsewhere")
    project = client.post("/api/projects", json={"name": "Album"}).json()

    assert client.get("/api/projects/proj-does-not-exist").status_code == 404
    assert client.patch("/api/projects/proj-does-not-exist", json={"name": "x"}).status_code == 404
    assert client.delete("/api/projects/proj-does-not-exist").status_code == 404
    assert client.post(f"/api/projects/{project['id']}/songs", json={"song_id": "song-does-not-exist"}).status_code == 404
    assert client.post("/api/projects/proj-does-not-exist/songs", json={"song_id": other_song["song_id"]}).status_code == 404
    assert client.delete(f"/api/projects/{project['id']}/songs/{other_song['song_id']}").status_code == 204  # no-op, not an error

    for bad_id in ("a'b", "a b", "x" * 81):
        assert client.get(f"/api/projects/{bad_id}").status_code == 422, bad_id
        assert client.post(f"/api/projects/{bad_id}/songs", json={"song_id": other_song["song_id"]}).status_code == 422, bad_id
    # An encoded slash never matches the route pattern at all: FastAPI 404s it, which is
    # still safe (nothing is looked up or executed), just a different status than a malformed id.
    assert client.get("/api/projects/..%2F..%2Fetc").status_code in (404, 422)

    assert client.post("/api/projects", json={"name": ""}).status_code == 422
    assert client.post("/api/projects", json={"name": "x" * 201}).status_code == 422
    assert client.post("/api/projects", json={"name": "ok", "description": "x" * 2001}).status_code == 422
    assert client.post("/api/projects", json={}).status_code == 422  # name required


def test_api_responses_never_leak_internal_details(client, h):
    song = create_song_via_api(client, h, "A Song")
    project = client.post("/api/projects", json={"name": "Album"}).json()
    client.post(f"/api/projects/{project['id']}/songs", json={"song_id": song["song_id"]})

    text = "".join([
        client.get("/api/projects").text,
        client.get(f"/api/projects/{project['id']}").text,
        client.get("/api/songs").text,
        client.get(f"/api/songs/{song['song_id']}").text,
    ])
    for leaked in (str(h.tmp_path), "provider", "fake", "/v1/audio"):
        assert leaked not in text, leaked


def test_api_html_and_script_content_is_stored_and_returned_verbatim_not_executed(client):
    """A JSON API returns data, not HTML: React (not the backend) is responsible for
    escaping when this is rendered, so storing it as-is is safe and correct."""

    name = "<script>alert(1)</script>"
    project = client.post("/api/projects", json={"name": name, "description": "<b>bold</b>"}).json()
    assert project["name"] == name
    assert client.get(f"/api/projects/{project['id']}").json()["description"] == "<b>bold</b>"


def test_api_project_list_uses_a_grouped_query_not_one_count_per_project(client, h, monkeypatch):
    for i in range(12):
        client.post("/api/projects", json={"name": f"Project {i}"})

    # sqlite3.Connection is a C type (its methods can't be monkeypatched on the instance),
    # so count queries by wrapping the module-level `sqlite3.connect` the repository calls.
    queries = []
    real_connect = sqlite3.connect

    class CountingConnection(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            queries.append(sql)
            return super().execute(sql, *args, **kwargs)

    def counting_connect(*args, **kwargs):
        return real_connect(*args, factory=CountingConnection, **kwargs)

    import app.jobs.repository as repo_module

    monkeypatch.setattr(repo_module.sqlite3, "connect", counting_connect)
    response = client.get("/api/projects")
    assert response.status_code == 200 and len(response.json()["items"]) == 12
    assert len(queries) <= 2  # PRAGMA + one SELECT for the projects+grouped counts, not one per project
