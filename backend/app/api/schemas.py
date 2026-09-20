"""Pydantic schemas for Tunora's own HTTP API — never ACE-Step's shapes."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from app.jobs.models import Job, JobStatus
from app.jobs.titles import derive_title
from app.songs.models import Song, SongSummary, Version, VersionEntry
from app.storage.filenames import safe_audio_filename

# Job.error holds raw exception text (it can contain filesystem paths or
# provider details), so it stays in the database/logs and is never returned.
PUBLIC_FAILURE_MESSAGE = "Generation failed."

_PUBLIC_AUDIO_FIELDS = ("key", "filename", "media_type", "size_bytes")
_PUBLIC_METADATA_FIELDS = ("bpm", "genres", "key_scale", "time_signature", "prompt", "lyrics")


class CreateJobRequest(BaseModel):
    title: Optional[str] = None
    # Generate another Version of an existing Song instead of a new Song.
    song_id: Optional[str] = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")
    prompt: str
    lyrics: str = ""
    language: str = "en"
    duration: Optional[float] = None
    seed: Optional[int] = None
    instrumental: bool = False
    batch_size: Optional[int] = None


class JobResponse(BaseModel):
    id: str
    title: str
    # Tunora ids of the Song/Version this job generates (null for pre-domain rows).
    song_id: Optional[str] = None
    version_id: Optional[str] = None
    version_number: Optional[int] = None
    provider: str
    status: str
    created_at: str
    submitted_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    result: Optional[dict[str, Any]] = None

    @classmethod
    def from_job(cls, job: Job, version: Optional[Version] = None) -> "JobResponse":
        return cls(
            id=job.id,
            title=job.title or derive_title(job.request.prompt),
            song_id=version.song_id if version else None,
            version_id=job.version_id,
            version_number=version.version_number if version else None,
            provider=job.provider,
            status=job.status.value,
            created_at=job.created_at.isoformat(),
            submitted_at=job.submitted_at.isoformat() if job.submitted_at else None,
            started_at=job.started_at.isoformat() if job.started_at else None,
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            error=PUBLIC_FAILURE_MESSAGE if job.status == JobStatus.FAILED else None,
            result=_public_result(job),
        )


def audio_url_for(job_id: str) -> str:
    """Tunora-owned URL of a job's audio resource (see routes_jobs.get_job_audio)."""

    return f"/api/jobs/{job_id}/audio"


def _public_result(job: Job) -> Optional[dict[str, Any]]:
    """Allowlist of result fields safe to return to clients.

    Built field by field (never copy-then-delete), so anything else the
    backend stores in Job.result -- absolute paths, provider locators -- is
    private by default. Audio is referenced by a Tunora URL, never a path.
    """

    result = job.result
    if job.status != JobStatus.COMPLETED or not isinstance(result, dict):
        return None
    audio = result.get("audio")
    if not isinstance(audio, dict):
        return None
    public_audio = {name: audio.get(name) for name in _PUBLIC_AUDIO_FIELDS}
    public_audio["filename"] = safe_audio_filename(
        audio.get("filename"), job_id=job.id, media_type=str(audio.get("media_type") or "")
    )
    public_audio["audio_url"] = audio_url_for(job.id)
    metadata = result.get("metadata") or {}
    return {
        "audio": public_audio,
        "duration": result.get("duration"),
        "metadata": {name: metadata[name] for name in _PUBLIC_METADATA_FIELDS if name in metadata},
    }


# -- Songs (Phase 5A) ---------------------------------------------------------------------------


class LatestVersionSummary(BaseModel):
    version_number: int
    duration: Optional[float] = None
    created_at: str


class SongSummaryResponse(BaseModel):
    id: str
    title: str
    version_count: int
    latest_version: LatestVersionSummary
    created_at: str
    updated_at: str


class SongListResponse(BaseModel):
    items: list[SongSummaryResponse]


class VersionAudioResponse(BaseModel):
    filename: str
    media_type: str
    size_bytes: int
    audio_url: str


class VersionResponse(BaseModel):
    id: str
    version_number: int
    is_latest: bool
    status: str
    created_at: str
    duration: Optional[float] = None
    # Null when the version has no stored audio (failed, still generating, or never completed).
    audio: Optional[VersionAudioResponse] = None
    prompt: str
    lyrics: str
    language: str
    instrumental: bool
    seed: Optional[int] = None


class SongDetailsResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    versions: list[VersionResponse]


def song_summary_response(summary: SongSummary) -> SongSummaryResponse:
    latest = summary.latest
    return SongSummaryResponse(
        id=summary.song.id,
        title=summary.song.title,
        version_count=summary.version_count,
        latest_version=LatestVersionSummary(
            version_number=latest.version_number,
            duration=latest.audio.duration if latest.audio else None,
            created_at=latest.created_at.isoformat(),
        ),
        created_at=summary.song.created_at.isoformat(),
        updated_at=summary.song.updated_at.isoformat(),
    )


def song_details_response(song: Song, entries: list[VersionEntry]) -> SongDetailsResponse:
    """Built field by field: no storage key, absolute path, provider name or task id can leak."""

    latest_number = max((e.version.version_number for e in entries), default=None)
    versions = []
    for entry in entries:
        v = entry.version
        audio = None
        if v.audio is not None and entry.job_id:
            audio = VersionAudioResponse(
                filename=safe_audio_filename(v.audio.filename, job_id=entry.job_id, media_type=v.audio.media_type),
                media_type=v.audio.media_type,
                size_bytes=v.audio.size_bytes,
                audio_url=audio_url_for(entry.job_id),
            )
        versions.append(
            VersionResponse(
                id=v.id,
                version_number=v.version_number,
                is_latest=v.version_number == latest_number,
                status=entry.job_status or "CREATED",
                created_at=v.created_at.isoformat(),
                duration=v.audio.duration if v.audio else None,
                audio=audio,
                prompt=v.spec.prompt,
                lyrics=v.spec.lyrics,
                language=v.spec.language,
                instrumental=v.spec.instrumental,
                seed=v.spec.seed,
            )
        )
    return SongDetailsResponse(
        id=song.id,
        title=song.title,
        created_at=song.created_at.isoformat(),
        updated_at=song.updated_at.isoformat(),
        versions=versions,
    )
