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

    Deliberately minimal: only what Step 13 actually needs. `delete()` and
    byte-streaming `get()` are not included — nothing in Phase 3 requires
    them yet, and adding them now would be speculative.
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
