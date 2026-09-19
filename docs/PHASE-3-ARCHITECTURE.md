# Tunora — Phase 3 Architecture (Vertical Slice)

Planning document only — no implementation yet (see [PHASE-3-DECISIONS.md](./PHASE-3-DECISIONS.md) for the STOP gate). Describes the target shape for: Create Song → Track Generation → Completed → Show Audio → Play → Show Saved Location → Download.

## High-level flow

```
Next.js UI (shadcn/ui + WaveSurfer.js)
        │  POST /api/songs (create + submit job)
        ▼
FastAPI backend (Tunora-owned)
        │  MusicGenerationProvider interface
        ▼
AceStepProvider
        │  POST http://127.0.0.1:8001/release_task
        │  POST http://127.0.0.1:8001/query_result  (polled)
        ▼
ACE-Step 1.5 API server (external, unmodified)
        │  writes audio into its own cache/output dir
        ▼
Tunora output handler: verify → copy into Tunora storage → update job record
        │
        ▼
Next.js UI polls Tunora job status → shows COMPLETED → play/download/saved-location
```

Tunora's UI and domain layer never call ACE-Step directly — only through `MusicGenerationProvider`, per `ARCHITECTURE-PRINCIPLES.md`.

## Provider abstraction

```
MusicGenerationProvider (interface)
    generate(request) -> provider_task_id
    get_status(provider_task_id) -> status, progress info
    get_result(provider_task_id) -> output audio path/bytes, metadata
    cancel(provider_task_id) -> best-effort; not exposed in ACE-Step's current API, so this may be a no-op/local-only cancel for Phase 3
```

`AceStepProvider` implements this against the confirmed live endpoints:
- `POST /release_task` — submit generation (maps Tunora's `CreateSongRequest` → ACE-Step's request shape; a working example payload already captured during manual testing: `prompt`, `lyrics`, `vocal_language`, `audio_duration`, `model`, `thinking`, `lm_backend`, `audio_format`, `use_random_seed`).
- `POST /query_result` — poll by task id for status/result.
- `GET /health` — startup/readiness check before accepting new jobs.

Future providers (`YuEProvider`, `HeartMuLaProvider`, etc.) implement the same interface; the UI/domain layer is unaware which one is active.

## Tunora job model

```
TunoraJob
    id                  # Tunora-owned identity, primary key
    provider            # e.g. "ace-step"
    providerTaskId       # ACE-Step's task id — never the primary identity
    title
    prompt
    lyrics
    language
    vocalType
    duration
    model
    seed
    status              # QUEUED | PROCESSING | COMPLETED | FAILED | (future: CANCELLED)
    progress            # truthful only: queue position or coarse phase, never a fabricated %
    outputPath          # Tunora-owned storage path once COMPLETED
    createdAt / startedAt / completedAt
    error               # populated on FAILED
```

`providerTaskId` is a foreign reference only — regenerating or switching providers must not require changing `TunoraJob.id`, consistent with the parent Tunora data model (`User → Project → Song → Version → Audio`) where regeneration creates a new Version rather than mutating in place.

## Job lifecycle

```
QUEUED → PROCESSING → COMPLETED
QUEUED → PROCESSING → FAILED
```

No fabricated progress percentages. If ACE-Step doesn't expose true percentage completion, the UI shows truthful state text ("QUEUED — position 1", "GENERATING") rather than an invented progress bar value.

## Output handling (Steps 14-15 of the Phase 3 spec)

On a COMPLETED result from `AceStepProvider.get_result()`:
1. Verify the output audio file exists and is non-empty.
2. Read basic metadata (duration, sample rate, format) — objective facts only, no quality judgment (audio quality requires human listening per the Phase 2 ground rules, which extend to Phase 3).
3. Copy (not rely on in place) into Tunora-owned storage, e.g. `I:\Tunora\data\audio\<slug>-<id>.<ext>` — never leave the canonical copy inside ACE-Step's `.cache/`, since that's ACE-Step's own working directory, not Tunora's.
4. Update the `TunoraJob`/song record with `outputPath` and expose:
   - an audio URL the UI can play (served by the Tunora backend, not directly from ACE-Step's cache)
   - the literal filesystem path, displayed to the user as "Saved Location"
5. Provide a Download action. If a future desktop/Electron-style shell allows it, an "Open Folder" action is a stretch goal — Phase 3 must not assume browser JS can open an arbitrary folder; if it can't, showing the path plus Download is sufficient.

## Backend shape

FastAPI, no unnecessary infra:

```
FastAPI app
    routes: create song, get job status, list recent jobs, download audio
    provider layer: MusicGenerationProvider / AceStepProvider
    job store: SQLite (Phase 3 POC scope — matches ACE-Step's own choice of SQLite-adjacent simplicity, but this is a fresh Tunora-owned schema, not shared with ACE-Step's own state)
    polling from the browser is acceptable for Phase 3; SSE/WebSocket deferred until polling proves inadequate
```

No Kubernetes, Kafka, microservices, Redis, PostgreSQL, auth, billing, or multi-GPU orchestration — none justified by Phase 3's single-user, single-GPU, local scope, per `NON-GOALS.md` and the Phase 3 spec's explicit "do not overengineer" section.

## Dashboard (minimum viable layout)

```
TUNORA — AI MUSIC STUDIO
[ + Create Song ]

RECENT GENERATIONS
  Song A   ✓ Completed   03:00   [Play] [Download]
  Song B   ⏳ Generating   Queue position: 1
```

Built from shadcn/ui primitives (Card, Badge, Progress, Button) already locked in Phase 1 — reference the audited candidates' layouts for UX conventions only, no code reuse (see [PHASE-3-UI-REUSE-DECISION.md](./PHASE-3-UI-REUSE-DECISION.md)).

## Open questions to resolve during implementation (not blocking the reuse decision)

- Exact `/release_task` request/response schema needs to be pinned from `acestep/api/http/release_task_models.py` and `release_task_request_parser.py` before writing `AceStepProvider` — Phase 3 implementation step 11 should read those files directly rather than relying on the one manually-captured example payload.
- Confirm whether `/query_result` exposes any queue-position or phase signal, or only a coarse status — determines what "truthful progress" can actually show.
