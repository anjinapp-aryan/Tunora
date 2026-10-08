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
from starlette.background import BackgroundTask

from app.api.schemas import CreateJobRequest, JobResponse
from app.audio.export import SUPPORTED_EXPORT_FORMATS
from app.jobs.models import JobStatus
from app.jobs.errors import AudioIntegrityError, AudioNotAvailableError, ExportConversionError, JobNotFoundError
from app.jobs.service import JobService
from app.projects.errors import ProjectNotFoundError
from app.songs.errors import InvalidIdError, InvalidOperationError, SongNotFoundError, SourceVersionNotFoundError
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
    if payload.source_version_id is not None and payload.song_id is None:
        raise HTTPException(status_code=422, detail="source_version_id needs the song_id it belongs to.")
    try:
        if payload.source_version_id is not None:
            # Phase 28: Revise / Retry -- a new Version of this song from one explicit Version's inputs.
            job = await service.create_revision(payload.song_id, payload.source_version_id, generation_request)
        else:
            job = await service.create_and_submit(
                generation_request, title=payload.title, song_id=payload.song_id, project_id=payload.project_id
            )
    except (SongNotFoundError, ProjectNotFoundError, InvalidIdError):
        raise HTTPException(status_code=404, detail="Song or project not found.")
    except SourceVersionNotFoundError:
        raise HTTPException(status_code=404, detail="Version not found for this song.")
    except InvalidOperationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
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
async def get_job_audio(
    job_id: str,
    request: Request,
    format: Optional[Literal["mp3", "wav"]] = Query(default=None, description="Export format (Phase 21): mp3 or wav. Omit for the canonical stored file."),
):
    """Serve a COMPLETED job's audio, or (with `?format=mp3|wav`) an on-demand export of it.

    The only client input is the Tunora job id and the export format; the file location comes
    from the trusted job record via AudioStorage. The canonical file (no `format`) is never
    touched by an export request: exporting converts a copy to a temporary file, which is deleted
    once the response has been sent, and creates no Version, Job or storage record.
    """

    service = _get_service(request)
    if format is None:
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

    try:
        export = service.resolve_export_audio(job_id, format)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found.")
    except AudioNotAvailableError:
        raise HTTPException(status_code=409, detail="Audio is not available for this job.")
    except AudioIntegrityError as exc:
        logger.error("audio unavailable for a completed job: %s", exc)
        raise HTTPException(status_code=500, detail="Audio is unavailable.")
    except ExportConversionError as exc:
        logger.error("export conversion failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not create this export.")

    # A real, unique temporary file (Phase 21) -- deleted once fully sent, success or client
    # disconnect, via Starlette's BackgroundTask. "attachment" because an export is a download,
    # never inline playback.
    return FileResponse(
        export.path,
        media_type=export.media_type,
        filename=export.filename,
        content_disposition_type="attachment",
        headers={"X-Content-Type-Options": "nosniff"},
        background=BackgroundTask(_cleanup_export, export.path),
    )


def _cleanup_export(path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("could not remove temporary export file")
