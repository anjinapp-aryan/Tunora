"""Unit tests for AceStepSongDirector against mocked HTTP responses.

No network access and no ACE-Step server required -- respx intercepts httpx
calls at the transport level. See tests/test_ace_step_director_smoke.py for the
real, end-to-end test against a running local ACE-Step server.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.director.ace_step import AceStepSongDirector
from app.director.errors import DirectorUnavailableError, InvalidDirectorRequestError, InvalidSongPlanError

BASE_URL = "http://127.0.0.1:8001"


def _wrap(data, code=200, error=None):
    return {"data": data, "code": code, "error": error, "timestamp": 0, "extra": None}


def _sample(**overrides):
    base = {
        "caption": "An emotional cinematic ballad with soft piano and acoustic guitar.",
        "lyrics": "[Verse 1]\nline one\n[Chorus]\nline two",
        "bpm": 92,
        "keyscale": "D minor",
        "duration": 143.0,
        "timesignature": "4",
        "vocal_language": "kn",
    }
    base.update(overrides)
    return base


@pytest.fixture
def director():
    return AceStepSongDirector(base_url=BASE_URL)


@pytest.mark.asyncio
async def test_create_plan_maps_a_full_ace_step_response_to_a_song_spec(director):
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.post("/v1/create_sample").mock(return_value=httpx.Response(200, json=_wrap(_sample())))
        spec = await director.create_plan("an emotional cinematic Kannada song about a mother")

    assert route.calls.last.request.url.path == "/v1/create_sample"
    body = route.calls.last.request.content
    assert b'"query"' in body and b"an emotional cinematic Kannada song about a mother".replace(b" ", b" ") in body
    assert (spec.prompt, spec.language, spec.duration, spec.bpm, spec.key_scale, spec.time_signature) == (
        "An emotional cinematic ballad with soft piano and acoustic guitar.", "kn", 143.0, 92, "D minor", "4",
    )
    assert spec.lyrics.startswith("[Verse 1]")
    assert spec.instrumental is False
    assert spec.title  # derived deterministically from the query, not the AI
    assert spec.requested_fields == frozenset({"instrumental"})  # nothing else was user-specified


@pytest.mark.asyncio
async def test_sends_instrumental_and_language_through_to_ace_step(director):
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.post("/v1/create_sample").mock(
            return_value=httpx.Response(200, json=_wrap(_sample(lyrics="[Instrumental]", vocal_language="unknown")))
        )
        await director.create_plan("a calm ambient piano piece", instrumental=True, language="hi")

    import json as _json

    sent = _json.loads(route.calls.last.request.content)
    assert sent == {"query": "a calm ambient piano piece", "instrumental": True, "vocal_language": "hi", "temperature": 0.85}


@pytest.mark.asyncio
async def test_explicit_user_language_overrides_the_planners_language(director):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/v1/create_sample").mock(return_value=httpx.Response(200, json=_wrap(_sample(vocal_language="en"))))
        spec = await director.create_plan("a love song", language="ta")  # planner ignored the hint and answered "en"

    assert spec.language == "ta"  # the user's explicit choice, not the planner's "en"
    assert "language" in spec.requested_fields


@pytest.mark.asyncio
async def test_explicit_user_duration_overrides_the_planners_duration(director):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/v1/create_sample").mock(return_value=httpx.Response(200, json=_wrap(_sample(duration=200.0))))
        spec = await director.create_plan("a song", duration=60.0)

    assert spec.duration == 60.0
    assert "duration" in spec.requested_fields


@pytest.mark.asyncio
async def test_explicit_user_title_overrides_the_derived_title(director):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/v1/create_sample").mock(return_value=httpx.Response(200, json=_wrap(_sample())))
        spec = await director.create_plan("a song about rain", title="Monsoon")

    assert spec.title == "Monsoon"
    assert "title" in spec.requested_fields


@pytest.mark.asyncio
async def test_instrumental_true_forces_empty_lyrics_even_if_the_planner_returns_some(director):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/v1/create_sample").mock(
            return_value=httpx.Response(200, json=_wrap(_sample(lyrics="[Verse]\nunexpected lyrics")))
        )
        spec = await director.create_plan("a piano piece", instrumental=True)

    assert spec.lyrics == "" and spec.instrumental is True


@pytest.mark.asyncio
async def test_na_duration_is_treated_as_unknown_not_an_error(director):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/v1/create_sample").mock(return_value=httpx.Response(200, json=_wrap(_sample(duration="N/A"))))
        spec = await director.create_plan("a song")
    assert spec.duration is None


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_field,value", [("bpm", 9999), ("bpm", "fast"), ("keyscale", 123), ("timesignature", "x" * 50)])
async def test_bad_informational_metadata_is_dropped_not_fatal(director, bad_field, value):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/v1/create_sample").mock(return_value=httpx.Response(200, json=_wrap(_sample(**{bad_field: value}))))
        spec = await director.create_plan("a song")  # must not raise
    assert spec.prompt  # the plan is still usable


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides,match",
    [
        ({"caption": ""}, "usable song description"),
        ({"caption": "   "}, "usable song description"),
        ({"caption": "x" * 2001}, "too long"),
        ({"lyrics": "x" * 5001}, "lyrics were too long"),
        ({"duration": -5}, "invalid duration"),
        ({"duration": 0}, "invalid duration"),
        ({"duration": 9999}, "outside the supported range"),
    ],
)
async def test_invalid_planner_output_is_rejected(director, overrides, match):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/v1/create_sample").mock(return_value=httpx.Response(200, json=_wrap(_sample(**overrides))))
        with pytest.raises(InvalidSongPlanError, match=match):
            await director.create_plan("a song")


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["", "   "])
async def test_empty_query_is_rejected_before_any_network_call(director, query):
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as mock:
        route = mock.post("/v1/create_sample").mock(return_value=httpx.Response(200, json=_wrap(_sample())))
        with pytest.raises(InvalidDirectorRequestError):
            await director.create_plan(query)
    assert route.call_count == 0


@pytest.mark.asyncio
async def test_oversized_query_is_rejected(director):
    with pytest.raises(InvalidDirectorRequestError):
        await director.create_plan("x" * 1001)


@pytest.mark.asyncio
async def test_http_failure_maps_to_director_unavailable(director):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/v1/create_sample").mock(return_value=httpx.Response(503, text="LLM not initialized"))
        with pytest.raises(DirectorUnavailableError):
            await director.create_plan("a song")


@pytest.mark.asyncio
async def test_network_timeout_maps_to_director_unavailable():
    director = AceStepSongDirector(base_url=BASE_URL, request_timeout=0.01)
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/v1/create_sample").mock(side_effect=httpx.TimeoutException("timed out"))
        with pytest.raises(DirectorUnavailableError):
            await director.create_plan("a song")


@pytest.mark.asyncio
async def test_malformed_json_response_maps_to_director_unavailable(director):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/v1/create_sample").mock(return_value=httpx.Response(200, text="not json"))
        with pytest.raises(DirectorUnavailableError):
            await director.create_plan("a song")
