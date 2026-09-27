# Phase 21 — On-Demand MP3/WAV Export

## 1. Executive Summary

Tunora can now export any COMPLETED job's canonical audio to MP3 or WAV on demand, via a `?format=`
query parameter on the existing `GET /api/jobs/{job_id}/audio` route. FLAC remains the sole canonical
stored format (unchanged since Phase 17). Exports are ephemeral: converted with `soundfile` into a
unique temporary file, streamed to the client, and deleted immediately after — never a new Version,
Job, or canonical storage entry, and no DB migration. One new backend runtime dependency was needed
(`soundfile`; see §4) — its license and that of its bundled MP3 encoder/decoder are verified in §18.

## 2. Architecture

```
Browser -> Next.js (/api/* rewrite) -> GET /api/jobs/{id}/audio?format=mp3|wav
                                                |
                                    routes_jobs.get_job_audio
                                                |
                                    JobService.resolve_export_audio(job_id, format)
                                        |                         |
                                resolve_audio(job_id)      app.audio.export.export_audio()
                                (existing, unchanged:            (new: soundfile FLAC -> MP3/WAV,
                                 trusted path resolution,         real tempfile, unlinked on any
                                 job/audio validation)            failure)
                                                |
                                FileResponse(..., background=BackgroundTask(delete tmp file))
```

No Song/Version/Job schema changed. `resolve_export_audio` calls the existing `resolve_audio` first,
so export inherits every existing validation and security guarantee (job-not-found, not-completed,
cross-job/path-traversal protection, integrity checks) without duplicating any of it — it only adds a
conversion step after the source is already resolved and verified.

## 3. Reuse Audit

- **Conversion**: `soundfile` (already present in ACE-Step's own venv; Phase 20 audit found it
  converts FLAC to MP3/WAV without FFmpeg). It was NOT present in Tunora's own backend venv, so it was
  added there explicitly (§4).
- **API shape**: extended the existing `GET /api/jobs/{job_id}/audio` route with one optional query
  parameter rather than adding a parallel export endpoint.
- **Filename sanitization**: reused `safe_audio_filename` (`app/storage/filenames.py`) — no second
  sanitizer.
- **Temp-file lifecycle**: reused the stdlib `tempfile` module plus Starlette's `BackgroundTask`
  (already the established pattern in this codebase for "serve, then clean up").
- **Frontend**: extended the existing `DownloadButton` / `downloadAudio` / `AudioResource` — no new
  download endpoint, no new API client, no new page.
- Rejected/unnecessary per the master prompt: FFmpeg, pydub, moviepy, cloud conversion, a custom
  encoder, Redis/Celery, a second sanitizer, a second audio route, a bitrate/quality picker UI.

## 4. Dependency Decision

`soundfile` was added to `backend/pyproject.toml` (`soundfile>=0.14.0`) via `uv add soundfile`.
Resulting lock additions:

| Package | Version | License |
|---|---|---|
| `soundfile` | 0.14.0 | BSD-3-Clause |
| `cffi` | 2.1.1 | MIT |
| `pycparser` | 3.0 | BSD-3-Clause (build-time dependency of cffi) |
| `numpy` | 2.5.3 | BSD-3-Clause |

`soundfile`'s wheel also bundles a prebuilt `libsndfile_x64.dll` (see §18) — it is not a separate
PyPI dependency, but is part of what `pip`/`uv` installs for this package and is the actual component
that performs FLAC decode and MP3/WAV encode.

Why existing dependencies could not do this: Tunora's only other backend dependencies are `fastapi`,
`uvicorn`, and `httpx` — none does audio decoding/encoding. `numpy` and `cffi` are transitive
requirements of `soundfile`, not something Tunora added independently.

## 5. API Design

`GET /api/jobs/{job_id}/audio` (unchanged path) gains one optional query parameter:

- `format` (optional, `Literal["mp3", "wav"]`): when omitted, behaves exactly as before (canonical
  file, `Content-Disposition: inline`). When `mp3` or `wav`, returns an on-demand export
  (`Content-Disposition: attachment`). Any other value is rejected by FastAPI's own `Literal`
  validation with `422` before any code in the route runs.

No new route, no new request/response schema beyond the one query parameter.

## 6. Export Flow

1. `routes_jobs.get_job_audio` receives `format`.
2. If `format` is set, `JobService.resolve_export_audio(job_id, format)`:
   a. Calls `resolve_audio(job_id)` — the existing, unmodified trusted-path resolution. Any of its
      existing errors (`JobNotFoundError`, `AudioNotAvailableError`, `AudioIntegrityError`) propagate
      unchanged.
   b. Calls `app.audio.export.export_audio(source.path, format, title=job.title)`, which reads the
      canonical file with `soundfile.read()` and writes a new temporary file with `soundfile.write()`
      in the target format.
   c. Builds the export's filename via `safe_audio_filename`, from the job's title (falling back to
      the job id) plus `-export.<format>`.
3. The route returns a `FileResponse` over the temporary file, with `background=BackgroundTask` that
   unlinks it after the response is fully sent (success, client disconnect, or any other terminal
   state Starlette reaches after opening the file).
4. Any conversion failure (`ExportError` from `export_audio`) is wrapped as `ExportConversionError`,
   logged with the real reason, and reported to the client as a fixed `500 "Could not create this
   export."` — never the underlying libsndfile message.

## 7. MP3 Configuration

One sensible default, no user-facing bitrate/quality picker: `soundfile`'s own default MP3 encoder
settings (`format="MP3"`, `subtype="MPEG_LAYER_III"`, no `compression_level`/`bitrate_mode` override).
Measured against real ACE-Step generations (§16): roughly 155–170 kbps VBR for 48 kHz stereo material
— a normal "good quality" MP3 bitrate range, achieved without any manual tuning.

## 8. WAV Configuration

16-bit PCM (`subtype="PCM_16"`), at the source's own sample rate and channel count (no resampling, no
channel mixing, no bit-depth/sample-rate selector).

## 9. Metadata Handling

Only a `title` tag is embedded, and only when Tunora actually has one (the job's title). Embedding is
best-effort: if the target container/subtype doesn't support the tag, the write is skipped silently
rather than failing the export. No other metadata (artist, album, cover art, provider details) is
invented or embedded.

## 10. Temporary File Strategy

`tempfile.mkstemp(suffix=f".{format}", prefix="tunora-export-")` creates a real, uniquely-named OS
temp file; the file descriptor is closed immediately (`os.close(fd)`) to avoid Windows file-locking
issues before `soundfile` reopens the path for writing. On any read or encode failure, the temp file
is unlinked (`missing_ok=True`) before re-raising as `ExportError` — no partially-written file is ever
left behind on failure. On success, the route attaches a `BackgroundTask` that deletes the file once
Starlette has fully sent the response. Verified by `test_temporary_export_files_are_removed_after_the_response_is_sent`
(spies on `export_audio`, asserts the path no longer exists immediately after the request completes)
and `test_a_corrupt_or_unreadable_source_fails_cleanly_with_no_leftover_file` (feeds genuinely
undecodable bytes and asserts nothing new appears under the system temp directory).

## 11. Security

- No subprocess/shell execution anywhere in the export path (`soundfile` calls into `libsndfile` via
  `cffi`, in-process).
- No FFmpeg invocation.
- No client-supplied path is ever used: `resolve_export_audio` takes only a job id and a fixed-literal
  format; the source path always comes from the trusted job record via `AudioStorage`.
- Errors never expose the underlying libsndfile message, an absolute path, or a provider detail — the
  client only ever sees a fixed `"Could not create this export."` string; the real reason is logged
  server-side only.
- Malformed/path-traversal job ids (`../../etc/passwd`, `..%2f..%2fetc%2fpasswd`, SQL-injection-shaped
  strings) are rejected the same way for export as for the canonical route (both resolve through the
  same `resolve_audio`/`get` call, which never treats the id as a filesystem path).

## 12. Concurrency

Verified with `asyncio.gather` firing four concurrent requests (`mp3, wav, mp3, wav`) against the same
job: each `tempfile.mkstemp()` call produces a distinct filename (its own random suffix), so there is
no collision and no shared mutable state between requests. All four returned correct, distinct,
valid-format content. No Redis/Celery/queue was needed or added.

## 13. Performance

Measured against a real ACE-Step FLAC Version (see §16 for the full real-GPU results):

| Duration | Source (FLAC) | MP3 export time | MP3 size | WAV export time | WAV size |
|---|---|---|---|---|---|
| 10 s | 990,334 B | 0.123 s | 214,010 B | 0.032 s | 1,920,102 B |
| 60 s | 6,085,291 B | 0.615 s | 1,186,802 B | 0.145 s | 11,520,102 B |
| 180 s | 24,341,151 B | 1.934 s | 3,839,570 B | 0.366 s | 34,560,102 B |

Sub-2-second conversion even at 180 s; no streaming architecture or optimization was needed or added.

## 14. Storage Impact

Canonical storage (`AudioStorage`/`LocalAudioStorage`) is never written to by export: verified by
`test_storage_never_gains_a_permanent_file_from_exporting` (lists the job's storage directory before
and after two exports; identical) and `test_the_canonical_source_file_is_byte_identical_after_exporting`
(SHA-256 of the canonical file unchanged after exporting it to both formats). Temporary export files
live only in the OS temp directory and are removed as described in §10.

## 15. Tests

`backend/tests/test_audio_export.py` — 20 tests:

- `TestExportAudio` (pure `export_audio()` function): WAV is valid PCM16 at the source rate/channels;
  MP3 is valid and close to source duration; a title tag is embedded when the encoder supports it; an
  unsupported format is rejected before any file is touched; a corrupt/unreadable source fails cleanly
  with no leftover temp file.
- `TestExportRoute` (HTTP, via `TestClient`): MP3 export downloads a valid playable file; WAV export
  downloads a valid playable PCM16 file; the canonical download is unaffected by `format` and stays
  inline; an unsupported format is rejected (422) without converting anything; a missing job is 404 for
  both canonical and export; a non-completed job refuses export (409); malformed/path-traversal job ids
  are rejected safely with no leak; a conversion failure is reported as a safe generic 500; exporting
  creates no Version or Job; the canonical source file is byte-identical after exporting; an existing
  (legacy) MP3 Version still downloads unchanged and can itself be exported to WAV; temporary export
  files are removed after the response is sent; storage never gains a permanent file from exporting;
  concurrent mixed-format exports do not collide; filenames are sanitized and use the existing
  extension mapping.

All 20 pass; full backend suite (`pytest tests -m "not smoke"`) is 656 passed, 16 deselected, clean.

## 16. Real GPU / E2E

`backend/tests/test_audio_export_smoke.py`, parametrized over 10 s / 60 s / 180 s real ACE-Step
generations: creates a real job, confirms the stored file is genuinely FLAC, exports to MP3 and WAV,
confirms each is a valid, playable file of the matching format/duration (via `soundfile.info`, not
byte-equality — different formats are not byte-identical), and confirms the canonical file is
unchanged after both exports. All 3 durations passed (results table in §13); full backend smoke suite
(16 real-GPU tests) passed clean afterward, confirming no regression elsewhere.

Playwright E2E (`frontend/e2e/create-song.spec.ts`) gained two tests: a full real flow (generate a
real song, confirm it's playable, export to MP3, export to WAV, download both, verify the canonical
file is untouched) and a mobile/tablet layout check (375px/768px/desktop, no horizontal overflow) for
the format picker. Both pass in Chromium. The full E2E suite (all pre-existing tests plus these two)
was rerun sequentially (never concurrently with the backend GPU suite — see §19) against the real
stack: all tests pass.

## 17. Browser Validation

Chromium: full pass, including both new Export tests and the pre-existing full suite. Firefox: the
main `playwright.config.ts` only configures a `chromium` project, so Firefox is not part of the
configured suite; it was nonetheless attempted best-effort via a temporary, uncommitted Firefox
project. An isolated diagnostic reproduced a genuine, pre-existing headless-Firefox audio-sink
limitation (`OnMediaSinkAudioError`) on the unmodified canonical playback path, with zero export
interaction involved — confirming it is not a Phase 21 regression, but an environment limitation
outside this phase's control. Safari was not tested: Phase 19 already established that real Safari
validation requires an Apple device, and Phase 21's master prompt explicitly does not require it.

## 18. License Verification

- **`soundfile`** 0.14.0: BSD-3-Clause (confirmed from its own `dist-info/METADATA`).
- **`libsndfile`** 1.2.2 (bundled as `_soundfile_data/libsndfile_x64.dll`, loaded via `cffi` at
  runtime — a separate shared library file, not statically linked into Tunora's own code): LGPL-2.1.
  Because it ships as an independent, dynamically-loaded `.dll` rather than being compiled into
  Tunora's or `soundfile`'s own binary, it satisfies LGPL's relinking requirement by construction —
  an end user (or Tunora) can swap that DLL for another LGPL-compliant build without touching any of
  Tunora's own source.
- **MP3 decode/encode implementation inside that DLL**: Phase 20 had left this unresolved. Binary
  string extraction from the actual bundled `libsndfile_x64.dll` in this environment confirms it
  embeds **LAME** (MP3 encoder) and **mpg123** (MP3 decoder) — both LGPL-2.1 as libraries (mpg123's
  command-line program is GPL, but the library component libsndfile links against is LGPL). Same
  reasoning applies: both are inside the same independent, dynamically-loaded DLL, not statically
  compiled into Tunora's own code.
- **WAV path**: PCM is not itself subject to any codec license; it goes through the same
  BSD/LGPL `soundfile`/`libsndfile` stack as MP3.
- No unresolved licensing question remains for this dependency.

## 19. Known Limitations

- Exports are not byte-identical across formats (expected — MP3 is lossy, and even WAV differs from
  FLAC only in container/bit-depth, not content, at 16-bit PCM).
- No persistent export cache: repeat requests for the same job/format re-convert every time (explicit
  Phase 21 non-goal — see §20 and the master prompt's caching guidance).
- Range requests are not supported for exports (only for the canonical file, via `FileResponse`'s
  built-in support) — an export's `Content-Length` is accurate, but a client requesting a byte range of
  an export gets the whole file; this was not advertised as supported for exports, matching what the
  architecture actually provides.
- Operational lesson (unrelated to the shipped feature but recorded because it happened during this
  phase): running the backend's real-GPU test suite concurrently with the Playwright E2E suite against
  the same live ACE-Step instance caused a real CUDA `device-side assert` inside ACE-Step's own code.
  Both suites must be run sequentially against one ACE-Step instance, never concurrently.
- The pre-existing Phase 19 Vitest timing race (`version-actions.test.tsx`, "selects the new version,
  moves Latest and re-enables actions once the job completes") is still present, unrelated to Phase 21
  (confirmed: passes when rerun alone in 2 of 3 attempts, a real-timer poll race, not a Phase 21
  regression). It was not touched, per the master prompt's explicit instruction not to fix it unless
  Phase 21 caused it.

## 20. Explicit Non-Goals (confirmed not implemented)

Canonical MP3/WAV storage; migrating any existing audio between formats; converting an existing MP3
Version to FLAC or vice versa; mastering/loudness normalization/audio effects; bitrate, sample-rate or
bit-depth editors; trimming/fade/crop; batch export; scheduled export; cloud export; persistent export
caching; music publishing/distribution integration.

## 21. Files Changed

**Backend**
- `backend/pyproject.toml`, `backend/uv.lock` — added `soundfile`.
- `backend/app/audio/__init__.py` (new)
- `backend/app/audio/export.py` (new) — `export_audio()`, `ExportError`, `ExportedAudio`,
  `SUPPORTED_EXPORT_FORMATS`.
- `backend/app/jobs/errors.py` — added `ExportConversionError`.
- `backend/app/jobs/service.py` — added `ExportedAudioResource`, `resolve_export_audio()`.
- `backend/app/api/routes_jobs.py` — `get_job_audio` accepts `format`; `_cleanup_export` helper.
- `backend/tests/test_audio_export.py` (new, 20 tests)
- `backend/tests/test_audio_export_smoke.py` (new, real-GPU smoke test)

**Frontend**
- `frontend/src/lib/audio/download-audio.ts` — `ExportFormat`, `downloadAudio(resource, format?)`.
- `frontend/src/lib/audio/format-bytes.ts` — `formatLabel()`.
- `frontend/src/components/audio/download-button.tsx` — format `<select>` picker.
- `frontend/src/lib/audio/download-audio.test.ts`, `frontend/src/lib/audio/format-bytes.test.ts`,
  `frontend/src/components/audio/download-button.test.tsx` — extended with Phase 21 coverage.
- `frontend/e2e/create-song.spec.ts` — two new tests (real export flow; mobile/tablet layout).
- `frontend/tsconfig.json` — added the throwaway E2E dist dir's generated-types paths (from
  `next typegen`, needed to run this phase's E2E build under its own dist dir).

**Docs**
- `docs/PHASE-21-IMPLEMENTATION.md` (this file).

## Final Git State

See the final report for the commit hash, branch verification, and push confirmation.
