"""Read-side persistence interface for Songs and Versions.

Writes that must be atomic with a Job (creating a generation, completing it)
live on `JobRepository`, because they span the songs, versions and jobs tables.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Sequence

from app.songs.models import Song, Version


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
