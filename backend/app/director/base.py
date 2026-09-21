"""SongDirector: converts a natural-language request into a validated SongSpec.

Deliberately small and boring (see docs/PHASE-7-AI-SONG-DIRECTOR.md §"No agent
framework"): one method, no tools, no multi-step planning, no autonomy. It never
generates audio -- that stays owned entirely by `JobService`/`MusicGenerationProvider`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.director.spec import SongSpec


class SongDirector(ABC):
    @abstractmethod
    async def create_plan(
        self,
        query: str,
        *,
        instrumental: bool = False,
        language: Optional[str] = None,
        duration: Optional[float] = None,
        title: Optional[str] = None,
        temperature: float = 0.85,
    ) -> SongSpec:
        """Turn `query` into a validated SongSpec.

        `instrumental`, `language`, `duration` and `title` are the user's OWN
        explicit choices (from the same fields Create Song already has) and always
        win over whatever the planner infers for them -- the planner only fills in
        what the user left unset. Raises `InvalidDirectorRequestError` for a bad
        request, `InvalidSongPlanError` for unusable planner output, and
        `DirectorUnavailableError` if the planner could not be reached. Never
        raises for "the AI didn't do a great job" -- that's a normal SongSpec the
        user can edit.
        """
