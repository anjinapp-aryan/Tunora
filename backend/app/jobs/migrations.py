"""Additive, repeat-safe SQLite schema migrations.

Schema version lives in `PRAGMA user_version` (stdlib, no dependency; see
docs/PHASE-4-SONG-VERSION-DOMAIN.md for why Alembic/yoyo were not adopted).
Each step runs in its own `BEGIN IMMEDIATE` transaction and re-checks the
version after taking the write lock, so two processes starting together
cannot both apply it. Steps never drop or rewrite existing user data.

  0 -> 1  baseline: `jobs` table (+ `title` column added in Milestone 1)
  1 -> 2  Song/Version domain: songs, versions, jobs.version_id, triggers,
          and a deterministic backfill (one legacy job -> one song -> version 1)
  2 -> 3  Version lineage: versions.operation / source_version_id / operation_params
          (existing versions become ORIGINAL with no source)
  3 -> 4  Projects (Phase 6): a `projects` table and `songs.project_id`
          (existing songs become unassigned: project_id = NULL)
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from typing import Any, Optional

from app.jobs.titles import derive_title
from app.providers.base import GenerationRequest

logger = logging.getLogger(__name__)

LATEST_VERSION = 4

_JOB_ID = re.compile(r"^tunora-([0-9a-fA-F-]{36})$")
_SPEC_FIELDS = tuple(GenerationRequest.__dataclass_fields__)


def migrate(conn: sqlite3.Connection) -> None:
    """Bring the database up to LATEST_VERSION. Safe to call on every start."""

    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current > LATEST_VERSION:
        raise RuntimeError(
            f"Database schema version {current} is newer than this Tunora build supports ({LATEST_VERSION})."
        )
    for target, step in ((1, _to_v1), (2, _to_v2), (3, _to_v3), (4, _to_v4)):
        if current >= target:
            continue
        _run_step(conn, target, step)


def _run_step(conn: sqlite3.Connection, target: int, step: Any) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute("PRAGMA user_version").fetchone()[0] >= target:
            conn.rollback()  # another process finished this step while we waited
            return
        step(conn)
        conn.execute(f"PRAGMA user_version = {int(target)}")
        conn.commit()
        logger.info("database migrated to schema version %s", target)
    except BaseException:
        conn.rollback()
        raise


def _to_v1(conn: sqlite3.Connection) -> None:
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
    columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
    if "title" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN title TEXT NOT NULL DEFAULT ''")


def _to_v2(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS songs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS versions (
            id TEXT PRIMARY KEY,
            song_id TEXT NOT NULL REFERENCES songs(id),
            version_number INTEGER NOT NULL CHECK (version_number >= 1),
            prompt TEXT NOT NULL,
            lyrics TEXT NOT NULL,
            language TEXT NOT NULL,
            duration REAL,
            seed INTEGER,
            instrumental INTEGER NOT NULL,
            batch_size INTEGER,
            provider TEXT NOT NULL,
            created_at TEXT NOT NULL,
            audio_key TEXT,
            audio_filename TEXT,
            audio_media_type TEXT,
            audio_size_bytes INTEGER,
            audio_duration REAL,
            UNIQUE (song_id, version_number)
        )
        """
    )
    # A version is a reproducible snapshot: the generation inputs can never be
    # rewritten, and once audio is attached it can never point somewhere else.
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS versions_snapshot_immutable
        BEFORE UPDATE OF song_id, version_number, prompt, lyrics, language, duration, seed,
                         instrumental, batch_size, provider, created_at ON versions
        BEGIN
            SELECT RAISE(ABORT, 'version generation snapshot is immutable');
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS versions_audio_write_once
        BEFORE UPDATE OF audio_key, audio_filename, audio_media_type, audio_size_bytes, audio_duration
        ON versions
        WHEN OLD.audio_key IS NOT NULL AND (
                NEW.audio_key IS NOT OLD.audio_key
             OR NEW.audio_filename IS NOT OLD.audio_filename
             OR NEW.audio_media_type IS NOT OLD.audio_media_type
             OR NEW.audio_size_bytes IS NOT OLD.audio_size_bytes
             OR NEW.audio_duration IS NOT OLD.audio_duration)
        BEGIN
            SELECT RAISE(ABORT, 'version audio is write-once');
        END
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
    if "version_id" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN version_id TEXT REFERENCES versions(id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_version_id ON jobs(version_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at)")
    _backfill_legacy_jobs(conn)


def _to_v3(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(versions)")}
    if "operation" not in columns:
        conn.execute("ALTER TABLE versions ADD COLUMN operation TEXT NOT NULL DEFAULT 'ORIGINAL'")
    if "source_version_id" not in columns:
        conn.execute("ALTER TABLE versions ADD COLUMN source_version_id TEXT REFERENCES versions(id)")
    if "operation_params" not in columns:
        conn.execute("ALTER TABLE versions ADD COLUMN operation_params TEXT")
    # Lineage is part of the immutable snapshot ...
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS versions_lineage_immutable
        BEFORE UPDATE OF operation, source_version_id, operation_params ON versions
        BEGIN
            SELECT RAISE(ABORT, 'version generation snapshot is immutable');
        END
        """
    )
    # ... and a version can only be derived from another version of the SAME song.
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS versions_source_same_song
        BEFORE INSERT ON versions
        WHEN NEW.source_version_id IS NOT NULL
         AND (SELECT song_id FROM versions WHERE id = NEW.source_version_id) IS NOT NEW.song_id
        BEGIN
            SELECT RAISE(ABORT, 'source version must belong to the same song');
        END
        """
    )


def _to_v4(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(songs)")}
    if "project_id" not in columns:
        # ON DELETE SET NULL: deleting a Project unassigns its Songs as part of the
        # single DELETE statement -- no separate "unassign" step that could be
        # skipped, and no Song/Version/audio row is ever touched.
        conn.execute("ALTER TABLE songs ADD COLUMN project_id TEXT REFERENCES projects(id) ON DELETE SET NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_songs_project_id ON songs(project_id)")


def legacy_ids(job_id: str) -> tuple[str, str]:
    """Deterministic (song_id, version_id) for a legacy job, so re-running is harmless."""

    match = _JOB_ID.match(job_id)
    suffix = match.group(1) if match else "legacy-" + hashlib.sha256(job_id.encode()).hexdigest()[:32]
    return f"song-{suffix}", f"ver-{suffix}"


def _spec_from_request_json(raw: Optional[str], job_id: str) -> dict[str, Any]:
    try:
        data = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        logger.warning("legacy job %s has unreadable request_json; using defaults", job_id)
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {k: data[k] for k in _SPEC_FIELDS if k in data}


def _legacy_audio(status: str, raw: Optional[str]) -> tuple[Any, ...]:
    if status != "COMPLETED" or not raw:
        return (None,) * 5
    try:
        result = json.loads(raw)
        audio = result["audio"]
        key, filename = audio["key"], audio["filename"]
        media_type, size = audio["media_type"], audio["size_bytes"]
    except (TypeError, ValueError, KeyError):
        return (None,) * 5
    if not all(isinstance(v, str) and v for v in (key, filename, media_type)):
        return (None,) * 5
    duration = result.get("duration")
    return key, filename, media_type, size if isinstance(size, int) else None, duration if isinstance(duration, (int, float)) else None


def _backfill_legacy_jobs(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT id, provider, status, request_json, created_at, result_json, title "
        "FROM jobs WHERE version_id IS NULL ORDER BY created_at, id"
    ).fetchall()
    for job_id, provider, status, request_json, created_at, result_json, title in rows:
        song_id, version_id = legacy_ids(job_id)
        spec = _spec_from_request_json(request_json, job_id)
        req = GenerationRequest(prompt=str(spec.get("prompt", "")), **{k: v for k, v in spec.items() if k != "prompt"})
        song_title = derive_title(req.prompt, title)
        conn.execute(
            "INSERT OR IGNORE INTO songs (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (song_id, song_title, created_at, created_at),
        )
        conn.execute(
            "INSERT OR IGNORE INTO versions (id, song_id, version_number, prompt, lyrics, language, duration, "
            "seed, instrumental, batch_size, provider, created_at, audio_key, audio_filename, "
            "audio_media_type, audio_size_bytes, audio_duration) "
            "VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                version_id, song_id, req.prompt, req.lyrics or "", req.language or "en", req.duration, req.seed,
                1 if req.instrumental else 0, req.batch_size, provider, created_at,
                *_legacy_audio(status, result_json),
            ),
        )
        conn.execute("UPDATE jobs SET version_id = ? WHERE id = ?", (version_id, job_id))
