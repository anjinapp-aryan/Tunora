# Phase 26 — Unified Creation Workflow (Audio Only / Audio + Video / Lyrics Video)

## 1. Objective

Phase 26 makes "what do you want to create?" the first decision on the Create page. It offers three choices:

- 🎵 **Audio Only**
- 🎬 **Audio + Video**
- 🎤 **Lyrics Video**

Each choice runs the existing pipeline in the fixed order **AUDIO → VERSION → VIDEO**:

- A video is made from the *exact* Version that the song generation creates.
- A video failure never fails the audio.
- "Create a video later" (Path A from Phase 24) still works exactly as before.

## 2. Starting point (Phases 23–25)

The phase builds on what Phases 23–25 already delivered:

- **Domain.** A `Song` has immutable `Version`s. A Version's audio is its primary asset. A `MusicVideo` is a derivative of **one** Version. Its `song_id` and `source_version_id` are enforced by DB triggers: same song, and the source is immutable.
- **Generation.** `POST /api/jobs` creates the Song, Version and Job in one transaction *before* calling ACE-Step. It returns `song_id` and `version_id` immediately.
- **Music Video lifecycle.** `MusicVideoService` covers `create`, `generate` (one render at a time), `retry` (in place, for FAILED only), `delete` (finished only) and restart recovery.
- **Visual styles.** Minimal, Dreamy, Bold, Cinematic and Karaoke, rendered with libass and LGPL FFmpeg.
- **User interface.**
  - The job page offers "Open song" and "Create a music video (optional)".
  - Song Details has a Music Videos section per selected Version, with Retry and Delete.

**The missing piece:** the user could not ask for a video *with* the song. They had to wait for the audio, open the song, and start a second flow.

## 3. Fresh OSS audit

The audit was run live against the GitHub API on 2026-09-28 (licenses verified via the API). It covered three areas:

- dependent-job and workflow libraries, for "run B after A";
- wizard and stepper UI, for the three-choice start;
- media-workflow prior art.

Hugging Face was not searched: no model is involved, and the phase only chains existing steps.

## 4. Candidates

| Candidate | License | Activity | What it offers | Decision |
|---|---|---|---|---|
| `coleifer/huey` | MIT | 6.0k★, pushed 2026-09-15 | Task queue with SQLite storage and pipelines (`.then()`) | **REJECT.** It needs a separate consumer process and its own task tables beside Tunora's job state machine. The one dependency here is a single "wait for this Version's audio" check. |
| `litements/litequeue` | MIT | 234★, 2026-07-31 | Minimal SQLite queue | **REJECT.** A queue adds nothing: the job and video tables already hold all state. |
| `Bogdanp/dramatiq` | LGPL-3.0 | 5.3k★ | Actor-based task queue with pipelines | **REJECT.** It needs a broker (Redis or RabbitMQ), which the project rules forbid. |
| `celery/celery` | BSD (NOASSERTION via the API) | 28.9k★ | Chains and chords | **REJECT.** It needs a broker, which the project rules forbid. |
| `PrefectHQ/prefect` | Apache-2.0 | 23.9k★ | Workflow orchestration | **REJECT.** It is a server plus a runtime, far heavier than one dependent step. |
| `temporalio/temporal` | MIT | 23.3k★ | Durable workflows | **REJECT.** It needs a separate cluster and service. |
| `damianricobelli/stepperize` | no license file (the API returns 404) | 1.6k★ | React stepper hooks | **REJECT.** The license is unclear, and a stepper is the wrong shape: three choices, one form. |
| `mantinedev/mantine` (Stepper) | MIT | 31.8k★ | Stepper component | **REJECT.** It would be a second UI kit beside shadcn/Base UI. |
| `Remy349/shadcn-ui-multi-form` | MIT | 74★ | Multi-step shadcn form example | **REFERENCE only.** Tunora needs a single page, not multiple steps. |

## 5. Decisions (REUSE → ADAPT → COMPOSE → BUILD)

**Reused:**

- `POST /api/jobs`, unchanged;
- `POST /api/songs/{id}/music-videos`, the renderer, the aligner, the styles and retry/delete;
- `MusicVideoCard`, `useMusicVideos`, `useJobStatus`;
- the sessionStorage "remember for the job page" pattern (`rememberJobPrompt`).

**Adapted:**

- **Music-video create** gains one optional flag, `wait_for_audio`, and one state, `WAITING_FOR_AUDIO`.
- **`MusicVideoCard`** is exported and gains `canRetry`.
- **Restart recovery** now resumes a waiting video instead of failing it.

**Composed:** the Create page calls the two existing endpoints in order.

**Built (small):**

- the `CreationIntent` module (frontend only);
- the three-card picker, using native radio inputs;
- the video options fieldset;
- the job page's video stage;
- `JobService.version_audio_state`.

**No new dependency** (backend or frontend) was added.

## 6. Architecture decision

- **CreationIntent is a frontend-only workflow choice** (`frontend/src/lib/creation-intent.ts`). It is never sent to the backend and never persisted. A song or video made through any intent is indistinguishable from one made through the older flows, so there is nothing to migrate and nothing to keep in sync.
- **There is no `CreationWorkflowService`.** The two existing endpoints already express the workflow:
  1. `POST /api/jobs` creates the Song, Version and Job and returns `version_id`.
  2. `POST /api/songs/{song_id}/music-videos?source_version_id=<that id>&wait_for_audio=true` creates the video.

  The only missing capability was accepting a Version whose audio does not exist *yet*. That belongs in `MusicVideoService`, which already owns the video lifecycle. A combined endpoint would have needed multipart parsing (a new dependency) or two uploads. It would also have duplicated validation.
- **The dependency is enforced on the server, not in the browser.** The browser uploads the background immediately, then the server waits for the audio. Closing the tab, navigating away or restarting the backend cannot lose the video request, and nothing depends on the page staying open.

**API decision (summary):** the existing APIs are reused. There is one additive optional query flag, `wait_for_audio` (default `false`, so the Phase 23–25 behaviour is unchanged), and one additive status value. There are no schema migrations, because `status` is a free TEXT column.

## 7. CreationIntent

| Intent | Submit label | Requests sent | Default style | Styles offered |
|---|---|---|---|---|
| `AUDIO_ONLY` | Generate Song | `POST /api/jobs` only | — | — |
| `AUDIO_AND_VIDEO` | Generate Song + Video | `POST /api/jobs`, then create video (`wait_for_audio=true`) | Cinematic | Cinematic, Karaoke, Minimal, Dreamy, Bold |
| `LYRICS_VIDEO` | Generate Song + Lyrics Video | same as Audio + Video | Karaoke | Karaoke, Cinematic, Bold, Minimal |

- **Lyrics Video** is the same pipeline with a lyric-first preset. It uses no second renderer and no new style. Dreamy is left out because its soft glow is the least legible for singing along.
- **Allowlists.** `isCreationIntent` is an allowlist. `styleForIntent` only ever returns a style the intent offers (anything else falls back to the intent's default), and the backend still rejects unknown styles with a 422.

## 8. Backend changes

- **`MusicVideoStatus.WAITING_FOR_AUDIO`** is a new state that comes before PENDING.
- **`JobService.version_audio_state(song_id, version_id)`** returns `"ready"`, `"pending"` or `"failed"` for one *exact* Version of that song. It raises for an unknown Version or another song's Version (so cross-song references are rejected), and it never modifies anything.
- **`MusicVideoService.create(..., wait_for_audio=False)`:**
  - A ready Version becomes a normal PENDING video.
  - A Version whose job is still running becomes a WAITING_FOR_AUDIO video.
  - A Version whose job ended without audio is rejected with a 409.
  - All existing checks still run before anything is stored: style and aspect allowlists, media type, magic bytes, decode check, lyrics required, instrumental rejected, one in-progress video per Version.
- **`generate` / `_await_audio`.** A waiting video polls `version_audio_state` every 2 s. It does this **outside the render lock**, so another video can render meanwhile.
  - If the audio is ready, the video moves to PENDING and renders from that Version's stored audio.
  - If the audio failed or the Song was deleted, the video becomes FAILED with the code `source_failed`. Its public message is "The song's audio could not be generated, so this video was not made."
  - If the service is stopping, the wait ends and the video stays WAITING_FOR_AUDIO.
- **`start_waiting(id)`** runs the wait on a daemon thread, not in the request's BackgroundTask, so a minutes-long wait never holds up a server shutdown. **`stop()`** is called from the lifespan `finally` and ends every wait.
- **Restart:**
  - `recover_interrupted()` now fails only PENDING, ALIGNING and RENDERING videos, because a render subprocess cannot resume.
  - `resume_waiting()` restarts the wait for WAITING_FOR_AUDIO videos. Job recovery (Phase 16) resumes their song's job, so a video requested with a song survives a backend restart.
- **Route.** `POST /api/songs/{id}/music-videos` accepts `wait_for_audio: bool = False`. It is validated by FastAPI, so `"maybe"` returns a 422.

## 9. Frontend changes

- **`CreationIntentPicker`** asks "What do you want to create?" with three cards. Each card is a label around a visually hidden native radio, so it has native keyboard, focus-ring and screen-reader semantics. It sits above the AI Song Director, so it is the first decision on the page.
- **`CreationVideoOptions`** appears only for a video intent. It holds:
  - the background file input, with the same allowlist and size limits as Song Details;
  - the Style select, listing only the intent's styles with its preset first;
  - a note that the video is made from this song's exact new Version once its audio is saved.
- **`CreateSongForm`** changes for video intents:
  - the Lyrics label drops "(optional)";
  - Instrumental is disabled, with an explanation;
  - `videoIneligibleReason` plus `validateBackground` run **before** the song starts, so a bad choice never costs a GPU generation.
- **Submit order.** On submit the form calls `createJob`, then `createMusicVideo({ sourceVersionId: job.version_id, waitForAudio: true })`. If the video request is refused after the audio has started (for example an undecodable background), the song still continues. The message is remembered per tab (`rememberJobVideoError`) and shown on the job page.
- **Job page (`JobMusicVideo`).** Below the audio stage, a "Music video" stage shows the video(s) made from **this job's Version**, filtered by `source_version_id`.
  - It uses the same card as Song Details: "Waiting for the audio…", "Aligning lyrics…", "Rendering…", "Completed" with a player and Download MP4, or "Failed" with Retry and Delete.
  - Retry is hidden when the song's own audio failed, because there is nothing to render from.
  - For Audio Only nothing is shown.
  - The "Create a music video (optional)" link (Path A) is kept.
- **Song Details** already separates the two assets per selected Version ("Audio: Ready" and "Music video: …"). `videoStateFor` now counts WAITING_FOR_AUDIO as "In progress…".

## 10. Invariants and how they are enforced

| Invariant | Enforced by |
|---|---|
| Audio Only never creates a video | The form sends no video request (unit test and E2E #1). Existing backend test: audio-only generation creates no video rows or files. |
| AUDIO → VERSION → VIDEO order | The video can only reference an existing `version_id`, returned by `POST /api/jobs`. The render starts only when `version_audio_state == "ready"`. |
| Exact Version, never "latest"/"v1" | `source_version_id` comes from the job response. `version_audio_state` looks up that id only (unit, API and E2E tests). |
| Video failure never fails the audio | Video state lives only in `music_videos`, and the job and Version are never written. Covered by `test_a_video_failure_after_the_audio_leaves_the_audio_and_retry_reuses_it` and E2E #4. |
| Retry Video reuses the same Song/Version/audio | Unchanged Phase 24 `retry`: same id and Version, no Job or Version created, audio byte-identical (unit test and E2E #4). |
| Delete Video keeps the audio | Unchanged Phase 24 `delete` (E2E #5 on the job page). |
| Multiple videos per Version | Unchanged: one *in progress* at a time, any number finished. |
| Cross-song Version rejected | `version_audio_state` raises `SourceVersionNotFoundError` (a 404), and the DB trigger stays in place. |
| "Create video later" preserved | `wait_for_audio` defaults to false. Without it, a Version still generating is rejected as before (unit test). The job-page link is unchanged. |

## 11. Security

- **Intent:** frontend allowlist; never sent to the backend.
- **Style:** frontend per-intent allowlist, backend `Literal` plus `STYLES` check.
- **`wait_for_audio`:** a strictly typed bool.
- **IDs:** validated by pattern. `version_audio_state` re-validates them and checks that the Version belongs to the Song.
- **Background upload:**
  - unchanged size caps and media-type allowlist;
  - magic-byte check;
  - FFmpeg `-xerror` single-frame decode check at create time, which runs even while waiting;
  - the renderer's policy-checked LGPL FFmpeg, with `-protocol_whitelist file`, `file:` inputs and no shell.
- **Lyrics:** still escaped by `ass_builder.escape`; this phase did not change ASS handling.
- **Paths:** no endpoint accepts a path. The waiting response exposes no internals (the API test asserts no background key or tmp path appears).
- **Error text:** `source_failed` maps to a fixed sentence, so provider errors (for example "gpu oom") never reach the UI (unit test).

## 12. Tests — backend

The new file is `backend/tests/music_videos/test_creation_workflow.py` (12 tests):

- waits for the exact new Version, then renders it; one audio generation only; audio byte-identical;
- a ready Version skips waiting;
- without `wait_for_audio`, a Version still generating is still rejected (Path A unchanged);
- the audio fails: the video fails safely with a fixed message and cannot be retried;
- the video fails after the audio: audio and job untouched; retry reuses the same audio; no new Job or Version;
- cross-song and unknown Versions rejected, with nothing stored;
- instrumental or lyric-less songs rejected, with nothing stored;
- one waiting video per Version; a waiting video cannot be deleted;
- waiting never holds the render lock; `stop()` leaves the video resumable;
- restart fails interrupted renders but resumes waiting videos, which then complete;
- deleting the Song while waiting ends the wait quietly;
- API: `wait_for_audio=true` returns 202 `WAITING_FOR_AUDIO` and uses `start_waiting`, not the BackgroundTask. Another song's Version returns 404, a non-bool flag 422 and an unknown style 422. No internals appear in the response.

Results: 12/12 passed. Music video suite 119 passed. Full backend (`-m "not smoke"`): **775 passed**, 17 deselected (smoke), 57.7 s.

## 13. Tests — frontend

- **`creation-intent.test.tsx` (new, 10 tests):**
  - intent allowlist;
  - per-intent style mapping and fallbacks;
  - vocals and lyrics required;
  - the page asks first and defaults to Audio Only;
  - Audio Only sends no video request;
  - Audio + Video sends `/api/jobs` first, then the video with the exact `version_id`, `cinematic` and `wait_for_audio=true`;
  - Lyrics Video uses `karaoke` with lyric-first styles only;
  - a missing background or lyrics is blocked before any generation;
  - Instrumental is disabled for video intents;
  - a failed video start still navigates and tells the job page.
- **`job-tracker.test.tsx` (+4 tests):**
  - the video stage shows only this Version's video, "Waiting for the audio…";
  - audio complete with a failed video offers Retry;
  - no Retry when the audio failed;
  - a start error is shown.

  One existing assertion was intentionally widened: the completed job page now also makes a read-only `GET /api/songs/{id}/music-videos`. It is still asserted that every request is a GET, so nothing is started.
- **`create-song-form.test.tsx`:** four `getByLabelText(/lyrics/i)` queries became `getByRole("textbox", { name: /lyrics/i })`, because the new "Lyrics Video" card also matches the old query. The assertions themselves are unchanged.
- **`music-videos.test.tsx` (+1 test):** a waiting video counts as "In progress…" for its own Version only.

Results: Full Vitest: **425 passed / 24 files**. `npm run typecheck` clean. `npx eslint`: 0 errors, 1 pre-existing warning (an unused `request` in `e2e/create-song.spec.ts`, which this phase did not touch).

## 14. Tests — real E2E

`frontend/e2e/creation-workflow.spec.ts` runs in real Chrome against a real ACE-Step, a throwaway backend on :8010 and Next on :3100. Nothing is mocked.

- **#1 Audio Only:** three cards, Audio Only by default, no overflow at 375 and 768 px, an instrumental song, player shown, no video stage, no video rows, Path A link present.
- **#3 Lyrics Video:** karaoke preset, Instrumental disabled, no overflow, song then video on the job page, "From Version 1 · 9:16 · Karaoke", exactly one Version.
- **#5 Delete video (same song as #3):** deleted from the job page; audio bytes and Versions unchanged; player still present.
- **#2 Audio + Video:**
  - the video exists immediately, bound to the job's `version_id`;
  - audio saved, then the video completed;
  - real playback in Chrome at 1080×1920 with time advancing;
  - Song Details shows Audio Ready and Music video Ready;
  - one Version; no internals in the API output.
- **#4 Video fails, then Retry:** the stored background is corrupted *while the video waits for the audio*. The audio completes, the video fails with "Music video generation failed.", and Retry on the job page completes it. Same video id and Version; audio byte-identical.

Results: **5/5 passed in 2.5 min** (run 3).

- **Run 1** failed at `locator.check()` on the visually hidden radio: Playwright cannot click a 1 px `sr-only` input that an icon overlaps. This was a test-harness issue, not a product bug; real users click the card. The spec now clicks the card (`getByTestId("intent-…")`) and asserts that the radio inside becomes checked.
- **Run 2** could not start because a Next dev server orphaned by stopping run 1 was holding :3100. It was killed and the tests re-run.

Backend log for run 3:
- the waiting phase lasted about 18–20 s per 60 s song (from `music video created` to `source audio ready`);
- one audio generation per test;
- the retry in #4 re-rendered the same video id from the same Version.

## 15. Regression

| Suite | Result |
|---|---|
| Backend unit/integration (`-m "not smoke"`) | 775 passed |
| Backend real-GPU music video smoke (`tests/test_music_video_smoke.py -m smoke`) | 1 passed (39.4 s) |
| Frontend Vitest | 425 passed |
| Typecheck | clean |
| ESLint | 0 errors (1 pre-existing warning) |
| `next build` (separate dist dir) | succeeded, all routes built |
| E2E `music-video.spec.ts` + `create-song.spec.ts` (real stack, Chrome) | **25 passed** (12.5 min) |
| E2E `creation-workflow.spec.ts` (new) | 5 passed |

Not re-run: other E2E specs unrelated to the Create page, job page or music videos. Backend smoke tests other than the music video one were not run in this phase.

## 16. Real GPU validation

All generations below were real ACE-Step generations: 60 s vocal songs using the Phase 22–25 vocal prompt, except #1, a short instrumental.

- **Hardware and runtime:**
  - GPU: NVIDIA GeForce RTX 5060 Ti, 16 GB (driver 591.86).
  - VRAM in use after the Phase 26 run, with the ACE-Step server resident: 11,405 / 16,311 MiB.
  - Local LGPL FFmpeg; Whisper base (CPU) for alignment.
- **Audio + Video (E2E #2, MP4 background, Cinematic):**
  - audio ready about 18 s after the request;
  - video rendered in 12.3 s;
  - 4 lines matched and 1 unmatched (one sung line not recognised; this is the documented provider/alignment limitation);
  - played in Chrome at 1080×1920.
- **Lyrics Video (E2E #3, JPG background, Karaoke):**
  - audio ready about 18 s after the request;
  - rendered in 13.2 s;
  - 5/5 lines matched.
- **Retry (E2E #4, PNG, Cinematic):**
  - the first render failed on the corrupted background, as intended;
  - the retry rendered in 12.9 s with 5/5 lines matched, audio byte-identical.
- **Audio Only (E2E #1):** instrumental, completed, no video work at all.
- **Regression renders** (Phase 23/24 specs): 15.0–16.1 s each.

Audio quality, vocals and lyric pronunciation were not judged here; that needs human listening. Only the objective facts above are claimed.

## 17. Responsive behaviour

The three cards form a single column below `sm` (640 px) and three columns above it. The video options fieldset and the file input are `min-w-0`/`max-w-full`. E2E #1 and #3 assert no horizontal overflow at 375 px and 768 px on the Create page (including the video options for #3), and they run at 1280 px desktop.

## 18. Performance

- Waiting costs one small SQLite read every 2 s per waiting video, on a daemon thread.
- Renders are still serialized by the existing lock, and the waiting thread never holds it.
- There is no change to render time: same renderer, same styles. Measured times are in §16.

## 19. Backward compatibility

- Every existing endpoint, response field and default is unchanged. `wait_for_audio` is optional and defaults to false.
- The status enum gained one value. Old clients see it only for videos created with the new flag.
- There is no DB migration (the schema stays at v6).
- The Phase 23/24/25 E2E and unit suites run unchanged, except for the test-query adjustments listed in §13.

## 20. Known limitations

- A lyric video needs vocals and lyrics, so an instrumental song cannot use the video intents. A visual-only video for instrumentals is deferred.
- ACE-Step can occasionally return a near-instrumental take for a vocal prompt. The video then fails with "None of this version's lyrics could be matched to its audio." This is the documented provider limitation, not a Tunora bug. Retry does not help; a new song generation does.
- If the video request itself is refused after the audio started (for example the background passes the browser checks but not the server's decode check), the message is kept in sessionStorage. In another tab the job page simply shows no video stage, and the song page's Create Music Video still works.
- A video whose source audio failed cannot be retried. Its message says why, and Retry is hidden on the job page. In Song Details, Retry returns the backend's 409 message.
- Only 9:16 is available, as in Phase 23.

## 21. Deferred work (not in this phase)

- A visual-only (no lyrics) video for instrumental songs.
- Choosing an intent for an *existing* song from Song Details; Path A already covers this with the full form.
- Cancelling a waiting video before its audio finishes (today: delete the song, or let it finish and delete the video).

## 22. Final architecture decision

**COMPOSE the existing endpoints, with one additive ADAPT.**

- The Create page's `CreationIntent` decides whether a second, existing request (create a Music Video of the exact new Version) follows `POST /api/jobs`.
- The backend's only new capability is `wait_for_audio`. It lets a Music Video be recorded before its Version has audio and render after it does, outside the render lock and resumable across restarts, without ever touching the audio.
- There is no CreationWorkflowService, no queue or workflow engine, no second renderer, no new dependency and no migration.
