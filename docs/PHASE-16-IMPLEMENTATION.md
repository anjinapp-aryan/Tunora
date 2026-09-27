# Phase 16 — Restart-Safe Job Recovery

Implementation record for Candidate R of `docs/PHASE-15-PRODUCT-CAPABILITY-GAP-AUDIT.md`:
"resume unfinished jobs after a backend restart."

## Problem and root cause

Killing the Tunora backend while a generation was in flight left the job in the database as
SUBMITTED/QUEUED/RUNNING forever, even though ACE-Step finished it (Phase 15 reproduced this live).
Root cause: polling ran only inside a FastAPI `BackgroundTask` started by the `POST` that created the
job. `GET /api/jobs/{id}` only reads the database and `lifespan` did no recovery, so after a restart
nothing ever polled the job again and its finished audio was never attached.

## Existing architecture reused (no new wheel)

`JobService.run_until_terminal` / `poll_once` (polling, timeout ceiling, transitions), the existing
completion pipeline (`complete_job`, `AudioStorage`, Version audio) and failure pipeline (`_fail`),
the persisted `jobs.provider_job_id` and persisted request (`operation`), the FastAPI `lifespan`, the
provider's `get_status`/`get_result`. No new dependency, table, migration, endpoint, UI, queue or
worker. ACE-Step is unchanged.

## Design

1. **Discovery:** new `JobRepository.list_unfinished()` (SQL `status NOT IN ('COMPLETED','FAILED')`,
   oldest first, unlimited). `JobService.search` was not reused because it loads only the newest window of
   jobs for the Library and sorts for display; a stranded job must never be missed. Recovered states:
   CREATED (only to fail it, see below), SUBMITTED, QUEUED, RUNNING.
2. **Resume:** `JobService.recover_unfinished_jobs()` runs once at startup. For each job with a
   `provider_job_id` it calls the existing `run_until_terminal` (concurrently, via `asyncio.gather`), so
   completion, storage, failure, timeout and transition handling are the same code as for a job that never
   lost its process. It never calls `generate`: nothing is resubmitted.
3. **Startup integration:** `main.py` `lifespan` starts recovery as one background `asyncio` task
   (`_recover_jobs`, which logs and swallows any failure) so the API is available immediately; on shutdown
   the task is cancelled and awaited so no polling task is left behind. `_configure_app_logging()` makes
   the existing `app.*` INFO logs visible under uvicorn (they were silently dropped before).
4. **Duplicate protection:** `JobService._polling` (in-memory set of job ids) guards `run_until_terminal`:
   a second call for a job that already has a loop returns the current state at once. Single-process
   modular monolith, so no distributed lock. The guard covers concurrent recoveries and a recovery
   overlapping a request-started loop.
5. **Isolation:** each job is recovered independently. A job without `provider_job_id` is failed ("never
   submitted", never resubmitted); a provider hook error fails only that job; an unexpected exception in one
   job's polling fails only that job (`_recover_one`); nothing can abort startup.
6. **Idempotency:** recovered jobs reach a terminal state, so later restarts find nothing to do (verified
   live: two extra restarts added 0 ACE-Step jobs and no Versions).

## Phase 14 Extract safety across a restart

Phase 14 kept the "this Extract must come from base" expectation in provider memory, which a restart
loses. Recovery restores it: the new provider hook `MusicGenerationProvider.register_recovered_job(job_id,
operation)` (no-op by default) is called with the persisted `provider_job_id` and `job.request.operation`
before polling; `AceStepMusicGenerationProvider.generate()` now uses the same method, so there is one
implementation and the Phase 14 validation itself is untouched. Invariants tested: recovered EXTRACT with
`dit_model` turbo, missing or null -> job FAILED, no audio; with `acestep-v15-base` -> COMPLETED;
non-Extract jobs are not checked.

## Two provider bugs the real restart test exposed

1. **Running jobs flipped to QUEUED.** ACE-Step's `stage` is free text once a job starts ("Phase 1:
   Generating CoT metadata...", "Decoding audio...", ...); the provider mapped anything except the exact
   string `running` to QUEUED. A recovered RUNNING job was reported QUEUED, the state machine rejected
   RUNNING -> QUEUED, and the job was failed ("Invalid state reported by provider") although ACE-Step
   finished it. Live poll survey (3 jobs, ~190 polls): stages seen `queued`, `Phase 1: ...`, `Generating
   music (batch size: 2)...`, `Preparing audio data...`, `Decoding audio...`, `succeeded`. Fix: only
   `queued`/empty means QUEUED; any other stage means RUNNING. This also fixes a latent failure in normal
   (non-recovery) polling.
2. **Unknown provider task ids looked "queued" forever.** For an id ACE-Step does not know (for example
   after ACE-Step itself restarted; its job store is in memory) `/query_result` returns `status 0` with an
   empty result list; the provider mapped that to QUEUED and the job would poll until Tunora's 30 minute
   ceiling. Every real queued/running job carries a result entry (0 empty results in the ~190 polls above).
   Fix: status 0 with an empty result list -> FAILED "ACE-Step does not know this job". Verified live:
   a job whose provider id was replaced by an unknown id failed immediately after recovery (0.0 s) with
   public error "Generation failed." and no audio.

## ACE-Step restart behavior

Backend restart recovery is implemented. ACE-Step's own restart is **not** recoverable (its in-memory
job store loses the task): the job fails visibly and immediately (fix 2), never resubmits, never fabricates
completion. Documented in `docs/TUNORA-SERVICE-MANAGEMENT.md`. Not tested with a real ACE-Step restart
(model reload takes minutes); the unknown-id behavior was verified by replacing the persisted id with one
ACE-Step does not know, which is what the server sees after a restart.

## Known window not covered

`create_and_submit` commits the job (CREATED, no provider id) before calling ACE-Step and stores the id
right after ACE-Step answers. A crash inside that window leaves an ACE-Step task Tunora has no id for; on
the next start the job is failed as "never submitted" (nothing is resubmitted), and ACE-Step's task is
orphaned. Closing this would need a pre-generated task id or a migration, out of scope.

## Files changed

`backend/app/jobs/repository.py` (`list_unfinished`), `backend/app/jobs/service.py` (`_polling` guard,
`recover_unfinished_jobs`, `_recover_one`), `backend/app/providers/base.py` (`register_recovered_job`
hook), `backend/app/providers/ace_step.py` (shared registration, stage mapping, unknown-id detection),
`backend/app/main.py` (startup task, cancellation, log configuration), tests
`backend/tests/jobs/test_recovery.py` (24) and `backend/tests/test_ace_step_provider.py` (+8),
`docs/TUNORA-SERVICE-MANAGEMENT.md`, this document and the Phase 15 audit document (committed with this
phase because it was still untracked). Dependencies: none added or removed. Database: no migration
(`LATEST_VERSION` stays 5). ACE-Step: unchanged.

## Tests

- New unit/integration tests (24): no jobs; SUBMITTED/QUEUED/RUNNING resumed and completed with stored audio and
  exactly one Version; provider RUNNING then COMPLETED; several jobs; COMPLETED/FAILED ignored and untouched;
  missing provider id failed without resubmission; provider FAILED; provider unavailable; unexpected exception
  isolated; malformed result isolated; provider-hook failure isolated; single loop per job (max concurrent
  provider queries = 1 with real overlap); concurrent recoveries; four repeated restarts; lineage preserved
  (Another Take); recovered Extract with base/turbo/missing/null model; non-Extract not checked; real app
  startup recovers a stranded job and hides provider ids in the public API; shutdown cancels recovery cleanly.
- Provider tests (+8): any started stage text is RUNNING, only queued/empty is QUEUED, unknown id fails.
- No frontend change.

## Mutation testing

15 targeted mutations, each run and restored: wrong status filter, recovery skipping jobs, duplicate guard
disabled, registry never released, missing-provider-id handling removed, completion path removed (no
polling), per-job isolation removed, provider-state restore removed, hook-failure handling removed, Extract
expectation not registered on recovery, expectation registered for every operation, startup recovery not run,
shutdown cancellation removed, stage mapping reverted, unknown-id detection removed. **15 of 15 caught.** Two
notes: the shutdown-cancellation mutant is detected by a hang (the test's `TestClient` never exits, so it had to
be killed): caught, but not a fast failure; and the duplicate-guard mutant initially **survived** because the
first test could not tell one polling loop from five (they shared one scripted answer list), so the test was
strengthened to count concurrent provider queries and now catches it.

## Real restart experiments (real ACE-Step, real GPU, throwaway backend and database)

Script kills only the Tunora backend process tree, leaves ACE-Step running, restarts the backend:

| Scenario | Status at kill | After restart | ACE-Step jobs submitted | Versions | Audio |
|---|---|---|---|---|---|
| Normal generation (run 1, before fix 1) | RUNNING | **FAILED** (bug 1) | 1 | 1 | none |
| Normal generation (final code) | RUNNING | COMPLETED | 1 | 1 | mp3, 10.000 s, 160,940 B |
| Two further restarts | - | still COMPLETED, unchanged | +0 | 1 | - |
| Extract vocals (final code) | SUBMITTED | COMPLETED | 1 | 2 (EXTRACT from Version 1) | mp3, 10.000 s |
| (earlier passing run of the same scenarios) | SUBMITTED / RUNNING | COMPLETED | 1 each | 1 / 2 | mp3 |

The Extract run used the base slot (Phase 14 configuration) and passed the model check; the wrong-model
failure on the real stack was not re-run (covered deterministically by the unit tests above). After
recovery, a temporary Playwright script (deleted afterwards) opened Library -> Song -> Version -> Play ->
Download for the recovered songs: playback advanced and the MP3 downloaded for both.

## Regression results (final code)

- Backend `pytest -m "not smoke"`: **598 passed** (566 before, +32: 24 recovery, 8 provider).
- Real-GPU smoke `pytest -m smoke` (live ACE-Step with the base slot): **13 passed**.
- Frontend (unchanged in this phase): `tsc` clean, ESLint 0 errors (1 pre-existing warning), Vitest **365 passed**, `next build` passes.
- Full Playwright suite (real stack, real GPU): **19 passed** (Create, Extend/Remix/Repaint, Extract, Another Take, Projects, Director, song management, Compare, drag-Repaint). An earlier attempt failed only because stale Next dev processes from a killed run blocked the Playwright web server; it was cleaned up and rerun.

## Security and performance

Recovery uses only persisted server-side state (job row, `provider_job_id`, request); nothing is accepted
from clients and no endpoint was added; the public API is unchanged and a test asserts the provider task id
and `provider_job_id` never appear in job/song responses. Logs carry job ids, statuses and counts only (no
prompts, lyrics, paths or provider internals). Startup does not wait for recovery; jobs are polled
concurrently; 0 unfinished jobs costs one indexed-free `SELECT` on a small table.

## Known limitations

- ACE-Step restart mid-job: the job fails visibly (cannot be recovered).
- The pre-acceptance crash window above.
- Recovered jobs get a fresh 30 minute polling budget.
- No real E2E restart test in Playwright: Playwright does not manage the backend process, so a clean
  in-suite kill/restart is not supported by the current test architecture; the real restart experiments
  above are the evidence.
- Extract stem quality (a Phase 14/15 open validation gap) is unaffected.
- The Phase 14 follow-up commit `f0fd87f` is still unpushed.

## Not part of Phase 16

Lossless/FLAC/WAV output, batch generation, prompt library, cover art, loudness, MIDI, chord detection,
lyric alignment, `lego`, `complete`, new Extract tracks, job cancellation, Redis/Celery/RQ or any queue.
