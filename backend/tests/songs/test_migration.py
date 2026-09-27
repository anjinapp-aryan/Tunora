"""Phase 4 schema migration: legacy jobs -> songs + version 1, non-destructive and repeat-safe."""

from __future__ import annotations

import json
import sqlite3

import pytest

from app.jobs import migrations
from app.jobs.migrations import LATEST_VERSION, legacy_ids, migrate
from app.jobs.models import JobStatus
from app.jobs.repository import SqliteJobRepository
from app.songs.models import VersionAudio

UUID_1 = "11111111-1111-4111-8111-111111111111"
UUID_2 = "22222222-2222-4222-8222-222222222222"
UUID_3 = "33333333-3333-4333-8333-333333333333"

LEGACY_COLUMNS = (
    "id, provider, status, request_json, created_at, submitted_at, started_at, completed_at, "
    "failed_at, provider_job_id, error, result_json, title"
)

PRE_TITLE_SCHEMA = """
CREATE TABLE jobs (
    id TEXT PRIMARY KEY, provider TEXT NOT NULL, status TEXT NOT NULL, request_json TEXT NOT NULL,
    created_at TEXT NOT NULL, submitted_at TEXT, started_at TEXT, completed_at TEXT, failed_at TEXT,
    provider_job_id TEXT, error TEXT, result_json TEXT
)
"""
WITH_TITLE_SCHEMA = PRE_TITLE_SCHEMA.replace("result_json TEXT\n", "result_json TEXT, title TEXT NOT NULL DEFAULT ''\n")


def audio_result(job_id: str, duration: float = 30.0) -> str:
    return json.dumps(
        {
            "audio": {
                "key": f"{job_id}/{job_id}.mp3",
                "absolute_path": f"C:/secret/{job_id}.mp3",
                "filename": f"{job_id}.mp3",
                "media_type": "audio/mpeg",
                "size_bytes": 470000,
            },
            "duration": duration,
            "metadata": {"bpm": 120},
        }
    )


def make_legacy_db(path, *, with_title: bool = True) -> None:
    """A database as it existed before Phase 4 (user_version 0), with realistic jobs."""

    conn = sqlite3.connect(path)
    conn.execute(WITH_TITLE_SCHEMA if with_title else PRE_TITLE_SCHEMA)
    rows = [
        # completed, vocal, all settings, user-chosen title
        (f"tunora-{UUID_1}", "ace-step", "COMPLETED",
         json.dumps({"prompt": "warm cinematic ballad", "lyrics": "[Verse] hello", "language": "kn", "duration": 60.0,
                     "seed": 42, "instrumental": False, "batch_size": None}),
         "2026-09-01T10:00:00+00:00", audio_result(f"tunora-{UUID_1}", 60.0), "Evening Rain"),
        # completed instrumental, no stored title -> derived
        (f"tunora-{UUID_2}", "ace-step", "COMPLETED",
         json.dumps({"prompt": "upbeat synth loop for a road trip today", "instrumental": True}),
         "2026-09-02T10:00:00+00:00", audio_result(f"tunora-{UUID_2}", 30.0), ""),
        # failed, has an error that must not be lost
        (f"tunora-{UUID_3}", "ace-step", "FAILED", json.dumps({"prompt": "broke", "seed": 7}),
         "2026-09-03T10:00:00+00:00", None, "Broken"),
        # running
        ("tunora-running-1", "ace-step", "RUNNING", json.dumps({"prompt": "in flight"}),
         "2026-09-04T10:00:00+00:00", None, ""),
        # unusual: non-uuid id, completed but with a corrupt result blob
        ("odd/legacy id", "ace-step", "COMPLETED", json.dumps({"prompt": "odd one"}), "2026-09-05T10:00:00+00:00", "[1, 2", ""),
    ]
    for job_id, provider, status, request_json, created_at, result_json, title in rows:
        if with_title:
            conn.execute(
                f"INSERT INTO jobs ({LEGACY_COLUMNS}) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, 'ace-task', ?, ?, ?)",
                (job_id, provider, status, request_json, created_at, "raw failure C:\\x" if status == "FAILED" else None,
                 result_json, title),
            )
        else:
            conn.execute(
                "INSERT INTO jobs (id, provider, status, request_json, created_at, provider_job_id, error, result_json) "
                "VALUES (?, ?, ?, ?, ?, 'ace-task', ?, ?)",
                (job_id, provider, status, request_json, created_at,
                 "raw failure C:\\x" if status == "FAILED" else None, result_json),
            )
    conn.commit()
    conn.close()


def raw(path, sql, params=()):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def legacy_snapshot(path):
    return [tuple(r) for r in raw(path, f"SELECT {LEGACY_COLUMNS.replace(', title', '')} FROM jobs ORDER BY id")]


# -- the migration itself ---------------------------------------------------------------------


def test_legacy_database_migrates_without_losing_any_job_data(tmp_path):
    db = tmp_path / "legacy.db"
    make_legacy_db(db)
    before = legacy_snapshot(db)

    SqliteJobRepository(db)

    assert legacy_snapshot(db) == before  # every original column of every job is byte-identical
    assert raw(db, "PRAGMA user_version")[0][0] == LATEST_VERSION
    assert raw(db, "SELECT COUNT(*) FROM jobs")[0][0] == 5
    assert raw(db, "SELECT COUNT(*) FROM songs")[0][0] == 5
    assert raw(db, "SELECT COUNT(*) FROM versions")[0][0] == 5
    assert raw(db, "SELECT COUNT(*) FROM jobs WHERE version_id IS NULL")[0][0] == 0


def test_each_legacy_job_becomes_one_song_with_version_1_linked_to_the_same_job(tmp_path):
    db = tmp_path / "legacy.db"
    make_legacy_db(db)
    repo = SqliteJobRepository(db)

    job = repo.get(f"tunora-{UUID_1}")
    version = repo.get_version(job.version_id)
    song = repo.get_song(version.song_id)

    assert version.version_number == 1 and version.provider == "ace-step"
    assert (version.id, song.id) == (f"ver-{UUID_1}", f"song-{UUID_1}")
    assert song.title == "Evening Rain"  # existing title preserved
    assert job.title == "Evening Rain"
    assert repo.list_versions(song.id) == [version]


def test_generation_settings_and_the_audio_reference_are_preserved(tmp_path):
    db = tmp_path / "legacy.db"
    make_legacy_db(db)
    repo = SqliteJobRepository(db)

    version = repo.get_version(repo.get(f"tunora-{UUID_1}").version_id)
    assert (version.spec.prompt, version.spec.lyrics, version.spec.language) == ("warm cinematic ballad", "[Verse] hello", "kn")
    assert (version.spec.duration, version.spec.seed, version.spec.instrumental) == (60.0, 42, False)
    assert version.audio == VersionAudio(
        key=f"tunora-{UUID_1}/tunora-{UUID_1}.mp3", filename=f"tunora-{UUID_1}.mp3",
        media_type="audio/mpeg", size_bytes=470000, duration=60.0,
    )
    # The job's own stored result (and therefore the audio route) is untouched.
    assert repo.get(f"tunora-{UUID_1}").result["audio"]["key"] == version.audio.key


def test_missing_optional_fields_take_defaults_and_titles_are_derived(tmp_path):
    db = tmp_path / "legacy.db"
    make_legacy_db(db)
    repo = SqliteJobRepository(db)

    job = repo.get(f"tunora-{UUID_2}")
    version = repo.get_version(job.version_id)
    assert version.spec.instrumental is True
    assert (version.spec.lyrics, version.spec.language, version.spec.duration, version.spec.seed) == ("", "en", None, None)
    assert repo.get_song(version.song_id).title == "Upbeat synth loop for a road"


def test_failed_and_running_jobs_migrate_without_audio(tmp_path):
    db = tmp_path / "legacy.db"
    make_legacy_db(db)
    repo = SqliteJobRepository(db)

    failed = repo.get(f"tunora-{UUID_3}")
    assert failed.status == JobStatus.FAILED and failed.error == "raw failure C:\\x"  # internal detail kept, not exposed
    assert repo.get_version(failed.version_id).audio is None
    assert repo.get_version(failed.version_id).spec.seed == 7
    assert repo.get_version(repo.get("tunora-running-1").version_id).audio is None


def test_unusual_legacy_rows_still_migrate_safely(tmp_path):
    db = tmp_path / "legacy.db"
    make_legacy_db(db)
    ids = legacy_ids("odd/legacy id")
    assert ids[0].startswith("song-legacy-") and ids[1].startswith("ver-legacy-")
    assert all("/" not in i and " " not in i for i in ids)

    SqliteJobRepository(db)

    # The corrupt result blob yields a version with NO audio reference (nothing invented), and the
    # migration neither crashed nor lost the job.
    rows = raw(db, "SELECT v.audio_key, v.prompt, j.result_json FROM versions v JOIN jobs j ON j.version_id = v.id WHERE j.id = ?", ("odd/legacy id",))
    assert len(rows) == 1
    assert rows[0]["audio_key"] is None and rows[0]["prompt"] == "odd one" and rows[0]["result_json"] == "[1, 2"


def test_pre_title_databases_migrate_too(tmp_path):
    db = tmp_path / "old.db"
    make_legacy_db(db, with_title=False)
    repo = SqliteJobRepository(db)
    assert repo.get(f"tunora-{UUID_1}").version_id == f"ver-{UUID_1}"
    assert repo.get_song(f"song-{UUID_1}").title == "Warm cinematic ballad"  # derived: no title column existed


def test_an_empty_or_new_database_gets_the_schema_and_no_rows(tmp_path):
    db = tmp_path / "new.db"
    repo = SqliteJobRepository(db)
    assert raw(db, "PRAGMA user_version")[0][0] == LATEST_VERSION
    assert raw(db, "SELECT COUNT(*) FROM songs")[0][0] == raw(db, "SELECT COUNT(*) FROM versions")[0][0] == 0
    assert repo.list() == []

    empty_legacy = tmp_path / "empty-legacy.db"
    sqlite3.connect(empty_legacy).execute(WITH_TITLE_SCHEMA).connection.close()
    SqliteJobRepository(empty_legacy)
    assert raw(empty_legacy, "SELECT COUNT(*) FROM songs")[0][0] == 0


# -- idempotency ------------------------------------------------------------------------------


def test_running_the_migration_again_creates_no_duplicates_and_changes_nothing(tmp_path):
    db = tmp_path / "legacy.db"
    make_legacy_db(db)
    SqliteJobRepository(db)
    state = (
        legacy_snapshot(db),
        [tuple(r) for r in raw(db, "SELECT * FROM songs ORDER BY id")],
        [tuple(r) for r in raw(db, "SELECT * FROM versions ORDER BY id")],
        [tuple(r) for r in raw(db, "SELECT id, version_id FROM jobs ORDER BY id")],
    )

    SqliteJobRepository(db)  # a normal restart
    conn = sqlite3.connect(db)
    migrate(conn)  # explicit second run
    conn.execute("PRAGMA user_version = 1")  # even if the version marker is lost, the backfill must not duplicate
    conn.commit()
    migrate(conn)
    conn.close()

    assert state == (
        legacy_snapshot(db),
        [tuple(r) for r in raw(db, "SELECT * FROM songs ORDER BY id")],
        [tuple(r) for r in raw(db, "SELECT * FROM versions ORDER BY id")],
        [tuple(r) for r in raw(db, "SELECT id, version_id FROM jobs ORDER BY id")],
    )
    assert raw(db, "SELECT COUNT(*) FROM songs")[0][0] == 5


def test_new_jobs_after_migration_do_not_disturb_migrated_songs(tmp_path):
    db = tmp_path / "legacy.db"
    make_legacy_db(db)
    repo = SqliteJobRepository(db)
    from tests.songs.test_domain import new_generation

    song = repo.get_song(f"song-{UUID_1}")
    _, version, _ = new_generation(repo, song=song, prompt="second take")

    assert version.version_number == 2  # continues after the migrated version 1
    assert repo.get_version(f"ver-{UUID_1}").version_number == 1
    assert repo.get_version(f"ver-{UUID_1}").spec.prompt == "warm cinematic ballad"


# -- failure safety ---------------------------------------------------------------------------


def test_a_failing_migration_step_rolls_back_completely_and_keeps_the_old_data(tmp_path, monkeypatch):
    db = tmp_path / "legacy.db"
    make_legacy_db(db)
    before = legacy_snapshot(db)

    def boom(conn):
        raise RuntimeError("simulated failure mid-backfill")

    monkeypatch.setattr(migrations, "_backfill_legacy_jobs", boom)
    with pytest.raises(RuntimeError, match="simulated"):
        SqliteJobRepository(db)

    assert legacy_snapshot(db) == before
    assert raw(db, "PRAGMA user_version")[0][0] == 1  # v2 step fully undone
    tables = {r[0] for r in raw(db, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "songs" not in tables and "versions" not in tables
    assert "version_id" not in {r[1] for r in raw(db, "PRAGMA table_info(jobs)")}

    monkeypatch.undo()  # the next start succeeds from that clean state
    SqliteJobRepository(db)
    assert raw(db, "SELECT COUNT(*) FROM songs")[0][0] == 5


def test_a_database_from_a_newer_build_is_refused_not_downgraded(tmp_path):
    db = tmp_path / "future.db"
    conn = sqlite3.connect(db)
    conn.execute(WITH_TITLE_SCHEMA)
    conn.execute(f"PRAGMA user_version = {LATEST_VERSION + 1}")
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="newer"):
        SqliteJobRepository(db)


def test_a_migrated_completed_job_still_serves_its_audio(tmp_path):
    """The audio route keeps working for pre-Phase-4 jobs (existing audio preserved in place)."""

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.routes_jobs import router
    from app.jobs.service import JobService
    from app.storage.local import LocalAudioStorage
    from tests.jobs.fakes import FakeProvider

    db = tmp_path / "legacy.db"
    make_legacy_db(db)
    sqlite3.connect(db).execute("DELETE FROM jobs WHERE id = 'odd/legacy id'").connection.commit()  # a corrupt blob cannot be loaded by the app (pre-existing)
    storage_root = tmp_path / "audio"
    job_id = f"tunora-{UUID_1}"
    (storage_root / job_id).mkdir(parents=True)
    (storage_root / job_id / f"{job_id}.mp3").write_bytes(b"ID3" + b"x" * 500)

    app = FastAPI()
    app.include_router(router)
    app.state.job_service = JobService(
        repository=SqliteJobRepository(db), provider=FakeProvider(), storage=LocalAudioStorage(storage_root)
    )
    client = TestClient(app)

    audio = client.get(f"/api/jobs/{job_id}/audio")
    assert audio.status_code == 200 and audio.content.startswith(b"ID3")
    body = client.get(f"/api/jobs/{job_id}").json()
    assert (body["song_id"], body["version_id"], body["version_number"]) == (f"song-{UUID_1}", f"ver-{UUID_1}", 1)
    assert body["title"] == "Evening Rain"
    assert body["result"]["audio"]["audio_url"] == f"/api/jobs/{job_id}/audio"
    assert "C:/secret" not in client.get("/api/jobs").text  # the stored absolute path never leaks
