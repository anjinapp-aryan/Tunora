"""Errors raised by the Project domain (Phase 6)."""

from __future__ import annotations


class ProjectNotFoundError(Exception):
    def __init__(self, project_id: str) -> None:
        super().__init__(f"No project found with id {project_id!r}")
        self.project_id = project_id


class InvalidProjectError(ValueError):
    """A project name/description is invalid (message is safe to show a user)."""
