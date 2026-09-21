"""Errors raised by the AI Song Director (Phase 7)."""

from __future__ import annotations


class DirectorError(Exception):
    """Base class for Song Director failures. Generation must never start on one of these."""


class DirectorUnavailableError(DirectorError):
    """The planner (ACE-Step's LM) could not be reached, timed out, or is not loaded."""


class InvalidSongPlanError(DirectorError):
    """The planner's output failed validation (message is safe to show a user).

    Treated as untrusted AI output, not trusted generation input: this is raised
    instead of silently guessing, clamping, or dropping a bad field.
    """


class InvalidDirectorRequestError(DirectorError, ValueError):
    """The user's own request to the Director (query/instrumental/language/duration)
    is malformed -- caught before any call to the planner is made."""
