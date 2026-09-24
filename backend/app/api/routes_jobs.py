"""Minimal FastAPI endpoints for validating Step 12's job lifecycle.

Intentionally thin — the full Create Song UI and richer endpoints are later
steps. Only enough surface exists here to create a job, check on it, and
list recent jobs, all returning Tunora-owned shapes only.
"""

from __future__ import annotations

import logging

from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.api.schemas import CreateJobRequest, JobResponse
from app.jobs.models import JobStatus
from app.jobs.errors import AudioIntegrityError, AudioNotAvailableError, JobNotFoundError
from app.jobs.service import JobService
from app.projects.errors import ProjectNotFoundError
from app.songs.errors import InvalidIdError, SongNotFoundError
from app.providers.base import GenerationRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _get_service(request: Request) -> JobService:
    return request.app.state.job_service


@router.post("", response_model=JobResponse)
async def create_job(payload: CreateJobRequest, request: Request, background_tasks: BackgroundTasks):
    service = _get_service(request)
    generation_request = GenerationRequest(
        prompt=payload.prompt,
        lyrics=payload.lyrics,
        language=payload.language,
        duration=payload.duration,
        seed=payload.seed,
        instrumental=payload.instrumental,
        batch_size=payload.batch_size,
    )
    try:
        job = await service.create_and_submit(
            generation_request, title=payload.title, song_id=payload.song_id, project_id=payload.project_id
        )
    except (SongNotFoundError, ProjectNotFoundError, InvalidIdError):
        raise HTTPException(status_code=404, detail="Song or project not found.")
    if job.status.value not in ("FAILED",):
        background_tasks.add_task(service.run_until_terminal, job.id)
    return _respond(service, [job])[0]


def _respond(service: JobService, jobs: list) -> list[JobResponse]:
    versions = service.versions_for(jobs)
    return [JobResponse.from_job(job, versions.get(job.version_id)) for job in jobs]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, request: Request):
    service = _get_service(request)
    try:
        job = service.get(job_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail=f"No job found with id {job_id!r}")
    return _respond(service, [job])[0]


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None, description="Only jobs in this status, e.g. COMPLETED"),
    q: str = Query("", max_length=100, description="Case-insensitive search in title and prompt"),
    sort: Literal["newest", "oldest", "title"] = "newest",
):
    service = _get_service(request)
    wanted: Optional[JobStatus] = None
    if status:
        try:
            wanted = JobStatus(status.upper())
        except ValueError:
            raise HTTPException(status_code=422, detail="Unknown status.")
    return _respond(service, service.search(status=wanted, query=q, sort=sort, limit=limit))


@router.get("/{job_id}/audio")
async def get_job_audio(job_id: str, request: Request):
    """Serve a COMPLETED job's audio. The only client input is the Tunora job id;
    the file location comes from the trusted job record via AudioStorage.
    Query parameters are deliberately ignored.
    """

    service = _get_service(request)
    try:
        audio = service.resolve_audio(job_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found.")
    except AudioNotAvailableError:
        raise HTTPException(status_code=409, detail="Audio is not available for this job.")
    except AudioIntegrityError as exc:
        logger.error("audio unavailable for a completed job: %s", exc)
        raise HTTPException(status_code=500, detail="Audio is unavailable.")

    # FileResponse (Starlette) provides Content-Length, ETag/Last-Modified and
    # HTTP Range support. "inline" so a future <audio> element can play it.
    return FileResponse(
        audio.path,
        media_type=audio.media_type,
        filename=audio.filename,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff"},
    )
