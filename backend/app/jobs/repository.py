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
from app.projects.errors import ProjectNotFoundError
from app.projects.models import Project, ProjectSongEntry, ProjectSummary
from app.projects.repository import ProjectRepository
from app.providers.base import GenerationRequest
from app.songs.errors import ImmutableVersionError, SongNotFoundError, VersionNotFoundError
from app.songs.models import Song, SongSummary, Version, VersionAudio, VersionEntry, utcnow
from app.songs.repository import PROJECT_FILTER_NONE, SongRepository

_MAX_IN_QUERY = 500


class JobRepository(SongRepository, ProjectRepository):
    """Persistence interface for generation jobs and the Song/Version/Project domain."""

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

    @abstractmethod
    def update_song(self, song_id: str, *, title: Optional[str] = None, is_favorite: Optional[bool] = None) -> Song:
        """Rename and/or (un)favorite a Song. Only the given fields change; `updated_at`
        always advances. Never touches a Version, a Job, or any audio. Raises
        SongNotFoundError if the Song does not exist."""

    @abstractmethod
    def delete_song(self, song_id: str) -> list[str]:
        """Delete a Song, all of its Versions, and their Jobs, in one transaction.

        Returns the (possibly empty) list of distinct audio storage keys that were
        attached to those Versions -- the caller deletes the actual files afterwards
        (see JobService.delete_song for why: a database transaction and a filesystem
        delete cannot be one atomic operation, so the DB is committed first and is
        the source of truth; the audio files are then best-effort cleaned up).
        Raises SongNotFoundError if the Song does not exist.
        """


# -- in memory ------------------------------------------------------------------------


class InMemoryJobRepository(JobRepository):
    """Process-local store. Does not survive a restart — tests only."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._songs: dict[str, Song] = {}
        self._versions: dict[str, Version] = {}
        self._projects: dict[str, Project] = {}
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

    def update_song(self, song_id: str, *, title: Optional[str] = None, is_favorite: Optional[bool] = None) -> Song:
        with self._lock:
            song = self._songs.get(song_id)
            if song is None:
                raise SongNotFoundError(song_id)
            updated = replace(
                song,
                title=song.title if title is None else title,
                is_favorite=song.is_favorite if is_favorite is None else is_favorite,
                updated_at=utcnow(),
            )
            self._songs[song_id] = updated
            return updated

    def delete_song(self, song_id: str) -> list[str]:
        with self._lock:
            if song_id not in self._songs:
                raise SongNotFoundError(song_id)
            version_ids = [v.id for v in self._versions.values() if v.song_id == song_id]
            keys = [v.audio.key for v in self._versions.values() if v.song_id == song_id and v.audio is not None]
            for job_id, job in list(self._jobs.items()):
                if job.version_id in version_ids:
                    del self._jobs[job_id]
            for version_id in version_ids:
                del self._versions[version_id]
            del self._songs[song_id]
            return keys

    def get_song(self, song_id: str) -> Optional[Song]:
        return self._songs.get(song_id)

    def get_version(self, version_id: str) -> Optional[Version]:
        return self._versions.get(version_id)

    def get_versions(self, version_ids: Sequence[str]) -> dict[str, Version]:
        return {vid: self._versions[vid] for vid in version_ids if vid in self._versions}

    def list_versions(self, song_id: str) -> list[Version]:
        return sorted((v for v in self._versions.values() if v.song_id == song_id), key=lambda v: v.version_number)

    def list_song_summaries(
        self, *, query: str, sort: str, limit: int, project: Optional[str] = None, favorite: Optional[bool] = None
    ) -> list[SongSummary]:
        needle = query.strip().lower()
        rows: list[SongSummary] = []
        for song in self._songs.values():
            if project == PROJECT_FILTER_NONE and song.project_id is not None:
                continue
            if project not in (None, PROJECT_FILTER_NONE) and song.project_id != project:
                continue
            if favorite is not None and song.is_favorite != favorite:
                continue
            playable = [v for v in self._versions.values() if v.song_id == song.id and v.audio is not None]
            if not playable:
                continue
            if needle and needle not in song.title.lower() and not any(needle in v.spec.prompt.lower() for v in self._versions.values() if v.song_id == song.id):
                continue
            rows.append(SongSummary(song=song, version_count=len(playable), latest=max(playable, key=lambda v: v.version_number)))
        if sort == "title":
            rows.sort(key=lambda r: (r.song.title.lower(), r.song.id))
        else:
            rows.sort(key=lambda r: (r.latest.created_at, r.song.id), reverse=(sort != "oldest"))
        return rows[:limit]

    def list_version_entries(self, song_id: str) -> list[VersionEntry]:
        entries = []
        for v in sorted((v for v in self._versions.values() if v.song_id == song_id), key=lambda v: v.version_number, reverse=True):
            jobs = sorted((j for j in self._jobs.values() if j.version_id == v.id), key=lambda j: j.created_at, reverse=True)
            entries.append(VersionEntry(version=v, job_id=jobs[0].id if jobs else None, job_status=jobs[0].status.value if jobs else None))
        return entries

    # -- projects (Phase 6) ---------------------------------------------------------

    def create_project(self, project: Project) -> None:
        with self._lock:
            self._projects[project.id] = project

    def get_project(self, project_id: str) -> Optional[Project]:
        return self._projects.get(project_id)

    def get_projects(self, project_ids: Sequence[str]) -> dict[str, Project]:
        return {pid: self._projects[pid] for pid in project_ids if pid in self._projects}

    def list_project_summaries(self, *, query: str, sort: str, limit: int) -> list[ProjectSummary]:
        needle = query.strip().lower()
        rows = []
        for project in self._projects.values():
            if needle and needle not in project.name.lower():
                continue
            count = sum(1 for s in self._songs.values() if s.project_id == project.id)
            rows.append(ProjectSummary(project=project, song_count=count))
        if sort == "title":
            rows.sort(key=lambda r: (r.project.name.lower(), r.project.id))
        else:
            rows.sort(key=lambda r: (r.project.updated_at, r.project.id), reverse=(sort != "oldest"))
        return rows[:limit]

    def update_project(self, project_id: str, *, name: Optional[str], description: Optional[str]) -> Project:
        with self._lock:
            current = self._projects.get(project_id)
            if current is None:
                raise ProjectNotFoundError(project_id)
            updated = replace(
                current,
                name=current.name if name is None else name,
                description=current.description if description is None else description,
                updated_at=utcnow(),
            )
            self._projects[project_id] = updated
            return updated

    def delete_project(self, project_id: str) -> None:
        with self._lock:
            if project_id not in self._projects:
                raise ProjectNotFoundError(project_id)
            del self._projects[project_id]
            for sid, song in list(self._songs.items()):
                if song.project_id == project_id:
                    self._songs[sid] = replace(song, project_id=None)

    def list_project_songs(self, project_id: str) -> list[ProjectSongEntry]:
        entries = []
        for song in self._songs.values():
            if song.project_id != project_id:
                continue
            versions = [v for v in self._versions.values() if v.song_id == song.id]
            entries.append(
                ProjectSongEntry(
                    song=song,
                    version_count=len(versions),
                    latest_version_number=max((v.version_number for v in versions), default=None),
                )
            )
        entries.sort(key=lambda e: (e.song.updated_at, e.song.id), reverse=True)
        return entries

    def assign_song_to_project(self, project_id: str, song_id: str) -> None:
        with self._lock:
            if project_id not in self._projects:
                raise ProjectNotFoundError(project_id)
            song = self._songs.get(song_id)
            if song is None:
                raise SongNotFoundError(song_id)
            self._songs[song_id] = replace(song, project_id=project_id, updated_at=utcnow())

    def remove_song_from_project(self, project_id: str, song_id: str) -> None:
        with self._lock:
            song = self._songs.get(song_id)
            if song is None:
                raise SongNotFoundError(song_id)
            if song.project_id == project_id:
                self._songs[song_id] = replace(song, project_id=None, updated_at=utcnow())


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
            operation=row["operation"],
            source_version_id=row["source_version_id"],
            operation_params=json.loads(row["operation_params"]) if row["operation_params"] else None,
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
                    "INSERT INTO songs (id, title, created_at, updated_at, project_id) VALUES (?, ?, ?, ?, ?)",
                    (new_song.id, new_song.title, _dt_to_str(new_song.created_at), _dt_to_str(new_song.updated_at), new_song.project_id),
                )
            elif conn.execute("SELECT 1 FROM songs WHERE id = ?", (version.song_id,)).fetchone() is None:
                raise SongNotFoundError(version.song_id)
            number = conn.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 FROM versions WHERE song_id = ?", (version.song_id,)
            ).fetchone()[0]
            spec = version.spec
            conn.execute(
                "INSERT INTO versions (id, song_id, version_number, prompt, lyrics, language, duration, seed, "
                "instrumental, batch_size, provider, created_at, operation, source_version_id, operation_params) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    version.id, version.song_id, number, spec.prompt, spec.lyrics, spec.language, spec.duration,
                    spec.seed, 1 if spec.instrumental else 0, spec.batch_size, version.provider,
                    _dt_to_str(version.created_at), version.operation, version.source_version_id,
                    json.dumps(version.operation_params) if version.operation_params else None,
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

    @staticmethod
    def _row_to_song(row: sqlite3.Row) -> Song:
        return Song(
            id=row["id"],
            title=row["title"],
            created_at=_str_to_dt(row["created_at"]),
            updated_at=_str_to_dt(row["updated_at"]),
            project_id=row["project_id"],
            is_favorite=bool(row["is_favorite"]),
        )

    def get_song(self, song_id: str) -> Optional[Song]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()
        return self._row_to_song(row) if row else None

    def update_song(self, song_id: str, *, title: Optional[str] = None, is_favorite: Optional[bool] = None) -> Song:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()
            if row is None:
                raise SongNotFoundError(song_id)
            current = self._row_to_song(row)
            new_title = current.title if title is None else title
            new_favorite = current.is_favorite if is_favorite is None else is_favorite
            now = _dt_to_str(utcnow())
            conn.execute(
                "UPDATE songs SET title = ?, is_favorite = ?, updated_at = ? WHERE id = ?",
                (new_title, 1 if new_favorite else 0, now, song_id),
            )
            conn.commit()
            return replace(current, title=new_title, is_favorite=new_favorite, updated_at=_str_to_dt(now))
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def delete_song(self, song_id: str) -> list[str]:
        # DB-first, then best-effort file cleanup (see JobRepository.delete_song's
        # docstring and docs/PHASE-9-SONG-MANAGEMENT.md "Filesystem deletion strategy"):
        # a DB transaction and a filesystem delete can't be one atomic operation, and
        # rolling back an already-deleted file is not possible, so the transaction that
        # CAN be made safe (the DB one) goes first and is the source of truth.
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM songs WHERE id = ?", (song_id,)).fetchone() is None:
                raise SongNotFoundError(song_id)
            keys = [
                r["audio_key"]
                for r in conn.execute(
                    "SELECT audio_key FROM versions WHERE song_id = ? AND audio_key IS NOT NULL", (song_id,)
                ).fetchall()
            ]
            conn.execute(
                "DELETE FROM jobs WHERE version_id IN (SELECT id FROM versions WHERE song_id = ?)", (song_id,)
            )
            conn.execute("DELETE FROM versions WHERE song_id = ?", (song_id,))
            conn.execute("DELETE FROM songs WHERE id = ?", (song_id,))
            conn.commit()
            return keys
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

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

    _SORT_CLAUSES = {
        "newest": "lv.created_at DESC, s.id",
        "oldest": "lv.created_at ASC, s.id",
        "title": "lower(s.title), s.id",
    }

    def list_song_summaries(
        self, *, query: str, sort: str, limit: int, project: Optional[str] = None, favorite: Optional[bool] = None
    ) -> list[SongSummary]:
        # One query: playable-version count and the latest playable version id per song
        # (no per-song follow-up queries); a second bulk lookup loads those versions.
        order_by = self._SORT_CLAUSES.get(sort, self._SORT_CLAUSES["newest"])  # whitelist, never user text
        needle = query.strip().lower()
        # '!' is the LIKE escape character, so user text cannot act as a wildcard.
        pattern = "%" + needle.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
        params: list[Any] = [needle, pattern, pattern]
        project_clause = ""
        if project == PROJECT_FILTER_NONE:
            project_clause = "AND s.project_id IS NULL "
        elif project is not None:
            project_clause = "AND s.project_id = ? "
            params.append(project)
        favorite_clause = ""
        if favorite is not None:
            favorite_clause = "AND s.is_favorite = ? "
            params.append(1 if favorite else 0)
        params.append(limit)
        sql = (
            "SELECT s.id, s.title, s.created_at, s.updated_at, s.project_id, s.is_favorite, lv.id AS latest_id, "
            "  (SELECT COUNT(*) FROM versions c WHERE c.song_id = s.id AND c.audio_key IS NOT NULL) AS version_count "
            "FROM songs s JOIN versions lv ON lv.song_id = s.id AND lv.audio_key IS NOT NULL "
            "  AND lv.version_number = (SELECT MAX(m.version_number) FROM versions m "
            "                           WHERE m.song_id = s.id AND m.audio_key IS NOT NULL) "
            "WHERE (? = '' OR lower(s.title) LIKE ? ESCAPE '!' "
            "       OR EXISTS (SELECT 1 FROM versions p WHERE p.song_id = s.id AND lower(p.prompt) LIKE ? ESCAPE '!')) "
            f"{project_clause}{favorite_clause}"
            f"ORDER BY {order_by} LIMIT ?"  # noqa: S608 - order_by/project_clause/favorite_clause are fixed, non-user-text
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        latest = self.get_versions([r["latest_id"] for r in rows])
        return [
            SongSummary(song=self._row_to_song(r), version_count=r["version_count"], latest=latest[r["latest_id"]])
            for r in rows
        ]

    def list_version_entries(self, song_id: str) -> list[VersionEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT v.*, j.id AS job_id, j.status AS job_status FROM versions v "
                "LEFT JOIN jobs j ON j.version_id = v.id WHERE v.song_id = ? "
                "ORDER BY v.version_number DESC, j.created_at DESC",
                (song_id,),
            ).fetchall()
        entries: dict[str, VersionEntry] = {}
        for row in rows:  # one entry per version; if it ever has several jobs the newest wins
            entries.setdefault(row["id"], VersionEntry(self._row_to_version(row), row["job_id"], row["job_status"]))
        return list(entries.values())

    # -- projects (Phase 6) ---------------------------------------------------------

    @staticmethod
    def _row_to_project(row: sqlite3.Row) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            description=row["description"] or "",
            created_at=_str_to_dt(row["created_at"]),
            updated_at=_str_to_dt(row["updated_at"]),
        )

    def create_project(self, project: Project) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO projects (id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (project.id, project.name, project.description, _dt_to_str(project.created_at), _dt_to_str(project.updated_at)),
            )

    def get_project(self, project_id: str) -> Optional[Project]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return self._row_to_project(row) if row else None

    def get_projects(self, project_ids: Sequence[str]) -> dict[str, Project]:
        ids = list(dict.fromkeys(project_ids))[:_MAX_IN_QUERY]
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM projects WHERE id IN ({placeholders})", ids).fetchall()  # noqa: S608
        return {row["id"]: self._row_to_project(row) for row in rows}

    _PROJECT_SORT_CLAUSES = {
        "newest": "p.updated_at DESC, p.id",
        "oldest": "p.updated_at ASC, p.id",
        "title": "lower(p.name), p.id",
    }

    def list_project_summaries(self, *, query: str, sort: str, limit: int) -> list[ProjectSummary]:
        # One query with a grouped song count -- never one COUNT(*) per project.
        order_by = self._PROJECT_SORT_CLAUSES.get(sort, self._PROJECT_SORT_CLAUSES["newest"])
        needle = query.strip().lower()
        pattern = "%" + needle.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
        sql = (
            "SELECT p.*, (SELECT COUNT(*) FROM songs s WHERE s.project_id = p.id) AS song_count "
            "FROM projects p WHERE (? = '' OR lower(p.name) LIKE ? ESCAPE '!') "
            f"ORDER BY {order_by} LIMIT ?"  # noqa: S608 - order_by comes from the fixed mapping above
        )
        with self._connect() as conn:
            rows = conn.execute(sql, (needle, pattern, limit)).fetchall()
        return [ProjectSummary(project=self._row_to_project(r), song_count=r["song_count"]) for r in rows]

    def update_project(self, project_id: str, *, name: Optional[str], description: Optional[str]) -> Project:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if row is None:
                raise ProjectNotFoundError(project_id)
            current = self._row_to_project(row)
            new_name = current.name if name is None else name
            new_description = current.description if description is None else description
            now = _dt_to_str(utcnow())
            conn.execute(
                "UPDATE projects SET name = ?, description = ?, updated_at = ? WHERE id = ?",
                (new_name, new_description, now, project_id),
            )
            conn.commit()
            return replace(current, name=new_name, description=new_description, updated_at=_str_to_dt(now))
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def delete_project(self, project_id: str) -> None:
        # ON DELETE SET NULL (see migrations._to_v4) unassigns every Song of this
        # Project as part of this one statement; no Song/Version/audio row is touched.
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        if cursor.rowcount != 1:
            raise ProjectNotFoundError(project_id)

    def list_project_songs(self, project_id: str) -> list[ProjectSongEntry]:
        sql = (
            "SELECT s.id, s.title, s.created_at, s.updated_at, s.project_id, s.is_favorite, "
            "  COUNT(v.id) AS version_count, MAX(v.version_number) AS latest_version_number "
            "FROM songs s LEFT JOIN versions v ON v.song_id = s.id "
            "WHERE s.project_id = ? GROUP BY s.id ORDER BY s.updated_at DESC, s.id"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, (project_id,)).fetchall()
        return [
            ProjectSongEntry(song=self._row_to_song(r), version_count=r["version_count"], latest_version_number=r["latest_version_number"])
            for r in rows
        ]

    def assign_song_to_project(self, project_id: str, song_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
                raise ProjectNotFoundError(project_id)
            cursor = conn.execute(
                "UPDATE songs SET project_id = ?, updated_at = ? WHERE id = ?",
                (project_id, _dt_to_str(utcnow()), song_id),
            )
            if cursor.rowcount != 1:
                raise SongNotFoundError(song_id)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def remove_song_from_project(self, project_id: str, song_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT project_id FROM songs WHERE id = ?", (song_id,)).fetchone()
            if row is None:
                raise SongNotFoundError(song_id)
            if row["project_id"] == project_id:
                conn.execute(
                    "UPDATE songs SET project_id = NULL, updated_at = ? WHERE id = ?",
                    (_dt_to_str(utcnow()), song_id),
                )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()
