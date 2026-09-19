# Tunora — Phase 3, Step 18: Saved Location — Reuse Audit

Question: after a song is generated and stored, how does Tunora tell the user "it is saved" and let them retrieve a copy, without exposing where the backend keeps it, without a second audio path, and without a new dependency unless one is genuinely needed?

Versions and licenses below were read with `npm view` or from the installed packages on 2026-09-19; entries marked "platform" are web standards or the browser, not packages.

| # | Candidate | Source | License | Version | What it provides | Does Tunora need it? | Decision | Reason |
|---|---|---|---|---|---|---|---|---|
| 1 | HTML `<a download>` attribute | WHATWG HTML standard | platform | n/a | Tells the browser to save a URL as a file under a given name | Yes | **REUSE** | It is the native "save file" mechanism; the name comes from the trusted backend filename. |
| 2 | `fetch` + `Blob` + `URL.createObjectURL` | Fetch / File API standards | platform | n/a | Lets script check the server's answer (status, content type, size) before handing bytes to the browser | Yes | **REUSE** | A bare link cannot report 404/409/500 or a network failure, and the step requires those messages and no false "download succeeded". |
| 3 | Starlette `FileResponse(content_disposition_type="attachment")` | Starlette (bundled with FastAPI) | BSD-3-Clause | 1.6.0 (installed) | Server-side `Content-Disposition: attachment` | Not now | **REJECT (available)** | Already used for inline playback. With (1)+(2) the browser names the file itself, so the server does not need a second disposition mode, a query parameter, or a `/download` endpoint. It stays available if a plain shareable download link is ever wanted. |
| 4 | `file-saver` | github.com/eligrey/FileSaver.js (npm) | MIT | 2.0.5 | Wraps the same blob + anchor technique for old browsers | No | **REJECT** | Adds a dependency for about ten lines of standard code; the supported browsers do not need its fallbacks. |
| 5 | `js-file-download` | npm | MIT | 0.4.12 | Same technique | No | **REJECT** | Same reason. |
| 6 | `downloadjs` | npm | MIT | 1.4.7 | Same technique | No | **REJECT** | Same reason. |
| 7 | Next.js download support | Next.js 16.3.5 (installed) | MIT | 16.3.5 | Nothing download-specific (a route handler could proxy a file) | No | **REJECT** | The existing `/api/*` rewrite already reaches the trusted FastAPI route; a Next route handler would only add a hop. |
| 8 | shadcn/ui `Button` | shadcn-ui/ui (already in repo) | MIT | n/a (copy-in) | Accessible button with disabled/busy styling | Yes | **REUSE** | Existing primitive; no new component library. |
| 9 | `lucide-react` `DownloadIcon`, `CheckIcon`, `Loader2Icon` | lucide.dev (already installed) | ISC | 1.47.0 | Icons | Yes | **REUSE** | Confirmed the icons exist in the installed version; no new icon package. |
| 10 | Existing backend contract: `AudioResource`, `audio.filename`, `GET /api/jobs/{id}/audio` | Steps 13/16 | project | n/a | Trusted lookup by job id, ownership check, `audio/*` type, Length, ETag, Range, `nosniff`, inline disposition | Yes | **REUSE** | Download uses this same route; nothing about it is weakened. |
| 11 | Filename sanitizing | Python stdlib (`os.path`, `re`) | PSF | 3.12 | Building blocks only; no library returns a header-safe audio filename | Yes | **BUILD (small)** | One 40-line function at the backend boundary (`app/storage/filenames.py`) because the stored name is read back from a database record and now reaches an HTTP header and the public API. |
| 12 | Vitest 5.0.1, Testing Library (react 16.3.3, user-event 14.6.7), Playwright 1.63.0 | already installed | MIT / MIT / Apache-2.0 | as listed | Unit, component and browser tests; Playwright has a `download` event that exposes the saved file | Yes | **REUSE** | Existing infrastructure covers everything, including observing a real browser download. |

## Existing contracts inspected (before changing anything)

- `backend/app/api/routes_jobs.py::get_job_audio` — returns `FileResponse(..., filename=audio.filename, content_disposition_type="inline")`, so the stored filename already reached a header (through Starlette's quoting) unsanitized beyond that.
- `backend/app/jobs/service.py::resolve_audio` and `AudioResource` — the single place a filename enters the audio route.
- `backend/app/api/schemas.py::_public_result` — allowlisted public result including `audio.filename`, `key`, `media_type`, `size_bytes`, `audio_url`.
- `AudioStorage` / `LocalAudioStorage` — unchanged; the stored file is `<job-id>/<job-id>.<ext>`.
- Frontend: `getAudioResource`, `isTunoraAudioUrl`, `JobTracker`, `AudioPlayer`, the shadcn `Button`, lucide icons, Vitest and Playwright setups.

## Answer to "did we add anything unnecessarily?"

No new npm or Python dependency was added. No second audio endpoint and no new query parameter were added. The only new backend code is the filename sanitizer (row 11), which has no off-the-shelf equivalent worth a dependency.
