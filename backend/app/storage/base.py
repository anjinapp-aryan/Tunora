"""Provider-agnostic (and backend-agnostic) audio storage abstraction.

Tunora's job lifecycle depends only on `AudioStorage` and `StoredAudio` —
never on whether the concrete implementation is local filesystem, S3, or
MinIO. `LocalAudioStorage` (local.py) is the only implementation today.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Union


@dataclass(frozen=True)
class StoredAudio:
    """Result of persisting one audio artifact into Tunora-owned storage."""

    key: str
    absolute_path: str
    filename: str
    media_type: str
    size_bytes: int


class AudioStorage(ABC):
    """Interface for persisting generated audio artifacts.

    Deliberately minimal: byte-streaming `get()` is not included — nothing
    requires it yet, and adding it now would be speculative. `delete()` (Phase 9)
    was added once Song deletion made it a genuine, not speculative, need.
    """

    @abstractmethod
    def save(self, source_path: Union[str, Path], *, job_id: str, media_type: str) -> StoredAudio:
        """Persist the artifact at `source_path` as the canonical audio for `job_id`.

        Raises a `StorageError` subclass (see errors.py) if the source is
        missing/empty/unreadable, or if the write itself fails. Never leaves
        a partially-written file at the final destination.
        """

    @abstractmethod
    def get_path(self, key: str) -> Path:
        """Resolve a storage key to an absolute filesystem path.

        Raises `InvalidStorageKeyError`/`PathTraversalError` for any key that
        is malformed or would resolve outside the storage root.
        """

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return whether an artifact exists at `key`."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Permanently remove the artifact at `key` (and any now-empty directory it
        leaves behind). Idempotent: deleting a key that doesn't exist is a no-op,
        not an error, so a repeated or partially-completed deletion stays safe.
        Raises `InvalidStorageKeyError`/`PathTraversalError` for a malformed key,
        exactly like `get_path` -- a key is never allowed to resolve outside the
        storage root, whether reading or deleting.
        """
