"""Phase 19: the read-only storage report (backend/scripts/storage_report.py)."""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "storage_report.py"
spec = importlib.util.spec_from_file_location("storage_report", SCRIPT)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def _make(root: Path, files: dict[str, int]) -> None:
    for key, size in files.items():
        path = root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)


def test_scan_finds_only_audio_files_with_relative_keys(tmp_path):
    _make(tmp_path, {"job-a/job-a.mp3": 100, "job-b/job-b.flac": 500, "job-b/notes.txt": 9, "job-c/job-c.wav": 1000})
    rows = report.scan(tmp_path)
    assert sorted(rows) == [("job-a/job-a.mp3", ".mp3", 100), ("job-b/job-b.flac", ".flac", 500), ("job-c/job-c.wav", ".wav", 1000)]
    assert all(str(tmp_path) not in key for key, _e, _s in rows)


def test_scan_of_a_missing_root_is_empty(tmp_path):
    assert report.scan(tmp_path / "nope") == []


def test_report_totals_per_format_largest_and_projection(tmp_path):
    _make(tmp_path, {"a/a.mp3": 2048, "b/b.flac": 10 * 1024, "c/c.flac": 30 * 1024})
    text = report.build_report(report.scan(tmp_path), songs=2, versions=3)
    assert "Audio files: 3" in text and "Database: 2 songs, 3 versions" in text
    assert ".flac" in text and ".mp3" in text
    assert "c/c.flac" in text and str(tmp_path) not in text  # relative keys only, no absolute paths
    assert "1.5 versions per song" in text and "10000 songs" in text


def test_report_without_a_database_says_what_it_assumed(tmp_path):
    _make(tmp_path, {"a/a.mp3": 1024})
    assert "assumed 3 versions per song" in report.build_report(report.scan(tmp_path), None, None)


def test_the_report_is_read_only_and_reads_the_database_read_only(tmp_path):
    _make(tmp_path / "audio", {"a/a.mp3": 1024})
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("create table songs (id text)")
    conn.execute("create table versions (id text)")
    conn.execute("insert into songs values ('s1')")
    conn.execute("insert into versions values ('v1'), ('v2')")
    conn.commit()
    conn.close()
    before = {p: p.read_bytes() for p in list((tmp_path / "audio").rglob("*.mp3")) + [db]}
    assert report.counts_from_db(db) == (1, 2)
    report.build_report(report.scan(tmp_path / "audio"), 1, 2)
    assert {p: p.read_bytes() for p in before} == before
    assert report.counts_from_db(tmp_path / "missing.db") == (None, None)
    assert report.counts_from_db(None) == (None, None)


def test_an_empty_storage_root_reports_cleanly(tmp_path):
    text = report.build_report([], None, None)
    assert "Audio files: 0" in text
