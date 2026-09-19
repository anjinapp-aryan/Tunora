"""LocalAudioStorage unit tests. Always uses pytest's tmp_path fixture for
both the fake "ACE-Step output" source files and the storage root itself —
never the real Tunora production storage directory.
"""

from __future__ import annotations

import os

import pytest

from app.storage.errors import (
    PathTraversalError,
    SourceArtifactEmptyError,
    SourceArtifactMissingError,
)
from app.storage.local import LocalAudioStorage


@pytest.fixture
def storage(tmp_path):
    return LocalAudioStorage(tmp_path / "storage-root")


def _write_source(tmp_path, name: str = "source.mp3", content: bytes = b"fake-mp3-bytes") -> str:
    path = tmp_path / name
    path.write_bytes(content)
    return str(path)


def test_save_persists_file_under_job_directory(storage, tmp_path):
    source = _write_source(tmp_path)

    stored = storage.save(source, job_id="tunora-1", media_type="audio/mpeg")

    assert stored.key == "tunora-1/tunora-1.mp3"
    assert os.path.isfile(stored.absolute_path)


def test_get_path_retrieves_the_saved_file(storage, tmp_path):
    source = _write_source(tmp_path, content=b"abc123")
    stored = storage.save(source, job_id="tunora-1", media_type="audio/mpeg")

    resolved = storage.get_path(stored.key)

    assert resolved.is_file()
    assert resolved.read_bytes() == b"abc123"


def test_exists_true_after_save_false_otherwise(storage, tmp_path):
    source = _write_source(tmp_path)
    stored = storage.save(source, job_id="tunora-1", media_type="audio/mpeg")

    assert storage.exists(stored.key) is True
    assert storage.exists("tunora-does-not-exist/tunora-does-not-exist.mp3") is False


def test_save_reports_correct_byte_size(storage, tmp_path):
    content = b"x" * 4096
    source = _write_source(tmp_path, content=content)

    stored = storage.save(source, job_id="tunora-1", media_type="audio/mpeg")

    assert stored.size_bytes == len(content)
    assert os.path.getsize(stored.absolute_path) == len(content)


def test_save_reports_the_media_type_it_was_given(storage, tmp_path):
    source = _write_source(tmp_path, name="source.wav")

    stored = storage.save(source, job_id="tunora-1", media_type="audio/wav")

    assert stored.media_type == "audio/wav"


def test_save_path_generation_is_deterministic_for_the_same_job_id(storage, tmp_path):
    source = _write_source(tmp_path)

    first = storage.save(source, job_id="tunora-fixed-id", media_type="audio/mpeg")
    second = storage.save(source, job_id="tunora-fixed-id", media_type="audio/mpeg")

    assert first.key == second.key == "tunora-fixed-id/tunora-fixed-id.mp3"


def test_multiple_jobs_do_not_collide(storage, tmp_path):
    source_a = _write_source(tmp_path, name="a.mp3", content=b"AAAA")
    source_b = _write_source(tmp_path, name="b.mp3", content=b"BBBB")

    stored_a = storage.save(source_a, job_id="tunora-a", media_type="audio/mpeg")
    stored_b = storage.save(source_b, job_id="tunora-b", media_type="audio/mpeg")

    assert stored_a.key != stored_b.key
    assert storage.get_path(stored_a.key).read_bytes() == b"AAAA"
    assert storage.get_path(stored_b.key).read_bytes() == b"BBBB"


def test_save_missing_source_raises(storage, tmp_path):
    missing = str(tmp_path / "does-not-exist.mp3")

    with pytest.raises(SourceArtifactMissingError):
        storage.save(missing, job_id="tunora-1", media_type="audio/mpeg")


def test_save_empty_source_raises(storage, tmp_path):
    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")

    with pytest.raises(SourceArtifactEmptyError):
        storage.save(str(empty), job_id="tunora-1", media_type="audio/mpeg")


@pytest.mark.parametrize(
    "bad_key",
    [
        "../escape.mp3",
        "tunora-1/../../escape.mp3",
        "a/b/../../../escape.mp3",
    ],
)
def test_get_path_rejects_path_traversal(storage, bad_key):
    with pytest.raises(PathTraversalError):
        storage.get_path(bad_key)


@pytest.mark.parametrize(
    "bad_key",
    [
        "C:\\Windows\\System32\\evil.mp3",
        "/etc/passwd",
        "\\\\server\\share\\file.mp3",
    ],
)
def test_get_path_rejects_absolute_paths(storage, bad_key):
    with pytest.raises(PathTraversalError):
        storage.get_path(bad_key)


def test_get_path_rejects_empty_key(storage):
    with pytest.raises(PathTraversalError):
        storage.get_path("")


def test_storage_root_containment_for_valid_keys(storage, tmp_path):
    source = _write_source(tmp_path)
    stored = storage.save(source, job_id="tunora-1", media_type="audio/mpeg")

    resolved = storage.get_path(stored.key)

    storage_root = (tmp_path / "storage-root").resolve()
    resolved.relative_to(storage_root)  # raises ValueError (and thus fails the test) if not contained


def test_save_is_atomic_no_temp_file_left_behind(storage, tmp_path):
    """The copy-to-temp-then-replace strategy should leave no `.tmp-*` file
    behind, and the final path should never be observably partial."""

    source = _write_source(tmp_path, content=b"y" * (1024 * 1024))  # 1MB, "large-ish"

    stored = storage.save(source, job_id="tunora-atomic", media_type="audio/mpeg")

    job_dir = storage.get_path(stored.key).parent
    leftover_temp_files = [p for p in job_dir.iterdir() if p.name.startswith(".") and "tmp-" in p.name]
    assert leftover_temp_files == []
    assert os.path.getsize(stored.absolute_path) == 1024 * 1024


def test_save_large_ish_file(storage, tmp_path):
    content = b"z" * (5 * 1024 * 1024)  # 5MB
    source = _write_source(tmp_path, content=content)

    stored = storage.save(source, job_id="tunora-large", media_type="audio/mpeg")

    assert stored.size_bytes == len(content)
    assert storage.get_path(stored.key).read_bytes() == content


def test_save_source_that_is_a_directory_raises(storage, tmp_path):
    directory = tmp_path / "not-a-file"
    directory.mkdir()

    with pytest.raises(SourceArtifactMissingError):
        storage.save(str(directory), job_id="tunora-1", media_type="audio/mpeg")


def test_storage_root_is_created_if_missing(tmp_path):
    root = tmp_path / "does" / "not" / "exist" / "yet"
    assert not root.exists()

    LocalAudioStorage(root)

    assert root.is_dir()
