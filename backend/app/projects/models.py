"""Project: organizational metadata over Songs (Phase 6).

A Project owns no audio and no Version; it only groups Songs (`Song.project_id`).
Deleting a Project never touches a Song, a Version or an audio file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.songs.models import Song, utcnow
from datetime import datetime


@dataclass(frozen=True)
class Project:
    """Name + optional description. `updated_at` changes on rename/edit only,
    never when a Song is added to or removed from the project."""

    id: str
    name: str
    description: str = ""
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


@dataclass(frozen=True)
class ProjectSummary:
    """One Projects-page row: a Project and how many Songs are assigned to it."""

    project: Project
    song_count: int


@dataclass(frozen=True)
class ProjectSongEntry:
    """One row of a Project's Song list: a Song plus enough to link into Song Details
    without duplicating Version data here."""

    song: Song
    version_count: int
    latest_version_number: Optional[int]
