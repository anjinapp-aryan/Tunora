"""Tunora's own persistence layer for jobs and the Song/Version domain.

`JobRepository` is the abstraction the rest of the app depends on (it extends
`SongRepository` because creating a generation and completing it must be
atomic across the songs, versions and jobs tables). Two implementations:

- `InMemoryJobRepository` — for fast unit tests; state is lost on process exit.
- `SqliteJobRepository` — the real persistence (see docs/PHASE-3-JOB-LIFECYCLE.md
  and docs/PHASE-4-SONG-VERSION-DOMAIN.md).

A future `PostgresJobRepository` implementing the same interface is a
drop-in replacement — nothing above this layer depends on SQL.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from abc import abstractmethod
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Sequence

from app.jobs.migrations import migrate
from app.jobs.models import Job, JobStatus
from app.providers.base import GenerationRequest
from app.songs.errors import ImmutableVersionError, SongNotFoundError, VersionNotFoundError
from app.songs.models import Song, Version, VersionAudio
from app.songs.repository import SongRepository

_MAX_IN_QUERY = 500


class JobRepository(SongRepository):
    """Persistence interface for generation jobs and the Song/Version domain."""

    @abstractmethod
    def create(self, job: Job) -> None:
        """Insert a job with no Song/Version (legacy/tests). Prefer create_generation."""

    @abstractmethod
    def get(self, job_id: str) -> Optional[Job]: ...

    @abstractmethod
    def update(self, job: Job) -> None: ...

    @abstractmethod
    def list(self, limit: int = 50) -> list[Job]: ...

    @abstractmethod
    def create_generation(self, *, new_song: Optional[Song], version: Version, job: Job) -> Version:
        """Atomically create (optionally) a Song, the next Version of it, and the Job.

        All-or-nothing. The version number is assigned inside the transaction
        (1 for a new song, otherwise max+1), `job.version_id` is set, and the
        stored Version is returned. Raises SongNotFoundError if `new_song` is
        None and `version.song_id` does not exist.
        """

    @abstractmethod
    def complete_job(self, job: Job, audio: VersionAudio) -> None:
        """Atomically persist a COMPLETED job and attach `audio` to its Version (write-once)."""


# -- in memory ------------------------------------------------------------------------


class InMemoryJobRepository(JobRepository):
    """Process-local store. Does not survive a restart — tests only."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._songs: dict[str, Song] = {}
        self._versions: dict[str, Version] = {}
        self._lock = threading.Lock()

    def create(self, job: Job) -> None:
        self._jobs[job.id] = job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def update(self, job: Job) -> None:
        self._jobs[job.id] = job

    def list(self, limit: int = 50) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)[:limit]

    def create_generation(self, *, new_song: Optional[Song], version: Version, job: Job) -> Version:
        with self._lock:
            if new_song is None and version.song_id not in self._songs:
                raise SongNotFoundError(version.song_id)
            if new_song is not None:
                self._songs[new_song.id] = new_song
            number = 1 + max((v.version_number for v in self._versions.values() if v.song_id == version.song_id), default=0)
            stored = replace(version, version_number=number)
            self._versions[stored.id] = stored
            job.version_id = stored.id
            self._jobs[job.id] = job
            return stored

    def complete_job(self, job: Job, audio: VersionAudio) -> None:
        with self._lock:
            if job.version_id:
                version = self._versions[job.version_id]
                if version.audio is not None and version.audio != audio:
                    raise ImmutableVersionError("version audio is write-once")
                self._versions[version.id] = replace(version, audio=audio)
            self._jobs[job.id] = job

    def get_song(self, song_id: str) -> Optional[Song]:
        return self._songs.get(song_id)

    def get_version(self, version_id: str) -> Optional[Version]:
        return self._versions.get(version_id)

    def get_versions(self, version_ids: Sequence[str]) -> dict[str, Version]:
        return {vid: self._versions[vid] for vid in version_ids if vid in self._versions}

    def list_versions(self, song_id: str) -> list[Version]:
        return sorted((v for v in self._versions.values() if v.song_id == song_id), key=lambda v: v.version_number)


# -- sqlite ---------------------------------------------------------------------------


def _dt_to_str(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _str_to_dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


_JOB_UPDATE_SQL = """
    UPDATE jobs SET provider=?, status=?, request_json=?, created_at=?,
        submitted_at=?, started_at=?, completed_at=?, failed_at=?,
        provider_job_id=?, error=?, result_json=?, title=?
    WHERE id=?
"""


class SqliteJobRepository(JobRepository):
    """SQLite-backed store — Tunora's persistence choice.

    Uses the stdlib `sqlite3` module directly rather than an ORM: at this
    scale (single-process, single-developer-machine) an ORM would add a
    dependency without solving a problem Tunora actually has. All SQL is
    parameterized. Schema changes go through `app.jobs.migrations`.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        conn = self._connect()
        try:
            migrate(conn)
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # -- row mapping ---------------------------------------------------------------

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
            version_id=row["version_id"],
        )

    @staticmethod
    def _row_to_version(row: sqlite3.Row) -> Version:
        audio = None
        if row["audio_key"] is not None:
            audio = VersionAudio(
                key=row["audio_key"],
                filename=row["audio_filename"],
                media_type=row["audio_media_type"],
                size_bytes=row["audio_size_bytes"],
                duration=row["audio_duration"],
            )
        return Version(
            id=row["id"],
            song_id=row["song_id"],
            version_number=row["version_number"],
            spec=GenerationRequest(
                prompt=row["prompt"],
                lyrics=row["lyrics"],
                language=row["language"],
                duration=row["duration"],
                seed=row["seed"],
                instrumental=bool(row["instrumental"]),
                batch_size=row["batch_size"],
            ),
            provider=row["provider"],
            created_at=_str_to_dt(row["created_at"]),
            audio=audio,
        )

    @staticmethod
    def _job_params(job: Job) -> tuple[Any, ...]:
        """Values in the column order of `_JOB_UPDATE_SQL` (minus the id)."""

        return (
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

    def _insert_job(self, conn: sqlite3.Connection, job: Job) -> None:
        conn.execute(
            """
            INSERT INTO jobs (id, provider, status, request_json, created_at, submitted_at, started_at,
                              completed_at, failed_at, provider_job_id, error, result_json, title, version_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (job.id, *self._job_params(job), job.version_id),
        )

    # -- jobs -----------------------------------------------------------------------

    def create(self, job: Job) -> None:
        with self._connect() as conn:
            self._insert_job(conn, job)

    def get(self, job_id: str) -> Optional[Job]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def update(self, job: Job) -> None:
        with self._connect() as conn:
            conn.execute(_JOB_UPDATE_SQL, (*self._job_params(job), job.id))

    def list(self, limit: int = 50) -> list[Job]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._row_to_job(row) for row in rows]

    # -- atomic domain writes ---------------------------------------------------------

    def create_generation(self, *, new_song: Optional[Song], version: Version, job: Job) -> Version:
        conn = self._connect()
        try:
            # IMMEDIATE takes the write lock up front, so two requests creating a
            # version of the same song serialize and cannot read the same MAX().
            conn.execute("BEGIN IMMEDIATE")
            if new_song is not None:
                conn.execute(
                    "INSERT INTO songs (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (new_song.id, new_song.title, _dt_to_str(new_song.created_at), _dt_to_str(new_song.updated_at)),
                )
            elif conn.execute("SELECT 1 FROM songs WHERE id = ?", (version.song_id,)).fetchone() is None:
                raise SongNotFoundError(version.song_id)
            number = conn.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 FROM versions WHERE song_id = ?", (version.song_id,)
            ).fetchone()[0]
            spec = version.spec
            conn.execute(
                "INSERT INTO versions (id, song_id, version_number, prompt, lyrics, language, duration, seed, "
                "instrumental, batch_size, provider, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    version.id, version.song_id, number, spec.prompt, spec.lyrics, spec.language, spec.duration,
                    spec.seed, 1 if spec.instrumental else 0, spec.batch_size, version.provider,
                    _dt_to_str(version.created_at),
                ),
            )
            job.version_id = version.id
            self._insert_job(conn, job)
            conn.commit()
            return replace(version, version_number=number)
        except BaseException:
            job.version_id = None
            conn.rollback()
            raise
        finally:
            conn.close()

    def complete_job(self, job: Job, audio: VersionAudio) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(_JOB_UPDATE_SQL, (*self._job_params(job), job.id))
            if job.version_id:
                try:
                    cursor = conn.execute(
                        "UPDATE versions SET audio_key=?, audio_filename=?, audio_media_type=?, "
                        "audio_size_bytes=?, audio_duration=? WHERE id=?",
                        (audio.key, audio.filename, audio.media_type, audio.size_bytes, audio.duration, job.version_id),
                    )
                except sqlite3.IntegrityError as exc:  # write-once trigger
                    raise ImmutableVersionError(str(exc)) from exc
                if cursor.rowcount != 1:
                    raise VersionNotFoundError(job.version_id)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    # -- songs / versions (read) ---------------------------------------------------------

    def get_song(self, song_id: str) -> Optional[Song]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()
        if row is None:
            return None
        return Song(
            id=row["id"],
            title=row["title"],
            created_at=_str_to_dt(row["created_at"]),
            updated_at=_str_to_dt(row["updated_at"]),
        )

    def get_version(self, version_id: str) -> Optional[Version]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM versions WHERE id = ?", (version_id,)).fetchone()
        return self._row_to_version(row) if row else None

    def get_versions(self, version_ids: Sequence[str]) -> dict[str, Version]:
        ids = list(dict.fromkeys(version_ids))[:_MAX_IN_QUERY]
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM versions WHERE id IN ({placeholders})", ids).fetchall()  # noqa: S608
        return {row["id"]: self._row_to_version(row) for row in rows}

    def list_versions(self, song_id: str) -> list[Version]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM versions WHERE song_id = ? ORDER BY version_number", (song_id,)
            ).fetchall()
        return [self._row_to_version(row) for row in rows]
