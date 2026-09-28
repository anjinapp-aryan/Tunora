"""MusicVideoService (Phase 23): Song Version -> TimedLyrics -> 9:16 MP4.

Orchestration only. It reads a Version (never changes it), stores the user's background, aligns
the Version's stored lyrics locally, renders with the policy-checked LGPL FFmpeg, and records the
result as a separate Music Video. Execution follows Tunora's existing model: FastAPI
BackgroundTasks in-process (no queue, no Redis/Celery), one render at a time (a lock -- rendering
is CPU-bound), and a restart marks interrupted videos FAILED (a render subprocess cannot resume;
nothing is ever re-run or duplicated automatically).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import replace
from pathlib import Path
from typing import AsyncIterator, Callable, Optional

from app.jobs.service import JobService
from app.music_videos import renderer as renderer_module
from app.music_videos.aligner import LocalForcedAligner, LyricsAligner
from app.music_videos.errors import (
    InvalidMusicVideoRequestError,
    MusicVideoInProgressError,
    MusicVideoNotFoundError,
    MusicVideoStateError,
)
from app.music_videos.ffmpeg import FFmpegTools, approved_ffmpeg
from app.music_videos.models import (
    ASPECT_RATIOS,
    STYLES,
    TERMINAL_MUSIC_VIDEO_STATUSES,
    MusicVideo,
    MusicVideoStatus,
)
from app.music_videos.renderer import FFmpegLibassRenderer, MusicVideoRenderer
from app.music_videos.repository import MusicVideoRepository
from app.music_videos.storage import MusicVideoStorage
from app.songs.errors import (
    InvalidIdError,
    SongNotFoundError,
    SourceAudioUnavailableError,
    SourceVersionNotFoundError,
)
from app.songs.ids import is_valid_id, new_music_video_id
from app.songs.models import utcnow

logger = logging.getLogger(__name__)

# Allowed background uploads: media type -> (stored extension, max bytes).
BACKGROUND_TYPES = {
    "image/jpeg": (".jpg", 20 * 1024 * 1024),
    "image/png": (".png", 20 * 1024 * 1024),
    "video/mp4": (".mp4", 200 * 1024 * 1024),
    "video/quicktime": (".mov", 200 * 1024 * 1024),
    "video/webm": (".webm", 200 * 1024 * 1024),
}

_SOURCE_GONE = (SongNotFoundError, SourceVersionNotFoundError, SourceAudioUnavailableError)

# Internal failure codes (stored as "<code>: <detail>") -> the only text the API may show.
FAILURE_MESSAGES = {
    "no_lyrics_matched": "None of this version's lyrics could be matched to its audio.",
    "interrupted": "Generation was interrupted when Tunora restarted. Please generate it again.",
    "source_unavailable": "The source version's audio is no longer available.",
    "failed": "Music video generation failed.",
}


def _looks_like(media_type: str, head: bytes) -> bool:
    if media_type == "image/jpeg":
        return head.startswith(b"\xff\xd8\xff")
    if media_type == "image/png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type in ("video/mp4", "video/quicktime"):
        return head[4:8] == b"ftyp"
    if media_type == "video/webm":
        return head.startswith(b"\x1a\x45\xdf\xa3")
    return False


def public_error(video: MusicVideo) -> Optional[str]:
    if video.status != MusicVideoStatus.FAILED:
        return None
    code = (video.error or "failed").split(":", 1)[0]
    return FAILURE_MESSAGES.get(code, FAILURE_MESSAGES["failed"])


class MusicVideoService:
    def __init__(
        self,
        *,
        repository: MusicVideoRepository,
        jobs: JobService,
        storage: MusicVideoStorage,
        tools_provider: Callable[[], FFmpegTools] = approved_ffmpeg,
        aligner_factory: Optional[Callable[[FFmpegTools], LyricsAligner]] = None,
        renderer_factory: Optional[Callable[[FFmpegTools], MusicVideoRenderer]] = None,
        background_checker: Optional[Callable[[FFmpegTools, Path], object]] = None,
        id_factory: Callable[[], str] = new_music_video_id,
    ) -> None:
        self._repository = repository
        self._jobs = jobs
        self._storage = storage
        self._tools_provider = tools_provider
        self._aligner_factory = aligner_factory or LocalForcedAligner
        self._renderer_factory = renderer_factory or FFmpegLibassRenderer
        self._check_background = background_checker or renderer_module.check_background
        self._id_factory = id_factory
        self._render_lock = threading.Lock()

    # -- create ------------------------------------------------------------------------------

    async def create(self, song_id: str, *, source_version_id: str, style: str, aspect_ratio: str,
                     media_type: str, chunks: AsyncIterator[bytes]) -> MusicVideo:
        """Validate everything, store the background, and record a PENDING Music Video.
        The caller schedules `generate(id)`. Raises InvalidIdError, SongNotFoundError,
        SourceVersionNotFoundError, SourceAudioUnavailableError, InvalidMusicVideoRequestError,
        MusicVideoInProgressError or FFmpegPolicyError."""

        if style not in STYLES:
            raise InvalidMusicVideoRequestError("Unknown style.")
        if aspect_ratio not in ASPECT_RATIOS:
            raise InvalidMusicVideoRequestError("Only 9:16 is supported.")
        media_type = (media_type or "").split(";", 1)[0].strip().lower()
        if media_type not in BACKGROUND_TYPES:
            raise InvalidMusicVideoRequestError("Background must be a JPG, PNG, MP4, MOV or WebM file.")
        version, _ = self._jobs.resolve_version_audio(song_id, source_version_id)
        if version.spec.instrumental or not version.spec.lyrics.strip():
            raise InvalidMusicVideoRequestError("This version has no lyrics to show in a music video.")
        if any(v.source_version_id == source_version_id and v.status not in TERMINAL_MUSIC_VIDEO_STATUSES
               for v in self._repository.list_for_song(song_id)):
            raise MusicVideoInProgressError(source_version_id)
        tools = self._tools_provider()

        video_id = self._id_factory()
        extension, max_bytes = BACKGROUND_TYPES[media_type]
        key = self._storage.background_key(video_id, extension)
        try:
            await self._storage.save_stream(key, chunks, max_bytes)
            path = self._storage.get_path(key)
            with open(path, "rb") as handle:
                if not _looks_like(media_type, handle.read(12)):
                    raise InvalidMusicVideoRequestError("The background file does not match its type.")
            self._check_background(tools, path)
            now = utcnow()
            video = MusicVideo(
                id=video_id, song_id=song_id, source_version_id=source_version_id,
                status=MusicVideoStatus.PENDING, style=style, aspect_ratio=aspect_ratio,
                background_key=key, background_media_type=media_type, created_at=now, updated_at=now,
            )
            self._repository.create(video)
        except BaseException:
            self._storage.delete_video(video_id)
            raise
        logger.info("music video created id=%s song_id=%s version_id=%s", video_id, song_id, source_version_id)
        return video

    # -- generate (background task) ----------------------------------------------------------

    def generate(self, music_video_id: str) -> MusicVideo:
        """Align, then render. Runs in the API process's worker thread; one render at a time."""

        with self._render_lock:
            video = self._repository.get(music_video_id)
            if video is None or video.status in TERMINAL_MUSIC_VIDEO_STATUSES:
                return video
            try:
                return self._generate(video)
            except Exception as exc:  # noqa: BLE001 -- every failure ends in FAILED, never a crash
                code = "source_unavailable" if isinstance(exc, _SOURCE_GONE) else "failed"
                logger.exception("music video %s failed", music_video_id)
                return self._fail(music_video_id, f"{code}: {exc.__class__.__name__}: {exc}")

    def _generate(self, video: MusicVideo) -> MusicVideo:
        tools = self._tools_provider()
        song = self._jobs.get_song(video.song_id)
        version, audio_path = self._jobs.resolve_version_audio(video.song_id, video.source_version_id)

        video = self._save(replace(video, status=MusicVideoStatus.ALIGNING))
        timed = self._aligner_factory(tools).align(audio_path, version.spec.lyrics, version.spec.language)
        timed_doc = {
            "version": 1, "duration": timed.duration, "source": timed.source,
            "lines": [{"text": l.text, "words": [{"text": w.text, "start": w.start, "end": w.end}
                                                 for w in l.words]} for l in timed.lines],
            "unaligned_lines": list(timed.unaligned_lines),
        }
        video = self._save(replace(video, timed_lyrics=timed_doc))
        if not timed.lines:
            return self._fail(video.id, "no_lyrics_matched: alignment matched no lines")

        video = self._save(replace(video, status=MusicVideoStatus.RENDERING))
        output_key = self._storage.output_key(video.id)
        result = self._renderer_factory(tools).render(
            audio_path, timed, self._storage.get_path(video.background_key), video.style,
            video.aspect_ratio, self._storage.get_path(output_key), title=song.title)
        now = utcnow()
        completed = replace(video, status=MusicVideoStatus.COMPLETED, duration=timed.duration,
                            output_key=output_key, output_size_bytes=result.size_bytes,
                            updated_at=now, completed_at=now, error=None)
        if not self._repository.update(completed):  # its Song was deleted while rendering
            self._storage.delete_video(video.id)
            return completed
        logger.info("music video %s completed in %.1fs (%d lines, %d unmatched)", video.id,
                    result.seconds, result.lines_rendered, len(timed.unaligned_lines))
        return completed

    def _save(self, video: MusicVideo) -> MusicVideo:
        video = replace(video, updated_at=utcnow())
        if not self._repository.update(video):
            raise MusicVideoNotFoundError(video.id)
        return video

    def _fail(self, music_video_id: str, error: str) -> MusicVideo:
        current = self._repository.get(music_video_id)
        if current is None:
            self._storage.delete_video(music_video_id)
            return current
        failed = replace(current, status=MusicVideoStatus.FAILED, error=error[:2000], updated_at=utcnow())
        self._repository.update(failed)
        return failed

    # -- retry / delete (Phase 24) -------------------------------------------------------------

    def retry(self, music_video_id: str) -> MusicVideo:
        """Retry a FAILED Music Video in place: same id, same source Version, style and stored
        background; its previous attempt's result is cleared and it goes back to PENDING. The
        caller schedules `generate(id)`. Audio is never regenerated and no Version or Job is
        created. Raises MusicVideoNotFoundError, MusicVideoStateError, MusicVideoInProgressError,
        or SourceAudioUnavailableError / SourceVersionNotFoundError if the source is gone."""

        video = self.get(music_video_id)
        if video.status != MusicVideoStatus.FAILED:
            raise MusicVideoStateError("Only a failed music video can be retried.")
        self._jobs.resolve_version_audio(video.song_id, video.source_version_id)
        if not self._storage.get_path(video.background_key).is_file():
            raise MusicVideoStateError("This video's background is no longer available. Create a new music video instead.")
        retried = self._repository.retry(music_video_id, utcnow())
        logger.info("music video %s retried (source version %s)", music_video_id, video.source_version_id)
        return retried

    def delete(self, music_video_id: str) -> None:
        """Delete one finished Music Video and its files. Never touches the Song, the source
        Version or its audio. Raises MusicVideoNotFoundError or MusicVideoStateError."""

        self.get(music_video_id)
        self._repository.delete(music_video_id)
        self._storage.delete_video(music_video_id)
        logger.info("music video %s deleted", music_video_id)

    # -- recovery ----------------------------------------------------------------------------

    def recover_interrupted(self) -> int:
        """At startup: a render/alignment subprocess cannot be resumed, so every Music Video left
        non-terminal by a previous process becomes FAILED (never silently re-run, so no duplicate).
        Returns how many were marked."""

        unfinished = self._repository.list_unfinished()
        for video in unfinished:
            self._fail(video.id, "interrupted: the backend restarted during generation")
            logger.warning("music video %s was interrupted by a restart; marked FAILED", video.id)
        return len(unfinished)

    # -- reads ---------------------------------------------------------------------------------

    def list_for_song(self, song_id: str) -> list[MusicVideo]:
        if not is_valid_id(song_id):
            raise InvalidIdError("Malformed song id.")
        self._jobs.get_song(song_id)
        return self._repository.list_for_song(song_id)

    def get(self, music_video_id: str) -> MusicVideo:
        if not is_valid_id(music_video_id):
            raise MusicVideoNotFoundError(music_video_id)
        video = self._repository.get(music_video_id)
        if video is None:
            raise MusicVideoNotFoundError(music_video_id)
        return video

    def output_path(self, music_video_id: str) -> tuple[MusicVideo, Path]:
        """The rendered MP4 of a COMPLETED Music Video. Raises MusicVideoNotFoundError."""

        video = self.get(music_video_id)
        if video.status != MusicVideoStatus.COMPLETED or not video.output_key:
            raise MusicVideoNotFoundError(music_video_id)
        path = self._storage.get_path(video.output_key)
        if not path.is_file():
            raise MusicVideoNotFoundError(music_video_id)
        return video, path

    # -- song deletion -------------------------------------------------------------------------

    def video_ids_for_song(self, song_id: str) -> list[str]:
        return [v.id for v in self._repository.list_for_song(song_id)] if is_valid_id(song_id) else []

    def delete_files(self, music_video_ids: list[str]) -> None:
        """Best-effort file cleanup after the Song's rows were deleted (ON DELETE CASCADE)."""

        for video_id in music_video_ids:
            self._storage.delete_video(video_id)

