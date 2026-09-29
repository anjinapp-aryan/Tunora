"""Schema v6 (music_videos) and the Music Video repository (Phase 23)."""

from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from app.jobs import migrations
from app.jobs.repository import SqliteJobRepository
from app.music_videos.errors import MusicVideoInProgressError
from app.music_videos.models import MusicVideo, MusicVideoStatus
from app.music_videos.repository import InMemoryMusicVideoRepository, SqliteMusicVideoRepository
from app.songs.models import utcnow


def _video(version, video_id="mv-1", status=MusicVideoStatus.PENDING, **kw):
    now = utcnow()
    return MusicVideo(id=video_id, song_id=kw.pop("song_id", version.song_id), source_version_id=version.id,
                      status=status, style="minimal_white", aspect_ratio="9:16",
                      background_key=f"{video_id}/background.jpg", background_media_type="image/jpeg",
                      created_at=now, updated_at=now, **kw)


def test_a_v5_database_upgrades_to_v6_without_touching_existing_rows(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    for target, step in ((1, migrations._to_v1), (2, migrations._to_v2), (3, migrations._to_v3),
                         (4, migrations._to_v4), (5, migrations._to_v5)):
        migrations._run_step(conn, target, step)
    conn.execute("INSERT INTO songs (id, title, created_at, updated_at) VALUES ('song-a', 'A', 't', 't')")
    conn.execute("INSERT INTO versions (id, song_id, version_number, prompt, lyrics, language, instrumental, "
                 "provider, created_at) VALUES ('ver-a', 'song-a', 1, 'p', 'la', 'en', 0, 'ace-step', 't')")
    conn.commit()
    before = [tuple(r) for r in conn.execute("SELECT * FROM songs")] + [tuple(r) for r in conn.execute("SELECT * FROM versions")]
    conn.close()

    SqliteJobRepository(db)  # runs migrate() like every start does
    SqliteJobRepository(db)  # and again: idempotent

    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 7 == migrations.LATEST_VERSION  # Phase 27 added v7
    after = [tuple(r) for r in conn.execute("SELECT * FROM songs")] + [tuple(r) for r in conn.execute("SELECT * FROM versions")]
    assert after == before
    assert conn.execute("SELECT count(*) FROM music_videos").fetchone()[0] == 0


async def test_the_database_refuses_a_source_version_from_another_song(mvh):
    a = await mvh.vocal_version()
    b = await mvh.vocal_version()
    with pytest.raises(sqlite3.IntegrityError, match="same song"):
        mvh.mv_repository.create(_video(a, song_id=b.song_id))


async def test_source_fields_are_immutable_in_the_database(mvh):
    version = await mvh.vocal_version()
    mvh.mv_repository.create(_video(version))
    conn = sqlite3.connect(mvh.db)
    for column, value in (("source_version_id", "ver-other"), ("style", "bold"), ("background_key", "../x")):
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(f"UPDATE music_videos SET {column} = ? WHERE id = 'mv-1'", (value,))


@pytest.mark.parametrize("kind", ["sqlite", "memory"])
async def test_repository_create_get_list_update(mvh, kind):
    repo = mvh.mv_repository if kind == "sqlite" else InMemoryMusicVideoRepository()
    version = await mvh.vocal_version()
    repo.create(_video(version, "mv-1", status=MusicVideoStatus.FAILED))
    repo.create(_video(version, "mv-2"))
    assert [v.id for v in repo.list_for_song(version.song_id)][0] == "mv-2"  # newest first
    done = replace(repo.get("mv-2"), status=MusicVideoStatus.COMPLETED, duration=12.5, output_key="mv-2/mv-2.mp4",
                   output_size_bytes=10, timed_lyrics={"version": 1, "lines": [], "unaligned_lines": ["x"]})
    assert repo.update(done) is True
    stored = repo.get("mv-2")
    assert (stored.status, stored.duration, stored.output_key, stored.unmatched_lines) == (
        MusicVideoStatus.COMPLETED, 12.5, "mv-2/mv-2.mp4", ["x"])
    assert repo.update(replace(done, id="mv-missing")) is False
    assert repo.list_unfinished() == []


@pytest.mark.parametrize("kind", ["sqlite", "memory"])
async def test_only_one_in_progress_video_per_version(mvh, kind):
    repo = mvh.mv_repository if kind == "sqlite" else InMemoryMusicVideoRepository()
    version = await mvh.vocal_version()
    repo.create(_video(version, "mv-1"))
    with pytest.raises(MusicVideoInProgressError):
        repo.create(_video(version, "mv-2"))
    repo.update(replace(repo.get("mv-1"), status=MusicVideoStatus.COMPLETED))
    repo.create(_video(version, "mv-3"))  # a finished one does not block a new one


async def test_deleting_the_song_removes_its_music_video_rows(mvh):
    version = await mvh.vocal_version()
    mvh.mv_repository.create(_video(version))
    mvh.service.delete_song(version.song_id)
    assert mvh.mv_repository.get("mv-1") is None
