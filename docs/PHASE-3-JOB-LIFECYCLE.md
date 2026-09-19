# Tunora — Phase 3, Step 12: Job Lifecycle

## 1. Reuse Audit

Step 11 established that Tunora, not ACE-Step, must be the source of truth for job existence and state (ACE-Step's `/query_result` returns an identical shape for "queued" and "unknown task_id"). This step needed: (a) a persistence layer that survives a FastAPI process restart, and (b) a mechanism to repeatedly poll the provider until a job finishes.

| Candidate | License | Verdict | Reasoning |
|---|---|---|---|
| **RQ** (Redis Queue) | MIT | ❌ REJECT for this step | Requires a Redis server — a new infrastructure dependency Tunora's locked stack explicitly wants to avoid until a demonstrated need exists. ACE-Step itself already serializes generation to one job at a time internally (`acestep/api/jobs/worker_loops.py`); Tunora doesn't need a second, separate distributed queue in front of a single-GPU, single-process backend. Previously the correct choice for a *future* multi-worker scale-out (per `docs/REUSE-MATRIX.md`), but premature here. |
| **Celery** | BSD-3 | ❌ REJECT | Same Redis/broker dependency issue as RQ, plus materially more operational complexity (workers, broker, result backend) for a single-developer-machine MVP. Explicitly named as infra to avoid in the Step 12 brief. |
| **APScheduler** | MIT | ❌ REJECT | Built for *scheduled/recurring* jobs (cron-like), not for "poll this one in-flight job every few seconds until it reaches a terminal state." Using it here would mean bending a scheduler library into a polling loop it wasn't designed for, adding a dependency without solving a problem plain `asyncio` doesn't already solve. |
| **asyncio background tasks (`asyncio.create_task` / `asyncio.sleep` loop)** | stdlib | ✅ **REUSE (winner, mechanism)** | Zero new dependency. A poll-until-terminal loop is exactly what `asyncio.sleep` + a loop already does well, and it matches ACE-Step's own one-job-at-a-time execution model — Tunora doesn't need concurrency control beyond what naturally exists. |
| **FastAPI `BackgroundTasks`** | part of FastAPI (already a dependency) | ✅ **REUSE (winner, trigger)** | The framework's own built-in mechanism for "do this after returning the response, in the same running process." No new dependency; directly matches "keep the architecture simple enough to run on one developer machine." |
| **SQLite (stdlib `sqlite3`)** | stdlib (public domain) | ✅ **REUSE (winner, persistence)** | Already the locked-stack MVP persistence choice (`CLAUDE.md`: "SQLite/PostgreSQL only when persistence is required" — it's now required, since jobs must survive a FastAPI process restart). Using the stdlib module directly, not an ORM, avoids adding SQLAlchemy before there's a real need for it — the `JobRepository` interface already isolates the rest of the app from this choice, so upgrading later costs nothing extra. |
| **In-memory dict** | n/a | Rejected as the *only* store | Survives within one running process (so it would technically satisfy "survive a FastAPI request boundary"), but not a process restart, and the brief explicitly asks for a restart test — kept only as `InMemoryJobRepository` for fast unit tests. |

**Decision:** BUILD a thin lifecycle layer — `JobService` orchestrating `JobRepository` (SQLite) and `MusicGenerationProvider` — triggered by FastAPI's own `BackgroundTasks`, using a plain `asyncio.sleep` polling loop. No Redis, no Celery, no APScheduler, no new dependency beyond what Step 11 already added (`httpx`) and what FastAPI/Python already provide. This is a BUILD decision under the Reuse-First Law's own terms: no existing package already provides "poll one HTTP-backed job to completion and persist state to SQLite" as a ready-made unit smaller than a full queue framework, and the queue frameworks that do exist solve a scaling problem Tunora doesn't have yet.

## 2. Architecture

```
Next.js (future)
   ↓  HTTP
FastAPI (app/api/routes_jobs.py)
   ↓
JobService (app/jobs/service.py)
   ↓                              ↓
JobRepository (SQLite)     MusicGenerationProvider
                                   ↓
                           AceStepMusicGenerationProvider (Step 11, unchanged)
                                   ↓
                           ACE-Step REST API → RTX 5060 Ti
```

`JobService` never imports `httpx` and never sees ACE-Step's response shapes — those stay entirely inside `AceStepMusicGenerationProvider`, exactly as required. `JobRepository` is an abstract interface; `SqliteJobRepository` is the only concrete implementation used today.

## 3. Job Domain Model (`app/jobs/models.py`)

```python
class Job:
    id: str                    # Tunora-owned, e.g. "tunora-<uuid4>"
    provider: str               # e.g. "ace-step"
    status: JobStatus
    request: GenerationRequest  # Step 11's provider-agnostic request
    created_at: datetime
    submitted_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    provider_job_id: str | None  # ACE-Step's task_id -- a foreign reference only
    error: str | None
    result: dict | None          # {"audio_path", "duration", "metadata"} once COMPLETED
```

`job.id` and `job.provider_job_id` are always distinct values (`tunora-<uuid4>` vs. whatever the provider returns) — verified by a dedicated test (`test_provider_job_id_is_stored_separately_from_tunora_job_id`).

## 4. State Machine (`app/jobs/state_machine.py`)

```
CREATED   → SUBMITTED, FAILED
SUBMITTED → QUEUED, RUNNING, COMPLETED, FAILED
QUEUED    → RUNNING, COMPLETED, FAILED
RUNNING   → COMPLETED, FAILED
COMPLETED → (terminal)
FAILED    → (terminal)
```

No `CANCELLED` state — ACE-Step exposes no cancel endpoint, so one is not invented. Same-state "transitions" (e.g. re-polling and finding it's still `QUEUED`) are treated as no-ops.

**Why SUBMITTED/QUEUED can jump straight to COMPLETED**: confirmed as a real possibility, not a hypothetical — Step 11's own smoke test completed a 10-second generation within roughly one polling interval, meaning `RUNNING` (or even `QUEUED`) may never be observed between a poll that saw `SUBMITTED` and the next poll that already sees `SUCCEEDED`. Disallowing these edges would make `JobService` raise `InvalidTransitionError` on a perfectly normal fast job, which is wrong.

`validate_transition()` raises `InvalidTransitionError` for anything not in the table (verified by 7 parametrized "invalid transition" tests, including going backwards and skipping `CREATED`). `JobService` never calls it with an unreachable target from application logic; the one place it *can* legitimately fire is if a provider ever reports a state that would require an illegal transition (e.g. going from `RUNNING` back to `QUEUED`) — `JobService.poll_once()` catches that specific case and converts it into a clean `FAILED` job with an explanatory error, rather than letting the exception crash the background polling task (see Error Handling below; tested by `test_backwards_provider_transition_fails_job_instead_of_crashing`).

## 5. JobRepository (`app/jobs/repository.py`)

Abstract interface: `create(job)`, `get(job_id) -> Job | None`, `update(job)`, `list(limit) -> list[Job]`. No `delete()` — nothing in Phase 3 needs it, and adding it now would be speculative.

- `InMemoryJobRepository` — dict-backed, used only in unit tests for speed.
- `SqliteJobRepository` — one `jobs` table, stdlib `sqlite3`, JSON-serializes `request` and `result`. This is the real MVP persistence.

**Postgres migration path**: a future `PostgresJobRepository` (likely via `asyncpg` or SQLAlchemy — re-run the reuse check *then*, not now) implements the same four methods. `JobService` and everything above it depends only on the `JobRepository` abstract class, never on SQL or a specific database, so swapping the implementation requires no change above this layer.

## 6. JobService (`app/jobs/service.py`)

- `create_and_submit(request) -> Job`: creates the job as `CREATED`, persists it, calls `provider.generate()`. On `ProviderError`, marks the job `FAILED` and returns it (does not raise) — the caller always gets a well-formed `Job` back. On success, stores `provider_job_id`, transitions to `SUBMITTED`.
- `poll_once(job_id) -> Job`: no-ops if already terminal; otherwise calls `provider.get_status()`, maps the provider's `JobState` (`QUEUED`/`RUNNING`/`SUCCEEDED`/`FAILED`) onto Tunora's `JobStatus`, and — only on `SUCCEEDED` — calls `provider.get_result()` to fetch and persist the actual result before marking `COMPLETED` (so a job is never marked `COMPLETED` without a result already attached).
- `run_until_terminal(job_id) -> Job`: loops `poll_once` + `asyncio.sleep(poll_interval_seconds)` until a terminal state, enforcing Tunora's own `max_poll_seconds` ceiling (default 30 minutes) independent of ACE-Step's own internal timeout — a job that never resolves is marked `FAILED` with a timeout message rather than polling forever.
- `get(job_id)` / `list(limit)`: reads, raising `JobNotFoundError` for an unknown id.

## 7. Provider Interaction

Exactly the contract from Step 11 — `MusicGenerationProvider.generate/get_status/get_result` — with no additions. `JobService` maps `JobState` (provider-level) to `JobStatus` (Tunora-level); these are deliberately two different enums so a future provider's state model can't leak into Tunora's own vocabulary.

## 8. Error Handling

| Condition | Handling |
|---|---|
| ACE-Step unavailable / provider raises `ProviderUnavailableError` at any stage | Job marked `FAILED`, `error` set from the exception message, persisted. No exception escapes `JobService`. |
| Provider timeout (`ProviderTimeoutError`) | Same as above — treated as any other `ProviderError`. |
| Provider reports `FAILED` | Job marked `FAILED` with the provider's own message. |
| Malformed/unexpected provider response (`ProviderResponseError`) | Same as above. |
| Unknown Tunora job id | `JobNotFoundError` raised by `poll_once`/`get`; the API layer maps this to HTTP 404. |
| Unknown provider job id | Not directly Tunora's concern here — Step 11's provider already turns this into a `ProviderResponseError` if ACE-Step's response is unusable; if ACE-Step returns its ambiguous "looks queued" shape for a bad id, Tunora will keep it `QUEUED` until its own `max_poll_seconds` ceiling fails it (documented limitation, not silently ignored). |
| Invalid state transition attempted internally | `InvalidTransitionError` (used directly in state-machine tests); when it would occur during automatic polling because a provider reported a state Tunora's machine can't reach from the current one, `JobService` catches it and fails the job cleanly instead of propagating. |
| Persistence failure | Not specifically caught/wrapped in this step — a `sqlite3` exception would propagate as-is. Flagged as a known limitation below rather than papered over with a broad `except Exception`. |

No raw stack traces are returned by the HTTP API — `routes_jobs.py` only ever returns `JobResponse` (Tunora's own shape) or a `404` with a plain message for unknown jobs.

## 9. Persistence

**SQLite**, one file (`tunora.db` by default, `TUNORA_DB_PATH` env var), one `jobs` table. Chosen over in-memory specifically because Step 12 requires surviving a FastAPI process restart, and over Postgres because nothing in Phase 3's single-user, single-machine scope needs a client-server database yet (per `NON-GOALS.md`).

## 10. Concurrency Model

Tunora accepts and tracks multiple jobs (each gets its own row + its own background polling task), but does not attempt to run multiple generations in parallel on the GPU — ACE-Step's own internal queue (`acestep/api/jobs/worker_loops.py`) already serializes actual execution to one job at a time. Tunora's polling tasks are lightweight (a `GET`-equivalent HTTP call every few seconds), so having several in flight concurrently — each waiting on ACE-Step's single-worker queue — is not a scaling problem at this size. No Celery/Kafka/Kubernetes was introduced.

## 11. Testing

**67/67 mocked/unit tests passed** (`uv run pytest tests -m "not smoke"`), covering (via `FakeProvider`, no network/GPU):
job creation + persistence, `CREATED→SUBMITTED`, `SUBMITTED→QUEUED`, `QUEUED→RUNNING`, `RUNNING→COMPLETED` (with result persisted), a valid failure transition from `RUNNING`, an invalid/backwards transition being converted to a clean `FAILED` job, an unknown job id raising `JobNotFoundError` (both from `poll_once` and `get`), provider-unavailable and provider-response-error handling at both submission and result-fetch time, a Tunora-side timeout producing a terminal `FAILED` job, `provider_job_id` being stored separately from and never equal to Tunora's own `job.id`, multiple independent jobs, SQLite round-trip persistence, and — explicitly — a simulated process-restart test (`test_sqlite_repository_survives_restart`: write with one `SqliteJobRepository` instance, discard it, open a fresh instance against the same file, confirm the job is still there). Five FastAPI endpoint tests confirm the HTTP layer returns only Tunora's own shape and never leaks a provider-specific field (e.g. `task_id`) — see `tests/test_api_jobs.py`.

## 12. Real Integration Test

**VERIFIED — PASSED** (`tests/test_job_lifecycle_smoke.py::test_real_job_lifecycle_end_to_end`, run against the real local ACE-Step API server, RTX 5060 Ti, `acestep-v15-turbo` + `acestep-5Hz-lm-1.7B`). Flow exercised: `POST /api/jobs` (10s instrumental prompt) → Tunora creates the job → submits to ACE-Step → stores `provider_job_id` → background task polls to `SUCCEEDED` → fetches result → `GET /api/jobs/{id}` returns `status: "COMPLETED"` with a `result.audio_path` that exists on disk and is non-empty. Wall time: 48.20s for the whole test process (includes uv/import overhead; the actual generation-and-poll portion is comparable to Step 11's ~12s). Confirmed no ACE-Step-specific structure (its `task_id` field name, `/v1/audio?path=` route strings, `wrap_response` envelope) appears anywhere in the HTTP response bodies.

## 13. Restart Test

**VERIFIED** — `test_sqlite_repository_survives_restart` (in `tests/jobs/test_repository.py`) creates a job with one `SqliteJobRepository` instance pointed at a temp file, discards that instance (simulating process exit), opens a brand-new `SqliteJobRepository` against the same file, and confirms the job and its status are still readable. This test passed as part of the 67-test run above.

## 14. Known Limitations

1. **Queued vs. unknown provider job id remains ambiguous** (inherited from Step 11) — if `provider_job_id` is ever wrong (a bug, a lost record on ACE-Step's side), Tunora will keep the job `QUEUED` until `max_poll_seconds` (default 1800s) expires and it's marked `FAILED` by timeout, rather than failing fast. Fast-failing this specific case would require ACE-Step to expose an unambiguous "not found" signal, which it currently does not.
2. **No cancel support** — consistent with Step 11 and this step's explicit instruction not to invent a `CANCELLED` state.
3. **No dedicated persistence-failure handling** — a `sqlite3` exception during `create`/`update`/`get` would currently propagate rather than being wrapped in a domain error. Acceptable for a single-file local SQLite DB in an MVP; worth revisiting if/when a real Postgres backend introduces connection-level failure modes.
4. **Retry is deliberately not implemented** — see below.
5. **Background task lifetime is tied to the FastAPI process** — if the process is killed mid-poll, the in-flight `run_until_terminal` loop dies with it. The job's last-persisted status remains in SQLite (not silently lost), but nothing automatically resumes polling a job that was `SUBMITTED`/`QUEUED`/`RUNNING` at restart time. A future step could add a "resume in-flight jobs on startup" pass; not built here because Step 12 didn't require it and it would add scope beyond the stated goal.

### Retry policy (explicit, per the brief's requirement)

- **What is retried**: nothing, automatically, in this step.
- **When**: N/A.
- **What is NOT retried**: job submission (`provider.generate()`) is not automatically retried on failure — a failed submission marks the job `FAILED` immediately. This avoids the real risk called out in the brief: blindly retrying `generate()` could submit a second, duplicate ACE-Step generation job for what the user thinks is one request. If automatic retry is added later, it must be scoped to idempotent operations only (`get_status`/`get_result` polling calls, which have no side effects) — never to `generate()` — or it must first ensure ACE-Step exposes some idempotency key.

## 15. Future PostgreSQL Migration Path

1. Implement `PostgresJobRepository(JobRepository)` (via `asyncpg` or SQLAlchemy Core — reuse-audit that choice when this actually becomes necessary, not preemptively).
2. Same four methods (`create`/`get`/update`/`list`), same `Job` dataclass in and out.
3. Swap the concrete class constructed in `app/main.py`'s `lifespan` — `JobService` and the API layer require zero changes, by construction.
4. Trigger for actually doing this: multi-user support or a real need for concurrent-writer safety beyond what SQLite offers — neither exists yet per `NON-GOALS.md`.
