# Tunora — Phase 3, Step 16: Completion + Audio Result

Scope: a COMPLETED job exposes a safe audio result, and Tunora serves that audio from its own storage at `GET /api/jobs/{job_id}/audio`. No player, waveform, download UI or Library (Step 17+).

## 1. Reuse Audit

Need: serve one local file per request, with correct headers and (for a future `<audio>` element) byte ranges, chosen by a trusted server-side lookup rather than a client path.

| Candidate | License / version | Capability | Fit | Decision |
|---|---|---|---|---|
| **Starlette `FileResponse`** (re-exported by FastAPI) | BSD-3-Clause, Starlette 1.6.0 (read from the installed package metadata) | Sets `Content-Length`, `ETag`, `Last-Modified`, `Accept-Ranges: bytes`; handles `Range` (single and multiple ranges, `Content-Range`, 416) and `If-Range`; `content_disposition_type` lets it be `inline`; reads in chunks | Already a dependency; sufficient for everything required | **REUSE (chosen)** |
| **`StreamingResponse`** | same package | Streams a generator; no built-in range/ETag/length | Would mean writing range handling ourselves | **REJECT** (worse than the option above) |
| **`StaticFiles` mount** | same package | Serves a directory tree by URL path | The URL would be the file path, which is exactly the model this step must avoid; no per-job check (COMPLETED, ownership) | **REJECT** |
| **Reverse-proxy file serving (nginx `X-Accel-Redirect`, sendfile)** | n/a | Offloads file transfer | New infrastructure, forbidden here and unnecessary for one local user | **REJECT** |
| **Third-party range/media-serving packages** | not searched | — | Not needed once `FileResponse` was confirmed to support ranges; adding a dependency would violate "don't add a dependency just because it exists" | **Not evaluated** |

Decision: no new dependency and no custom range code. The only code written is the Tunora-specific part: deciding *which* file may be served for a job (`JobService.resolve_audio`) and the route.

## 2. Storage Integration

Unchanged from Step 13. The route never touches the filesystem directly: `JobService.resolve_audio` reads the job from `JobRepository`, then resolves the recorded key through `AudioStorage.get_path` (which already rejects `..`, drive letters, UNC and absolute keys, and enforces the storage root). Dependency direction is preserved: `route → JobService → {JobRepository, AudioStorage}`; ACE-Step is not involved after generation. `Job.result.audio.absolute_path` is still persisted internally (Step 13) but is no longer needed or used for serving.

## 3. Audio Artifact Contract

The existing Step 13 record was sufficient, so no new artifact model was added: `Job.result = {"audio": {key, absolute_path, filename, media_type, size_bytes}, duration, metadata}`.

The public representation changed from denylist to **allowlist** (`app/api/schemas.py`): a client receives, and only for COMPLETED jobs,

```json
"result": {
  "audio": { "key": "tunora-…/tunora-….mp3", "filename": "tunora-….mp3", "media_type": "audio/mpeg",
             "size_bytes": 160940, "audio_url": "/api/jobs/tunora-…/audio" },
  "duration": 10.0,
  "metadata": { "bpm": …, "genres": …, "key_scale": …, "time_signature": …, "prompt": …, "lyrics": … }
}
```

Never returned: `absolute_path`, storage root, ACE-Step temp path, ACE-Step task id, `/v1/audio?path=…`, `audio_paths`, or any other key that may be added to `Job.result` later (new fields are private by default). `duration` is what the provider reported, not a measured value.

Related contract change that goes beyond the literal audio field, made because the requirement is "no absolute filesystem path exposed": `JobResponse.error` used to return the raw internal failure text, which for storage failures contains file paths (for example "Failed to store generated audio: Source artifact does not exist: C:\…"). It is now the fixed string `"Generation failed."` for FAILED jobs and `null` otherwise; the raw text stays in the database. Consequence: one Step 12 API test asserted the raw text (`"connection refused" in error`); I changed that single assertion to the new contract (`error == "Generation failed."` and the raw text absent from the response). No other existing test was removed or loosened.

## 4. Audio Endpoint

`GET /api/jobs/{job_id}/audio` (`app/api/routes_jobs.py::get_job_audio`), following the existing `/api/jobs` prefix. Input: the job id only. Query parameters are ignored, not rejected (tested with `?path=`, `?file=`, `?key=`). Response: Starlette `FileResponse` with `Content-Type` from the stored `media_type`, `Content-Length`, `ETag`/`Last-Modified`, `Accept-Ranges: bytes`, `Content-Disposition: inline; filename="<job-id>.mp3"` (Tunora-controlled name), and `X-Content-Type-Options: nosniff`.

Status codes: 200 (or 206 for a range); 404 unknown job; 409 job exists but is not COMPLETED; 500 `{"detail": "Audio is unavailable."}` for any data-integrity or storage problem. Details go to the server log only (`logger.error`).

## 5. Security Model

The file location comes only from the trusted job record. `resolve_audio` refuses to serve unless all of these hold: job is COMPLETED; `result.audio` has non-empty `key`, `media_type`, `filename`; the key starts with `"<this job's id>/"` (a job can never serve another job's artifact); the media type starts with `audio/` (a tampered or corrupt record can't cause `text/html` to be served from the API origin); `AudioStorage.get_path` accepts the key (rejects traversal/absolute/drive/UNC and re-checks containment in the storage root); the file exists; the file is non-empty. Anything else is a generic 500 with no path in the body.

Tested attacks (all responses asserted to contain neither the planted secret file nor any other artifact's bytes): tampered stored keys `../secret.txt`, `../../secret.txt`, `tunora-a/../../secret.txt`, `tunora-a/../../../secret.txt`, literal `..%2f..%2fsecret.txt`, `%2e%2e/%2e%2e/secret.txt`, `C:\Windows\win.ini`, `C:/Windows/win.ini`, `\\server\share\x.mp3`, `//server/share/x.mp3`, `/etc/passwd`, and an empty key; a job whose key points at another job's file; traversal, encoded traversal, drive-letter and absolute paths supplied as the URL job id (never reach the filesystem — they are just unknown ids); client-supplied path query parameters. As a mutation check, disabling the ownership check made the cross-job test fail, then it was restored. Encoded `%2e%2e` keys are not decoded by the storage layer, so they are treated as ordinary (nonexistent) names and fail as "missing file"; that is safe, though it means those cases are rejected by the missing-file rule rather than a traversal rule.

Not covered: authentication (none exists; single-user local MVP), symlink attacks inside the storage root (not tested), and TOCTOU between the existence check and the read (a file replaced by someone with write access to the storage directory).

## 6. State Behavior

| Job state | `/audio` | `GET /api/jobs/{id}` `result` / `error` |
|---|---|---|
| CREATED, SUBMITTED, QUEUED, RUNNING | 409 | `null` / `null` |
| FAILED | 409 | `null` / `"Generation failed."` |
| COMPLETED with valid artifact | 200 / 206 | allowlisted result / `null` |
| COMPLETED, record missing or invalid | 500 generic | `result` is `null` if no audio dict is recorded |
| COMPLETED, file missing/empty/unreadable | 500 generic | result still lists the audio (the record exists; the file is what is missing) |
| Unknown job | 404 | 404 |

The last two COMPLETED rows are an honesty gap: the job payload can claim audio that the audio route then refuses. The frontend treats the route, not the payload, as the source of truth once Step 17 loads it; Step 15's page shows only a static "Audio ready".

## 7. Content-Type

Taken from the stored artifact's `media_type`, which Step 13 derives from the actual file extension via the stdlib `mimetypes` table (with a small fallback for opus/aac). It is not hard-coded to `audio/mpeg`. A WAV artifact is served as `audio/wav` (tested). The current pipeline produces MP3 (ACE-Step's default `audio_format`), so the real runs returned `audio/mpeg`. No additional format support was added.

## 8. Range-Request Decision

No custom code. `FileResponse` already implements HTTP range handling; verified by a unit test (`Range: bytes=10-19` returns 206, exactly those bytes, `Content-Range: bytes 10-19/<size>`, `Accept-Ranges: bytes`) and by the real integration test (`bytes=0-99` against a real generated file). **Not verified**: range requests through the Next.js `/api/*` rewrite (the E2E fetched the whole file through it and got 200). Browsers need working ranges for seeking in `<audio>`, so Step 17 must test that path and fall back to a direct backend URL or a Next route handler only if the rewrite breaks it. `HEAD` is not implemented (FastAPI `GET` routes do not answer it); not needed for playback.

## 9. Frontend Contract

`frontend/src/lib/api/jobs.ts`: typed `JobResult`/`JobAudio` replace the earlier `Record<string, unknown>`; `audioUrl(jobId)` is the only place an audio URL is built; `getAudioResource(job)` returns `{url, filename, mediaType, sizeBytes, durationSeconds}` only when the job is COMPLETED, has an audio artifact, and the backend's `audio_url` is exactly `/api/jobs/<id>/audio`; anything else (for example an ACE-Step URL) is ignored, not rendered. `JobTracker` shows "Audio ready" only when that resource exists and exposes it as `data-audio-url` on the marker (Tunora's own relative URL, not a link). A COMPLETED job with no usable resource shows "Your song finished, but its audio is not available right now." No `<audio>`, player, waveform, download button or link was added.

## 10. Error Handling

Route: fixed generic messages, details logged. Frontend: unchanged Step 14/15 handling; the tracker never renders `job.error` (and the API no longer returns raw text). The audio URL is not fetched by the UI in this step.

## 11. Backend Tests

**137 passed** (`uv run pytest tests -m "not smoke"`, up from 95 with 42 new tests in `tests/test_api_audio.py`): 200 with correct body, `Content-Type`, `Content-Length` and headers; WAV media type; 206 range; ignored query parameters; 409 for CREATED/SUBMITTED/QUEUED/RUNNING/FAILED; 404 unknown job; COMPLETED with no result, deleted file, empty file, storage failures (`StorageWriteError`, `OSError`), non-audio media type; the 12 tampered-key cases; cross-job artifact; 5 traversal-style job ids; the public result being an exact allowlist; no path/port/provider id/ACE-Step URL/`audio_paths` in any job JSON (single and list); FAILED returning the fixed message and no result; in-progress jobs having no result. Fakes and tmp directories only, no GPU.

## 12. Real Integration Test

`tests/test_audio_endpoint_smoke.py`, real ACE-Step, **passed** (about 36 s including startup): `POST /api/jobs` (10 s instrumental) → `COMPLETED` → `GET /api/jobs/<id>/audio` with only the job id → 200, `Content-Type: audio/mpeg`, `Content-Length` non-zero and equal to both the body length and the recorded `size_bytes`; the body is byte-for-byte the file in Tunora's storage; `Range: bytes=0-99` returns 206 with the first 100 bytes; no temp-dir path, `/v1/audio`, port 8001 or `absolute_path` appears in the job JSON, list JSON or response headers; a `?path=` pointing at the SQLite file still returns the audio. All three real-GPU smoke tests (Steps 11, 12/13, 16) pass together. Audio quality was not assessed (not possible for me).

## 13. E2E Test

Playwright, real stack (Next dev → FastAPI → ACE-Step), **3/3 passed**; the main test took about 18 s. It creates a song, tracks it, reloads mid-run, reaches "Generation complete" and "Audio ready", confirms the marker's `data-audio-url` is `/api/jobs/<id>/audio`, requests that URL through the Next proxy (200, `audio/*`, non-empty body whose length equals `Content-Length` and the recorded `size_bytes`), asserts no `audio`/`video`/`canvas` element, and asserts the rendered page, full page source and job payload contain no `/v1/audio`, `:8001`, `absolute_path`, `.cache`, ACE-Step task id or drive-letter path. Two of my first assertions were false positives worth recording: scanning the whole page source for a drive-letter pattern matches Next.js dev flight data, and the pattern also matched `http://` inside SVG markup; the final check scans the rendered markup for drive letters (with a "not preceded by a letter" guard) and the full source only for the unambiguous tokens.

## 14. Known Limitations

- 500 for integrity problems is deliberately generic, so a UI cannot tell "file missing" from "storage broken".
- The job payload can list audio that the audio route later refuses (see §6).
- Range through the Next rewrite is unverified (§8).
- `metadata.prompt`/`lyrics` are returned to any caller; they are the user's own input echoed by the provider, but there is no authentication in the MVP, so anyone who can reach the API can read them.
- No caching policy beyond `ETag`/`Last-Modified`; no `HEAD`.
- No symlink or TOCTOU hardening.
- Audio is not validated as decodable (Step 13 limitation carried over); the endpoint trusts the recorded media type only up to the `audio/` prefix.
- `absolute_path` still lives in the database record.
- The tampered-key tests exercise `LocalAudioStorage`'s rules; another `AudioStorage` implementation would need its own equivalent checks.

## 15. Step 17 Integration Notes

- `<audio src>` and WaveSurfer can point at `getAudioResource(job).url`; do not build URLs elsewhere.
- Verify seeking (Range) through the Next.js rewrite first; that is the most likely surprise.
- WaveSurfer decodes the whole file for peaks unless given precomputed peaks; for short clips this is fine, for 3-minute files consider fetch + `decodeAudioData` cost.
- Handle 409/500 from the audio URL in the player UI instead of trusting the job payload.
- Autoplay policies mean playback must start from a user gesture.
- Decide whether download (`Content-Disposition: attachment`) needs a separate route or a query flag; do not reuse a client-supplied filename.
