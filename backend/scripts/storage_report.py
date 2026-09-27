"""Read-only storage report for a local Tunora installation (developer tool; standard library only).

Shows how much disk the stored audio uses, split by format, plus a simple projection. It never writes, deletes or
moves anything, exposes no endpoint, and prints only storage keys relative to the storage root (no absolute paths).

    cd backend
    .venv\\Scripts\\python.exe scripts\\storage_report.py [--storage-root ./data/audio] [--db tunora.db]

Defaults follow the backend: TUNORA_STORAGE_ROOT (default ./data/audio) and TUNORA_DB_PATH (default tunora.db).
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Optional

AUDIO_EXTENSIONS = (".mp3", ".flac", ".wav", ".ogg", ".opus", ".aac")
PROJECTION_SONGS = (100, 1000, 10000)


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def scan(root: Path) -> list[tuple[str, str, int]]:
    """(relative key with forward slashes, extension, size in bytes) for every audio file under `root`."""
    rows = []
    if not root.is_dir():
        return rows
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
            rows.append((path.relative_to(root).as_posix(), path.suffix.lower(), path.stat().st_size))
    return rows


def counts_from_db(db_path: Optional[Path]) -> tuple[Optional[int], Optional[int]]:
    """(songs, versions) from the database opened read-only, or (None, None) when unavailable."""
    if db_path is None or not db_path.is_file():
        return None, None
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            return (conn.execute("select count(*) from songs").fetchone()[0], conn.execute("select count(*) from versions").fetchone()[0])
        finally:
            conn.close()
    except sqlite3.Error:
        return None, None


def build_report(rows: list[tuple[str, str, int]], songs: Optional[int], versions: Optional[int], top: int = 5) -> str:
    lines = []
    by_ext: dict[str, list[int]] = defaultdict(list)
    for _key, ext, size in rows:
        by_ext[ext].append(size)
    total = sum(size for _k, _e, size in rows)
    lines.append(f"Audio files: {len(rows)}   total {_human(total)}")
    if songs is not None:
        lines.append(f"Database: {songs} songs, {versions} versions")
    lines.append("")
    lines.append(f"{'format':8s} {'files':>6s} {'total':>10s} {'average':>10s}")
    for ext in sorted(by_ext):
        sizes = by_ext[ext]
        lines.append(f"{ext:8s} {len(sizes):6d} {_human(sum(sizes)):>10s} {_human(sum(sizes) / len(sizes)):>10s}")
    if rows:
        lines.append("")
        lines.append(f"Average per audio file: {_human(total / len(rows))}")
        lines.append(f"Largest {min(top, len(rows))}:")
        for key, _ext, size in sorted(rows, key=lambda r: -r[2])[:top]:
            lines.append(f"  {_human(size):>9s}  {key}")
        per_song = (versions / songs) if songs and versions else 3.0
        basis = f"{per_song:.1f} versions per song from the database" if songs and versions else "an assumed 3 versions per song (no database found)"
        lines.append("")
        lines.append(f"Projection at the current average file size, using {basis} (an estimate, not a forecast):")
        for n in PROJECTION_SONGS:
            lines.append(f"  {n:6d} songs -> {_human(n * per_song * (total / len(rows)))}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--storage-root", default=os.environ.get("TUNORA_STORAGE_ROOT", "./data/audio"))
    ap.add_argument("--db", default=os.environ.get("TUNORA_DB_PATH", "tunora.db"))
    a = ap.parse_args()
    songs, versions = counts_from_db(Path(a.db))
    print(build_report(scan(Path(a.storage_root)), songs, versions))


if __name__ == "__main__":
    main()
