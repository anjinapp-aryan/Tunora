"""Errors raised by AudioStorage implementations."""

from __future__ import annotations


class StorageError(Exception):
    """Base class for all storage errors."""


class SourceArtifactMissingError(StorageError):
    """The artifact path handed to save() does not exist on disk."""


class SourceArtifactEmptyError(StorageError):
    """The artifact path handed to save() exists but is zero bytes."""


class SourceArtifactUnreadableError(StorageError):
    """The artifact path handed to save() exists but could not be read."""


class StorageWriteError(StorageError):
    """The storage backend could not write the artifact (disk/permission/etc.)."""


class InvalidStorageKeyError(StorageError):
    """A storage key is malformed (wrong shape, wrong number of segments, ...)."""


class PathTraversalError(InvalidStorageKeyError):
    """A storage key would resolve outside the configured storage root."""
