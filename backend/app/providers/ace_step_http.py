"""Shared HTTP envelope handling for ACE-Step's REST API.

ACE-Step wraps every response as `{"data": ..., "code": int, "error": str|null, ...}`
(see docs/en/API.md §2). Both `AceStepMusicGenerationProvider` (generation) and
`AceStepSongDirector` (planning, Phase 7) talk to the same server and must parse
that envelope identically -- this module is the one place that does it, so a
change to ACE-Step's response shape only needs fixing once.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.providers.errors import ProviderResponseError, ProviderUnavailableError


def unwrap_envelope(response: httpx.Response, path: str) -> Any:
    """Return the `data` field of an ACE-Step response, or raise a provider error."""

    if response.status_code >= 500:
        raise ProviderUnavailableError(f"ACE-Step API returned {response.status_code} for {path}")
    if response.status_code >= 400:
        raise ProviderResponseError(f"ACE-Step API returned {response.status_code} for {path}: {response.text}")

    try:
        body = response.json()
    except ValueError as exc:
        raise ProviderResponseError(f"ACE-Step API returned a non-JSON response for {path}") from exc

    if not isinstance(body, dict) or "data" not in body:
        raise ProviderResponseError(f"ACE-Step API response for {path} is missing the 'data' envelope")
    if body.get("error"):
        raise ProviderResponseError(f"ACE-Step API returned an error for {path}: {body['error']}")

    return body["data"]
