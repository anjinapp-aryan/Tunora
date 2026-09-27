# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What Tunora is

Free, open-source-first, self-hostable AI Music Studio: describe a song (optionally lyrics/language/duration), generate it with a local open-source model, play it in the browser with a waveform, download it, and browse it in a Library. Suno/Udio are UX benchmarks only; no proprietary code, models, weights, datasets or branding may be used.

Repo layout: `backend/` (FastAPI), `frontend/` (Next.js), `docs/` (decisions and per-phase write-ups), `ACE-Step-1.5/` (git **submodule**: the upstream model server, treated as an external dependency; never add Tunora code there and never commit its local/untracked files), `start-tunora.ps1`.

State: the vertical slice Create → Generate → Track → Save → Play/Seek → Download → Song-oriented Library → Song Details (`/songs/{id}`, version history and selection) works end to end and is tested. Song → Version → Audio domain exists (Phases 4–5A); there is no UI to create a new version, Projects, or Extend/Remix/Repaint yet. Read the latest `docs/PHASE-*.md` / `docs/MILESTONE-*.md` before assuming what exists; they record what was actually verified and known limitations.

## The rule that governs everything: Reuse-First Law

`docs/REUSE-FIRST-LAW.md`: **REUSE → ADAPT → COMPOSE → BUILD**. Before adding any capability or dependency, do a fresh audit (license, maturity, fit, cost) and record the decision in `docs/`. Check each license separately: source code, model, weights, dataset. Do not add a dependency merely because it exists; several steps here deliberately used stdlib/platform features instead (SQLite `PRAGMA user_version` instead of Alembic, native `<a download>` instead of file-saver, native `<details>`/radio instead of extra UI libs). Hard rejects already made: MinIO (AGPLv3/archived), AudioCraft/MusicGen weights (CC-BY-NC), aeneas, madmom models, ComfyUI/A1111 code (GPL/AGPL). See `docs/LICENSE-AUDIT.md`, `COST-AUDIT.md`, `NON-GOALS.md`. No mandatory paid service; no Kubernetes/Kafka/Redis/Celery unless a demonstrated need.

## Commands

Everything runs locally on Windows (PowerShell/Git Bash). `uv` for Python, `npm` for the frontend.

```bash
# Start all three services (ACE-Step :8001, backend :8000, frontend :3000), each in its own window
powershell -File start-tunora.ps1 [-OpenBrowser] [-NoWait]

# Backend (cd backend)
uv sync
uv run uvicorn app.main:app --port 8000
uv run pytest tests -m "not smoke"                      # unit/integration, no GPU
uv run pytest tests -m smoke                            # REAL ACE-Step generations; needs ACE-Step up on :8001 (skips if unreachable)
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

**E2E is not mocked**: it needs ACE-Step, a backend, and Next.js. It does two real GPU generations per run (~60 s). Useful env: `E2E_PORT` (Next, default 3100), `E2E_BACKEND_PORT` (default 8000), `E2E_DIST_DIR` (separate Next build dir so it can run beside another `next dev`), `E2E_STORAGE_ROOT` (backend storage dir; required by the missing-audio test and enables byte-for-byte comparison with the stored file). Run it against a throwaway `TUNORA_DB_PATH`/`TUNORA_STORAGE_ROOT`, e.g. backend on port 8010:
`E2E_BACKEND_PORT=8010 E2E_DIST_DIR=.next-e2e E2E_STORAGE_ROOT=<dir> npx playwright test`.

Frontend is **Next.js 16**: its APIs differ from older versions; `frontend/AGENTS.md` says to read `node_modules/next/dist/docs/` before writing Next code. Route props use generated types (`PageProps<...>`, run `npx next typegen` if they are missing).

## Architecture (needs several files to see)

```
Browser -> Next.js (/api/* rewrite) -> FastAPI routes -> JobService -> JobRepository (SQLite)
                                                      |-> MusicGenerationProvider -> AceStepMusicGenerationProvider -> ACE-Step REST API
                                                      |-> AudioStorage -> LocalAudioStorage -> filesystem
```

- **Composition root is `backend/app/main.py`** (lifespan): the only place that names concrete provider/repository/storage. Everything else depends on the abstractions (`app/providers/base.py`, `app/jobs/repository.py`, `app/storage/base.py`). ACE-Step request/response shapes, task ids and its `/v1/audio` URLs must never leave `app/providers/ace_step.py`.
- **Job vs Song vs Version** (`app/jobs`, `app/songs`): a `Job` is only the execution/lifecycle of one generation (state machine in `jobs/state_machine.py`, polled by `JobService.run_until_terminal` as a FastAPI BackgroundTask). A `Song` is the durable identity; a `Version` is an immutable generation snapshot (`spec` is the provider-neutral `GenerationRequest`) with a write-once audio reference; `jobs.version_id` links a job to the version it produces. `POST /api/jobs` with `song_id` creates the next Version of an existing Song. Song + Version + Job are created in one `BEGIN IMMEDIATE` transaction that **commits before** the provider is called; completion (`complete_job`) atomically marks the job COMPLETED and attaches audio. Version numbers are per song, assigned inside the transaction, `UNIQUE(song_id, version_number)`; SQLite triggers make snapshots immutable.
- **Persistence and migrations**: stdlib `sqlite3`, all queries parameterized, no ORM. Schema changes go through `app/jobs/migrations.py` (versioned by `PRAGMA user_version`, one `BEGIN IMMEDIATE` transaction per step, additive only, idempotent). Legacy jobs map 1:1 to a song with version 1; audio files are never moved (key stays `<job-id>/<job-id>.<ext>`). Add new steps rather than editing old ones.
- **Audio is served only through `GET /api/jobs/{id}/audio`** (Starlette `FileResponse`: Range, ETag, Content-Length). The client sends only a job id; the file is resolved from the trusted job record via `AudioStorage` with ownership/media-type/containment checks in `JobService.resolve_audio`. Downloads reuse that same route on the client (fetch + Blob + `<a download>`); there is deliberately no second endpoint. Filenames are sanitized once in `app/storage/filenames.py`.
- **Public API is an allowlist** (`app/api/schemas.py`): `absolute_path`, storage key internals, `Job.error` (returns a fixed "Generation failed."), provider task ids and ACE-Step URLs must never appear in a response, page, or log shown to users. Tests assert this; keep it that way for every new endpoint (validate ids with `app/songs/ids.py`, never accept paths).
- **Frontend** (`frontend/src`): `lib/api/jobs.ts` is the only API client and the only place audio URLs are built (`isTunoraAudioUrl` guards every use). Job tracking is a hand-written polling hook (`lib/jobs/use-job-status.ts`: recursive timeout, no overlap, backoff, stops on terminal state/404/unmount). The single player is `components/audio/audio-player.tsx` on WaveSurfer.js: it downloads and decodes the whole file once and plays from a blob, so it makes one plain GET (no Range); Range support exists and is tested for future direct streaming. shadcn/ui components live in `components/ui` (Base UI based).

## Testing conventions

Backend uses `FakeProvider`/`FakeAudioStorage` (`tests/jobs/fakes.py`) for unit tests; real `LocalAudioStorage` over `tmp_path` where storage behavior matters; tests marked `smoke` hit the real ACE-Step and are skipped when it is unreachable. `asyncio_mode = "auto"`. Classify results honestly: unit ≠ integration ≠ real E2E ≠ real GPU; a skipped smoke test is not a pass. Audio quality, vocals and pronunciation need human listening; report only objective facts. Never weaken or delete a test to make a change pass; if a contract intentionally changes, update the assertion and say so. jsdom cannot decode audio, so player logic is unit-tested with a fake WaveSurfer and real playback is verified only in Playwright.

## Locked-in decisions and constraints

- **Model**: ACE-Step 1.5 (MIT code, Apache-2.0 weights) behind `MusicGenerationProvider`; fallbacks (DiffRhythm2, YuE) need local validation before becoming providers. Dev GPU RTX 5060 Ti 16 GB. Exact lyric-to-vocal timing is not guaranteed; do not claim language support beyond what was actually validated.
- **Storage** local filesystem behind `AudioStorage`; **DB** SQLite; **job execution** in-process (FastAPI BackgroundTasks + polling), no queue. Only replace these with evidence.
- **Audio tooling**: FFmpeg LGPL-only build (never `--enable-gpl`), soundfile, librosa. Demucs weight license is disputed (blocking for commercial use); basic-pitch has the cleanest license.
- Do not clone Suno/Udio UI or branding; do not build a custom foundation model.
- `docs/` holds the audit trail (`REUSE-*.md`, `LICENSE-AUDIT.md`, `MODEL-CANDIDATES.md`, `PHASE-*`, `MILESTONE-*`); consult it instead of re-deriving decisions.

## Environment notes

Windows. Some long-lived local processes (a `next dev`, a backend, the ACE-Step server) may hold ports 3000/8000/8001 and refuse `taskkill` (access denied); use alternate ports/`E2E_DIST_DIR` rather than fighting them. Only one `next dev` can use a given `distDir` (`NEXT_DIST_DIR`) at a time. The frontend, backend and ACE-Step each need their own dependency install (`npm install`, `uv sync` in `backend` and in `ACE-Step-1.5`).
