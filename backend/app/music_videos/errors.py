"""Errors raised by the Music Video domain. Messages marked "safe" may be shown to users."""

from __future__ import annotations


class MusicVideoNotFoundError(Exception):
    def __init__(self, music_video_id: str) -> None:
        super().__init__(f"No music video found with id {music_video_id!r}")
        self.music_video_id = music_video_id


class InvalidMusicVideoRequestError(ValueError):
    """The request is invalid (unknown style, unsupported background, ...). Message is safe."""


class MusicVideoInProgressError(Exception):
    """A music video for this Version is already being generated (duplicate request)."""


class FFmpegPolicyError(RuntimeError):
    """No approved (LGPL-only, with libass/OpenH264/AAC) FFmpeg is available. Message is safe."""


class AlignmentError(RuntimeError):
    """Lyric alignment failed or the local alignment engine is not installed. Message is internal."""


class RenderError(RuntimeError):
    """FFmpeg could not render the video. Message is internal (logs only)."""


class MusicVideoStateError(Exception):
    """The action is not allowed in the video's current state (retry a non-failed video, delete
    one still being generated). Message is safe to show."""
