from app.jobs.models import Job, JobStatus
from app.jobs.repository import InMemoryJobRepository, SqliteJobRepository
from app.providers.base import GenerationRequest


def _make_job(job_id: str = "tunora-1") -> Job:
    return Job(
        id=job_id,
        provider="ace-step",
        status=JobStatus.CREATED,
        request=GenerationRequest(prompt="p", lyrics="l", language="en", duration=10.0),
    )


def test_in_memory_repository_create_get_update():
    repo = InMemoryJobRepository()
    job = _make_job()
    repo.create(job)

    fetched = repo.get(job.id)
    assert fetched is not None
    assert fetched.status == JobStatus.CREATED

    job.status = JobStatus.SUBMITTED
    repo.update(job)
    assert repo.get(job.id).status == JobStatus.SUBMITTED


def test_repository_get_unknown_returns_none():
    repo = InMemoryJobRepository()
    assert repo.get("does-not-exist") is None


def test_sqlite_repository_persists_fields_roundtrip(tmp_path):
    db_path = tmp_path / "tunora.db"
    repo = SqliteJobRepository(db_path)
    job = _make_job()
    job.provider_job_id = "ace-step-task-abc"
    repo.create(job)

    fetched = repo.get(job.id)
    assert fetched.id == job.id
    assert fetched.provider == "ace-step"
    assert fetched.provider_job_id == "ace-step-task-abc"
    assert fetched.request == job.request
    assert fetched.status == JobStatus.CREATED


def test_sqlite_repository_survives_restart(tmp_path):
    """Simulates a FastAPI process restart: a fresh repository instance
    pointed at the same database file must see jobs written before restart.
    """

    db_path = tmp_path / "tunora.db"

    repo_before_restart = SqliteJobRepository(db_path)
    job = _make_job("tunora-restart-test")
    job.status = JobStatus.RUNNING
    repo_before_restart.create(job)
    del repo_before_restart  # simulate process exit

    repo_after_restart = SqliteJobRepository(db_path)
    fetched = repo_after_restart.get("tunora-restart-test")
    assert fetched is not None
    assert fetched.status == JobStatus.RUNNING


def test_sqlite_repository_list_orders_newest_first(tmp_path):
    repo = SqliteJobRepository(tmp_path / "tunora.db")
    job1 = _make_job("tunora-a")
    job2 = _make_job("tunora-b")
    repo.create(job1)
    repo.create(job2)

    jobs = repo.list(limit=10)
    assert {j.id for j in jobs} == {"tunora-a", "tunora-b"}


def test_sqlite_title_roundtrip_and_migration_of_an_old_database(tmp_path):
    import sqlite3

    db_path = tmp_path / "old.db"
    # A database created before titles existed (no title column).
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE jobs (id TEXT PRIMARY KEY, provider TEXT NOT NULL, status TEXT NOT NULL, "
            "request_json TEXT NOT NULL, created_at TEXT NOT NULL, submitted_at TEXT, started_at TEXT, "
            "completed_at TEXT, failed_at TEXT, provider_job_id TEXT, error TEXT, result_json TEXT)"
        )
        conn.execute(
            "INSERT INTO jobs (id, provider, status, request_json, created_at) VALUES (?, ?, ?, ?, ?)",
            ("tunora-old", "ace-step", "COMPLETED", '{"prompt": "old song"}', "2026-01-01T00:00:00+00:00"),
        )

    repo = SqliteJobRepository(db_path)  # must migrate, not fail or lose data
    old = repo.get("tunora-old")
    assert old is not None and old.title == "" and old.status == JobStatus.COMPLETED

    new = _make_job("tunora-new")
    new.title = "Brand New"
    repo.create(new)
    assert SqliteJobRepository(db_path).get("tunora-new").title == "Brand New"
