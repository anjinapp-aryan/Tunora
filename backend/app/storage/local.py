"""Local filesystem implementation of AudioStorage.

Layout: `<root>/<job_id>/<job_id>.<ext>` — one directory per job (room for
future companion files: cover art, stems, waveform peaks) named after
Tunora's own job id, never ACE-Step's temp filename. Deterministic,
collision-resistant (job ids are unique), easy to inspect/back up/migrate
(one job = one folder), and fully independent of ACE-Step's own directory
layout.
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path, PurePosixPath
from typing import Union

from app.storage.base import AudioStorage, StoredAudio
from app.storage.errors import (
    PathTraversalError,
    SourceArtifactEmptyError,
    SourceArtifactMissingError,
    SourceArtifactUnreadableError,
    StorageWriteError,
)


class LocalAudioStorage(AudioStorage):
    """Persists audio artifacts under a configurable local storage root."""

    def __init__(self, root: Union[str, Path]) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, source_path: Union[str, Path], *, job_id: str, media_type: str) -> StoredAudio:
        source = Path(source_path)
        self._validate_source(source)

        ext = source.suffix or ".bin"
        filename = f"{job_id}{ext}"
        job_dir = self._root / job_id
        final_path = job_dir / filename

        try:
            job_dir.mkdir(parents=True, exist_ok=True)
            # Copy to a temp file in the *same* directory, then atomically
            # rename into place, so a reader never observes a partially
            # written file at the final path -- even if source and root are
            # on different filesystems (a plain os.replace(source, final)
            # would not be atomic in that case; copy-then-replace-within-
            # the-destination-directory is).
            tmp_path = job_dir / f".{filename}.tmp-{uuid.uuid4().hex}"
            shutil.copyfile(source, tmp_path)
            os.replace(tmp_path, final_path)
        except OSError as exc:
            raise StorageWriteError(f"Failed to store audio for job {job_id!r}: {exc}") from exc

        size_bytes = final_path.stat().st_size
        key = f"{job_id}/{filename}"
        return StoredAudio(
            key=key,
            absolute_path=str(final_path),
            filename=filename,
            media_type=media_type,
            size_bytes=size_bytes,
        )

    def get_path(self, key: str) -> Path:
        self._validate_key(key)
        candidate = (self._root / key).resolve()
        if not self._is_within_root(candidate):
            raise PathTraversalError(f"Storage key {key!r} resolves outside the storage root")
        return candidate

    def exists(self, key: str) -> bool:
        try:
            path = self.get_path(key)
        except PathTraversalError:
            return False
        return path.is_file()

    # -- internals ---------------------------------------------------------

    def _validate_source(self, source: Path) -> None:
        if not source.exists():
            raise SourceArtifactMissingError(f"Source artifact does not exist: {source}")
        if not source.is_file():
            raise SourceArtifactMissingError(f"Source artifact is not a file: {source}")
        if source.stat().st_size == 0:
            raise SourceArtifactEmptyError(f"Source artifact is empty: {source}")
        try:
            with open(source, "rb") as handle:
                handle.read(1)
        except OSError as exc:
            raise SourceArtifactUnreadableError(f"Source artifact could not be read: {source}") from exc

    def _validate_key(self, key: str) -> None:
        """Reject anything that could point outside the storage root.

        Parsed as a POSIX path regardless of host OS, and checked for a
        drive letter (":") and leading slash, so both Windows-style
        (`C:\\...`) and POSIX-style (`/etc/...`) absolute paths are caught
        even on the platform that wouldn't otherwise recognize them as
        absolute (e.g. `Path("/etc/passwd").is_absolute()` is False on
        Windows).
        """

        if not key:
            raise PathTraversalError("Storage key must not be empty")
        normalized = key.replace("\\", "/")
        if normalized.startswith("/") or ":" in normalized:
            raise PathTraversalError(f"Storage key must be a relative path, got {key!r}")
        if ".." in PurePosixPath(normalized).parts:
            raise PathTraversalError(f"Storage key must not contain '..' segments: {key!r}")

    def _is_within_root(self, candidate: Path) -> bool:
        try:
            candidate.relative_to(self._root)
            return True
        except ValueError:
            return False
