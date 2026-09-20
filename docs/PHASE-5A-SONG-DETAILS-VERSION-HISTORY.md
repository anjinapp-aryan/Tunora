# Phase 5A — Song Details, Version History, Song-oriented Library

Exposes the Phase 4 Song → Version → Audio domain in the UI. The Library now shows one row per **Song** (not per job or version); a new Song page lists versions newest-first and lets the user select one to play and download. No regenerate/extend/remix UI, Projects, or other new product features.

```
Library (one row per Song)
   |  Open Song
   v
Song Details  /songs/{songId}
   |  select a Version (client-side only)
   v
Version --> existing AudioPlayer (WaveSurfer) + existing DownloadButton
              |
              v   GET /api/jobs/{job_id}/audio   (unchanged route)
```

## 1. Reuse audit

Versions/licenses from `npm view` and the installed packages, 2026-09-20.

| Need | Candidates | Decision |
|---|---|---|
| Version selection / tabs | `@radix-ui/react-tabs` 1.1.21 (MIT), `@headlessui/react` 2.2.10 (MIT), `react-aria-components` 1.21.1 (Apache-2.0), `@base-ui/react` 1.8.0 (MIT, already installed via shadcn, no Tabs/Radio component generated) | **REJECT new dependencies; REUSE the platform.** A native `<fieldset>` + `<input type="radio">` gives keyboard arrows, a checked state exposed to assistive tech and a group label for free. Tabs would mislead (panels are not separate documents). |
| Collapsible details / accordion | `@radix-ui/react-accordion` 1.2.20 (MIT) | **REUSE native `<details>`** (already used for Advanced options and Job ID). |
| Grouped Library list | any list/tree library | **BUILD (SQL)**: grouping is a database concern; the UI just renders rows. |
| Breadcrumb / back navigation | shadcn breadcrumb | **REUSE** a plain `Link` styled with the existing `buttonVariants`. |
| Date formatting | date-fns, dayjs | **REUSE `Date.toLocaleDateString`** (already used); extracted to `lib/format-date.ts` so two components share it. |
| Data fetching | TanStack Query, SWR | **REUSE the project pattern** (abortable `useEffect` + a typed client), consistent with the Library and job tracking. |
| Audio player / waveform / download | any | **REUSE unchanged**: `AudioPlayer`, `DownloadButton`, `formatTime`, `safeDownloadName`. No second player, waveform or download endpoint. |
| Empty/error states | — | **REUSE** existing patterns and copy. |

No dependency was added.

## 2. Library domain change

The Library's primary entity is the Song. `GET /api/songs` returns songs that have at least one **playable** version (audio attached). `version_count` counts playable versions; the "latest" shown is the highest playable `version_number`. A song whose only takes failed is not listed (as failed jobs were not before), but its Song Details still resolve. `GET /api/jobs` is unchanged (still one row per job); the UI no longer uses it for the Library.

## 3. Song Details architecture

Route **`/songs/{songId}`** (the existing `/create`, `/library`, `/jobs/{jobId}` are untouched; the job page still works). `SongDetailsView` loads one `GET /api/songs/{id}` (song + all versions), shows the title, an active-version panel, and the version list. The active version defaults to the newest version that has audio (falling back to the newest). "Latest" always means the highest `version_number` overall, which can be a failed take; in that case the default selection is the newest playable one and the failed latest is marked "Audio unavailable".

## 4. API design

- `GET /api/songs?q=&sort=newest|oldest|title&limit=` → `{items: [{id, title, version_count, latest_version:{version_number, duration, created_at}, created_at, updated_at}]}`. `q` ≤ 100 chars, `limit` 1–200; other values → 422.
- `GET /api/songs/{song_id}` → `{id, title, created_at, updated_at, versions:[{id, version_number, is_latest, status, created_at, duration, audio:{filename, media_type, size_bytes, audio_url}|null, prompt, lyrics, language, instrumental, seed}]}`, newest version first. One response instead of a separate versions endpoint (fewer endpoints, one query, no N+1).
- `audio_url` is `/api/jobs/{job_id}/audio` built by the backend from the version's own job; the response never contains the storage key, absolute path, provider name or task id. Built field by field (allowlist).
- No new database tables or migrations: two new repository read methods, both over existing tables.

## 5. Version selection

A radio group. Selecting a version only changes React state: the active panel re-renders and the player/download components receive that version's URL. Tests assert no request of any kind is made on selection (no POST, no job, no song reload) and the backend test proves reading songs/versions/audio leaves row counts and version rows byte-identical.

## 6. Audio player integration

`<AudioPlayer key={version.id} src=...>`: changing the key unmounts the old WaveSurfer instance (destroyed; fetch aborted) and creates a new one at position 0 for the selected version, so there is exactly one instance and one audio download per selected version. Existing loading/error handling is unchanged. A version with no audio shows "Audio is temporarily unavailable." and no player.

## 7. Download behavior

`<DownloadButton key=... resource=...>` is given the selected version's resource, so it fetches that version's `audio_url` and saves it under that version's backend-sanitized filename (`safeDownloadName` fallback). Same route as playback; no second endpoint. Verified in unit tests (the fetch URL and saved name switch with the selection) and in the real E2E (bytes equal each version's own stored file).

## 8. Search behavior

Case-insensitive substring match on the song title **or any of its versions' prompts** (the existing "title or description" behavior), so a song matches once regardless of how many versions match. The search text is bound as data with `LIKE ... ESCAPE '!'` (`%`, `_` and `!` are escaped), tested with `%`, `_`, quotes, backslash and a UNION injection string.

## 9. Sorting behavior

`newest`/`oldest` order by the **latest playable version's `created_at`** (a Song's most recent activity), `title` is A–Z. Consequence, chosen deliberately and tested: generating a new version moves the song to the top of "newest first", which matches "what I worked on last". It differs from the old job-based order only by grouping. Song `created_at` is displayed separately. The ORDER BY comes from a fixed whitelist, never user text.

## 10. Security

Song ids are validated at the route (`^[A-Za-z0-9][A-Za-z0-9-]*$`, ≤ 80) and the service; malformed → 422, unknown → 404 (the UI shows the same safe "Song not found" for both). Tested: `'`, spaces, dots, leading `-`, 81 chars, encoded backslash/drive letter/injection/CRLF, encoded `../` traversal, SQL injection in `q`, bad `sort`/`limit`. Versions are loaded by the song's own id (`WHERE v.song_id = ?`), so a version can never be returned under another song; a test creates two songs and asserts disjoint version ids and audio URLs. There is no version-by-id route, so a fake version id has nothing to reach; job audio stays bound to its own job whatever `song_id`/`version_id` a request names. Responses were scanned for paths, provider strings, storage keys, error text and ports (real-run response included). The Library issues a constant number of SELECTs (asserted ≤ 2 for 30 songs).

## 11. Accessibility

Native radio group in a labelled `fieldset`/`legend` ("Versions"); arrow keys move the selection (tested); the active version has a checked state, a border, and the text "(selected)", plus a "Latest" text badge, so nothing depends on colour. The "Open Song" link's accessible name includes the title ("Open song: I Will Rise"). A unit test found a real bug: the radio's accessible name ran words together ("Version 1Latest…") because adjacent spans had no whitespace; fixed. Player and download keep their existing accessibility. Not verified: screen-reader output, axe.

## 12. Responsive behavior

One layout. Real-browser checks at 375, 768 and desktop for the Song page (Play/Pause, download, sliders, time, waveform, version list, title all visible and inside the viewport, no horizontal overflow) and at 375 for the Library row; long titles use `overflow-wrap:anywhere`. Screenshots at desktop (Song page) and 375 px (Library) were reviewed by eye.

## 13. Test evidence (executed this session)

| Check | Result |
|---|---|
| Backend `pytest -m "not smoke"` | **VERIFIED** 283 passed (was 266; +17 song API/repository tests) |
| Real-GPU smoke (`-m smoke`) | **VERIFIED** 4 passed (including the Phase 4 two-version test, re-run) |
| Frontend Vitest / tsc / ESLint / build | **VERIFIED** 231 passed (was 200) / clean / clean / `/songs/[songId]` builds |
| Real E2E (Next → FastAPI → ACE-Step → RTX 5060 Ti) | **VERIFIED** 7/7, four real generations per run (three songs) |
| Real two-version scenario | **VERIFIED**: titled "I Will Rise" via the UI (Version 1), Version 2 generated for the same song; the Library shows ONE row "2 versions / Latest: Version 2" with no per-job links; Song page lists Version 2 (Latest) then Version 1, Version 2 selected by default; each version's waveform, play, pause, both seeks and download were exercised; switching to Version 1 made the player `data-audio-url` and the saved file Version 1's, back to Version 2 likewise; player duration matches the API duration within 2 s; jobs count unchanged by selecting versions; Version 1's file hash and bytes identical before and after Version 2 and after all selections |
| Mutation checks | (1) ignoring the selected version in `SongDetailsView` → the E2E failed at the Version 1 selection; (2) hard-coding `version_count` to 1 → the E2E failed at "2 versions". Both reverted. Also: counting failed versions and reversing the newest sort each failed a backend test |
| Existing E2E (create/generate/play/seek/Range/download/missing-audio/Library) | **VERIFIED** unchanged and passing; the Library steps now go through the Song page |

Existing tests changed for intentional contract changes only: the Library unit tests (rows are songs, no per-row download), the E2E's Library section (opens `/songs/{id}`), and `listSongs` (job-based) removed from `jobs.ts` with its tests replaced by `songs.ts` equivalents.

## 14. Known limitations

- **Title authority:** `Song.title` is what the Library and Song page display. The job page and job API still show `Job.title` (a snapshot from creation); they only diverge once a rename exists (none yet). Not refactored, per scope.
- No UI to create a new version (the API accepts `song_id`; the E2E uses it). Failed/in-progress takes appear only on the Song page.
- The Library shows only songs with a playable version.
- Selection is not in the URL (no `?version=` deep link).
- Song search/sort loads through SQL `LIKE` and a whole-table aggregate per request; fine at local scale, not indexed for full-text.
- A version whose file was deleted after completion is listed as playable; the safe error appears when its audio is read (unchanged behavior).
- E2E accumulates songs in its throwaway database across runs (rows are pinned by song id, so this does not affect results).
- Chromium only; no axe/screen-reader run.
- An old `next dev` (port 3000) and backend (port 8000) from before this session cannot be stopped from this shell; E2E ran on ports 3100/8010.

## 15. Deferred

Regenerate/Extend/Remix/Repaint, rename/delete, Projects, AI Song Director, multi-provider UI, stems, video, sharing, authentication (all later phases).
