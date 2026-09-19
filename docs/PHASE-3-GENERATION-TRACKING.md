# Tunora — Phase 3, Step 15: Generation Tracking

## 1. Reuse Audit

Question: how should the browser follow a Tunora job to a terminal state? The backend already exposes `GET /api/jobs/{id}`; there is one such endpoint in the MVP.

| Candidate | License / version (from `npm view`, 2026-09-19) | What it gives | Cost for this feature | Decision |
|---|---|---|---|---|
| **Native `fetch` + a small React hook** | n/a (platform + React) | Full control over stop conditions, abort, backoff | ~70 lines; we must write and test overlap/unmount handling ourselves | **BUILD (chosen)** |
| **TanStack Query** | MIT, 5.103.1, ~1.7 MB unpacked npm size | `refetchInterval` (can be a function of the last result), retry/backoff, abort signals, request de-duplication, caching | New dependency plus a `QueryClientProvider`; caching/dedupe are unused with one polled endpoint | **REFERENCE** — genuinely capable of this job; revisit when the Library adds several cached lists |
| **SWR** | MIT, 2.5.1, ~320 KB unpacked npm size | `refreshInterval`, dedupe, error retry | Same reasoning; conditional stop needs a function/`null` interval and manual 404 handling | **REFERENCE** |
| **Server-Sent Events** | browser standard | Push from server | Needs a streaming endpoint and connection lifecycle on the backend; nothing today produces events (JobService only updates a DB row) | **REJECT for now** |
| **WebSockets** | browser standard | Bidirectional push | Requires new server infrastructure; the instructions forbid it unless proven necessary | **REJECT** |
| **Next.js data-fetching (server components / route handlers)** | part of Next | Server-side fetch | The page must update live in the browser; a server component would not, and a route handler would only add a hop | **REJECT** for live tracking |

Decision: hand-written hook, no new dependency. This is a BUILD under the Reuse-First Law's own test (a library would add a dependency and a provider without solving a problem we have), and the honest summary is that TanStack Query would also have been a defensible choice. The capability claims for TanStack Query and SWR above come from prior knowledge of their documented APIs; they were not exercised in this session, only their license and version were checked.

## 2. Tracking Architecture

```
/jobs/[jobId]  (server component, passes jobId)
   └─ JobTracker (client)            src/components/job/job-tracker.tsx
        ├─ useJobStatus(jobId)       src/lib/jobs/use-job-status.ts
        │     └─ getJob(jobId, {signal})   src/lib/api/jobs.ts  (typed client from Step 14)
        │           └─ GET /api/jobs/{id}  → Next.js rewrite → FastAPI → JobService → JobRepository
        └─ recallJobPrompt(jobId)    src/lib/jobs/job-summary.ts (optional request summary)
```

The browser only calls Tunora's `GET /api/jobs/{id}`. It never calls ACE-Step, `/release_task`, `/query_result`, `/health` or `/v1/audio`. `JobService` is not bypassed. Nothing is persisted client-side as job state; React state is rebuilt from the backend on every mount.

## 3. API Contract

Unchanged. `GET /api/jobs/{id}` returns `JobResponse`: `id, provider, status, created_at, submitted_at, started_at, completed_at, error, result`. `status` is exactly Tunora's enum (`CREATED, SUBMITTED, QUEUED, RUNNING, COMPLETED, FAILED`), so no frontend status mapping layer was written; the type is used directly. 404 is returned for an unknown id. The contract has no progress field and no request echo, so neither was invented.

Request summary ("where available"): the API does not return the request, so the create form stores the user's own prompt in `sessionStorage` and the job page shows it if present. It is best-effort and per-tab: absent in a new tab or another browser, never required for tracking.

## 4. Polling Decision

Plain HTTP polling with a recursive timeout. Reasoning: one endpoint, single user, generations of tens of seconds, and the backend has no push mechanism to feed SSE/WebSockets.

## 5. Polling Interval

**2 seconds** while a job is non-terminal. Observed generations are roughly 10–50 seconds, so 2 s gives a status change visible within about two seconds at a cost of 0.5 requests/second per open tab; the request is a single-row SQLite read. Longer intervals would make short generations feel stuck; shorter ones add traffic without giving the user new information, since the backend itself only advances state on its own 3-second poll of ACE-Step (`DEFAULT_POLL_INTERVAL_SECONDS`). This is a judgment call, not a measured optimum.

## 6. Retry Behavior

A failed poll (network error, HTTP 5xx, unreadable body) never changes the job's status. It sets `connectionProblem`, keeps the last known job on screen, and retries with backoff **2 s → 4 s → 8 s → 15 s**, repeating 15 s. Any success resets the sequence and clears the message. There is no retry limit: a backend that is temporarily down is expected to come back, and the only thing that ends tracking is a terminal state or a 404. (Consequence: a tab left open against a permanently dead backend keeps trying every 15 s; see limitations.) `POST` submission is not retried anywhere, consistent with Step 12.

## 7. State Handling

Displayed exactly by Tunora status:

| Status | Heading / message | Steps (Submitted · Queued · Generating · Complete) |
|---|---|---|
| (none yet) | "Checking your song…" | — |
| CREATED | "Generating your song" — "Preparing your request…" | none observed yet |
| SUBMITTED | "Your request was sent. Waiting for a turn…" | Submitted in progress |
| QUEUED | "Waiting in line — another song may be generating first." | Submitted done, Queued in progress |
| RUNNING | "Your song is being composed. This usually takes under a minute." | first two done, Generating in progress |
| COMPLETED | "Generation complete — Your song is ready." + "Audio ready" marker | all done |
| FAILED | "Generation failed" + alert "We couldn't complete this generation." | hidden (where it failed is not shown) |

Skip-ahead transitions (`SUBMITTED → COMPLETED`, `QUEUED → COMPLETED`, allowed by Step 12) render correctly because the UI shows the latest observed status and marks every earlier step done; it never depends on having seen the intermediate ones. Tested.

**Progress is indeterminate on purpose**: the backend provides no percentage, so the bar is a pulsing `role="progressbar"` with no `aria-valuenow`, and a test asserts no `NN%` text appears. The "under a minute" wording in the RUNNING message is a rough expectation from observed runs of short clips, not a promise, and longer durations (up to 3 minutes are selectable) may exceed it — worth softening later.

## 8. Terminal States

COMPLETED and FAILED both stop polling immediately. COMPLETED shows "Audio ready" as static text only: no player, no waveform, no download, no link to audio, and the audio key/filename/media type in `result` are not rendered (Step 16). FAILED shows a fixed generic message; `job.error` is never rendered because it can contain raw exception text (see limitations).

## 9. Network Failures

Covered in §6. A failed request produces "Connection problem — retrying. Your song is still being tracked." (`role="status"`); the heading and steps stay as last known. It is impossible for a network failure to display "Generation failed": that heading is driven only by the backend's `status`.

## 10. 404 Behavior

A 404 from `GET /api/jobs/{id}` stops polling and shows "Job not found" with an alert and a "Back to Create Song" link. Verified against the real backend in E2E (exactly one response, none afterwards).

## 11. Accessibility

Single `h1` per state; status headline and message sit in an `aria-live="polite"` region (`aria-atomic`) so changes are announced; FAILED and not-found use `role="alert"`; connection problem uses `role="status"`; steps are an `<ol>` with `aria-current="step"` and visible text ("done", "in progress", "waiting") in addition to icons, so nothing depends on color alone; decorative icons are `aria-hidden`; the spinner and pulse honour `prefers-reduced-motion` (`motion-reduce:animate-none`); the only interactive control is a normal link. Verified with Testing Library queries and code review; no screen-reader or axe run was done.

## 12. Tests

**Frontend: 51/51 vitest pass** (up from 19), `tsc` and `eslint` clean, `next build` succeeds. New: 13 hook tests (`use-job-status.test.ts`) and 19 component tests (`job-tracker.test.tsx`), plus the earlier Step 14 tests. They cover: initial fetch to `GET /api/jobs/{id}`; CREATED/SUBMITTED/QUEUED/RUNNING/COMPLETED/FAILED rendering; polling continuing and then stopping on COMPLETED and FAILED; skip-ahead; no overlapping requests (a pending request blocks further ones); unmount cleanup (timer cleared, in-flight request aborted, no state update afterwards); temporary network error and 5xx without a FAILED state; backoff schedule and cap; 404 stop; refresh/direct navigation restarting from the backend; safe rendering (no traceback, path, `ace-step`, provider job id, `absolute_path`, transport URL, filename); no numeric progress; no audio element, play or download control. All use mocked `fetch` with fake timers; no GPU. As a check that the tests actually bite, reintroducing an interval-style poll made 8 hook tests fail, and it was reverted.

## 13. E2E Test

Playwright against the real stack (Next.js dev → FastAPI → ACE-Step), **3/3 passed**; the first test took about 25 seconds:

1. Create a real instrumental generation from the form; land on `/jobs/<id>`; see a real Tunora state ("generating" or "complete") and the remembered prompt; **reload the page mid-run** and confirm it still tracks and shows the same job id; wait (up to 150 s, not a fixed duration) until the heading becomes "Generation complete"; the backend agrees (`COMPLETED`); no `<audio>` element exists; after the terminal state the number of status responses stays constant for three polling intervals (polling stopped).
2. Unknown id `/jobs/tunora-does-not-exist` shows "Job not found" and produces exactly one status response.
3. No horizontal overflow at 375 px on Create Song.

Findings while writing them: React StrictMode (dev only) mounts effects twice, so the browser starts and aborts one extra request on load; the E2E counts completed responses, not requests, and production builds do not do this. My first version of the 404 check also mistakenly counted the page navigation itself; the log timestamps showed it.

Not covered by real E2E: a backend that dies mid-job (connection-problem UI is covered by mocked tests only) and the FAILED path against a genuinely failing generation.

## 14. Known Limitations

- **Backend restart mid-job leaves the job non-terminal forever.** Step 12 has no resume-on-startup, so the UI would show "Generating" and poll indefinitely (every 2 s, since the API keeps answering). This is a backend gap the tracking UI cannot fix or detect.
- **The API still returns the raw `error` string** in `JobResponse` (Step 12/13 behavior). The UI never displays it, but the value is reachable by anyone calling the API; scrubbing belongs in the backend and was out of scope here. The `provider` name is also in the payload but not displayed.
- **Multiple tabs poll independently**; each is correct, nothing is coordinated, traffic is per tab. Sharing one poll across tabs is not implemented.
- **No pause while the tab is hidden**; polling continues in background tabs (browsers may throttle timers).
- **Request summary is per tab** (`sessionStorage`); a directly opened URL shows no prompt.
- **FAILED gives no reason and no retry action** beyond returning to Create Song.
- **Job history is not reachable** other than by URL until the Library exists.
- **No numeric progress**, by design.
- The "under a minute" message may be wrong for long durations.

## 15. Future Realtime / SSE Consideration

Not implemented. If polling cost or latency ever matters (many concurrent users, multiple tabs, long jobs), the natural next step is a `GET /api/jobs/{id}/events` Server-Sent Events endpoint fed by `JobService` state changes; SSE fits better than WebSockets because the traffic is one-way and it reconnects natively. It would also be the point to reconsider TanStack Query for cache sharing across tabs/views. None of that is justified by the current single-user, single-GPU MVP.
