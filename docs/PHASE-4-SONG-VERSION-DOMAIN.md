# Phase 4 — Song + Version Domain

Goal: stop treating a Job as a Song. Introduce **Song → Version → Audio**, keep the Job as the execution record, and do it without breaking the working MVP or losing existing data. Scope is the domain foundation only: no Song Details page, version history UI, Projects, Extend/Remix/Repaint or new providers.

## 1. Reuse audit

Versions and licenses read from PyPI on 2026-09-20.

| Candidate | License / version | What it offers | Decision |
|---|---|---|---|
| **Alembic** | MIT, 1.20.0 | Full migration framework | **REJECT for now.** Requires SQLAlchemy; Tunora uses stdlib `sqlite3` behind a repository interface. Two additive steps do not justify an ORM and a migration environment. Revisit if the schema grows past a handful of migrations or Postgres arrives. |
| **SQLAlchemy / SQLModel** | MIT, 2.0.54 / 0.0.42 | ORM, unit-of-work, relationship modelling | **REJECT.** Same reason; would replace a working, tested repository layer. |
| **yoyo-migrations** | Apache, 9.0.0 | Plain-SQL/Python migration runner, SQLite support | **REFERENCE.** Closest fit; not adopted because it adds a dependency and its own bookkeeping table for what `PRAGMA user_version` already does. |
| **sqlite-utils / sqlite-migrate** | Apache-2.0, 4.2.1 / 0.2 | SQLite helpers, small migration runner | **REJECT.** Extra dependencies (7 for sqlite-utils) for behavior we need in ~40 lines. |
| **uuid6 / python-ulid** | MIT, 2025.0.1 / 4.0.1 | Time-ordered ids | **REJECT.** Ordering comes from `created_at` and `version_number`; random UUID4 matches the existing job-id philosophy and needs nothing new. |
| **Immutable/versioned-record libraries** (e.g. history-tracking add-ons) | not evaluated in depth | Row history via ORM hooks | **REJECT.** Our need is narrower — immutable snapshots plus write-once audio — and SQLite triggers give that with no dependency. |
| **Stdlib**: `sqlite3` (`BEGIN IMMEDIATE`, `PRAGMA user_version`, triggers, `UNIQUE`/`CHECK`/foreign keys), `uuid`, `json` | PSF | Everything required | **REUSE.** |
| **Existing Tunora code**: `GenerationRequest` (provider-neutral), `derive_title`, `AudioStorage`, `JobRepository` pattern, id style | project | | **REUSE.** `GenerationRequest` *is* the version's generation spec, so no new `GenerationSpec` type or table was created. |

Result: **no new dependency.** Built: the domain dataclasses, the migration runner, and the two repository implementations' new methods.

## 2. Existing architecture (inspected first)

`Job` (id `tunora-<uuid4>`, provider, status, `request: GenerationRequest`, timestamps, `provider_job_id`, `error`, `result` JSON holding the audio reference, `title`) was persisted in one SQLite table `jobs`; the schema was created ad hoc in `SqliteJobRepository.__init__` with a one-off `ALTER TABLE` for `title`. Audio lives in `AudioStorage` at `<job-id>/<job-id>.<ext>`; the audio route resolves it from `job.result`. A Job was the only identity a song had.

## 3. Why Job ≠ Song

A Job answers "what is generating / did it fail / when". A song's identity must outlive any one generation: regenerating must not create a second song, and an old result must stay reproducible. So identity moved to Song, a reproducible snapshot to Version, and the Job now points at the Version it produces.

## 4. Domain model

```
Song   (id, title, created_at, updated_at)            title is the only mutable field (later phases)
 |
 +-- Version 1   (id, song_id, version_number, spec: GenerationRequest, provider, created_at, audio?)
 |     |
 |     +-- Job   (execution: status, timestamps, provider task id, error)   jobs.version_id -> versions.id
 |     |
 |     +-- Audio  reference (key, filename, media type, size, duration) -> bytes in AudioStorage
 |
 +-- Version 2
       +-- Job
       +-- Audio
```

- Song 1—N Version. Version 1—0..1 Audio. A Version is produced by a Job (`jobs.version_id`); in the current flow that is 1:1 (a retry of the same take is not modelled yet — a new attempt is a new Version).
- Code: `app/songs/{models,ids,errors,repository}.py`. Job gained `version_id`.
- **Provider independence:** `Version.spec` is `GenerationRequest`; `Version.provider` is a name string. `app/songs` imports nothing from ACE-Step or `httpx` (asserted by a test that scans the package source). The provider only ever receives a `GenerationRequest` (also tested), never a song or version id.

## 5. Schema (schema version 2)

```
songs(id PK, title, created_at, updated_at)
versions(id PK, song_id FK->songs, version_number >= 1, prompt, lyrics, language, duration, seed,
         instrumental, batch_size, provider, created_at,
         audio_key, audio_filename, audio_media_type, audio_size_bytes, audio_duration,
         UNIQUE(song_id, version_number))
jobs(... unchanged columns ..., version_id FK->versions)          indexes: idx_jobs_version_id, idx_jobs_created_at
triggers: versions_snapshot_immutable, versions_audio_write_once
```

Indexes, with the query each serves: `UNIQUE(song_id, version_number)` (also the lookup index for `list_versions` and the `MAX(version_number)` scan); `versions.id`/`songs.id` primary keys; `idx_jobs_version_id` (job ↔ version joins); `idx_jobs_created_at` (the existing `ORDER BY created_at DESC` list). Nothing else was indexed; the library's title/prompt search is still an in-memory filter (unchanged from Milestone 1).

## 6. Migration strategy

Mechanism: `app/jobs/migrations.py`, versioned with `PRAGMA user_version` (stdlib). Steps: `0→1` baseline (`jobs`, plus the Milestone 1 `title` column), `1→2` the domain. Each step runs in its own `BEGIN IMMEDIATE` transaction, **re-checks the version after taking the write lock** (two processes starting together cannot both apply it), and rolls back completely on any error. A database from a *newer* build is refused rather than downgraded. It runs on every start and is a no-op once current. Migrations only add; nothing is dropped or rewritten.

## 7. Legacy data

Evaluated: one legacy Job → one Song → Version 1 → the same Job. Jobs contain everything needed (prompt, lyrics, language, duration, seed, instrumental, provider, title, created_at, audio reference in `result_json`), and no legacy record links two jobs as "the same song", so grouping would be guessing. **Chosen: 1 job → 1 song → version 1.** Rules:

- **Deterministic ids**: `song-<uuid>` / `ver-<uuid>` taken from the job's `tunora-<uuid>` suffix; a job with an unusual id gets `song-legacy-<sha256[:32]>`. Combined with `INSERT OR IGNORE` and a `WHERE version_id IS NULL` filter, re-running cannot create duplicates — even if the version marker is lost (tested).
- Song title = stored title, else derived from the prompt (same rule as before). Version spec from `request_json` with defaults for missing keys. Version audio copied from `result_json.audio` only for COMPLETED jobs with a well-formed record; malformed blobs yield **no** audio reference (nothing invented).
- Jobs, their `result_json` and the audio files are **not modified or moved**; the storage key stays `<job-id>/<job-id>.<ext>` so no file migration exists. The job's stored result remains the source the audio route uses.
- Tested against a hand-built legacy DB (pre-title and with-title schemas, completed/failed/running jobs, a non-UUID id, a corrupt blob, empty DB), byte-for-byte comparison of every original column, an injected mid-backfill failure (full rollback, `user_version` stays 1, next start succeeds), and a **copy of a real database** created by the earlier E2E runs: 6 jobs → 6 songs, 6 versions, 6 with audio, unchanged on a second run, and the E2E then ran green against that migrated copy.

## 8. Version immutability

Enforced in three layers: (1) the repository exposes no update for a version's snapshot; (2) SQLite triggers `RAISE(ABORT)` on any `UPDATE` of `song_id, version_number, prompt, lyrics, language, duration, seed, instrumental, batch_size, provider, created_at`; (3) audio is **write-once** — attaching the identical value again is a harmless no-op (crash retry), a different value is refused (`ImmutableVersionError`). Tested per column through raw SQL. Not covered by immutability: `Song.title` (mutable by design, but no rename operation exists yet).

## 9. Version numbering and concurrency

`version_number = MAX(version_number)+1` per song, computed **inside** `BEGIN IMMEDIATE` (the write lock is taken before the read, so concurrent creators serialize instead of reading the same maximum), with `UNIQUE(song_id, version_number)` as the backstop. Verified by 12 threads released together on one song: numbers 2..13, no duplicates, no errors. Numbers are per song (Song B also starts at 1). A generation that fails still consumed its number, and a *failed insert* does not burn one (both tested). Gaps therefore mean "a take that failed", never a reused number.

## 10. Job relationship

Chosen model: `Job.version_id → Version` (Job is the execution of a Version). Version 1—N Job is *possible* in the schema but not used yet. Job keeps its own copy of the request and its result JSON (existing behavior), so all existing endpoints work unchanged.

## 11. Audio relationship

`AudioStorage` is untouched. The Version stores an audio **reference** (key, filename, media type, size, duration), attached in the same transaction that marks the Job COMPLETED. The Job's `result` still holds the audio record used by `GET /api/jobs/{id}/audio`, so there are two references to the same file, kept consistent by that transaction (accepted duplication; see debt).

## 12. Transaction boundaries

- `create_generation`: one transaction inserts the Song (if new), the Version (number assigned inside) and the Job. Any failure rolls back all three (tested: duplicate job id after the song/version inserts leaves nothing behind, `job.version_id` reset).
- The transaction **commits before** the ACE-Step call. Tested with a provider that opens a second connection and takes `BEGIN IMMEDIATE` during `generate()`: it succeeds and already sees the committed version row.
- `complete_job`: job update + audio attach in one transaction (after the file is safely in storage).
- Restart safety: a job created and submitted, then a process restart, is restored with its version and can be completed by a new service instance (tested).
- Known remaining window: if the process dies after `storage.save` but before `complete_job`, the audio file exists but the job/version are not completed; re-polling completes it idempotently (storage overwrite is atomic and identical, audio attach is idempotent).

## 13. Provider abstraction

Unchanged: `JobService → MusicGenerationProvider → AceStepMusicGenerationProvider`. A future provider needs nothing from the domain except `GenerationRequest`.

## 14. API compatibility

Preserved, unchanged in behavior: `POST /api/jobs`, `GET /api/jobs`, `GET /api/jobs/{id}`, `GET /api/jobs/{id}/audio`, Library filters, titles, downloads, missing-audio handling. Additive changes only:
- `JobResponse` gains `song_id`, `version_id`, `version_number` (Tunora ids; null for a job that predates the domain and could not be migrated).
- `CreateJobRequest` gains optional `song_id`: generate the **next Version of an existing Song**. Unknown id → 404 `Song not found.`; malformed id (path separators, quotes, spaces, over 80 chars, leading `-`) → 422 before reaching the service. This is the minimum needed to create Version 2 without new UI; no `/songs` endpoints, no version listing route, no UI.
- Frontend: only the `GenerationJob` type gained three optional fields.

## 15. Testing evidence (all executed this session)

| Check | Result |
|---|---|
| Backend `pytest -m "not smoke"` | **VERIFIED** 266 passed (was 190): 49 domain/persistence (both repository implementations where common), 13 migration, 14 service/API |
| Real ACE-Step smoke (`-m smoke`) | **VERIFIED** 4 passed, including the new test: real generation creates Song + Version 1; a second real generation with the same `song_id` creates Version 2 (`song_id` equal, numbers 1 and 2, different audio key); Version 1's record, file hash and size are unchanged afterwards; SQLite shows 1 song / 2 versions / 2 jobs / no job without a version; no path or provider id in any API response |
| Frontend Vitest / tsc / ESLint / production build | **VERIFIED** 200 passed / clean / clean / builds |
| Real Playwright E2E (Next → FastAPI → ACE-Step), against a **migrated copy of a real pre-Phase-4 database** | **VERIFIED** 5/5: create, generate, play, seek, Range, download bytes, Library → search → open same song → play/seek/download, plus the missing-audio 500 case |
| Legacy audio after migration | **VERIFIED** via HTTP: migrated jobs serve `200 audio/mpeg` (480,812 bytes); the jobs returning 500 are the earlier Test-B songs whose files that test deleted on purpose |
| Mutation checks | Changing the version-number query to a constant made 8 tests fail (then restored) |

## 16. Security

Every SQL statement is parameterized; the only two f-strings build a list of `?` placeholders and cast an int for `PRAGMA user_version` (no user input). Song ids from clients are validated (`^[A-Za-z0-9][A-Za-z0-9-]{0,79}$`) at both the schema and service layers; tested with traversal, backslash, drive-letter, SQL-injection, over-length and control-character inputs. A Version is only reachable through the repository by its own id, `list_versions(B)` never returns A's versions, and job audio stays bound to its own job whatever `song_id`/`version_id` a request names (tested). API responses expose only Tunora ids: no absolute path, storage root, ACE-Step id, `/v1/audio` or port (asserted on job JSON, list JSON and the real-GPU run). `Job.error` remains internal.

## 17. Known limitations and debt

- **Two references to the audio** (job result and version) — consistent by transaction, but redundant. Collapse when Song Details makes the Version the read path.
- **`Job.title` duplicates `Song.title`.** Responses still use the job's title snapshot; a future rename must update or replace that.
- **A corrupt `request_json`/`result_json` blob makes that job unreadable** (`repository.get`/`list` raise) — pre-existing, now documented; the migration itself tolerates such rows. One bad row would break the library listing; skipping unreadable rows is a small follow-up.
- **No API to list a song's versions, view a song, rename it, delete anything, or retry a take** — deferred by scope. `song_id` on job creation is the only new write path.
- Version 1—N Job is allowed by the schema but unused.
- The library still lists jobs (one row per version); grouping by song is Phase 5.
- Search is still an in-memory filter over the newest 500 jobs.
- Version numbers can have gaps (failed takes).
- Trigger-based immutability is SQLite-specific; a Postgres backend would need equivalents.
- Concurrency was verified on one machine with threads, not with multiple processes.
- ACE-Step, `next dev` and an old backend from before this session still cannot be stopped from this shell (access denied); the E2E ran on separate ports.

## Deferred (later phases)

Song Details page, version history UI, Projects, Extend/Remix/Repaint (each creates a new Version by design), AI Song Director, more providers, advanced audio, music video.
