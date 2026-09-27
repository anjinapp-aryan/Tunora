"""Music Video API (Phase 23).

POST /api/songs/{song_id}/music-videos           create (background file = request body)
GET  /api/songs/{song_id}/music-videos           list a Song's Music Videos (newest first)
GET  /api/music-videos/{music_video_id}          one Music Video (status polling)
GET  /api/music-videos/{music_video_id}/video    the rendered MP4 (Range/ETag via FileResponse)

The background is sent as the raw request body with its media type in Content-Type, and the other
fields as query parameters. That keeps uploads streaming and size-capped without adding a multipart
parser dependency. Nothing here accepts a filesystem path, and no response contains one.
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Path, Query, Request
from fastapi.responses import FileResponse

from app.api.schemas import MusicVideoListResponse, MusicVideoResponse, music_video_response
from app.music_videos.errors import (
    FFmpegPolicyError,
    InvalidMusicVideoRequestError,
    MusicVideoInProgressError,
    MusicVideoNotFoundError,
)
from app.music_videos.models import MusicVideo
from app.music_videos.service import BACKGROUND_TYPES, MusicVideoService, public_error
from app.songs.errors import InvalidIdError, SongNotFoundError, SourceAudioUnavailableError, SourceVersionNotFoundError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["music-videos"])

_ID = r"^[A-Za-z0-9][A-Za-z0-9-]*$"
_MAX_UPLOAD = max(limit for _, limit in BACKGROUND_TYPES.values())


def _service(request: Request) -> MusicVideoService:
    return request.app.state.music_video_service


def _respond(request: Request, video: MusicVideo, numbers: Optional[dict[str, int]] = None) -> MusicVideoResponse:
    if numbers is None:
        versions = request.app.state.job_service.list_versions(video.song_id)
        numbers = {v.id: v.version_number for v in versions}
    return music_video_response(video, numbers.get(video.source_version_id), public_error(video))


@router.post("/api/songs/{song_id}/music-videos", response_model=MusicVideoResponse, status_code=202)
async def create_music_video(
    request: Request,
    background_tasks: BackgroundTasks,
    song_id: str = Path(max_length=80, pattern=_ID),
    source_version_id: str = Query(max_length=80, pattern=_ID),
    style: Literal["minimal_white", "dreamy", "bold"] = Query("minimal_white"),
    aspect_ratio: Literal["9:16"] = Query("9:16"),
):
    """Create a Music Video of one existing, completed Version of this Song. Returns 202 at once;
    poll GET /api/music-videos/{id} until COMPLETED or FAILED."""

    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > _MAX_UPLOAD):
        raise HTTPException(status_code=413, detail="The background file is too large.")
    service = _service(request)
    try:
        video = await service.create(
            song_id, source_version_id=source_version_id, style=style, aspect_ratio=aspect_ratio,
            media_type=request.headers.get("content-type", ""), chunks=request.stream())
    except (InvalidIdError, SongNotFoundError):
        raise HTTPException(status_code=404, detail="Song not found.")
    except SourceVersionNotFoundError:
        raise HTTPException(status_code=404, detail="Version not found for this song.")
    except SourceAudioUnavailableError:
        raise HTTPException(status_code=409, detail="This version has no audio available.")
    except MusicVideoInProgressError:
        raise HTTPException(status_code=409, detail="A music video for this version is already being generated.")
    except InvalidMusicVideoRequestError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except FFmpegPolicyError as exc:
        logger.error("music video unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="Music video rendering is not available on this server.")
    background_tasks.add_task(service.generate, video.id)
    return _respond(request, video)


@router.get("/api/songs/{song_id}/music-videos", response_model=MusicVideoListResponse)
async def list_music_videos(request: Request, song_id: str = Path(max_length=80, pattern=_ID)):
    try:
        videos = _service(request).list_for_song(song_id)
    except (InvalidIdError, SongNotFoundError):
        raise HTTPException(status_code=404, detail="Song not found.")
    numbers = {v.id: v.version_number for v in request.app.state.job_service.list_versions(song_id)}
    return MusicVideoListResponse(items=[_respond(request, v, numbers) for v in videos])


@router.get("/api/music-videos/{music_video_id}", response_model=MusicVideoResponse)
async def get_music_video(request: Request, music_video_id: str = Path(max_length=80, pattern=_ID)):
    try:
        video = _service(request).get(music_video_id)
    except MusicVideoNotFoundError:
        raise HTTPException(status_code=404, detail="Music video not found.")
    return _respond(request, video)


@router.get("/api/music-videos/{music_video_id}/video")
async def get_music_video_file(request: Request, music_video_id: str = Path(max_length=80, pattern=_ID)):
    """The rendered MP4. FileResponse gives Content-Length, ETag and HTTP Range (for seeking)."""

    try:
        video, path = _service(request).output_path(music_video_id)
    except MusicVideoNotFoundError:
        raise HTTPException(status_code=404, detail="Music video not found.")
    return FileResponse(path, media_type="video/mp4", filename=f"tunora-{video.id}.mp4",
                        content_disposition_type="inline", headers={"X-Content-Type-Options": "nosniff"})
