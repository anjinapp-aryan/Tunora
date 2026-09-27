"""Persistence interface for the Project domain (Phase 6).

Implemented alongside `SongRepository` by the same repository object
(`JobRepository`/`SqliteJobRepository`), because Projects, Songs and Versions
live in one SQLite file and a single connection/lock is enough — there is no
reason to split them into a second repository or a second database.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Sequence

from app.projects.models import Project, ProjectSongEntry, ProjectSummary

PROJECT_SORT_ORDERS = ("newest", "oldest", "title")


class ProjectRepository(ABC):
    @abstractmethod
    def create_project(self, project: Project) -> None: ...

    @abstractmethod
    def get_project(self, project_id: str) -> Optional[Project]: ...

    @abstractmethod
    def get_projects(self, project_ids: Sequence[str]) -> dict[str, Project]:
        """Batched lookup (one query), so listing Songs never does one query per Project."""

    @abstractmethod
    def list_project_summaries(self, *, query: str, sort: str, limit: int) -> list[ProjectSummary]:
        """Every Project with its Song count, via one grouped query (no N+1)."""

    @abstractmethod
    def update_project(self, project_id: str, *, name: Optional[str], description: Optional[str]) -> Project:
        """Rename and/or redescribe a Project. Raises ProjectNotFoundError if missing."""

    @abstractmethod
    def delete_project(self, project_id: str) -> None:
        """Delete a Project. Its Songs are NOT deleted; they become unassigned
        (`project_id = NULL`). Raises ProjectNotFoundError if missing."""

    @abstractmethod
    def list_project_songs(self, project_id: str) -> list[ProjectSongEntry]:
        """Songs assigned to a Project, newest-updated first, each with its total
        version count and highest version number (one grouped query)."""

    @abstractmethod
    def assign_song_to_project(self, project_id: str, song_id: str) -> None:
        """Set a Song's project. Idempotent: assigning it again, or to the project
        it is already in, is a no-op. Moves the Song if it was in another Project."""

    @abstractmethod
    def remove_song_from_project(self, project_id: str, song_id: str) -> None:
        """Unassign a Song from a Project (project_id -> NULL). A no-op if the Song
        is not currently in that Project (e.g. already removed)."""
