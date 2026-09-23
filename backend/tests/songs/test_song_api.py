"""Phase 5A: song-oriented Library and Song Details API (GET /api/songs, /api/songs/{id})."""

from __future__ import annotations

import sqlite3
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router as jobs_router
from app.api.routes_songs import router as songs_router
from app.jobs.models import JobStatus
from app.jobs.repository import InMemoryJobRepository, SqliteJobRepository
from app.providers.base import GenerationJob, GenerationRequest, GenerationResult, GenerationStatus, JobState
from app.providers.errors import ProviderUnavailableError
from tests.songs.test_service_versions import ACE_ID, Harness


@pytest.fixture
def h(tmp_path):
    return Harness(tmp_path)


@pytest.fixture
def client(h):
    app = FastAPI()
    app.include_router(jobs_router)
    app.include_router(songs_router)
    app.state.job_service = h.service
    return TestClient(app)


def generate(client, h, prompt="a song", *, song_id=None, title=None, content=None):
    """One completed generation through the real API path (FakeProvider + real storage)."""

    h.provider.generate_response = GenerationJob(job_id=ACE_ID, provider="ace-step", status=JobState.QUEUED)
    h.provider.status_responses = [GenerationStatus(job_id=ACE_ID, status=JobState.SUCCEEDED)]
    seq = len(list(h.tmp_path.iterdir()))
    h.provider.result_response = GenerationResult(
        job_id=ACE_ID,
        audio_path=h.source_audio(f"o{seq}.mp3", content or f"{prompt}-{seq}".encode() * 50),
        duration=float(30 + seq),
        metadata={},
    )
    body = {"prompt": prompt}
    if song_id:
        body["song_id"] = song_id
    if title:
        body["title"] = title
    resp = client.post("/api/jobs", json=body)
    assert resp.status_code == 200, resp.text
    time.sleep(0.01)  # distinct created_at ordering
    return resp.json()


def failed_generation(client, h, song_id):
    h.provider.generate_response = ProviderUnavailableError("down C:\\secret")
    resp = client.post("/api/jobs", json={"prompt": "will fail", "song_id": song_id})
    assert resp.json()["status"] == "FAILED"
    return resp.json()


def three_versions(client, h, title="I Will Rise"):
    v1 = generate(client, h, "rise up", title=title)
    v2 = generate(client, h, "rise higher", song_id=v1["song_id"])
    v3 = generate(client, h, "rise highest", song_id=v1["song_id"])
    return v1, v2, v3


# -- Library grouping ---------------------------------------------------------------------------


def test_versions_of_the_same_song_are_one_library_row_with_a_count_and_latest(client, h):
    v1, v2, v3 = three_versions(client, h)
    other = generate(client, h, "unrelated", title="Other Song")

    items = client.get("/api/songs").json()["items"]

    assert len(items) == 2  # NOT four rows
    rise = next(i for i in items if i["id"] == v1["song_id"])
    assert rise["title"] == "I Will Rise" and rise["version_count"] == 3
    assert rise["latest_version"]["version_number"] == 3
    assert rise["latest_version"]["duration"] is not None
    assert next(i for i in items if i["id"] == other["song_id"])["version_count"] == 1
    assert set(rise) == {"id", "title", "version_count", "latest_version", "created_at", "updated_at", "project", "is_favorite"}  # Phase 6/9: project, is_favorite added
    assert set(rise["latest_version"]) == {"version_number", "duration", "created_at"}


def test_the_job_listing_is_unchanged_and_still_lists_one_row_per_job(client, h):
    three_versions(client, h)
    assert len(client.get("/api/jobs?status=COMPLETED").json()) == 3


def test_a_song_without_any_playable_version_is_not_in_the_library(client, h):
    h.provider.generate_response = ProviderUnavailableError("down")
    job = client.post("/api/jobs", json={"prompt": "never worked"}).json()
    assert job["status"] == "FAILED"
    assert client.get("/api/songs").json() == {"items": []}
    assert client.get(f"/api/songs/{job['song_id']}").status_code == 200  # details still exist


def test_a_failed_newest_version_does_not_hide_or_replace_the_playable_latest(client, h):
    v1 = generate(client, h, "good take", title="Mixed")
    failed_generation(client, h, v1["song_id"])

    row = client.get("/api/songs").json()["items"][0]
    assert (row["version_count"], row["latest_version"]["version_number"]) == (1, 1)

    versions = client.get(f"/api/songs/{v1['song_id']}").json()["versions"]
    assert [v["version_number"] for v in versions] == [2, 1]
    # Phase 5B: a failed version is never marked Latest; the newest version WITH audio is.
    assert versions[0]["status"] == "FAILED" and versions[0]["audio"] is None and versions[0]["is_latest"] is False
    assert versions[1]["audio"] is not None and versions[1]["is_latest"] is True


# -- Song Details ---------------------------------------------------------------------------------


def test_song_details_list_versions_newest_first_with_one_latest_and_their_own_audio(client, h):
    v1, v2, v3 = three_versions(client, h)

    body = client.get(f"/api/songs/{v1['song_id']}").json()

    assert body["title"] == "I Will Rise" and body["id"] == v1["song_id"]
    versions = body["versions"]
    assert [v["version_number"] for v in versions] == [3, 2, 1]
    assert [v["is_latest"] for v in versions] == [True, False, False]
    assert [v["audio"]["audio_url"] for v in versions] == [f"/api/jobs/{j['id']}/audio" for j in (v3, v2, v1)]
    assert [v["id"] for v in versions] == [v3["version_id"], v2["version_id"], v1["version_id"]]
    bytes_by_version = [client.get(v["audio"]["audio_url"]).content for v in versions]
    assert len(set(bytes_by_version)) == 3  # each version really has its own audio
    assert all(v["audio"]["size_bytes"] == len(b) for v, b in zip(versions, bytes_by_version))
    assert versions[2]["prompt"] == "rise up" and versions[0]["prompt"] == "rise highest"
    assert set(versions[0]) == {
        "id", "version_number", "is_latest", "operation", "source_version_number", "status", "created_at", "duration", "audio",
        "prompt", "lyrics", "language", "instrumental", "seed",
    }
    assert set(versions[0]["audio"]) == {"filename", "media_type", "size_bytes", "audio_url"}


def test_reading_songs_and_versions_never_creates_jobs_or_changes_data(client, h, tmp_path):
    v1, *_ = three_versions(client, h)

    def counts():
        conn = sqlite3.connect(h.db)
        try:
            return tuple(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("songs", "versions", "jobs"))
        finally:
            conn.close()

    before = counts()
    dump = sqlite3.connect(h.db).execute("SELECT * FROM versions ORDER BY id").fetchall()
    for _ in range(3):
        client.get("/api/songs")
        details = client.get(f"/api/songs/{v1['song_id']}").json()
        for v in details["versions"]:
            client.get(v["audio"]["audio_url"])  # "selecting" a version = reading its audio
    assert counts() == before == (1, 3, 3)
    assert sqlite3.connect(h.db).execute("SELECT * FROM versions ORDER BY id").fetchall() == dump


def test_a_version_with_a_deleted_file_is_listed_and_fails_safely_when_its_audio_is_read(client, h):
    v1 = generate(client, h, "p", title="Gone")
    (h.tmp_path / "audio" / v1["id"] / f"{v1['id']}.mp3").unlink()

    version = client.get(f"/api/songs/{v1['song_id']}").json()["versions"][0]
    assert version["audio"]["audio_url"] == f"/api/jobs/{v1['id']}/audio"
    audio = client.get(version["audio"]["audio_url"])
    assert audio.status_code == 500 and audio.json() == {"detail": "Audio is unavailable."}


# -- errors -----------------------------------------------------------------------------------------


def test_unknown_song_is_404_and_malformed_ids_are_rejected_without_touching_anything(client, h):
    assert client.get("/api/songs/song-does-not-exist").status_code == 404
    assert client.get("/api/songs/ver-does-not-exist").status_code == 404
    for bad in ("a'b", "a b", "a.b", "-lead", "x" * 81, "a%5Cb", "C%3A%5CWindows", "a%27%20OR%20%271%27=%271", "%2e%2e", "a%0d%0ab"):
        status = client.get(f"/api/songs/{bad}").status_code
        assert status == 422, (bad, status)
    for weird in ("..%2F..%2Fetc%2Fpasswd", "..%5C..%5Cx", "%2Fetc%2Fpasswd"):
        assert client.get(f"/api/songs/{weird}").status_code in (404, 422), weird


def test_bad_library_parameters_are_422(client):
    assert client.get("/api/songs?sort=../../etc/passwd").status_code == 422
    assert client.get("/api/songs?sort=DROP TABLE songs").status_code == 422
    assert client.get("/api/songs?limit=0").status_code == 422
    assert client.get("/api/songs?limit=999").status_code == 422
    assert client.get("/api/songs?q=" + "x" * 101).status_code == 422


# -- cross-song protection ------------------------------------------------------------------------------


def test_a_song_never_returns_another_songs_versions_or_audio(client, h):
    a1, a2, _ = three_versions(client, h, title="Song A")
    b1 = generate(client, h, "b one", title="Song B")
    b2 = generate(client, h, "b two", song_id=b1["song_id"])

    a = client.get(f"/api/songs/{a1['song_id']}").json()
    b = client.get(f"/api/songs/{b1['song_id']}").json()

    a_ids, b_ids = {v["id"] for v in a["versions"]}, {v["id"] for v in b["versions"]}
    assert a_ids.isdisjoint(b_ids) and len(a_ids) == 3 and len(b_ids) == 2
    a_audio = {v["audio"]["audio_url"] for v in a["versions"]}
    assert f"/api/jobs/{b1['id']}/audio" not in a_audio and f"/api/jobs/{b2['id']}/audio" not in a_audio
    assert {v["prompt"] for v in b["versions"]} == {"b one", "b two"}
    # Version numbers restart per song, but identities never cross.
    assert [v["version_number"] for v in b["versions"]] == [2, 1] and a["versions"][0]["version_number"] == 3


# -- search + sort ------------------------------------------------------------------------------------------


def test_search_matches_title_or_any_version_prompt_and_groups_the_song_once(client, h):
    v1, *_ = three_versions(client, h)
    generate(client, h, "quiet piano", title="Evening")

    def titles(q):
        return [i["title"] for i in client.get("/api/songs", params={"q": q}).json()["items"]]

    assert titles("I Will Rise") == ["I Will Rise"]
    assert client.get("/api/songs", params={"q": "i will rise"}).json()["items"][0]["version_count"] == 3
    assert titles("HIGHEST") == ["I Will Rise"]  # an older/newer version's prompt still finds the song, once
    assert titles("piano") == ["Evening"]
    assert titles("no-such-thing") == []
    assert len(titles("")) == 2


def test_search_text_is_data_never_sql_or_a_wildcard(client, h):
    three_versions(client, h)
    for hostile in ("%", "_", "'", "' OR 1=1 --", "\\", "x' UNION SELECT * FROM jobs --", "!"):
        assert client.get("/api/songs", params={"q": hostile}).json() == {"items": []}, hostile
    assert len(client.get("/api/songs").json()["items"]) == 1  # tables intact


def test_sorting_newest_oldest_and_title_and_a_new_version_moves_the_song_up(client, h):
    zebra = generate(client, h, "z", title="Zebra")
    apple = generate(client, h, "a", title="Apple")
    mango = generate(client, h, "m", title="Mango")

    def order(sort):
        return [i["title"] for i in client.get("/api/songs", params={"sort": sort}).json()["items"]]

    assert order("newest") == ["Mango", "Apple", "Zebra"]
    assert order("oldest") == ["Zebra", "Apple", "Mango"]
    assert order("title") == ["Apple", "Mango", "Zebra"]
    generate(client, h, "z again", song_id=zebra["song_id"])  # newest activity is a new version of Zebra
    assert order("newest") == ["Zebra", "Mango", "Apple"]
    assert order("oldest")[0] == "Apple"
    assert client.get("/api/songs", params={"limit": 2}).json()["items"].__len__() == 2


# -- leaks + performance + legacy + repository parity ----------------------------------------------------------------


def test_song_responses_expose_no_paths_keys_provider_ids_or_errors(client, h):
    v1, *_ = three_versions(client, h)
    failed_generation(client, h, v1["song_id"])
    text = client.get("/api/songs").text + client.get(f"/api/songs/{v1['song_id']}").text
    for leaked in (str(h.tmp_path), "absolute_path", ACE_ID, "provider", "/v1/audio", "8001", "secret", "down", "error", ".mp3/"):
        assert leaked not in text, leaked
    assert '"key"' not in text


def test_library_listing_does_not_query_per_song(tmp_path, monkeypatch):
    repository = SqliteJobRepository(tmp_path / "tunora.db")
    from tests.songs.test_domain import new_generation

    for i in range(30):
        _, _, job = new_generation(repository, prompt=f"song {i}")
        repository.complete_job(job, __import__("app.songs.models", fromlist=["VersionAudio"]).VersionAudio(
            key=f"{job.id}/{job.id}.mp3", filename=f"{job.id}.mp3", media_type="audio/mpeg", size_bytes=10, duration=5.0
        ))
    statements: list[str] = []
    original = SqliteJobRepository._connect

    def traced(self):
        conn = original(self)
        conn.set_trace_callback(lambda sql: statements.append(sql) if sql.lstrip().upper().startswith("SELECT") else None)
        return conn

    monkeypatch.setattr(SqliteJobRepository, "_connect", traced)
    assert len(repository.list_song_summaries(query="", sort="newest", limit=50)) == 30
    assert len(statements) <= 2  # one summary query + one bulk version lookup, not 30+


def test_pre_domain_jobs_appear_in_the_song_library_after_migration(tmp_path):
    from tests.songs.test_migration import UUID_1, make_legacy_db

    db = tmp_path / "legacy.db"
    make_legacy_db(db)
    sqlite3.connect(db).execute("DELETE FROM jobs WHERE id = 'odd/legacy id'").connection.commit()
    from app.jobs.service import JobService
    from tests.jobs.fakes import FakeAudioStorage, FakeProvider

    app = FastAPI()
    app.include_router(songs_router)
    app.state.job_service = JobService(repository=SqliteJobRepository(db), provider=FakeProvider(), storage=FakeAudioStorage())
    client = TestClient(app)

    items = client.get("/api/songs").json()["items"]
    assert {i["title"] for i in items} == {"Evening Rain", "Upbeat synth loop for a road"}  # only the two with audio
    assert all(i["version_count"] == 1 and i["latest_version"]["version_number"] == 1 for i in items)
    details = client.get(f"/api/songs/song-{UUID_1}").json()
    assert details["versions"][0]["audio"]["audio_url"] == f"/api/jobs/tunora-{UUID_1}/audio"


def test_in_memory_repository_behaves_the_same(tmp_path):
    from app.songs.models import VersionAudio
    from tests.songs.test_domain import new_generation

    repo = InMemoryJobRepository()
    song, v1, j1 = new_generation(repo, prompt="rise up")
    _, v2, j2 = new_generation(repo, song=song, prompt="rise more")
    _, _, j3 = new_generation(repo, song=song, prompt="fails")
    for job in (j1, j2):
        repo.complete_job(job, VersionAudio(key="k", filename="f.mp3", media_type="audio/mpeg", size_bytes=1, duration=2.0))
    (summary,) = repo.list_song_summaries(query="MORE", sort="newest", limit=10)
    assert (summary.version_count, summary.latest.version_number) == (2, 2)
    entries = repo.list_version_entries(song.id)
    assert [e.version.version_number for e in entries] == [3, 2, 1] and entries[0].job_id == j3.id
    assert repo.list_song_summaries(query="zzz", sort="title", limit=10) == []
