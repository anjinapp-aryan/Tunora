# Tunora — Phase 3, Step 11: ACE-Step MusicGenerationProvider Integration

## Architecture

```
Tunora domain / (future) FastAPI routes
        ↓  GenerationRequest / GenerationJob / GenerationStatus / GenerationResult
MusicGenerationProvider  (app/providers/base.py)
        ↓  implements
AceStepMusicGenerationProvider  (app/providers/ace_step.py)
        ↓  httpx (async HTTP client)
ACE-Step 1.5 REST API  (http://127.0.0.1:8001, unmodified, external)
        ↓
RTX 5060 Ti — generation
```

`backend/app/providers/` is the **only** place in Tunora that knows ACE-Step's request/response shapes. Everything else — future FastAPI routes, the job lifecycle (Step 12), the UI — talks only to `MusicGenerationProvider` and its four dataclasses (`GenerationRequest`, `GenerationJob`, `GenerationStatus`, `GenerationResult`). Adding a second provider (`YuEProvider`, etc.) later means writing one new file that implements the same interface; nothing else in Tunora changes.

## Reuse check (Step 11.3)

- **HTTP client**: `httpx` (BSD-3-Clause, the de facto standard async HTTP client for FastAPI-based Python backends) — reused as-is rather than hand-rolling connection/timeout/retry handling. No custom HTTP layer was written.
- **HTTP mocking for tests**: `respx` (BSD-3-Clause), the standard httpx-native mocking library — reused instead of building a fake transport/server by hand.
- **Background job/queue mechanism**: intentionally **not** introduced in this step. Step 11 only needed request/response mapping over HTTP; no queue was built. When Step 12 needs one, the "Simple background job mechanism initially" from the locked stack should be re-evaluated with the same reuse-first check before writing anything custom.
- No existing PyPI package was found that already speaks ACE-Step's specific `/release_task` + `/query_result` polling contract as a typed client — this is a small, ACE-Step-specific adapter, which is squarely within the BUILD-when-nothing-fits gate of the Reuse-First Law (a 5-endpoint bespoke wrapper around one project's private-ish REST contract is not something a generic package would or should provide).

## ACE-Step API contract (verified from source, not guessed)

The ACE-Step API server was not initially running, so the contract was confirmed by reading the actual FastAPI route/model source in `ACE-Step-1.5/acestep/api/` rather than assumed from documentation — then re-confirmed against the live `/health` endpoint and a real generation run (see Test Results). Relevant files: `api/http/release_task_route.py`, `api/http/release_task_models.py` (`GenerateMusicRequest`), `api/http/query_result_route.py`, `api/http/query_result_service.py`, `api/http/audio_route.py`, `api/server_utils.py` (`STATUS_MAP`), `api/jobs/local_cache_updates.py`.

### `POST /release_task`

Request: JSON body matching (a subset of) `GenerateMusicRequest` — Tunora only ever sets `prompt`, `lyrics`, `vocal_language`, `audio_duration`, `seed`/`use_random_seed`, `batch_size`, `model`; every other field keeps ACE-Step's own default.

Response (wrapped in the server's standard envelope):
```json
{"data": {"task_id": "<id>", "status": "queued", "queue_position": 1}, "code": 200, "error": null, "timestamp": ..., "extra": null}
```

### `POST /query_result`

Request: `{"task_id_list": ["<id>", ...]}`.

Response: `{"data": [{"task_id", "result": "<json-encoded list, as a string>", "status": 0|1|2, "progress_text"?}], ...}`.

**Confirmed API quirk**: `STATUS_MAP = {"queued": 0, "running": 0, "succeeded": 1, "failed": 2}` (`acestep/api/server_utils.py`) — the outer integer `status` **cannot distinguish queued from running**; both map to `0`. The only disambiguator is the `"stage"` string (`"queued"` / `"running"` / `"succeeded"` / `"failed"`) on the first item inside the JSON-encoded `result` field. `AceStepMusicGenerationProvider` reads `stage` specifically to tell these apart — this is documented in the provider's own module docstring so the reason isn't lost the next time someone reads the code.

On success, each item in the decoded `result` list looks like:
```json
{"file": "<absolute path>", "status": 1, "stage": "succeeded", "prompt": "...", "lyrics": "...",
 "metas": {"bpm": 120, "duration": 30.5, "genres": "...", "keyscale": "...", "timesignature": "..."}}
```
On failure, `status: 2` and (per `local_cache_updates.py`) a `"stage": "failed"`; a top-level `"error"` field is populated when the record store has an error message.

An **unknown/never-submitted task_id returns the same shape as a freshly-queued one** (`{"task_id": ..., "result": "[]", "status": 0}`, no `stage`) — the API has no way to distinguish "queued" from "doesn't exist." `AceStepMusicGenerationProvider` reports this as `QUEUED` because that's the literal, honest reading of the response; this is called out below as a known limitation rather than papered over.

### `GET /v1/audio?path=<file>`

Serves the audio file at `path`, but only if it resolves inside the server's `temp_audio_dir` (403 otherwise); returns `Content-Type` by extension (mp3/wav/flac/ogg). Since Tunora's backend runs on the same machine as ACE-Step in this phase, `AceStepMusicGenerationProvider.get_result()` returns **both** the raw filesystem path (`audio_path`, recovered from the `file` field — usable for the Step 14 copy-into-Tunora-storage step) and an HTTP URL through this endpoint (`metadata["audio_url"]`, usable for direct browser playback without the backend needing to proxy bytes itself).

**Correction found only by running the real smoke test, not by reading source alone**: `job_result_payload.py::build_generation_success_response` already wraps every audio path through `path_to_audio_url()` before it's stored server-side, so `/query_result`'s `file` field is never a raw filesystem path — it arrives as `/v1/audio?path=<url-encoded absolute path>` (e.g. `/v1/audio?path=I%3A%5CTunora%5C...%5Csong.mp3`). The real filesystem path (`raw_audio_paths` server-side) is never exposed over `/query_result` at all. `AceStepMusicGenerationProvider._extract_filesystem_path()` recovers the real path by parsing the `path` query parameter back out of `file`, and `audio_url` is built as `base_url + file` directly (since `file` is already the route, not a bare path). This is exactly the kind of undocumented-field risk the task explicitly warned about — confirmed by the real run, not assumed, and the first unit-test/real-run mismatch was caught and fixed in this step.

### `GET /health`

`{"data": {"status": "ok", "service": "ACE-Step API", ...}, ...}` — used by `AceStepMusicGenerationProvider.is_available()` for a best-effort readiness check.

## Request/response mapping

| Tunora `GenerationRequest` | ACE-Step `/release_task` field |
|---|---|
| `prompt` | `prompt` |
| `lyrics` (or `""` if `instrumental=True`) | `lyrics` |
| `language` | `vocal_language` |
| `duration` | `audio_duration` |
| `seed` (or none → random) | `seed` + `use_random_seed` |
| `batch_size` | `batch_size` |

| ACE-Step response | Tunora `GenerationStatus` / `GenerationResult` |
|---|---|
| `status=0`, `stage="queued"` | `JobState.QUEUED` |
| `status=0`, `stage="running"`, `progress` | `JobState.RUNNING`, `progress` |
| `status=1`, first `result` item | `JobState.SUCCEEDED` → `GenerationResult(audio_path=file, duration=metas.duration, metadata={...})` |
| `status=2`, `error`/`progress_text` | `JobState.FAILED`, `message` |
| anything else | `ProviderResponseError` (never silently guessed) |

## Error handling

| Condition | Raised |
|---|---|
| Connection refused / DNS failure / other transport error | `ProviderUnavailableError` |
| Request exceeds the HTTP client's timeout | `ProviderTimeoutError` |
| HTTP 5xx from ACE-Step | `ProviderUnavailableError` |
| HTTP 4xx from ACE-Step | `ProviderResponseError` |
| Non-JSON body, missing `data` envelope, `error` field set, missing `task_id`/`status`, `result` not valid JSON/not a list, unrecognized status code | `ProviderResponseError` |
| `get_result()` called on a job that is `FAILED` | `ProviderResponseError` with ACE-Step's own error detail |
| `get_result()` called before the job reached `SUCCEEDED` | `ProviderResponseError` telling the caller to check `get_status()` first |

No exception type leaks httpx or ACE-Step-specific details into calling code — every failure surfaces as one of Tunora's own four provider errors (`app/providers/errors.py`).

## Files created

- `backend/pyproject.toml`, `backend/README.md`
- `backend/app/__init__.py`
- `backend/app/providers/__init__.py`
- `backend/app/providers/base.py` — `MusicGenerationProvider` interface + domain dataclasses (`GenerationRequest`, `GenerationJob`, `GenerationStatus`, `GenerationResult`, `JobState`)
- `backend/app/providers/errors.py` — `ProviderError`, `ProviderUnavailableError`, `ProviderTimeoutError`, `ProviderResponseError`
- `backend/app/providers/ace_step.py` — `AceStepMusicGenerationProvider`
- `backend/tests/__init__.py`
- `backend/tests/test_ace_step_provider.py` — 17 mocked unit tests
- `backend/tests/test_ace_step_smoke.py` — real end-to-end smoke test (marked `smoke`, self-skips if the server isn't reachable)

No files modified — this is a new `backend/` directory; nothing pre-existing in the Tunora repo overlapped with it (verified in Step 11.1: only `ACE-Step-1.5/`, `CLAUDE.md`, `docs/` existed beforehand).

## Test results

### Mocked unit tests (`uv run pytest tests -m "not smoke"`)

**17/17 PASSED.** Covers: successful submission + `task_id` extraction, request-field mapping, instrumental → forced-empty-lyrics, queued/running/failed status parsing (including the `stage`-disambiguation quirk), succeeded-result → audio/metadata mapping, failed-job and not-yet-finished `get_result()` guards, read timeout → `ProviderTimeoutError`, connection error → `ProviderUnavailableError`, HTTP 5xx → `ProviderUnavailableError`, malformed/non-JSON body → `ProviderResponseError`, missing `data` envelope → `ProviderResponseError`, missing `task_id` → `ProviderResponseError`, health check true/false.

### Real ACE-Step smoke test (`uv run pytest tests -m smoke`)

**VERIFIED — 1/1 PASSED**, run twice against the real local ACE-Step API server (started via `uv run acestep-api`, `acestep-v15-turbo` DiT + `acestep-5Hz-lm-1.7B` LM per `.env`, RTX 5060 Ti).

- **Run 1** (cold-ish, model already resident from prior manual testing): submitted a 10s instrumental job, polled to `SUCCEEDED`, `get_result()` initially failed — `os.path.isfile()` returned `False` because `audio_path` was still the raw `/v1/audio?path=...` route string (the bug described above). This is what surfaced the `file`-field discovery.
- Fixed `AceStepMusicGenerationProvider` to recover the real filesystem path, added a unit test reproducing the exact real-world `file` value, reran mocked suite (17/17 still pass) and the smoke test again.
- **Run 2** (post-fix): PASSED in 12.28s wall time for the whole test (submission + poll + result-fetch; most of that is one 5Hz-LM+DiT generation on an already-warm model). Objective facts checked, not audio quality: output file `.cache/acestep/tmp/api_audio/57674d0d-33df-6168-5d9d-7e15a56e9b9f.mp3` exists on disk, size 160,940 bytes, non-empty, `GenerationResult.duration == 10.0` (matches the requested `audio_duration`). Whether the 10-second instrumental clip actually sounds like "an upbeat instrumental synth loop" is a human-listening judgment this step does not and cannot make.

This is a real, on-GPU run — not a mock — satisfying Step 11.11.

## Known limitations

1. **Queued vs. unknown task_id are indistinguishable** — ACE-Step's `/query_result` returns the identical shape for a task that's genuinely queued and one that was never submitted (typo'd ID, expired record, etc.). Tunora's provider reports both as `QUEUED`; a caller polling an invalid ID forever will simply see it stay `QUEUED`. This should be mitigated in Step 12 by having Tunora's own job store be the source of truth for "does this job exist," using the provider only for status of jobs Tunora knows it submitted.
2. **No native cancel support** — ACE-Step's confirmed API surface has no cancel/abort endpoint, so `MusicGenerationProvider` intentionally does not declare a `cancel()` method yet (the Phase 3 architecture doc noted cancel would be "best-effort/local-only" — deferred until there's a real endpoint or a queue-side mechanism to not-dequeue a job).
3. **Progress is coarse** — `progress` (0.0–1.0) is only present once a job is `RUNNING`, and its granularity depends entirely on ACE-Step's own internal reporting; Tunora does not fabricate finer-grained progress.
4. **Single in-process queue on the ACE-Step side** — `acestep/api/jobs/worker_loops.py` shows ACE-Step processes its queue one job at a time; Tunora's provider doesn't need its own concurrency control against ACE-Step, but should not assume multiple jobs run in true parallel on one ACE-Step instance.
5. **Auth is currently disabled** — the dev `.env` has `ACESTEP_API_KEY` commented out, so `AceStepMusicGenerationProvider`'s optional `api_key`/Bearer-header support is implemented but untested against a real enforced-auth server in this step.

## Future provider extension strategy

Any new model (`YuEProvider`, `HeartMuLaProvider`, ...) implements `MusicGenerationProvider` (`generate`/`get_status`/`get_result`) and owns 100% of its request/response mapping internally, exactly like `AceStepMusicGenerationProvider` does here. Nothing upstream of the provider layer — future FastAPI routes, job lifecycle, UI — should ever need to change to add a provider; provider selection becomes a matter of instantiating a different class (or, later, a config-driven registry) at the composition root.
