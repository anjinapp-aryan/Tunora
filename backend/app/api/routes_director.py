"""AI Song Director API (Phase 7): natural language -> a reviewable SongSpec.

This never creates a Song, Version or Job -- it only calls the Director and
returns a plan. Generation is started afterwards through the existing,
unchanged `POST /api/jobs`, using the plan's fields as that endpoint's body.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.schemas import CreateSongPlanRequest, SongPlanResponse, song_plan_response
from app.director.base import SongDirector
from app.director.errors import DirectorUnavailableError, InvalidDirectorRequestError, InvalidSongPlanError

router = APIRouter(prefix="/api/songs", tags=["director"])


def _get_director(request: Request) -> SongDirector:
    return request.app.state.song_director


@router.post("/plan", response_model=SongPlanResponse)
async def create_song_plan(payload: CreateSongPlanRequest, request: Request):
    director = _get_director(request)
    try:
        spec = await director.create_plan(
            payload.query,
            instrumental=payload.instrumental,
            language=payload.language,
            duration=payload.duration,
            title=payload.title,
        )
    except InvalidDirectorRequestError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except InvalidSongPlanError:
        raise HTTPException(status_code=502, detail="The AI director produced an unusable plan. Please try again.")
    except DirectorUnavailableError:
        raise HTTPException(status_code=503, detail="The AI director is unavailable right now. Please try again.")
    return song_plan_response(spec)
