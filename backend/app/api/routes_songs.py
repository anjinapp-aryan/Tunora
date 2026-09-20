"""Song-oriented read API (Phase 5A): the Library and Song Details.

Songs are the Library's primary entity; versions and their audio hang off them.
Audio itself is still served only by GET /api/jobs/{job_id}/audio: a version
just carries that Tunora URL. Nothing here accepts a path, and versions are
only ever returned under the song that owns them.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Path, Query, Request

from app.api.routes_jobs import _respond
from app.api.schemas import (
    JobResponse,
    SongDetailsResponse,
    SongListResponse,
    VersionOperationRequest,
    song_details_response,
    song_summary_response,
)
from app.jobs.service import JobService
from app.providers.errors import UnsupportedOperationError
from app.songs.errors import (
    InvalidIdError,
    InvalidOperationError,
    SongNotFoundError,
    SourceAudioUnavailableError,
    SourceVersionNotFoundError,
)

router = APIRouter(prefix="/api/songs", tags=["songs"])


def _get_service(request: Request) -> JobService:
    return request.app.state.job_service


@router.get("", response_model=SongListResponse)
async def list_songs(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    q: str = Query("", max_length=100, description="Case-insensitive search in song title and prompts"),
    sort: Literal["newest", "oldest", "title"] = "newest",
):
    summaries = _get_service(request).list_songs(query=q, sort=sort, limit=limit)
    return SongListResponse(items=[song_summary_response(s) for s in summaries])


@router.get("/{song_id}", response_model=SongDetailsResponse)
async def get_song(
    request: Request,
    song_id: str = Path(max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$"),
):
    try:
        song, entries = _get_service(request).song_details(song_id)
    except (SongNotFoundError, InvalidIdError):
        raise HTTPException(status_code=404, detail="Song not found.")
    return song_details_response(song, entries)


_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9-]*$"


@router.post("/{song_id}/versions/{version_id}/{operation}", response_model=JobResponse)
async def create_version_from_operation(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: VersionOperationRequest,
    song_id: str = Path(max_length=80, pattern=_ID_PATTERN),
    version_id: str = Path(max_length=80, pattern=_ID_PATTERN),
    operation: Literal["extend", "remix", "repaint"] = Path(),
):
    """Create a NEW version of a song from one of its existing versions. The source version
    is only read; the result is a normal job that will produce the new version."""

    service = _get_service(request)
    try:
        job = await service.create_version_from_operation(
            song_id,
            version_id,
            operation.upper(),
            prompt=payload.prompt,
            lyrics=payload.lyrics,
            extend_seconds=payload.extend_seconds,
            repaint_start=payload.repaint_start,
            repaint_end=payload.repaint_end,
            remix_strength=payload.remix_strength,
        )
    except (InvalidIdError, SongNotFoundError, SourceVersionNotFoundError):
        raise HTTPException(status_code=404, detail="Song or version not found.")
    except SourceAudioUnavailableError:
        raise HTTPException(status_code=409, detail="The source audio is unavailable.")
    except InvalidOperationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except UnsupportedOperationError:
        raise HTTPException(status_code=422, detail="This operation is not supported.")
    if job.status.value != "FAILED":
        background_tasks.add_task(service.run_until_terminal, job.id)
    return _respond(service, [job])[0]
