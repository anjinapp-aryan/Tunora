"""Song-oriented read API (Phase 5A): the Library and Song Details.

Songs are the Library's primary entity; versions and their audio hang off them.
Audio itself is still served only by GET /api/jobs/{job_id}/audio: a version
just carries that Tunora URL. Nothing here accepts a path, and versions are
only ever returned under the song that owns them.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request

from app.api.schemas import (
    SongDetailsResponse,
    SongListResponse,
    song_details_response,
    song_summary_response,
)
from app.jobs.service import JobService
from app.songs.errors import InvalidIdError, SongNotFoundError

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
