"""Phase 21: on-demand FLAC -> MP3/WAV export.

Reuses `soundfile` (already installed for ACE-Step; verified in the Phase 20 audit, see
docs/PHASE-21-IMPLEMENTATION.md). FLAC stays canonical: exporting never creates a Version or Job,
never touches the stored file, and produces a temporary file the route deletes once sent.
"""

from __future__ import annotations

import asyncio
import hashlib
import io

import numpy as np
import pytest
import soundfile as sf
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router as jobs_router
from app.audio.export import ExportError, export_audio
from app.jobs.errors import ExportConversionError
from app.providers.base import GenerationRequest, GenerationResult, GenerationStatus, JobState
from tests.songs.test_service_versions import ACE_ID, Harness


def _real_audio_bytes(fmt: str, *, seconds: float = 0.5, rate: int = 8000, channels: int = 2) -> bytes:
    """A short, genuinely decodable tone -- real audio, not a placeholder string."""
    t = np.linspace(0, seconds, int(seconds * rate), endpoint=False)
    tone = 0.2 * np.sin(2 * np.pi * 440 * t).astype("float32")
    data = np.tile(tone[:, None], (1, channels))
    buf = io.BytesIO()
    sf.write(buf, data, rate, format=fmt)
    return buf.getvalue()


@pytest.fixture
def h(tmp_path):
    return Harness(tmp_path)


async def _completed_job(h, *, ext: str, content: bytes, title: str | None = None) -> "Job":
    """Like `Harness.generate_to_completion`, but with a real, decodable file under the exact
    extension a real Version of that format would have (`generate_to_completion` always names its
    fake output `.mp3`, which is fine for tests that don't care about the actual bytes, but wrong
    here where the export tests need a genuine FLAC -- or, for one test, a genuine legacy MP3)."""

    job = await h.service.create_and_submit(GenerationRequest(prompt="a song"), title=title)
    h.provider.status_responses = [GenerationStatus(job_id=ACE_ID, status=JobState.SUCCEEDED)]
    h.provider.result_response = GenerationResult(
        job_id=ACE_ID, audio_path=h.source_audio(f"out-{job.id}.{ext}", content), duration=0.5, metadata={},
    )
    return await h.service.poll_once(job.id)


async def _completed_flac_job(h, *, content: bytes | None = None):
    content = content if content is not None else _real_audio_bytes("FLAC")
    return await _completed_job(h, ext="flac", content=content)


def _song_id(h, job) -> str:
    return h.repository.get_version(job.version_id).song_id


# -- app/audio/export.py: pure conversion --------------------------------------------------------------


class TestExportAudio:
    def test_wav_export_is_valid_pcm16_with_the_source_rate_and_channels(self, tmp_path):
        src = tmp_path / "src.flac"
        src.write_bytes(_real_audio_bytes("FLAC", rate=22050, channels=2))
        exported = export_audio(src, "wav")
        try:
            data, rate = sf.read(exported.path)
            info = sf.info(exported.path)
            assert rate == 22050 and data.shape[1] == 2
            assert info.subtype == "PCM_16"
            assert exported.media_type == "audio/wav"
        finally:
            exported.path.unlink()

    def test_mp3_export_is_valid_and_close_to_the_source_duration(self, tmp_path):
        src = tmp_path / "src.flac"
        src.write_bytes(_real_audio_bytes("FLAC", seconds=1.0, rate=8000, channels=1))
        exported = export_audio(src, "mp3")
        try:
            info = sf.info(exported.path)
            assert info.format == "MP3"
            assert abs(info.duration - 1.0) < 0.15  # MP3 encoder padding/priming, not sample-exact
            assert exported.media_type == "audio/mpeg"
        finally:
            exported.path.unlink()

    def test_a_title_tag_is_embedded_when_the_encoder_supports_it(self, tmp_path):
        src = tmp_path / "src.flac"
        src.write_bytes(_real_audio_bytes("FLAC"))
        exported = export_audio(src, "mp3", title="My Song")
        try:
            with sf.SoundFile(exported.path) as f:
                assert f.title == "My Song"
        finally:
            exported.path.unlink()

    def test_an_unsupported_format_is_rejected_before_any_file_is_touched(self, tmp_path):
        src = tmp_path / "src.flac"
        src.write_bytes(_real_audio_bytes("FLAC"))
        with pytest.raises(ValueError):
            export_audio(src, "aac")

    def test_a_corrupt_or_unreadable_source_fails_cleanly_with_no_leftover_file(self, tmp_path):
        import tempfile as _tempfile
        from pathlib import Path

        src = tmp_path / "not-audio.flac"
        src.write_bytes(b"this is not a real audio file")
        # `export_audio` creates its temp file via `tempfile.mkstemp()`, i.e. in the real system
        # temp dir -- not under pytest's `tmp_path`. Snapshot that same directory so a stray file
        # left behind by an unrelated earlier run never gets misread as one this call created.
        temp_dir = Path(_tempfile.gettempdir())
        before = set(temp_dir.glob("tunora-export-*"))
        with pytest.raises(ExportError):
            export_audio(src, "wav")
        leftovers = set(temp_dir.glob("tunora-export-*")) - before
        assert leftovers == set()


# -- HTTP route: GET /api/jobs/{id}/audio?format=mp3|wav -----------------------------------------------


@pytest.fixture
def client(h):
    app = FastAPI()
    app.include_router(jobs_router)
    app.state.job_service = h.service
    return TestClient(app)


class TestExportRoute:
    async def test_mp3_export_downloads_a_valid_playable_file(self, h, client):
        job = await _completed_flac_job(h)
        r = client.get(f"/api/jobs/{job.id}/audio", params={"format": "mp3"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "audio/mpeg"
        assert "attachment" in r.headers["content-disposition"]
        assert r.headers["content-length"] == str(len(r.content))
        info = sf.info(io.BytesIO(r.content))
        assert info.format == "MP3"

    async def test_wav_export_downloads_a_valid_playable_pcm16_file(self, h, client):
        job = await _completed_flac_job(h)
        r = client.get(f"/api/jobs/{job.id}/audio", params={"format": "wav"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "audio/wav"
        info = sf.info(io.BytesIO(r.content))
        assert info.format == "WAV" and info.subtype == "PCM_16"

    async def test_the_canonical_download_is_unaffected_by_format_and_stays_inline(self, h, client):
        job = await _completed_flac_job(h)
        r = client.get(f"/api/jobs/{job.id}/audio")
        assert r.status_code == 200 and r.headers["content-type"] == "audio/flac"
        assert "inline" in r.headers["content-disposition"]

    async def test_an_unsupported_format_is_rejected_without_converting_anything(self, h, client):
        job = await _completed_flac_job(h)
        r = client.get(f"/api/jobs/{job.id}/audio", params={"format": "aac"})
        assert r.status_code == 422

    async def test_a_missing_job_is_404_for_both_the_canonical_route_and_export(self, client):
        assert client.get("/api/jobs/tunora-does-not-exist/audio").status_code == 404
        assert client.get("/api/jobs/tunora-does-not-exist/audio", params={"format": "mp3"}).status_code == 404

    async def test_a_job_that_is_not_completed_refuses_export(self, h, client):
        from app.providers.base import GenerationRequest

        job = await h.service.create_and_submit(GenerationRequest(prompt="not finished"))
        r = client.get(f"/api/jobs/{job.id}/audio", params={"format": "mp3"})
        assert r.status_code == 409

    async def test_malformed_job_ids_do_not_leak_internals_and_are_rejected_safely(self, client):
        # (a literal NUL byte is rejected by the test HTTP client itself before it ever reaches
        # the server, so it isn't a meaningful case to send here)
        for bad in ("../../etc/passwd", "..%2f..%2fetc%2fpasswd", "'; DROP TABLE jobs; --"):
            r = client.get(f"/api/jobs/{bad}/audio", params={"format": "mp3"})
            assert r.status_code == 404
            assert "etc/passwd" not in r.text and "DROP TABLE" not in r.text

    async def test_export_conversion_failure_is_a_safe_generic_error(self, h, client, monkeypatch):
        job = await _completed_flac_job(h)
        monkeypatch.setattr(
            "app.jobs.service.export_audio",
            lambda *a, **k: (_ for _ in ()).throw(ExportError("libsndfile exploded: /internal/path")),
        )
        r = client.get(f"/api/jobs/{job.id}/audio", params={"format": "mp3"})
        assert r.status_code == 500
        assert "libsndfile" not in r.text and "/internal/path" not in r.text
        assert r.json()["detail"] == "Could not create this export."

    async def test_no_version_or_job_is_created_by_exporting(self, h, client):
        job = await _completed_flac_job(h)
        jobs_before = len(h.repository.list(limit=200))
        versions_before = len(h.repository.list_versions(_song_id(h, job)))
        client.get(f"/api/jobs/{job.id}/audio", params={"format": "mp3"})
        client.get(f"/api/jobs/{job.id}/audio", params={"format": "wav"})
        assert len(h.repository.list(limit=200)) == jobs_before
        assert len(h.repository.list_versions(_song_id(h, job))) == versions_before

    async def test_the_canonical_source_file_is_byte_identical_after_exporting(self, h, client):
        job = await _completed_flac_job(h)
        source_path = h.storage.get_path(f"{job.id}/{job.id}.flac")
        before = hashlib.sha256(source_path.read_bytes()).hexdigest()
        client.get(f"/api/jobs/{job.id}/audio", params={"format": "mp3"})
        client.get(f"/api/jobs/{job.id}/audio", params={"format": "wav"})
        after = hashlib.sha256(source_path.read_bytes()).hexdigest()
        assert before == after

    async def test_an_existing_mp3_version_still_downloads_unchanged_and_can_still_be_exported(self, h, client):
        # A real, decodable "legacy" (pre-Phase-17) MP3 Version -- generate_to_completion's own
        # default already stores its fake output under a .mp3 key/media type; give it real bytes.
        job = await h.generate_to_completion(content=_real_audio_bytes("MP3"))
        r = client.get(f"/api/jobs/{job.id}/audio")
        assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"
        r2 = client.get(f"/api/jobs/{job.id}/audio", params={"format": "wav"})
        assert r2.status_code == 200 and sf.info(io.BytesIO(r2.content)).format == "WAV"

    async def test_temporary_export_files_are_removed_after_the_response_is_sent(self, h, client, monkeypatch):
        from app.audio import export as export_module

        captured = []
        real = export_module.export_audio

        def spy(*args, **kwargs):
            result = real(*args, **kwargs)
            captured.append(result.path)
            return result

        monkeypatch.setattr("app.jobs.service.export_audio", spy)
        job = await _completed_flac_job(h)
        client.get(f"/api/jobs/{job.id}/audio", params={"format": "mp3"})
        assert len(captured) == 1 and not captured[0].exists()

    async def test_storage_never_gains_a_permanent_file_from_exporting(self, h, client):
        job = await _completed_flac_job(h)
        before = sorted(p.name for p in h.storage.get_path(f"{job.id}").parent.iterdir())
        client.get(f"/api/jobs/{job.id}/audio", params={"format": "mp3"})
        client.get(f"/api/jobs/{job.id}/audio", params={"format": "wav"})
        after = sorted(p.name for p in h.storage.get_path(f"{job.id}").parent.iterdir())
        assert before == after

    async def test_concurrent_mixed_format_exports_do_not_collide(self, h, client):
        job = await _completed_flac_job(h)

        def fetch(fmt):
            return client.get(f"/api/jobs/{job.id}/audio", params={"format": fmt})

        results = await asyncio.gather(*[asyncio.to_thread(fetch, fmt) for fmt in ("mp3", "wav", "mp3", "wav")])
        assert all(r.status_code == 200 for r in results)
        assert [sf.info(io.BytesIO(r.content)).format for r in results] == ["MP3", "WAV", "MP3", "WAV"]

    async def test_filename_is_sanitized_and_uses_the_existing_allowlisted_extension_mapping(self, h, client):
        from app.providers.base import GenerationRequest, GenerationResult, GenerationStatus, JobState
        from tests.songs.test_service_versions import ACE_ID

        job = await h.service.create_and_submit(GenerationRequest(prompt="p"), title="../weird\r\nname?.mp3")
        h.provider.status_responses = [GenerationStatus(job_id=ACE_ID, status=JobState.SUCCEEDED)]
        h.provider.result_response = GenerationResult(
            job_id=ACE_ID, audio_path=h.source_audio(f"out-{job.id}.flac", _real_audio_bytes("FLAC")), duration=0.5, metadata={},
        )
        job = await h.service.poll_once(job.id)
        r = client.get(f"/api/jobs/{job.id}/audio", params={"format": "mp3"})
        disposition = r.headers["content-disposition"]
        assert "\r" not in disposition and "\n" not in disposition and ".." not in disposition
        assert disposition.strip().endswith('.mp3"') or disposition.strip().endswith(".mp3")
