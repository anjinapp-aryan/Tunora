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

    @abstractmethod
    async def refine(self, spec: SongSpec, instruction: str, *, temperature: float = 0.85) -> SongSpec:
        """Apply a natural-language change request to an existing SongSpec (Phase 8).

        This modifies the given plan -- it is not a new independent request. `title`,
        `language`, `duration` and `instrumental` are the user's existing explicit
        choices and are carried over unchanged (refinement only touches the
        description/lyrics side, since ACE-Step's own formatting capability has no
        way to be asked to change them). Raises the same errors as `create_plan`.
        Never called for "Generate": it creates nothing (no Song, Version or Job).
        """
