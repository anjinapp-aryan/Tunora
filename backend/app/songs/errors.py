"""Errors raised by the Song/Version domain."""

from __future__ import annotations


class SongNotFoundError(Exception):
    def __init__(self, song_id: str) -> None:
        super().__init__(f"No song found with id {song_id!r}")
        self.song_id = song_id


class VersionNotFoundError(Exception):
    def __init__(self, version_id: str) -> None:
        super().__init__(f"No version found with id {version_id!r}")
        self.version_id = version_id


class InvalidIdError(ValueError):
    """An id does not have the shape Tunora generates."""


class ImmutableVersionError(Exception):
    """An attempt to change a Version's generation snapshot or overwrite its audio."""
