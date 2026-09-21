"""Read-side persistence interface for Songs and Versions.

Writes that must be atomic with a Job (creating a generation, completing it)
live on `JobRepository`, because they span the songs, versions and jobs tables.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Sequence

from app.songs.models import Song, SongSummary, Version, VersionEntry

SORT_ORDERS = ("newest", "oldest", "title")

# Sentinel for `list_song_summaries(project=...)`: songs with no Project (never a
# valid Tunora id, so it can never collide with a real project id).
PROJECT_FILTER_NONE = "none"


class SongRepository(ABC):
    @abstractmethod
    def get_song(self, song_id: str) -> Optional[Song]: ...

    @abstractmethod
    def get_version(self, version_id: str) -> Optional[Version]: ...

    @abstractmethod
    def get_versions(self, version_ids: Sequence[str]) -> dict[str, Version]: ...

    @abstractmethod
    def list_versions(self, song_id: str) -> list[Version]:
        """A song's versions, oldest first (version_number ascending)."""

    @abstractmethod
    def list_song_summaries(
        self, *, query: str, sort: str, limit: int, project: Optional[str] = None
    ) -> list[SongSummary]:
        """Library rows: songs with at least one playable version (audio attached).

        `version_count` counts playable versions; `latest` is the highest
        playable version_number. `query` is a case-insensitive substring match
        on the song title or any version's prompt. Ordering (`sort`):
        newest/oldest by the latest playable version's created_at, title A-Z.
        `project`: None = every song, `PROJECT_FILTER_NONE` = only songs with no
        Project, any other value = only songs in that Project.
        """

    @abstractmethod
    def list_version_entries(self, song_id: str) -> list[VersionEntry]:
        """Every version of one song (playable or not), newest version_number first."""
