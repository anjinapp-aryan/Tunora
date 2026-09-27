"""MusicVideoService (Phase 23): validation, lifecycle, unmatched lyrics, failures, recovery."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.music_videos.errors import (
    AlignmentError,
    FFmpegPolicyError,
    InvalidMusicVideoRequestError,
    MusicVideoInProgressError,
    RenderError,
)
from app.music_videos.models import MusicVideoStatus
from app.music_videos.service import public_error
from app.songs.errors import InvalidIdError, SongNotFoundError, SourceAudioUnavailableError, SourceVersionNotFoundError
from tests.music_videos.conftest import JPEG, LYRICS, MP4, PNG, timed_doc


def _files(mvh):
    return sorted(p.relative_to(mvh.mv_storage.root).as_posix() for p in mvh.mv_storage.root.rglob("*") if p.is_file())


# -- source Version validation ----------------------------------------------------------------


async def test_create_records_a_pending_video_and_stores_only_the_background(mvh):
    version = await mvh.vocal_version()
    video = await mvh.create(version)
    assert video.status == MusicVideoStatus.PENDING and video.id.startswith("mv-")
    assert (video.song_id, video.source_version_id, video.style, video.aspect_ratio) == (
        version.song_id, version.id, "minimal_white", "9:16")
    assert _files(mvh) == [f"{video.id}/background.jpg"]


async def test_missing_song_version_and_cross_song_version_are_rejected(mvh):
    a = await mvh.vocal_version()
    b = await mvh.vocal_version()
    with pytest.raises(SongNotFoundError):
        await mvh.mv.create("song-missing", source_version_id=a.id, style="minimal_white", aspect_ratio="9:16",
                            media_type="image/jpeg", chunks=_one(JPEG))
    with pytest.raises(SourceVersionNotFoundError):
        await mvh.create(a, source_version_id="ver-missing")
    with pytest.raises(SourceVersionNotFoundError):  # a Version of ANOTHER song
        await mvh.create(a, source_version_id=b.id)
    with pytest.raises(InvalidIdError):
        await mvh.create(a, source_version_id="../../etc/passwd")
    assert _files(mvh) == []


async def test_an_incomplete_version_or_deleted_audio_is_rejected(mvh):
    from app.providers.base import GenerationRequest

    job = await mvh.service.create_and_submit(GenerationRequest(prompt="p", lyrics=LYRICS))
    unfinished = mvh.repository.get_version(job.version_id)
    with pytest.raises(SourceAudioUnavailableError):
        await mvh.create(unfinished)
    version = await mvh.vocal_version()
    mvh.storage.get_path(version.audio.key).unlink()
    with pytest.raises(SourceAudioUnavailableError):
        await mvh.create(version)


async def test_an_instrumental_or_lyric_less_version_is_rejected(mvh):
    instrumental = await mvh.vocal_version(instrumental=True)
    with pytest.raises(InvalidMusicVideoRequestError, match="no lyrics"):
        await mvh.create(instrumental)
    empty = await mvh.vocal_version(lyrics="   ")
    with pytest.raises(InvalidMusicVideoRequestError, match="no lyrics"):
        await mvh.create(empty)


# -- background validation ----------------------------------------------------------------------


@pytest.mark.parametrize("body, media_type", [(JPEG, "image/jpeg"), (PNG, "image/png"), (MP4, "video/mp4")])
async def test_supported_background_types(mvh, body, media_type):
    version = await mvh.vocal_version()
    video = await mvh.create(version, body=body, media_type=media_type)
    assert video.background_media_type == media_type


@pytest.mark.parametrize("body, media_type, message", [
    (b"MZ\x90\x00 an .exe", "application/x-msdownload", "must be a JPG"),
    (b"<svg onload=alert(1)>", "image/svg+xml", "must be a JPG"),
    (b"not really a jpeg", "image/jpeg", "does not match its type"),
    (JPEG, "video/mp4", "does not match its type"),
    (b"", "image/jpeg", "empty"),
])
async def test_bad_backgrounds_are_rejected_and_leave_no_files(mvh, body, media_type, message):
    version = await mvh.vocal_version()
    with pytest.raises(InvalidMusicVideoRequestError, match=message):
        await mvh.create(version, body=body, media_type=media_type)
    assert _files(mvh) == []


async def test_an_oversized_background_is_rejected_while_streaming(mvh, monkeypatch):
    from app.music_videos import service as service_module

    monkeypatch.setitem(service_module.BACKGROUND_TYPES, "image/jpeg", (".jpg", 100))
    version = await mvh.vocal_version()
    with pytest.raises(InvalidMusicVideoRequestError, match="larger than"):
        await mvh.create(version, body=JPEG + b"\x00" * 200)
    assert _files(mvh) == []


async def test_a_background_rejected_by_ffprobe_leaves_no_files(mvh):
    def refuse(tools, path):
        raise InvalidMusicVideoRequestError("The background resolution is not supported.")

    mvh.mv._check_background = refuse
    version = await mvh.vocal_version()
    with pytest.raises(InvalidMusicVideoRequestError, match="resolution"):
        await mvh.create(version)
    assert _files(mvh) == []


async def test_unknown_style_and_aspect_ratio_are_rejected(mvh):
    version = await mvh.vocal_version()
    with pytest.raises(InvalidMusicVideoRequestError):
        await mvh.create(version, style="../../evil")
    with pytest.raises(InvalidMusicVideoRequestError, match="9:16"):
        await mvh.create(version, aspect_ratio="16:9")


async def test_no_approved_ffmpeg_means_no_video_and_no_files(mvh):
    mvh.tools_error = FFmpegPolicyError("GPL build")
    version = await mvh.vocal_version()
    with pytest.raises(FFmpegPolicyError):
        await mvh.create(version)
    assert _files(mvh) == [] and mvh.mv_repository.list_for_song(version.song_id) == []


async def test_a_duplicate_request_while_one_is_in_progress_is_rejected(mvh):
    version = await mvh.vocal_version()
    await mvh.create(version)
    with pytest.raises(MusicVideoInProgressError):
        await mvh.create(version)
    assert len(mvh.mv_repository.list_for_song(version.song_id)) == 1


# -- generation lifecycle -------------------------------------------------------------------------


async def test_generate_aligns_the_stored_lyrics_then_renders_and_completes(mvh):
    version = await mvh.vocal_version()
    video = await mvh.create(version, style="bold")
    done = mvh.mv.generate(video.id)

    assert done.status == MusicVideoStatus.COMPLETED
    audio_path, lyrics, language = mvh.aligner.calls[0]
    assert audio_path == mvh.storage.get_path(version.audio.key) and lyrics == LYRICS and language == "en"
    call = mvh.renderer.calls[0]
    assert (call["style"], call["aspect"], call["title"], call["lines"]) == ("bold", "9:16", mvh.repository.get_song(version.song_id).title, 1)
    assert call["background"] == mvh.mv_storage.get_path(video.background_key)
    stored = mvh.mv_repository.get(video.id)
    assert stored.output_key == f"{video.id}/{video.id}.mp4" and stored.duration == 12.5 and stored.completed_at
    assert stored.matched_line_count == 1 and stored.unmatched_lines == ["I will rise"]
    assert mvh.mv.output_path(video.id)[1].is_file()


async def test_unmatched_lyrics_are_never_rendered_and_the_stored_lyrics_are_unchanged(mvh):
    version = await mvh.vocal_version()
    mvh.aligner.doc = timed_doc(["With every fear I walk away"], unaligned=["I wake up to a brand new day", "I will rise"])
    video = await mvh.create(version)
    mvh.mv.generate(video.id)
    assert mvh.renderer.calls[0]["lines"] == 1  # only the matched line reaches the renderer
    assert mvh.mv_repository.get(video.id).unmatched_lines == ["I wake up to a brand new day", "I will rise"]
    assert mvh.repository.get_version(version.id).spec.lyrics == LYRICS


async def test_zero_matched_lines_fails_with_a_clear_message(mvh):
    version = await mvh.vocal_version()
    mvh.aligner.doc = timed_doc([], unaligned=["I wake up to a brand new day"])
    video = await mvh.create(version)
    failed = mvh.mv.generate(video.id)
    assert failed.status == MusicVideoStatus.FAILED and mvh.renderer.calls == []
    assert public_error(failed) == "None of this version's lyrics could be matched to its audio."


@pytest.mark.parametrize("stage", ["align", "render"])
async def test_alignment_or_render_errors_fail_safely_without_leaking_details(mvh, stage):
    version = await mvh.vocal_version()
    if stage == "align":
        mvh.aligner.error = AlignmentError(r"C:\secret\path Traceback stable-ts exploded")
    else:
        mvh.renderer.error = RenderError(r"ffmpeg failed: C:\secret\lyrics.ass")
    video = await mvh.create(version)
    failed = mvh.mv.generate(video.id)
    assert failed.status == MusicVideoStatus.FAILED
    assert "secret" in failed.error  # kept internally for the logs ...
    assert public_error(failed) == "Music video generation failed."  # ... never shown
    assert not mvh.mv_storage.get_path(f"{video.id}/{video.id}.mp4").exists()


async def test_source_audio_deleted_before_rendering_fails_as_source_unavailable(mvh):
    version = await mvh.vocal_version()
    video = await mvh.create(version)
    mvh.storage.get_path(version.audio.key).unlink()
    failed = mvh.mv.generate(video.id)
    assert public_error(failed) == "The source version's audio is no longer available."


async def test_generate_is_a_no_op_for_a_finished_or_unknown_video(mvh):
    version = await mvh.vocal_version()
    video = await mvh.create(version)
    mvh.mv.generate(video.id)
    mvh.mv.generate(video.id)
    assert len(mvh.renderer.calls) == 1
    assert mvh.mv.generate("mv-unknown") is None


async def test_the_source_version_is_never_modified_and_no_version_or_job_is_created(mvh):
    version = await mvh.vocal_version()
    jobs_before, versions_before = len(mvh.repository.list(200)), len(mvh.repository.list_versions(version.song_id))
    audio_bytes = mvh.storage.get_path(version.audio.key).read_bytes()
    video = await mvh.create(version)
    mvh.mv.generate(video.id)
    assert mvh.repository.get_version(version.id) == version
    assert mvh.storage.get_path(version.audio.key).read_bytes() == audio_bytes
    assert len(mvh.repository.list(200)) == jobs_before
    assert len(mvh.repository.list_versions(version.song_id)) == versions_before


# -- restart and deletion ----------------------------------------------------------------------------


async def test_restart_marks_interrupted_videos_failed_and_never_reruns_them(mvh):
    version = await mvh.vocal_version()
    video = await mvh.create(version)
    mvh.mv_repository.update(replace(mvh.mv_repository.get(video.id), status=MusicVideoStatus.RENDERING))
    assert mvh.mv.recover_interrupted() == 1
    failed = mvh.mv_repository.get(video.id)
    assert failed.status == MusicVideoStatus.FAILED and public_error(failed).startswith("Generation was interrupted")
    assert mvh.renderer.calls == [] and mvh.mv.recover_interrupted() == 0
    await mvh.create(version)  # the user can generate again; the failed one does not block it


async def test_a_song_deleted_while_rendering_leaves_no_files(mvh):
    version = await mvh.vocal_version()
    video = await mvh.create(version)
    original = mvh.renderer.render

    def render_then_song_deleted(*args, **kwargs):
        result = original(*args, **kwargs)
        mvh.service.delete_song(version.song_id)
        return result

    mvh.renderer.render = render_then_song_deleted
    mvh.mv.generate(video.id)
    assert _files(mvh) == [] and mvh.mv_repository.get(video.id) is None


async def test_delete_files_removes_only_that_videos_directory(mvh):
    version = await mvh.vocal_version()
    a = await mvh.create(version)
    mvh.mv.generate(a.id)
    b = await mvh.create(version)
    mvh.mv.delete_files([a.id, "../../escape", ""])
    assert all(f.startswith(b.id) for f in _files(mvh))


async def _one_gen(body):
    yield body


def _one(body):
    return _one_gen(body)
