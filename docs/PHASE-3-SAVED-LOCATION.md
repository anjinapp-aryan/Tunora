# Tunora — Phase 3, Step 18: Saved Location

## 1. Objective

When a job is COMPLETED and its audio is stored, tell the user plainly that the audio is saved, and give them a safe way to download a copy:

    Generation complete → Audio saved → Download

No Library, Projects, versioning, file management, authentication, cloud storage or `AudioStorage` redesign.

## 2. Reuse Audit Summary

Full table in [PHASE-3-SAVED-LOCATION-REUSE-AUDIT.md](./PHASE-3-SAVED-LOCATION-REUSE-AUDIT.md). Outcome: reuse the browser's own `<a download>` plus `fetch`/`Blob`, the existing trusted audio route, shadcn `Button`, lucide icons and the existing test tooling; reject `file-saver`, `js-file-download`, `downloadjs` and a server-side attachment mode; build one small backend function for filename sanitizing. No dependency was added.

## 3. Existing Contracts Inspected

Before editing, I read the audio route, `resolve_audio`/`AudioResource`, `_public_result`, `AudioStorage`/`LocalAudioStorage`, and the frontend `getAudioResource`, `isTunoraAudioUrl`, `JobTracker`, `AudioPlayer`, and the installed shadcn/lucide/test tooling. Findings that shaped the design: the route already serves the right bytes with Range, ETag and `nosniff`; `audio.filename` was already part of the public contract; and that filename was passed to the response header straight from the database record.

## 4. Saved-Location UX Decision

The user-facing idea is "Saved in Tunora", never a path. When `status === COMPLETED` **and** a valid audio resource exists, the job page shows, inside the existing live region:

- "Your song is ready."
- "✓ Audio saved in Tunora"

then the existing audio player, then a **Download MP3** button showing the size, for example "Download MP3 (2.7 MB)". The button label follows the media type (MP3/WAV/FLAC/OGG/Opus/AAC, otherwise "Download audio"). Nothing renders a filesystem path, storage root, storage key or backend URL. For CREATED, SUBMITTED, QUEUED, RUNNING, FAILED, and for a COMPLETED job without a valid audio resource, none of the saved notice, player or download control is shown (FAILED keeps Step 15's generic failure; `Job.error` is never displayed).

Honest scope of "Audio saved": it is shown because the backend reports COMPLETED with a stored audio record. The UI does not independently re-check that the file still exists when rendering; a missing file is discovered when the player loads or the user downloads (see §10 and §12).

## 5. Download Architecture

Question posed by the step: can `GET /api/jobs/{job_id}/audio` serve both inline playback and a download without breaking Step 17? Answer: **yes, with no server change to the route's behavior.** The browser decides "save" versus "play", not the server:

1. Click Download → `fetch("/api/jobs/<id>/audio", {cache: "no-store"})` — the same route the player uses (only after `isTunoraAudioUrl` accepts the URL).
2. If the server does not answer 200 with a non-empty `audio/*` body, show a fixed message and save nothing.
3. Otherwise wrap the bytes in a `Blob`, create an object URL, click a temporary `<a download="<filename>">`, remove it, and revoke the URL after 10 s.

Decision: no `/download` endpoint, no `?download=1` parameter, no `attachment` mode. The route still answers `Content-Disposition: inline`. Trade-offs: the file passes through browser memory as a Blob (fine for the 30 s–3 min clips, about 0.5–3 MB); a copied link opens inline rather than forcing a save; and "Download started." means the browser was handed the file, not that it finished writing it (a page cannot know).

## 6. Filename Strategy

One filename contract, owned by the backend. `audio.filename` (stored as `<job-id>.<ext>`) is now sanitized at the boundary by `safe_audio_filename` (`backend/app/storage/filenames.py`), which is used in exactly two places: `JobService.resolve_audio` (so the `Content-Disposition` header) and `_public_result` (so the public API). Both therefore always agree. Guarantees: only the basename survives (both `/` and `\` are separators); only `[A-Za-z0-9._-]`; `..` sequences collapsed; no control characters or CR/LF; length-limited; an allowed audio extension (`mp3, wav, flac, ogg, opus, aac`, else derived from the media type); deterministic fallback `tunora-<job-id>.<ext>` when nothing usable remains. The frontend does not build a name: `safeDownloadName` only accepts the backend value if it matches a strict pattern and otherwise falls back to `tunora-<job-id>` (a defensive, contract-violation path). The real download's suggested filename was `<job-id>.mp3`.

Not handled: Windows reserved device names (for example `con.mp3`) — not reachable because names are Tunora-generated, but not blocked either. The filename is job-id based, not song-title based, because there is no title concept yet.

## 7. Security Model

Unchanged and re-verified: the server chooses the file from the trusted job record; ownership check (`<job-id>/` prefix); `audio/*` media-type check; storage-root containment; generic 500 for integrity problems; query parameters ignored. New in this step: (a) the filename in the header and API is sanitized (a tampered record containing `../`, backslashes, CR, LF, quotes, drive letters, non-ASCII or 400 characters cannot inject a header or path); (b) the frontend refuses to fetch or save from any URL that is not exactly `/api/jobs/<id>/audio`; (c) the download error messages are fixed text.

## 8. API Changes

**None to routes, parameters or response shape.** Behavior change: `audio.filename` in the public JSON, and the filename in `Content-Disposition`, are now sanitized values. For normal Tunora files (`<uuid-id>.mp3`) they are byte-for-byte the same as before.

## 9. Frontend Changes

- `src/lib/audio/download-audio.ts`: `downloadAudio(resource)`, `saveBlob`, `DownloadError` and the fixed messages (404 "Audio is no longer available.", 409 "Audio is not ready yet.", 500/other "Audio is temporarily unavailable.", network "Download failed. Please try again.").
- `src/components/audio/download-button.tsx`: button with loading/disabled/`aria-busy` state, a duplicate-click guard, "Download started." (`role="status"`) only after the save was handed to the browser, and error text (`role="alert"`).
- `src/lib/audio/format-bytes.ts`: size text and the format label.
- `src/lib/api/jobs.ts`: `safeDownloadName`, used by `getAudioResource`.
- `src/components/job/job-tracker.tsx`: the saved notice and the download control, only for COMPLETED with a valid resource.

An accessibility bug was found by a unit test: the button's accessible name was "Download MP3(157 KB)" because no whitespace separated the label from the size; fixed with an explicit space.

## 10. Test Results

- **Backend: 175 passed** (up from 137). New: 25 `safe_audio_filename` tests and 13 route tests: a tampered stored filename (`../../x`, `..\..\x`, CR, LF, CRLF header injection, quote injection, drive letter, absolute path, non-ASCII, 400 characters) always yields a header matching `inline; filename="[A-Za-z0-9…].mp3"` and a public filename equal to it, with unchanged bytes; Range 206/`Content-Range`/`Content-Length`/ETag/`nosniff` unchanged with a hostile filename; `?filename=`, `?name=`, `?download=1`, `?disposition=attachment` and a CRLF query cannot change the filename or disposition; download uses the same route and identical bytes and length. The Step 16 traversal, absolute-path, cross-job, missing-artifact and state tests all still pass. Mutation check: replacing the sanitizer's return with the raw name made the new tests fail; restored.
- **Frontend: 183 passed** (up from 131): `downloadAudio` (success path, object-URL release, 404/409/500/503/400, network failure, body failure, empty or non-audio body on HTTP 200, seven unsafe URLs never fetched), `DownloadButton` (accessible name with size, formats, loading state and duplicate prevention, each error message with no leak and no false success, retry), `safeDownloadName`, `formatBytes`, and `JobTracker` (saved notice and download only for COMPLETED with a valid resource; absent for CREATED, SUBMITTED, QUEUED, RUNNING, FAILED, no resource and a foreign URL; no path or provider text rendered). The Step 17 player tests and Step 15 polling tests pass unchanged. Mutation check: bypassing the URL check made seven tests fail; restored.
- `tsc` clean, ESLint clean, `next build` succeeds.
- Real-GPU smoke tests: 3/3 pass.

## 11. Real E2E Results

Playwright against the real stack (Next dev → FastAPI → ACE-Step, real generation): **4/4 passed**, main test about 51 s. It created a short instrumental song, tracked it with a mid-run reload, and at COMPLETED saw the player and "Audio saved in Tunora" and an enabled "Download MP3". Clicking Download produced a real browser download:

- suggested filename `tunora-<uuid>.mp3` (equal to the backend `audio.filename`, matching the safe pattern);
- content type from the route `audio/mpeg`; size non-zero and equal to `audio.size_bytes` and to `Content-Length`;
- the downloaded bytes were **identical** to the bytes served by the route **and** to the file on the backend's disk (the test read the storage directory);
- the download used the same route: exactly two plain GETs in total (player + download), no Range, no other URL;
- "Download started." appeared only after the browser handed over the file;
- playback still worked afterwards (`currentTime` advanced after Play);
- the Step 17 Range suite still passed against both the FastAPI origin and the Next proxy (`bytes=0-99` returned 206 with the right `Content-Range`, `Content-Length` and bytes, plus mid-file, open-ended, suffix and 416 cases);
- polling stopped after completion;
- no path, `/v1/audio`, port 8001, task id or drive letter in the rendered UI, page source or job payload;
- 768 px and 375 px: no horizontal overflow, and the Play button, sliders, time, waveform, saved notice and Download button are all inside the viewport (desktop, 768 px and 375 px screenshots reviewed by eye);
- a **real error path**: the test deleted the stored file, clicked Download, and the UI showed "Audio is temporarily unavailable." (a real HTTP 500), no "Download started.", no path, and the player still displayed.

Not verified: a real 404/409 from the server in the browser (unit-tested only), non-Chromium browsers, and whether the saved file ends up in the user's download folder (Playwright observes the browser's download, not the OS).

## 12. Known Limitations

- "Audio saved" reflects the backend record, not a live file check; if the file is later removed, the notice stays until a play or download attempt fails (the real error test shows the safe message, but the notice remains).
- The download goes through browser memory; very large files would be heavier. Not measured.
- The route still serves inline, so a shared/copied link plays rather than downloads.
- The client logs failures with `console.error` for debugging (visible in the dev-server log); that is not shown to users.
- The public API still returns `audio.key` (`<job-id>/<filename>`, no path) from Step 16; the UI never shows it. Removing it would change the earlier contract and was not done here.
- Filenames are job-id based, not song titles; Windows reserved names are not specially handled.
- Chromium only; no axe or screen-reader run (the accessible names, roles and live regions were verified with Testing Library and in the browser's accessibility roles).

## 13. What Was NOT Implemented

The Song Library, Projects, versioning, file management, search, filters, pagination, playlists, favorites, authentication, cloud or S3/MinIO storage, a new audio endpoint, a background cleanup system, database migrations, and Step 19.
