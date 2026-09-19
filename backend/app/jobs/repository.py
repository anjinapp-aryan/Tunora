"""Tunora's own job persistence layer.

`JobRepository` is the abstraction the rest of the app depends on. Two
implementations are provided:

- `InMemoryJobRepository` — for fast unit tests; state is lost on process exit.
- `SqliteJobRepository` — the MVP's real persistence (see
  docs/PHASE-3-JOB-LIFECYCLE.md for the reuse audit behind this choice).

A future `PostgresJobRepository` implementing the same interface is a
drop-in replacement — `JobService` and everything above it depends only on
this abstraction, never on SQL or a specific database.
"""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.jobs.models import Job, JobStatus
from app.providers.base import GenerationRequest


class JobRepository(ABC):
    """Persistence interface for Tunora generation jobs."""

    @abstractmethod
    def create(self, job: Job) -> None: ...

    @abstractmethod
    def get(self, job_id: str) -> Optional[Job]: ...

    @abstractmethod
    def update(self, job: Job) -> None: ...

    @abstractmethod
    def list(self, limit: int = 50) -> list[Job]: ...


class InMemoryJobRepository(JobRepository):
    """Process-local job store. Does not survive a restart — tests only."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def create(self, job: Job) -> None:
        self._jobs[job.id] = job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def update(self, job: Job) -> None:
        self._jobs[job.id] = job

    def list(self, limit: int = 50) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)[:limit]


def _dt_to_str(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _str_to_dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


class SqliteJobRepository(JobRepository):
    """SQLite-backed job store — Tunora's MVP persistence choice.

    Uses the stdlib `sqlite3` module directly rather than an ORM: at this
    scale (single-process, single-developer-machine, a handful of columns)
    an ORM would add a dependency without solving a problem Tunora actually
    has, and the `JobRepository` interface already isolates callers from
    this implementation detail.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    submitted_at TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    failed_at TEXT,
                    provider_job_id TEXT,
                    error TEXT,
                    result_json TEXT,
                    title TEXT NOT NULL DEFAULT ''
                )
                """
            )
            # Additive migration for databases created before titles existed.
            columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
            if "title" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN title TEXT NOT NULL DEFAULT ''")

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        return Job(
            id=row["id"],
            provider=row["provider"],
            status=JobStatus(row["status"]),
            request=GenerationRequest(**json.loads(row["request_json"])),
            created_at=_str_to_dt(row["created_at"]),
            submitted_at=_str_to_dt(row["submitted_at"]),
            started_at=_str_to_dt(row["started_at"]),
            completed_at=_str_to_dt(row["completed_at"]),
            failed_at=_str_to_dt(row["failed_at"]),
            provider_job_id=row["provider_job_id"],
            error=row["error"],
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            title=row["title"] or "",
        )

    def _job_to_params(self, job: Job) -> tuple[Any, ...]:
        return (
            job.id,
            job.provider,
            job.status.value,
            json.dumps(asdict(job.request)),
            _dt_to_str(job.created_at),
            _dt_to_str(job.submitted_at),
            _dt_to_str(job.started_at),
            _dt_to_str(job.completed_at),
            _dt_to_str(job.failed_at),
            job.provider_job_id,
            job.error,
            json.dumps(job.result) if job.result is not None else None,
            job.title,
        )

    def create(self, job: Job) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, provider, status, request_json, created_at,
                                   submitted_at, started_at, completed_at, failed_at,
                                   provider_job_id, error, result_json, title)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._job_to_params(job),
            )

    def get(self, job_id: str) -> Optional[Job]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def update(self, job: Job) -> None:
        params = self._job_to_params(job)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs SET provider=?, status=?, request_json=?, created_at=?,
                    submitted_at=?, started_at=?, completed_at=?, failed_at=?,
                    provider_job_id=?, error=?, result_json=?, title=?
                WHERE id=?
                """,
                params[1:] + (job.id,),
            )

    def list(self, limit: int = 50) -> list[Job]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_job(row) for row in rows]
