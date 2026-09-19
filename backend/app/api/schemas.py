"""Pydantic schemas for Tunora's own HTTP API — never ACE-Step's shapes."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from app.jobs.models import Job, JobStatus
from app.storage.filenames import safe_audio_filename

# Job.error holds raw exception text (it can contain filesystem paths or
# provider details), so it stays in the database/logs and is never returned.
PUBLIC_FAILURE_MESSAGE = "Generation failed."

_PUBLIC_AUDIO_FIELDS = ("key", "filename", "media_type", "size_bytes")
_PUBLIC_METADATA_FIELDS = ("bpm", "genres", "key_scale", "time_signature", "prompt", "lyrics")


class CreateJobRequest(BaseModel):
    prompt: str
    lyrics: str = ""
    language: str = "en"
    duration: Optional[float] = None
    seed: Optional[int] = None
    instrumental: bool = False
    batch_size: Optional[int] = None


class JobResponse(BaseModel):
    id: str
    provider: str
    status: str
    created_at: str
    submitted_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    result: Optional[dict[str, Any]] = None

    @classmethod
    def from_job(cls, job: Job) -> "JobResponse":
        return cls(
            id=job.id,
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
