"""Persistence for Music Videos (Phase 23).

Same approach as the Song/Version/Project repositories: stdlib `sqlite3`, parameterized SQL,
the same database file, and the same `migrate()` (schema v6 adds `music_videos`). It is a
separate small class rather than more methods on the (already large) job repository because a
Music Video never takes part in a Song/Version/Job transaction -- it only references them.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.jobs.migrations import migrate
from app.music_videos.errors import MusicVideoInProgressError, MusicVideoNotFoundError, MusicVideoStateError
from app.music_videos.models import TERMINAL_MUSIC_VIDEO_STATUSES, MusicVideo, MusicVideoStatus


class MusicVideoRepository(ABC):
    @abstractmethod
    def create(self, video: MusicVideo) -> None:
        """Insert a new Music Video. Atomically refuses (MusicVideoInProgressError) when another
        non-terminal Music Video already exists for the same source Version."""

    @abstractmethod
    def get(self, music_video_id: str) -> Optional[MusicVideo]: ...

    @abstractmethod
    def list_for_song(self, song_id: str) -> list[MusicVideo]:
        """Newest first."""

    @abstractmethod
    def update(self, video: MusicVideo) -> bool:
        """Persist status/progress/output fields. Returns False if the row no longer exists
        (e.g. its Song was deleted while it rendered). Source fields are never changed."""

    @abstractmethod
    def list_unfinished(self) -> list[MusicVideo]:
        """Every non-terminal Music Video (restart recovery)."""

    @abstractmethod
    def retry(self, music_video_id: str, now: datetime) -> MusicVideo:
        """Atomically put a FAILED video back to PENDING (clearing its previous attempt's result),
        keeping the same id, source Version, style and background. Raises MusicVideoNotFoundError,
        MusicVideoStateError (not FAILED) or MusicVideoInProgressError (another video of the same
        Version is in progress)."""

    @abstractmethod
    def delete(self, music_video_id: str) -> None:
        """Delete one finished (COMPLETED/FAILED) video row. Never touches a Song, Version or
        Job. Raises MusicVideoNotFoundError or MusicVideoStateError (still being generated)."""


class InMemoryMusicVideoRepository(MusicVideoRepository):
    def __init__(self) -> None:
        self._videos: dict[str, MusicVideo] = {}
        self._lock = threading.Lock()

    def create(self, video: MusicVideo) -> None:
        with self._lock:
            if any(v.source_version_id == video.source_version_id and v.status not in TERMINAL_MUSIC_VIDEO_STATUSES
                   for v in self._videos.values()):
                raise MusicVideoInProgressError(video.source_version_id)
            self._videos[video.id] = video

    def get(self, music_video_id: str) -> Optional[MusicVideo]:
        return self._videos.get(music_video_id)

    def list_for_song(self, song_id: str) -> list[MusicVideo]:
        return sorted((v for v in self._videos.values() if v.song_id == song_id),
                      key=lambda v: (v.created_at, v.id), reverse=True)

    def update(self, video: MusicVideo) -> bool:
        with self._lock:
            current = self._videos.get(video.id)
            if current is None:
                return False
            self._videos[video.id] = replace(
                current, status=video.status, duration=video.duration, output_key=video.output_key,
                output_size_bytes=video.output_size_bytes, timed_lyrics=video.timed_lyrics,
                error=video.error, updated_at=video.updated_at, completed_at=video.completed_at,
            )
            return True

    def delete_song(self, song_id: str) -> None:
        """Test helper mirroring the SQLite ON DELETE CASCADE."""
        with self._lock:
            for key in [k for k, v in self._videos.items() if v.song_id == song_id]:
                del self._videos[key]

    def list_unfinished(self) -> list[MusicVideo]:
        return [v for v in self._videos.values() if v.status not in TERMINAL_MUSIC_VIDEO_STATUSES]

    def retry(self, music_video_id: str, now: datetime) -> MusicVideo:
        with self._lock:
            current = self._videos.get(music_video_id)
            if current is None:
                raise MusicVideoNotFoundError(music_video_id)
            if current.status != MusicVideoStatus.FAILED:
                raise MusicVideoStateError("Only a failed music video can be retried.")
            if any(v.source_version_id == current.source_version_id and v.status not in TERMINAL_MUSIC_VIDEO_STATUSES
                   for v in self._videos.values()):
                raise MusicVideoInProgressError(current.source_version_id)
            retried = replace(current, status=MusicVideoStatus.PENDING, duration=None, output_key=None,
                              output_size_bytes=None, timed_lyrics=None, error=None, updated_at=now,
                              completed_at=None)
            self._videos[music_video_id] = retried
            return retried

    def delete(self, music_video_id: str) -> None:
        with self._lock:
            current = self._videos.get(music_video_id)
            if current is None:
                raise MusicVideoNotFoundError(music_video_id)
            if current.status not in TERMINAL_MUSIC_VIDEO_STATUSES:
                raise MusicVideoStateError("This music video is still being generated.")
            del self._videos[music_video_id]


def _dt(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


_COLUMNS = ("id, song_id, source_version_id, status, style, aspect_ratio, background_key, "
            "background_media_type, duration, output_key, output_size_bytes, timed_lyrics_json, "
            "error, created_at, updated_at, completed_at")


class SqliteMusicVideoRepository(MusicVideoRepository):
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

    @staticmethod
    def _row(row: sqlite3.Row) -> MusicVideo:
        return MusicVideo(
            id=row["id"], song_id=row["song_id"], source_version_id=row["source_version_id"],
            status=MusicVideoStatus(row["status"]), style=row["style"], aspect_ratio=row["aspect_ratio"],
            background_key=row["background_key"], background_media_type=row["background_media_type"],
            duration=row["duration"], output_key=row["output_key"], output_size_bytes=row["output_size_bytes"],
            timed_lyrics=json.loads(row["timed_lyrics_json"]) if row["timed_lyrics_json"] else None,
            error=row["error"], created_at=_parse_dt(row["created_at"]), updated_at=_parse_dt(row["updated_at"]),
            completed_at=_parse_dt(row["completed_at"]),
        )

    def create(self, video: MusicVideo) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            active = conn.execute(
                "SELECT 1 FROM music_videos WHERE source_version_id = ? AND status NOT IN (?, ?)",
                (video.source_version_id, MusicVideoStatus.COMPLETED.value, MusicVideoStatus.FAILED.value),
            ).fetchone()
            if active is not None:
                raise MusicVideoInProgressError(video.source_version_id)
            conn.execute(
                f"INSERT INTO music_videos ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (video.id, video.song_id, video.source_version_id, video.status.value, video.style,
                 video.aspect_ratio, video.background_key, video.background_media_type, video.duration,
                 video.output_key, video.output_size_bytes,
                 json.dumps(video.timed_lyrics) if video.timed_lyrics is not None else None,
                 video.error, _dt(video.created_at), _dt(video.updated_at), _dt(video.completed_at)),
            )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get(self, music_video_id: str) -> Optional[MusicVideo]:
        conn = self._connect()
        try:
            row = conn.execute(f"SELECT {_COLUMNS} FROM music_videos WHERE id = ?", (music_video_id,)).fetchone()
            return self._row(row) if row else None
        finally:
            conn.close()

    def list_for_song(self, song_id: str) -> list[MusicVideo]:
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM music_videos WHERE song_id = ? ORDER BY created_at DESC, id DESC",
                (song_id,),
            ).fetchall()
            return [self._row(r) for r in rows]
        finally:
            conn.close()

    def update(self, video: MusicVideo) -> bool:
        conn = self._connect()
        try:
            cur = conn.execute(
                "UPDATE music_videos SET status = ?, duration = ?, output_key = ?, output_size_bytes = ?, "
                "timed_lyrics_json = ?, error = ?, updated_at = ?, completed_at = ? WHERE id = ?",
                (video.status.value, video.duration, video.output_key, video.output_size_bytes,
                 json.dumps(video.timed_lyrics) if video.timed_lyrics is not None else None,
                 video.error, _dt(video.updated_at), _dt(video.completed_at), video.id),
            )
            conn.commit()
            return cur.rowcount == 1
        finally:
            conn.close()

    def list_unfinished(self) -> list[MusicVideo]:
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM music_videos WHERE status NOT IN (?, ?) ORDER BY created_at",
                (MusicVideoStatus.COMPLETED.value, MusicVideoStatus.FAILED.value),
            ).fetchall()
            return [self._row(r) for r in rows]
        finally:
            conn.close()


    def retry(self, music_video_id: str, now: datetime) -> MusicVideo:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(f"SELECT {_COLUMNS} FROM music_videos WHERE id = ?", (music_video_id,)).fetchone()
            if row is None:
                raise MusicVideoNotFoundError(music_video_id)
            current = self._row(row)
            if current.status != MusicVideoStatus.FAILED:
                raise MusicVideoStateError("Only a failed music video can be retried.")
            active = conn.execute(
                "SELECT 1 FROM music_videos WHERE source_version_id = ? AND status NOT IN (?, ?)",
                (current.source_version_id, MusicVideoStatus.COMPLETED.value, MusicVideoStatus.FAILED.value),
            ).fetchone()
            if active is not None:
                raise MusicVideoInProgressError(current.source_version_id)
            conn.execute(
                "UPDATE music_videos SET status = ?, duration = NULL, output_key = NULL, output_size_bytes = NULL, "
                "timed_lyrics_json = NULL, error = NULL, updated_at = ?, completed_at = NULL WHERE id = ?",
                (MusicVideoStatus.PENDING.value, _dt(now), music_video_id),
            )
            conn.commit()
            return replace(current, status=MusicVideoStatus.PENDING, duration=None, output_key=None,
                           output_size_bytes=None, timed_lyrics=None, error=None, updated_at=now, completed_at=None)
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def delete(self, music_video_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT status FROM music_videos WHERE id = ?", (music_video_id,)).fetchone()
            if row is None:
                raise MusicVideoNotFoundError(music_video_id)
            if row["status"] not in (MusicVideoStatus.COMPLETED.value, MusicVideoStatus.FAILED.value):
                raise MusicVideoStateError("This music video is still being generated.")
            conn.execute("DELETE FROM music_videos WHERE id = ?", (music_video_id,))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()


def require(video: Optional[MusicVideo], music_video_id: str) -> MusicVideo:
    if video is None:
        raise MusicVideoNotFoundError(music_video_id)
    return video
