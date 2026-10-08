# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What Tunora is

Free, open-source-first, self-hostable AI Music Studio: describe a song (optionally lyrics/language/duration), generate it with a local open-source model, play it in the browser with a waveform, download it, browse it in a Library, iterate on it, and turn a Version into a lyric music video. Suno/Udio are UX benchmarks only; no proprietary code, models, weights, datasets or branding may be used.

Repo layout: `backend/` (FastAPI), `frontend/` (Next.js), `docs/` (decisions and per-phase write-ups), `ACE-Step-1.5/` (git **submodule**: the upstream model server, treated as an external dependency; never add Tunora code there and never commit its local/untracked files), `start-tunora.ps1`/`stop-tunora.ps1`/`restart-tunora.ps1`/`tunora-services.ps1` (service management, see `docs/TUNORA-SERVICE-MANAGEMENT.md`).

State (through Phase 28): Create → Generate → Track → Save → Play/Seek → Download (FLAC canonical, MP3/WAV on-demand export) → Song-oriented Library → Song Details (`/songs/{id}`, version history and selection) → Extend/Remix/Repaint (new Versions of an existing Song) → Projects (organizational grouping of Songs) → AI Song Director (natural language → reviewable `SongSpec` → generation) → Music Videos (Phases 23–27: lyric video from a Version, 9:16/16:9/1:1, HD/4K) → Revise & Retry (Phase 28: new Version from a stored Version's inputs) all work end to end. Phases 29–30 are AI-video feasibility labs (results only, not product features). Read the latest `docs/PHASE-*.md` / `docs/MILESTONE-*.md` before assuming what exists; they record what was actually verified and known limitations — phase numbering is not contiguous across doc types (`*-IMPLEMENTATION.md` vs `*-PRODUCT-CAPABILITY-GAP-AUDIT.md`).

## The rule that governs everything: Reuse-First Law

`docs/REUSE-FIRST-LAW.md`: **REUSE → ADAPT → COMPOSE → BUILD**. Before adding any capability or dependency, do a fresh audit (license, maturity, fit, cost) and record the decision in `docs/` (see the `docs/PHASE-*-REUSE-AUDIT.md` files for the format). Check each license separately: source code, model, weights, dataset. Do not add a dependency merely because it exists; several steps here deliberately used stdlib/platform features or the existing local model instead (SQLite `PRAGMA user_version` instead of Alembic, native `<a download>` instead of file-saver, native `<details>`/radio instead of extra UI libs, ACE-Step's own 5Hz-LM planner instead of a second LLM or an agent framework for the AI Song Director). Hard rejects already made: MinIO (AGPLv3/archived), AudioCraft/MusicGen weights (CC-BY-NC), aeneas, madmom models, ComfyUI/A1111 code (GPL/AGPL). See `docs/LICENSE-AUDIT.md`, `COST-AUDIT.md`, `NON-GOALS.md`. No mandatory paid service; no Kubernetes/Kafka/Redis/Celery unless a demonstrated need.

## Commands

Everything runs locally on Windows (PowerShell/Git Bash). `uv` for Python, `npm` for the frontend.

```bash
# Start/stop/restart all three services (ACE-Step :8001, backend :8000, frontend :3000), each in its own window.
# Safe by construction: only the process actually listening on 8001/8000/3000 is ever touched, never by name.
powershell -File start-tunora.ps1 [-OpenBrowser] [-NoWait]
powershell -File stop-tunora.ps1 [-Force]
powershell -File restart-tunora.ps1 [-NoBrowser] [-Force]
# tunora-services.ps1 is shared helpers, dot-sourced by the three above; never run it directly.

# Backend (cd backend)
uv sync
uv run uvicorn app.main:app --port 8000
uv run pytest tests -m "not smoke"                      # unit/integration, no GPU
uv run pytest tests -m smoke                            # REAL ACE-Step generations/planner calls; needs ACE-Step up on :8001 (skips if unreachable)
uv run pytest tests/songs/test_domain.py::test_name -q  # single test

# Frontend (cd frontend)
npm install
npm run dev            # http://localhost:3000; /api/* is proxied to TUNORA_API_URL (default http://127.0.0.1:8000)
npm test               # vitest; single file: npx vitest run src/components/audio/download-button.test.tsx
npm run typecheck && npx eslint
npm run build
npm run test:e2e       # Playwright against the REAL stack (see below)
```

Backend env: `TUNORA_DB_PATH` (default `tunora.db`), `TUNORA_STORAGE_ROOT` (default `./data/audio`), `ACE_STEP_BASE_URL` (default `http://127.0.0.1:8001`). Relative paths resolve against the process cwd; `backend/data/` and `*.db` are gitignored.

**E2E is not mocked**: it needs ACE-Step, a backend, and Next.js, and does several real GPU generations/planner calls per full run. Useful env: `E2E_PORT` (Next, default 3100), `E2E_BACKEND_PORT` (default 8000), `E2E_DIST_DIR` (separate Next build dir so it can run beside another `next dev`), `E2E_STORAGE_ROOT` (backend storage dir; required by the missing-audio test and enables byte-for-byte comparison with the stored file). Run it against a throwaway `TUNORA_DB_PATH`/`TUNORA_STORAGE_ROOT`, e.g. backend on port 8010:
`E2E_BACKEND_PORT=8010 E2E_DIST_DIR=.next-e2e E2E_STORAGE_ROOT=<dir> npx playwright test`.
The throwaway E2E database accumulates rows across runs (nothing cleans it up); tests that assert on a title/name give it a `Date.now()` suffix to avoid colliding with a leftover row.

Frontend is **Next.js 16**: its APIs differ from older versions; `frontend/AGENTS.md` says to read `node_modules/next/dist/docs/` before writing Next code. Route props use generated types (`PageProps<...>`, run `npx next typegen` if they are missing).

## Architecture (needs several files to see)

```
Browser -> Next.js (/api/* rewrite) -> FastAPI routes -> JobService -> JobRepository (SQLite)
                                                      |-> MusicGenerationProvider -> AceStepMusicGenerationProvider -> ACE-Step REST API
                                                      |-> AudioStorage -> LocalAudioStorage -> filesystem
                                    -> SongDirector -> AceStepSongDirector -> ACE-Step's own LM endpoints
                                    -> MusicVideoService -> LyricsAligner (local Whisper, worker process) + FFmpegLibassRenderer
```

- **Composition root is `backend/app/main.py`** (lifespan): the only place that names concrete provider/repository/storage/director/renderer implementations, and the only place router registration **order** matters — `director_router` is included before `songs_router` because the static `/api/songs/plan` would otherwise be shadowed by `/api/songs/{song_id}`. Everything else depends on the abstractions (`app/providers/base.py`, `app/jobs/repository.py`, `app/storage/base.py`, `app/director/base.py`). ACE-Step request/response shapes, task ids and its `/v1/audio` URLs must never leave `app/providers/ace_step.py` / `app/director/ace_step.py` (shared envelope parsing: `app/providers/ace_step_http.py`).
- **Job vs Song vs Version** (`app/jobs`, `app/songs`): a `Job` is only the execution/lifecycle of one generation (state machine in `jobs/state_machine.py`, polled by `JobService.run_until_terminal` as a FastAPI BackgroundTask). A `Song` is the durable identity; a `Version` is an immutable generation snapshot (`spec` is the provider-neutral `GenerationRequest`) with a write-once audio reference; `jobs.version_id` links a job to the version it produces. `POST /api/jobs` with `song_id` creates the next Version of an existing Song. Song + Version + Job are created in one `BEGIN IMMEDIATE` transaction that **commits before** the provider is called; completion (`complete_job`) atomically marks the job COMPLETED and attaches audio. Version numbers are per song, assigned inside the transaction, `UNIQUE(song_id, version_number)`; SQLite triggers make snapshots immutable.
- **Creative operations and Revise** (`app/songs/operations.py`): Extend/Remix/Repaint read one existing Version's audio and create a **new** Version of the same Song — the source is never modified. `REVISE` (Phase 28) is a text-to-music operation: the Create form opens on one Version's stored `spec` (failed Versions included, since inputs are written before submission — this is also how Retry works), and generating appends a new Version. `Version.operation`/`source_version_id`/`operation_params` record lineage; a source must belong to the same Song (enforced by a DB trigger).
- **Persistence and migrations**: stdlib `sqlite3`, all queries parameterized, no ORM. Schema changes go through `app/jobs/migrations.py` (versioned by `PRAGMA user_version`, one `BEGIN IMMEDIATE` transaction per step, additive only, idempotent). Legacy jobs map 1:1 to a song with version 1; audio files are never moved (key stays `<job-id>/<job-id>.<ext>`). Add new steps rather than editing old ones.
- **Audio is served only through `GET /api/jobs/{id}/audio`** (Starlette `FileResponse`: Range, ETag, Content-Length). The client sends only a job id; the file is resolved from the trusted job record via `AudioStorage` with ownership/media-type/containment checks in `JobService.resolve_audio`. Downloads reuse that same route on the client (fetch + Blob + `<a download>`); there is deliberately no second endpoint. Filenames are sanitized once in `app/storage/filenames.py`.
- **Public API is an allowlist** (`app/api/schemas.py`): `absolute_path`, storage key internals, `Job.error` (returns a fixed "Generation failed."), provider task ids, source audio paths for creative operations and ACE-Step URLs must never appear in a response, page, or log shown to users. Tests assert this; keep it that way for every new endpoint (validate ids with `app/songs/ids.py`, never accept paths).
- **Frontend** (`frontend/src`): `lib/api/jobs.ts` is the only generation-job API client and the only place audio URLs are built (`isTunoraAudioUrl` guards every use); `lib/api/songs.ts`, `projects.ts`, `director.ts` are the other clients. Job tracking is a hand-written polling hook (`lib/jobs/use-job-status.ts`: recursive timeout, no overlap, backoff, stops on terminal state/404/unmount). The single player is `components/audio/audio-player.tsx` on WaveSurfer.js: it downloads and decodes the whole file once and plays from a blob, so it makes one plain GET (no Range); Range support exists and is tested for future direct streaming. shadcn/ui components live in `components/ui` (Base UI based).
- **Projects** (`app/projects`, Phase 6): a `Project` is pure organizational metadata over `Song` (`Song.project_id`) — it owns no audio and no Version. Deleting a Project never touches a Song, Version, or audio file.
- **AI Song Director** (`app/director`, Phases 7–8): `SongDirector` turns a natural-language request into a provider-neutral, reviewable `SongSpec` (`create_plan`/`refine`) — deliberately "small and boring": one method, no tools, no multi-step planning, no autonomy, and it never generates audio itself. Fields the user supplied explicitly (`REQUESTABLE_FIELDS`) are tracked in `requested_fields` and the Director must never overwrite them with an AI guess. A plan only becomes a Song/Version/Job through the existing, unchanged `POST /api/jobs`.
- **Music Videos** (`app/music_videos`, Phases 23–27; reference `docs/PHASE-23-MUSIC-VIDEO-COMPOSER.md`, formats `docs/PHASE-27-MULTI-FORMAT-MUSIC-VIDEO.md`): a Music Video is a presentation artifact of one Version, not a Version — it never changes Song/Version/audio. Lyrics are aligned by a local Whisper worker process; rendering is one policy-checked LGPL FFmpeg + libass command (no shell, `file:` inputs only, OpenH264 + AAC), in-process, one render at a time. No LLM, cloud service or GPU model.

## Testing conventions

Backend uses `FakeProvider`/`FakeAudioStorage` (`tests/jobs/fakes.py`) for unit tests, `respx` to mock ACE-Step HTTP for provider/director unit tests, and real `LocalAudioStorage` over `tmp_path` where storage behavior matters; tests marked `smoke` hit the real ACE-Step and are skipped when it is unreachable. `asyncio_mode = "auto"`. Classify results honestly: unit ≠ integration ≠ real E2E ≠ real GPU; a skipped smoke test is not a pass. Audio quality, vocals and pronunciation need human listening; report only objective facts. Never weaken or delete a test to make a change pass; if a contract intentionally changes, update the assertion and say so. jsdom cannot decode audio, so player logic is unit-tested with a fake WaveSurfer and real playback is verified only in Playwright. A known Vitest flake (`version-actions.test.tsx`, a real-timer poll race) can fail under heavy parallel load — re-run that file alone before treating it as a regression.

## Locked-in decisions and constraints

- **Model**: ACE-Step 1.5 (MIT code, Apache-2.0 weights) behind `MusicGenerationProvider`, and its own 5Hz-LM behind `SongDirector` — no second model/runtime for planning. Fallbacks (DiffRhythm2, YuE) need local validation before becoming providers. Dev GPU RTX 5060 Ti 16 GB. Exact lyric-to-vocal timing is not guaranteed; do not claim language support beyond what was actually validated.
- **Storage** local filesystem behind `AudioStorage`; **DB** SQLite; **job execution** in-process (FastAPI BackgroundTasks + polling), no queue. Only replace these with evidence.
- **Audio/video tooling**: FFmpeg LGPL-only build (never `--enable-gpl`), soundfile, librosa. Demucs weight license is disputed (blocking for commercial use); basic-pitch has the cleanest license.
- Do not clone Suno/Udio UI or branding; do not build a custom foundation model; do not add a second LLM or an agent framework (LangChain/LangGraph) unless a reuse audit proves ACE-Step's own planner insufficient. AI video experiments use only fictional/synthetic performers — no real-person identity cloning or face-swapping.
- `docs/` holds the audit trail (`REUSE-*.md`, `LICENSE-AUDIT.md`, `MODEL-CANDIDATES.md`, `PHASE-*`, `MILESTONE-*`); consult it instead of re-deriving decisions.

## Environment notes

Windows. Some long-lived local processes (a `next dev`, a backend, the ACE-Step server) may hold ports 3000/8000/8001 and refuse `taskkill` (access denied); prefer `stop-tunora.ps1`/`restart-tunora.ps1` or alternate ports/`E2E_DIST_DIR` rather than fighting them by hand. Only one `next dev` can use a given `distDir` (`NEXT_DIST_DIR`) at a time. The frontend, backend and ACE-Step each need their own dependency install (`npm install`, `uv sync` in `backend` and in `ACE-Step-1.5`). ACE-Step's LM lazy-loads on first request (a health check does not trigger it); the first real call after a fresh start can take several minutes.

ACE-Step must be started with `ACESTEP_CONFIG_PATH2=acestep-v15-base` (a second model slot, done by `tunora-services.ps1`) for Extract to work — turbo (the default model) doesn't support the `extract` task and ACE-Step **silently** falls back to the turbo handler instead of erroring. Tunora checks the returned `dit_model` and fails the job visibly rather than saving a wrong result, but a manually-started ACE-Step without that env var breaks Extract while leaving Create/Extend/Remix/Repaint/Another Take unaffected.
