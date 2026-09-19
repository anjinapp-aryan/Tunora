# Milestone 1 — Create Song polish, song titles, and the Song Library

Builds on the validated Steps 1–18 flow (Create → Generate → Track → Save → Play → Download). Nothing in that flow was replaced; every earlier test still passes.

## Why this order

The prompt lists UX polish, a song title, and a Library as the next capabilities. The Library needs a human-readable title to be usable (a list of job ids is not a library), and the polish items are small and independent, so they were done together as one stable milestone. Versions, Projects, Extend/Remix/Repaint, the AI Song Director, more providers and video were **not** started: each depends on a real Song/Version domain, which this milestone deliberately does not introduce (see "Deferred and debt").

## Reuse audit

| Need | Candidates | Decision |
|---|---|---|
| Toast for "Download started." | `sonner` 2.0.8 (MIT, shadcn's toast) vs. an auto-clearing inline status | **BUILD (tiny)**: one status message that clears after 4 s (`role="status"`, so it is still announced). A toast library would add a dependency and a global provider for one message; revisit if more notifications appear. |
| "Advanced options" disclosure | native `<details>/<summary>` vs. a Radix/Base UI accordion | **REUSE platform**: built-in keyboard and screen-reader behavior, no dependency. It is forced open when a field inside it has a validation error. |
| Vocal / Instrumental control | native radio group in a `<fieldset><legend>` vs. shadcn RadioGroup | **REUSE platform**: accessible by default; shadcn's RadioGroup is not installed and would be a new component for two options. |
| "Job ID" as secondary information | same `<details>` | **REUSE platform**: "Details" section, collapsed. |
| Title generation | LLM, library, simple rule | **BUILD (simple, deterministic)**: user-supplied title, else the first six words of the prompt, else "Untitled song". No LLM, as the prompt required. |
| Library search / sort | SQLite FTS5, a search library, plain filtering | **BUILD (simple)**: case-insensitive substring match on title and prompt, and three sort orders, done in `JobService.search` over the newest 500 jobs. FTS5 or an index is not justified at local single-user scale. |
| Library list UI | existing shadcn primitives | **REUSE**: `Input`, `NativeSelect`, `DownloadButton`, the existing `getAudioResource`, `formatTime` and links to the existing job page. No second player and no second storage path. |

No dependency was added. Licenses touched: none new.

## What changed

**Backend**
- `app/jobs/titles.py`: `clean_title` (strips control characters, collapses whitespace, caps at 80) and `derive_title`.
- `Job.title`; the SQLite table gets a `title` column through an **additive migration** (`ALTER TABLE … ADD COLUMN` when missing, so existing databases keep working; tested with a pre-title database). Jobs without a stored title get a derived one at response time.
- `CreateJobRequest.title` (optional) and `JobResponse.title` (always present).
- `GET /api/jobs` gained `status`, `q` (max 100 characters), `sort` (`newest|oldest|title`, validated) and a bounded `limit`. Invalid values return 422 and never reach the filesystem.

**Frontend**
- Create Song: **Vocals** is now a Vocal/Instrumental radio group; the optional **Song title** and **Seed** moved under **Advanced options**. No voice-identity controls were added because the backend does not support them (tested).
- Job page: the song title is shown; the technical Job ID moved into a collapsed **Details** section.
- "Download started." disappears after 4 seconds.
- New **Library** page (`/library`) and a header nav (Create / Library): completed songs with title, date, duration, a link to the song page, and a Download button; search (debounced 300 ms), sort, empty, no-match, loading and error-with-retry states.
- Tooling: `E2E_PORT`, `E2E_BACKEND_PORT`, `E2E_DIST_DIR` let the E2E run beside another dev server (`next.config.ts` reads `NEXT_DIST_DIR`); ESLint ignores `.next-*` build folders.

## Verification (run in this session)

| Check | Result |
|---|---|
| Backend unit/integration (`pytest -m "not smoke"`) | **VERIFIED** 190 passed (was 175): titles, title persistence and old-database migration, library filter/sort/search/validation, no path or provider leak in the list |
| Real-GPU smoke tests | **VERIFIED** 3 passed |
| Frontend (Vitest) | **VERIFIED** 200 passed (was 183) |
| TypeScript / ESLint / production build | **VERIFIED** clean; `/library` is in the build |
| Real E2E (Next → FastAPI → ACE-Step → RTX 5060 Ti) | **VERIFIED** 4/4: create with the new form (Instrumental radio), derived title shown and the job id absent from the heading, playback/seek/waveform, Range through the proxy, download bytes equal to the stored file, "Download started." disappears, a real 500 on a deleted file, then the Library lists the song, search filters it, no technical id is shown, 375 px has no overflow, and opening it shows the player |
| Screenshots reviewed by eye | Create (desktop) and Library (375 px) |

Existing test changes (intentional contract changes only): the exact-key assertion on the job JSON now includes `title`; the E2E and form tests use the radio instead of the switch; the job-page tests look for the Job ID inside Details.

## Known limitations and technical debt

- **A "song" is still a job.** Library rows link to `/jobs/<id>`, and the title lives on the job. Versions and Projects need a separate Song entity (Song → Version → Audio, as in the architecture principles); introducing it now would be speculative. Expect an id/URL migration then.
- Library search loads the newest 500 jobs and filters in memory. Fine locally; not an indexed search.
- Failed and in-progress jobs are not listed (the Library shows completed songs only); there is no delete or rename.
- Titles are not used in filenames (still job-id based).
- Durations shown are the provider-reported values.
- In the E2E, the final Library → song-page step opens a job whose file the test had deleted earlier, so it proves navigation and the safe player state, not playback from the Library.
- Two long-lived local processes (a `next dev` on port 3000 and a backend on 8000, apparently from outside this session) could not be stopped from here (access denied), so the E2E ran on separate ports. The 8000 backend runs the older code.
- Playwright and unit tests cover Chromium only; no axe or screen-reader run.

## Next recommended work (evidence-based)

1. **Song entity** (Song → Version → Audio) with a migration from existing jobs — the prerequisite for Versions, Projects and any Regenerate/Extend/Remix/Repaint.
2. Song Details page built on that entity (prompt, lyrics, language, duration, versions), reusing `AudioPlayer`.
3. Validate ACE-Step's supported task types (cover/repaint/extend) with real runs before exposing any UI for them.
