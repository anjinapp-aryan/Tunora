# Phase 28 — Revise & Retry

## 1. Problem

The Phase 28 product audit (`docs/PHASE-28-PRODUCT-AUDIT.md`) found two gaps in the core loop, create → listen → change → generate again:

1. **No way to revise a song.** The backend could already make a new Version of an existing Song with a different spec (`POST /api/jobs` with `song_id`), but no screen ever sent it. After listening, a user who wanted to change the prompt, lyrics or settings could only:
   - start a new song, which loses the song identity and history;
   - use Another Take, which keeps the same inputs;
   - use Remix or Repaint, which are audio-conditioned.
2. **A failed generation lost the user's input.** The failure page linked to an empty Create form, although the inputs were already stored in the failed Version's snapshot. USER-JOURNEYS "Key interaction 4" requires a retry without re-entering fields.

## 2. Product rationale

A **Song** is the identity; a **Version** is an immutable attempt. Revising a song must therefore append a Version, never overwrite one. Recovering from a failure must return the user's own inputs.

Both needs are one mechanism: open the existing Create form on **one explicit Version's stored inputs**, let the user change anything, and generate a **new Version of the same Song**.

## 3. Existing backend capability discovered

| Piece | Where | Reused as |
|---|---|---|
| New Version of an existing Song with its own spec | `JobService.create_and_submit(..., song_id=…)` creates Song + Version + Job atomically and commits before ACE-Step is called | The generation path, unchanged |
| Lineage (`operation`, `source_version_id`, `operation_params`) with immutability and same-song DB triggers | migration v3 | Revision lineage |
| Every Version stores its generation inputs (prompt, lyrics, language, duration, seed, instrumental), **including failed Versions**, because they are written before submission | `Version.spec`, `_base_spec` | The prefill for Revise **and** for Retry. No new persistence was needed (§14 of the prompt). |
| Fresh text-to-music operation beside ORIGINAL (Another Take) | `_TEXT_TO_MUSIC_OPERATIONS` | Pattern for `REVISE` |
| Restart recovery of in-flight jobs by persisted provider id | Phase 16 | Unchanged; covers revisions |
| Create form (react-hook-form + zod), `setValue` prefill from the Director plan, the refine panel | `create-song-form.tsx` | One form in three modes |
| The Library lists a song once and counts its playable Versions | `list_song_summaries` | Unchanged; a revised song stays one row |

What was missing:

- the UI to open the form on a Version;
- lineage for a revision (an edited spec was only possible as ORIGINAL, without a source);
- a Retry path on the failure page;
- the requested duration in the Song API. It only returned the measured audio length, which a failed Version does not have.

## 4. OSS audit (2026-09-29)

| Candidate | License | Decision | Reason |
|---|---|---|---|
| Tunora's own `POST /api/jobs` + `song_id`, lineage, Version spec | — | **REUSE** | It already implements "new Version from a spec" atomically, with recovery. |
| react-hook-form `defaultValues` (already a dependency) | MIT | **REUSE** | Prefilling a form from stored values is its built-in feature, so no form-state library is needed. |
| TanStack Query / SWR "retry" | MIT | **REJECT** | Those retry *requests*. Tunora needs a new *generation attempt* with user-editable inputs, which is domain logic. Tunora also polls by hand by design (Phase 3). |
| `react-hook-form-persist`, `use-local-storage-state` (browser form persistence) | MIT | **REJECT** | The inputs are already persisted server-side in the Version snapshot. A browser copy would duplicate them, would not survive another device or tab, and could drift from the truth. |
| Stepper/wizard form kits (e.g. Stepperize, Mantine Stepper) | no license / MIT | **REJECT** | One page, one form. It was already rejected in Phase 26. |
| Versioned-draft patterns (git-like immutable revisions) | — | **REFERENCE** | They confirm the model Tunora already uses: an immutable snapshot plus a pointer to its source. |

No new dependency was added, backend or frontend.

## 5. Architecture

```
Song Details: [Revise Version N]   /   Failed job page: [Retry / Revise]
          │  /create?song=<songId>&version=<versionId>   (ids only, validated by pattern)
          ▼
ReviseSong (client) ── GET /api/songs/{songId} ── finds THAT version (not latest, not first)
          │           RETRY if its status is FAILED, else REVISE; extracted tracks refused
          ▼
CreateSongForm(source)  ← the same Create form; prefilled via revisionDefaults(version)
          │  POST /api/jobs {song_id, source_version_id, prompt, lyrics, language, duration, seed, instrumental}
          ▼
JobService.create_revision ── validates song, version ∈ song, not EXTRACT, non-empty prompt
          │  operation=REVISE, source_version_id, operation_params={"changed": [...]}
          ▼
create_and_submit (unchanged) ── Song(existing) + Version(n+1) + Job, commit, then ACE-Step text2music
          ▼
run_until_terminal / restart recovery (unchanged) ── the new Version gets its own FLAC
```

## 6. Revise workflow

1. In Song Details, select any Version, then click **Revise Version N**. The link sits in the selected Version's panel and is shown for completed, failed and in-progress Versions. Extracted tracks don't get it.
2. The Create page opens as **"Revise song"**. A context line reads: "Revising *Title* from Version N … This creates a new version of the same song; Version N is not changed."
3. Version N's prompt, lyrics, language, duration, vocal/instrumental and seed are prefilled. The seed is under Advanced options, which opens automatically when a seed is stored.
4. The user edits anything. The AI refine panel ("describe a change") works on the prefilled spec. The new-song Director is hidden, and so are title and project, because a Version has neither: the song keeps both.
5. **Generate New Version** creates Version N+1 of the same Song and opens its job page, where the new audio plays. The Phase 26 intents also work here (Audio + Video / Lyrics Video on the revised Version).

## 7. Retry workflow

1. A failed job page shows **Retry / Revise** as its primary action, with the note "Your description, lyrics and settings are kept …". The fresh start is renamed "Start a new song instead".
2. The Create page opens as **"Retry generation"**, prefilled from the failed Version's stored inputs.
3. **Retry Generation** submits the inputs as they are, or changed. The result is a **new Job** and a **new Version** of the same Song (`REVISE` from the failed Version). The failed Job and Version stay exactly as they were: status FAILED and unchanged history.
4. If the retry also fails, its own failed page offers Retry / Revise again with the **latest** inputs, because it links to the retry's own Version.

## 8. Version semantics

```
Song A
 ├── Version 1  ORIGINAL                     (untouched)
 ├── Version 2  REVISE · from Version 1      prompt changed
 ├── Version 3  REVISE · from Version 1      lyrics changed (explicitly revised from V1, not the latest)
 └── Version 4  REVISE · from Version 2      duration changed
```

**Revise vs Retry** — both are the same operation, `REVISE`, because both are "a fresh generation from one Version's inputs". The distinction is recorded, not guessed:

- `operation_params.changed` lists the fields that differ from the source;
- an empty list is a retry (identical inputs);
- a non-empty list is a revision.

The UI names the action from the source's state: **Retry / Revise** for a failed source, **Revise** otherwise. History shows "Revision · from Version N".

Other rules:

- A revision copies nothing from the source at generation time except what the user submits. `batch_size` is never taken, so one output always becomes one Version.
- Extracted tracks cannot be revised (the same rule as Another Take). Revise the Version they came from instead.

## 9. Prompt, lyrics and settings handling

| Field | Prefilled from | Notes |
|---|---|---|
| Prompt | `version.prompt` | Required, trimmed. An empty prompt is rejected (422). |
| Lyrics | `version.lyrics` | Cleared for instrumental Versions, as in Create. |
| Language | `version.language` | Falls back to English only if the stored value is not one of the form's 11 languages. |
| Duration | `requested_duration`, the **requested** length and new in the API; falls back to the audio length | Snapped to the form's offered lengths (30/60/120/180 s), exactly as the Director's suggestions are. |
| Vocals / Instrumental | `version.instrumental` | — |
| Seed | `version.seed` | Blank means random, as in Create. |

Title and project belong to the Song and are not part of a revision. No new setting was invented.

## 10. API changes

- **`POST /api/jobs`** accepts an optional `source_version_id`. The pattern is validated, and it requires `song_id` (otherwise 422). With both present the request is a Revise/Retry, handled by `JobService.create_revision`:

  | Condition | Result |
  |---|---|
  | Unknown song | 404 |
  | Unknown version, or a version of **another song** | 404; the DB trigger also refuses it |
  | Malformed id | 422 |
  | Empty prompt, or an extracted-track source | 422 |
  | Otherwise | 200 with the new Job (same `song_id`, new `version_id`, next `version_number`) |

  Without `source_version_id` the endpoint is unchanged.
- **`GET /api/songs/{id}`**: each Version gains `requested_duration`. This is additive; the two exact-key allowlist tests were updated to include it.
- **Provider:** `REVISE` is a supported operation and plain text-to-music (no source audio), exactly like `ANOTHER_TAKE`.

## 11. UI changes

- **Create page:** `?song=&version=` renders `ReviseSong`, which loads the song, finds the Version and shows "Revise song" or "Retry generation". Otherwise the page is unchanged.
- **`CreateSongForm`:** one component with an optional `source`. Create mode is unchanged. In Revise/Retry mode it:
  - prefills the fields;
  - shows the context line;
  - hides the Director, title and project;
  - shows the refine panel;
  - uses the submit labels "Generate New Version" or "Retry Generation";
  - sends `song_id` + `source_version_id`.
- **Song Details:** a "Revise Version N" or "Retry / Revise Version N" link on the selected Version.
- **Job page (failed):** a "Retry / Revise" primary action; the fresh start is renamed "Start a new song instead".
- **History and comparison:** the new operation name "Revision".

## 12. Database changes

**None.** The schema stays at v7. `REVISE` is a new value in the existing free-text `operation` column. Lineage uses the existing `source_version_id` and `operation_params` columns, and their existing triggers (immutable lineage, same-song source) cover revisions.

## 13. Error handling

- **Deleted song:** the Create page shows "We couldn't find that song …" and offers "Create a new song instead".
- **Unknown or deleted Version, or another song's Version:** "That version isn't part of this song any more." The backend also returns 404.
- **Extracted track:** refused, both in the UI message and by a backend 422.
- **Empty prompt:** blocked by form validation, and the backend returns 422.
- **Retry fails again:** a new failed Job, with Retry / Revise offered again.
- **Duplicate submission:** the submit button is disabled while a request is in flight, the same as Create. There is no server-side idempotency key, as before (§19).
- Messages are fixed strings; nothing internal is shown.

## 14. Restart recovery

A revision is an ordinary Job whose request is stored with `operation="REVISE"`. Phase 16 recovery therefore resumes it by its persisted provider id, without ever resubmitting it (unit test: `test_a_revision_in_flight_is_recovered_after_a_restart`). The real restart runs are in §18.

## 15. Security

- **The client sends only two ids** (song and version). They are pattern-checked in the page and at the API.
- **The server never trusts `source_version_id`.** `create_revision` checks that the Version belongs to the Song, and the `versions_source_same_song` trigger enforces it again in the database.
- **Prompt, lyrics and settings** go through the same request model and provider path as Create.
- No path is accepted or returned, no shell is used, and no dependency was added.

## 16. Tests

- **Backend:** new file `tests/songs/test_revise_retry.py` (9 tests):
  - a new Version of the same Song, with the source's row, spec, job and audio byte-identical;
  - it starts from the explicit Version, not the latest, and identical inputs record as a retry;
  - settings changes are recorded only on the new Version;
  - cross-song, unknown, malformed and empty-prompt requests are rejected with nothing written;
  - an extracted track is refused;
  - the provider runs REVISE as text-to-music;
  - a failed generation keeps its inputs, and its retry is a new Job and Version of the same Song while the old Job stays FAILED;
  - the API contract, errors and `requested_duration`;
  - a revision in flight is recovered after a restart, without resubmission.
- **Contract updates:** two exact-key allowlist tests now include `requested_duration`. One failed-page test uses the renamed "Start a new song instead" link.
- **Frontend:**
  - `revise-song.test.tsx` (6 tests): prefill mapping, retry vs revise, extract refusal, the encoded link; the explicit Version opens prefilled (not the latest) with clear context and no title or Director; the submit payload is exactly `{song_id, source_version_id, …edited fields}`; Retry mode; error states.
  - `song-details.test.tsx` (+2): the link follows the *selected* Version; failed Versions get "Retry / Revise"; extracted tracks get no link.
  - `job-tracker.test.tsx` (+1): a failed job links Retry / Revise to its own Version.

RESULTS_TESTS

## 17. E2E results

`frontend/e2e/revise-retry.spec.ts` runs on the real stack: real ACE-Step, the backend on :8010, Next, and Chrome.

- **#1 Revise prompt:** a Song (in a Project) → Song Details → select V1 → Revise. The form is prefilled, with no overflow at 375 or 768 px. The prompt is changed → Generate New Version → the job page completes and plays. The result is V2 `REVISE` from V1. V1 is field-for-field unchanged and its audio byte-identical. V2 has its own audio.
- **#2 Revise lyrics:** V1 is explicitly selected while V2 is the latest. The result is V3 from V1, with new lyrics and V1's prompt; V1's lyrics are unchanged.
- **#3 Revise settings:** duration 30 → 60 from V2 gives V4 from V2, `requested_duration` 60 and real audio longer than 45 s. The Library lists **one** song with 4 Versions, the Project still contains it, and Song Details shows 4 Versions.
- **#5 Revise Version 2:** V1 → V2 → (select V2) → V3. The V2 form was prefilled with V2's *own* prompt. The result is three completed Versions with three distinct audio files.
- **#4 Failed generation → Retry / Revise:** a real Tunora backend with an unreachable ACE-Step (on the same database) fails a generation through the normal provider-unavailable path. Then:
  - the failed job page offers Retry / Revise;
  - the form is back with prompt, lyrics, language `es`, duration 60 and seed 1234;
  - the duration is changed to 30 → Retry Generation → a real success;
  - the new Job differs from the failed one, the Song is the same, the failed Job is still FAILED, V1 is FAILED and V2 is COMPLETED from V1 with the retried inputs.

RESULTS_E2E

## 18. Real validation

RESULTS_REAL

## 19. Known limitations

- **Duration snapping.** The form offers 30/60/120/180 s, so revising a Version made with another length (e.g. an Extend result of 75 s) proposes the nearest offered length. The field shows it before the user submits.
- **Revise and Retry share one operation.** The difference lives in `operation_params.changed`, and the UI labels the action from the source's status. History shows both as "Revision · from Version N".
- **No server-side idempotency key.** A double submit is prevented only by the disabled button, as for Create.
- **No revision of extracted tracks.** Revise their source instead.

## 20. Deferred work (kept out of scope, from the product audit)

- Lyric-video timing reliability (unsung vs unaligned lines; ACE-Step's own timestamps).
- Storage hygiene (duplicated backgrounds, videos missing from the storage report, Version delete).
- Binding the frontend to localhost and running a production build.
- Housekeeping: stale CLAUDE.md, the untracked Phase 20 doc, the large `JobService`, the duplicated style lists, and the two drifting video forms.

None of these were touched. `create_revision` was added beside the existing operations and nothing else was moved.
