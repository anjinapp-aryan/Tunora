"""AceStepSongDirector: adapts ACE-Step 1.5's own 5Hz-LM planner to `SongDirector`.

Phase 7 reuse decision (docs/PHASE-7-AI-SONG-DIRECTOR.md): ACE-Step already ships
exactly this capability -- `POST /v1/create_sample` turns one natural-language
`query` into a caption, lyrics and metadata using its local 5Hz LM (the same
model/server Tunora already depends on for generation). Verified against the
real, running server (see the doc's evidence section) before writing this
adapter: no second LLM, no external service, no new model download.

`/v1/create_sample`'s own docstring: "the API equivalent of the Gradio UI's
Simple Mode 'Create Sample' button". Confirmed live that it honours an explicit
`instrumental`/`vocal_language` (never invents lyrics when instrumental=True,
never picks a different language than the one given) -- so only `duration` and
`title` need Tunora-side enforcement, since `/v1/create_sample` has no duration
input and no title field at all.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from app.director.base import SongDirector
from app.director.errors import DirectorUnavailableError, InvalidDirectorRequestError, InvalidSongPlanError
from app.director.spec import REQUESTABLE_FIELDS, SongSpec
from app.director.validation import (
    validate_bpm,
    validate_duration,
    validate_language,
    validate_lyrics,
    validate_prompt,
    validate_short_text,
    validate_title,
)
from app.jobs.titles import derive_title
from app.providers.ace_step_http import unwrap_envelope
from app.providers.errors import ProviderError

QUERY_MAX = 1000  # matches the existing Create Song prompt limit


class AceStepSongDirector(SongDirector):
    """Calls ACE-Step's own `/v1/create_sample` and normalizes the result into a SongSpec."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8001",
        request_timeout: float = 180.0,  # LM planning was observed taking up to ~90s locally
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=request_timeout)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def create_plan(
        self,
        query: str,
        *,
        instrumental: bool = False,
        language: Optional[str] = None,
        duration: Optional[float] = None,
        title: Optional[str] = None,
        temperature: float = 0.85,
    ) -> SongSpec:
        query = (query or "").strip()
        if not query:
            raise InvalidDirectorRequestError("Describe the song you want first.")
        if len(query) > QUERY_MAX:
            raise InvalidDirectorRequestError(f"Keep the description under {QUERY_MAX} characters.")
        if not isinstance(instrumental, bool):
            raise InvalidDirectorRequestError("Instrumental must be true or false.")
        requested_language = validate_language(language) if language else ""
        requested_duration = validate_duration(duration) if duration is not None else None
        requested_title = validate_title(title) if title else ""

        payload = {
            "query": query,
            "instrumental": instrumental,
            "vocal_language": requested_language or "unknown",
            "temperature": temperature,
        }
        data = await self._post("/v1/create_sample", payload)
        if not isinstance(data, dict):
            raise InvalidSongPlanError("The AI director returned an unusable response.")

        # -- validate every AI-produced field as untrusted input ------------------------
        prompt = validate_prompt(data.get("caption"))
        lyrics = validate_lyrics(data.get("lyrics"), instrumental=instrumental)
        planner_language = validate_language(data.get("vocal_language"))
        planner_duration = validate_duration(data.get("duration")) if data.get("duration") not in (None, "N/A") else None
        bpm = validate_bpm(data.get("bpm"))
        key_scale = validate_short_text(data.get("keyscale") or data.get("key_scale"), 40)
        time_signature = validate_short_text(data.get("timesignature") or data.get("time_signature"), 10)

        # -- explicit user fields ALWAYS win over the planner's guess --------------------
        requested_fields = set()
        final_language = requested_language or planner_language
        if requested_language:
            requested_fields.add("language")
        final_duration = requested_duration if requested_duration is not None else planner_duration
        if requested_duration is not None:
            requested_fields.add("duration")
        requested_fields.add("instrumental")  # instrumental is always an explicit user choice, never inferred
        final_title = requested_title or derive_title(query)
        if requested_title:
            requested_fields.add("title")

        return SongSpec(
            title=final_title,
            prompt=prompt,
            lyrics=lyrics,
            language=final_language,
            duration=final_duration,
            instrumental=instrumental,
            bpm=bpm,
            key_scale=key_scale,
            time_signature=time_signature,
            requested_fields=frozenset(requested_fields) & REQUESTABLE_FIELDS,
        )

    async def _post(self, path: str, json_body: dict[str, Any]) -> Any:
        url = f"{self._base_url}{path}"
        try:
            response = await self._client.post(url, json=json_body)
        except httpx.TimeoutException as exc:
            raise DirectorUnavailableError("The AI director timed out. Please try again.") from exc
        except httpx.HTTPError as exc:
            raise DirectorUnavailableError("Could not reach the AI director.") from exc
        try:
            return unwrap_envelope(response, path)
        except ProviderError as exc:
            raise DirectorUnavailableError(str(exc)) from exc
