"""MusicVideo: a rendered presentation of one audio Version (Phase 23)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from app.music_videos.profiles import ASPECT_RATIOS, DEFAULT_PROFILE_ID  # noqa: F401 -- re-exported
from app.songs.models import utcnow


class MusicVideoStatus(str, Enum):
    """PENDING (accepted, waiting for the renderer) -> ALIGNING (timing the lyrics) ->
    RENDERING (composing the MP4) -> COMPLETED; any non-terminal state can become FAILED.
    WAITING_FOR_AUDIO (Phase 26) comes before PENDING when a video is requested together with its
    song: the exact source Version exists, but its audio is still being generated."""

    WAITING_FOR_AUDIO = "WAITING_FOR_AUDIO"
    PENDING = "PENDING"
    ALIGNING = "ALIGNING"
    RENDERING = "RENDERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


TERMINAL_MUSIC_VIDEO_STATUSES = frozenset({MusicVideoStatus.COMPLETED, MusicVideoStatus.FAILED})

STYLES = ("minimal_white", "dreamy", "bold", "cinematic", "karaoke")  # Phase 25 adds the last two


@dataclass(frozen=True)
class MusicVideo:
    """`song_id`, `source_version_id`, `style`, `aspect_ratio`, `output_profile` (Phase 27; the
    canonical format, see profiles.py -- `aspect_ratio` is always that profile's ratio) and the
    background never change after creation (a DB trigger enforces it). `timed_lyrics` is the
    TimedLyrics document the video was rendered from -- including the lines that could NOT be matched to the audio -- so
    a future manual-timing provider can start from it. `error` is internal (logs only)."""

    id: str
    song_id: str
    source_version_id: str
    status: MusicVideoStatus
    style: str
    aspect_ratio: str
    background_key: str
    background_media_type: str
    output_profile: str = DEFAULT_PROFILE_ID
    duration: Optional[float] = None
    output_key: Optional[str] = None
    output_size_bytes: Optional[int] = None
    timed_lyrics: Optional[dict] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    completed_at: Optional[datetime] = None

    @property
    def matched_line_count(self) -> int:
        return len((self.timed_lyrics or {}).get("lines", []))

    @property
    def unmatched_lines(self) -> list[str]:
        return list((self.timed_lyrics or {}).get("unaligned_lines", []))
