"""Song, Version and audio reference.

`Version.spec` reuses `GenerationRequest` (already provider-neutral), so the
domain never depends on ACE-Step or any provider request shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.providers.base import GenerationRequest


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Song:
    """A song's durable identity. Only title/updated_at may ever change."""

    id: str
    title: str
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


@dataclass(frozen=True)
class VersionAudio:
    """Reference to the stored audio of a Version (bytes live in AudioStorage)."""

    key: str
    filename: str
    media_type: str
    size_bytes: int
    duration: Optional[float] = None


@dataclass(frozen=True)
class Version:
    """One reproducible generation snapshot of a Song.

    `version_number` is 1, 2, 3... within the song and is assigned by the
    repository at creation (pass 0 to request the next number). Everything
    except `audio` is immutable; `audio` is write-once.
    """

    id: str
    song_id: str
    spec: GenerationRequest
    provider: str
    version_number: int = 0
    created_at: datetime = field(default_factory=utcnow)
    audio: Optional[VersionAudio] = None
    # How this version was made: ORIGINAL, or a creative operation on `source_version_id`
    # (another version of the same song). Immutable, like the rest of the snapshot.
    operation: str = "ORIGINAL"
    source_version_id: Optional[str] = None
    operation_params: Optional[dict] = None


@dataclass(frozen=True)
class VersionEntry:
    """A Version plus the job that produced it (needed to reach its audio route)."""

    version: Version
    job_id: Optional[str]
    job_status: Optional[str]


@dataclass(frozen=True)
class SongSummary:
    """One Library row: a Song, how many playable versions it has, and the newest playable one."""

    song: Song
    version_count: int
    latest: Version
