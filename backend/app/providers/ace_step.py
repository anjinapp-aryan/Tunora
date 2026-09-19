"""ACE-Step 1.5 implementation of MusicGenerationProvider.

Talks to the ACE-Step REST API (confirmed from the ACE-Step-1.5 source at
`acestep/api/http/release_task_route.py`, `query_result_route.py`,
`audio_route.py`, and `acestep/api/server_utils.py::STATUS_MAP`, since the
API server was not running to fetch a live OpenAPI document during this
integration):

    POST /release_task   -> {"data": {"task_id", "status", "queue_position"}, ...}
    POST /query_result    -> {"data": [{"task_id", "result": <json str>, "status": 0|1|2,
                                          "progress_text"}], ...}
    GET  /v1/audio?path=  -> streams the audio file (used to build a playable URL)

`result` is itself a JSON-encoded list of items shaped like:
    {"file": "<path or ''>", "status": 0|1|2, "progress": 0.0-1.0, "stage": "queued"|
     "running"|"succeeded"|"failed", "metas": {...}, "error": "..." (optional)}

Confirmed against a real local run (not just source reading): on success, `file`
is NOT a raw filesystem path — it is already the `/v1/audio?path=<url-encoded
absolute path>` route string (built server-side by `job_result_payload.py`'s
`path_to_audio_url`). The real filesystem path (`raw_audio_paths` server-side)
is never exposed over `/query_result`. This provider recovers the filesystem
path by parsing the `path` query parameter back out of `file`.

STATUS_MAP maps both "queued" and "running" to the integer 0 — the outer
`status` field alone cannot distinguish them; `stage` on the first result
item is required. This is a real ACE-Step API quirk, not a Tunora choice.

This module is the ONLY place in Tunora that should know these shapes.
"""

from __future__ import annotations

import json
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

import httpx

from app.providers.base import (
    GenerationJob,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
    JobState,
    MusicGenerationProvider,
)
from app.providers.errors import (
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


class AceStepMusicGenerationProvider(MusicGenerationProvider):
    """MusicGenerationProvider backed by a locally-running ACE-Step 1.5 API server."""

    name = "ace-step"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8001",
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        request_timeout: float = 30.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_model = default_model
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=request_timeout)

    async def aclose(self) -> None:
        """Close the underlying HTTP client if this provider created it."""

        if self._owns_client:
            await self._client.aclose()

    async def is_available(self) -> bool:
        """Best-effort check of ACE-Step's /health endpoint."""

        try:
            response = await self._client.get(f"{self._base_url}/health")
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    # -- MusicGenerationProvider -------------------------------------------------

    async def generate(self, request: GenerationRequest) -> GenerationJob:
        payload = self._build_release_task_payload(request)
        data = await self._post("/release_task", payload)
        task_id = data.get("task_id") if isinstance(data, dict) else None
        if not task_id:
            raise ProviderResponseError("ACE-Step /release_task response is missing 'task_id'")
        return GenerationJob(job_id=str(task_id), provider=self.name, status=JobState.QUEUED)

    async def get_status(self, job_id: str) -> GenerationStatus:
        item = await self._query_result_item(job_id)
        state, progress, message = self._parse_status_item(item)
        return GenerationStatus(job_id=job_id, status=state, progress=progress, message=message)

    async def get_result(self, job_id: str) -> GenerationResult:
        item = await self._query_result_item(job_id)
        state, _progress, message = self._parse_status_item(item)

        if state == JobState.FAILED:
            raise ProviderResponseError(
                f"ACE-Step job {job_id} failed: {message or 'no error detail provided'}"
            )
        if state != JobState.SUCCEEDED:
            raise ProviderResponseError(
                f"ACE-Step job {job_id} has not finished (status={state.value}); "
                "call get_status() before get_result()"
            )

        result_list = self._parse_result_field(item)
        audio_items = [
            entry for entry in result_list if isinstance(entry, dict) and entry.get("file")
        ]
        if not audio_items:
            raise ProviderResponseError(
                f"ACE-Step job {job_id} succeeded but returned no audio file path"
            )

        primary = audio_items[0]
        metas = primary.get("metas") or {}
        audio_path = self._extract_filesystem_path(primary["file"])
        return GenerationResult(
            job_id=job_id,
            audio_path=audio_path,
            duration=metas.get("duration"),
            metadata={
                "audio_url": f"{self._base_url}{primary['file']}",
                "audio_paths": [
                    self._extract_filesystem_path(entry["file"]) for entry in audio_items
                ],
                "prompt": primary.get("prompt", ""),
                "lyrics": primary.get("lyrics", ""),
                "bpm": metas.get("bpm"),
                "genres": metas.get("genres", ""),
                "key_scale": metas.get("keyscale", ""),
                "time_signature": metas.get("timesignature", ""),
            },
        )

    @staticmethod
    def _extract_filesystem_path(file_field: str) -> str:
        """Recover the real filesystem path from ACE-Step's `/v1/audio?path=...` string.

        ACE-Step's `/query_result` never exposes a raw filesystem path directly
        (see module docstring) — `file` is already a route string. Fall back to
        returning it unchanged if it doesn't match that shape, so a future
        ACE-Step change that starts returning raw paths doesn't silently break.
        """

        parsed = urlparse(file_field)
        query_path = parse_qs(parsed.query).get("path")
        if query_path:
            return query_path[0]
        return file_field

    # -- request/response mapping -------------------------------------------------

    def _build_release_task_payload(self, request: GenerationRequest) -> dict[str, Any]:
        """Map Tunora's GenerationRequest onto ACE-Step's GenerateMusicRequest fields."""

        payload: dict[str, Any] = {
            "prompt": request.prompt,
            "lyrics": "" if request.instrumental else request.lyrics,
            "vocal_language": request.language,
        }
        if request.duration is not None:
            payload["audio_duration"] = request.duration
        if request.seed is not None:
            payload["use_random_seed"] = False
            payload["seed"] = request.seed
        else:
            payload["use_random_seed"] = True
        if request.batch_size is not None:
            payload["batch_size"] = request.batch_size
        if self._default_model:
            payload["model"] = self._default_model
        return payload

    def _parse_result_field(self, item: dict[str, Any]) -> list[Any]:
        raw = item.get("result", "[]")
        if isinstance(raw, list):
            return raw
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ProviderResponseError(
                "ACE-Step /query_result 'result' field was not valid JSON"
            ) from exc
        if not isinstance(parsed, list):
            raise ProviderResponseError("ACE-Step /query_result 'result' field was not a JSON list")
        return parsed

    def _parse_status_item(
        self, item: dict[str, Any]
    ) -> tuple[JobState, Optional[float], Optional[str]]:
        status_int = item.get("status")
        result_list = self._parse_result_field(item)
        first = (
            result_list[0]
            if result_list and isinstance(result_list[0], dict)
            else {}
        )
        stage = first.get("stage")
        progress = first.get("progress")
        message = item.get("progress_text") or first.get("error")

        if status_int == 1:
            state = JobState.SUCCEEDED
        elif status_int == 2:
            state = JobState.FAILED
        elif status_int == 0:
            # ACE-Step's STATUS_MAP collapses "queued" and "running" to the same
            # integer (0); only the per-item "stage" string disambiguates them.
            state = JobState.RUNNING if stage == "running" else JobState.QUEUED
        else:
            raise ProviderResponseError(
                f"ACE-Step /query_result returned an unrecognized status code: {status_int!r}"
            )
        return state, progress, message

    # -- HTTP plumbing -------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        if self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    async def _post(self, path: str, json_body: dict[str, Any]) -> Any:
        url = f"{self._base_url}{path}"
        try:
            response = await self._client.post(url, json=json_body, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"ACE-Step request to {path} timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"Could not reach ACE-Step API at {url}") from exc

        if response.status_code >= 500:
            raise ProviderUnavailableError(
                f"ACE-Step API returned {response.status_code} for {path}"
            )
        if response.status_code >= 400:
            raise ProviderResponseError(
                f"ACE-Step API returned {response.status_code} for {path}: {response.text}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderResponseError(
                f"ACE-Step API returned a non-JSON response for {path}"
            ) from exc

        if not isinstance(body, dict) or "data" not in body:
            raise ProviderResponseError(
                f"ACE-Step API response for {path} is missing the 'data' envelope"
            )
        if body.get("error"):
            raise ProviderResponseError(f"ACE-Step API returned an error for {path}: {body['error']}")

        return body["data"]

    async def _query_result_item(self, job_id: str) -> dict[str, Any]:
        data = await self._post("/query_result", {"task_id_list": [job_id]})
        if not isinstance(data, list) or not data:
            raise ProviderResponseError(f"ACE-Step /query_result returned no entry for job {job_id}")
        item = data[0]
        if not isinstance(item, dict) or "status" not in item:
            raise ProviderResponseError(
                f"ACE-Step /query_result entry for job {job_id} is missing 'status'"
            )
        return item
