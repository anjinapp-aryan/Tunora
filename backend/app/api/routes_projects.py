"""Project API (Phase 6): organizational metadata over Songs.

A Project never carries audio or Version data; it only groups Songs. Adding or
removing a Song here changes exactly one column (`Song.project_id`) -- no
Song, Version, Job or audio file is ever created, copied or deleted.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request

from app.api.schemas import (
    AssignSongRequest,
    CreateProjectRequest,
    ProjectDetailsResponse,
    ProjectListResponse,
    ProjectResponse,
    ProjectSongResponse,
    UpdateProjectRequest,
    project_details_response,
    project_response,
    project_summary_response,
)
from app.jobs.service import JobService
from app.projects.errors import InvalidProjectError, ProjectNotFoundError
from app.songs.errors import InvalidIdError, SongNotFoundError

router = APIRouter(prefix="/api/projects", tags=["projects"])

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9-]*$"


def _get_service(request: Request) -> JobService:
    return request.app.state.job_service


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    q: str = Query("", max_length=100, description="Case-insensitive search in project name"),
    sort: Literal["newest", "oldest", "title"] = "newest",
):
    summaries = _get_service(request).list_projects(query=q, sort=sort, limit=limit)
    return ProjectListResponse(items=[project_summary_response(s) for s in summaries])


@router.post("", response_model=ProjectResponse)
async def create_project(payload: CreateProjectRequest, request: Request):
    try:
        project = _get_service(request).create_project(payload.name, payload.description)
    except InvalidProjectError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return project_response(project)


@router.get("/{project_id}", response_model=ProjectDetailsResponse)
async def get_project(request: Request, project_id: str = Path(max_length=80, pattern=_ID_PATTERN)):
    try:
        project, entries = _get_service(request).project_details(project_id)
    except (ProjectNotFoundError, InvalidIdError):
        raise HTTPException(status_code=404, detail="Project not found.")
    return project_details_response(project, entries)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    payload: UpdateProjectRequest, request: Request, project_id: str = Path(max_length=80, pattern=_ID_PATTERN)
):
    service = _get_service(request)
    try:
        project = service.update_project(project_id, name=payload.name, description=payload.description)
    except (ProjectNotFoundError, InvalidIdError):
        raise HTTPException(status_code=404, detail="Project not found.")
    except InvalidProjectError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return project_response(project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(request: Request, project_id: str = Path(max_length=80, pattern=_ID_PATTERN)):
    """Deletes the Project only. Its Songs, their Versions and their audio are untouched;
    the songs simply become unassigned (see docs/PHASE-6-PROJECTS-WORKSPACES.md)."""

    service = _get_service(request)
    try:
        service.delete_project(project_id)
    except (ProjectNotFoundError, InvalidIdError):
        raise HTTPException(status_code=404, detail="Project not found.")


@router.post("/{project_id}/songs", response_model=ProjectSongResponse)
async def add_song(
    payload: AssignSongRequest, request: Request, project_id: str = Path(max_length=80, pattern=_ID_PATTERN)
):
    """Adds an EXISTING song to a project. Never creates a Song, Version, Job or audio file."""

    service = _get_service(request)
    try:
        song = service.add_song_to_project(project_id, payload.song_id)
    except (ProjectNotFoundError, SongNotFoundError, InvalidIdError):
        raise HTTPException(status_code=404, detail="Project or song not found.")
    versions = service.list_versions(song.id)
    playable = [v.version_number for v in versions]
    return ProjectSongResponse(
        id=song.id,
        title=song.title,
        version_count=len(versions),
        latest_version_number=max(playable) if playable else None,
        created_at=song.created_at.isoformat(),
        updated_at=song.updated_at.isoformat(),
    )


@router.delete("/{project_id}/songs/{song_id}", status_code=204)
async def remove_song(
    request: Request,
    project_id: str = Path(max_length=80, pattern=_ID_PATTERN),
    song_id: str = Path(max_length=80, pattern=_ID_PATTERN),
):
    """Removes a song from a project. The song, its versions and its audio are untouched."""

    service = _get_service(request)
    try:
        service.remove_song_from_project(project_id, song_id)
    except (ProjectNotFoundError, SongNotFoundError, InvalidIdError):
        raise HTTPException(status_code=404, detail="Project or song not found.")
