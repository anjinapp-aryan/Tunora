# Phase 10: Provider Metadata + Version Comparison

This is the implementation record for the MVP recommended by
`docs/PHASE-10-CAPABILITY-GAP-AUDIT.md` and explicitly accepted by the user.
It is not a rewrite of that audit.

## 1. Scope

**In scope and built:** surfacing the generation provider's own
bpm/genres/key_scale/time_signature (already computed and stored, previously
Job-only) on the Song/Version API, and a "Compare Versions" view on Song
Details that descriptively compares exactly two versions of the same Song
using two existing `AudioPlayer` instances plus the newly-surfaced metadata.

**Explicitly out of scope, not built:** RMS, peak, LUFS, sample rate,
channels, codec, bitrate, spectrograms, synchronized/linked playback,
crossfade, audio similarity/diff scoring, fingerprinting, embeddings,
BPM/key/genre/time-signature recalculation, any new provider, any new
database migration, any new dependency.

## 2. Audit reference

`docs/PHASE-10-CAPABILITY-GAP-AUDIT.md`, accepted MVP (its §21/Final
Decision): zero new dependencies, no migration, extend the existing
`GET /api/songs/{id}` response only.

## 3. Reuse decisions

- **REUSE**: `WaveSurfer.js`/`AudioPlayer` (mounted twice, once per
  comparison side, exactly as it is mounted once today); the existing
  Song/Version/lineage domain model, entirely unmodified; the existing
  `_public_result`/allowlist pattern in `app/api/schemas.py` (mirrored, not
  duplicated with different conventions); the existing version-selection UI
  pattern (radio list) for the single-version view; `operationLabel()`,
  `formatTime()`, `versionAudioResource()` — all reused unchanged in the new
  comparison component.
- **ADAPT**: `jobs.result_json` (already stores ACE-Step's own
  bpm/genres/key_scale/time_signature under `result["metadata"]`, exactly as
  `JobResponse` already exposed it) is now also read by
  `list_version_entries()` and surfaced on `VersionResponse.metadata`.
- **COMPOSE**: the Compare Versions feature itself — two version selectors +
  two `AudioPlayer`s + a metadata table + a descriptive diff, composed
  entirely from existing pieces.
- **BUILD (the true, minimal gap)**: the `VersionMetadata` domain type, the
  `_version_metadata_from_result()` extraction/allowlist helper, and the
  `VersionComparison` UI component. Nothing else.

## 4. Provider metadata mapping

Traced end to end before writing anything:

1. `app/providers/ace_step.py::get_result()` already builds
   `GenerationResult.metadata = {"bpm": ..., "genres": ..., "key_scale": ...,
   "time_signature": ..., ...}` from ACE-Step's own `primary["metas"]`
   (unchanged, not touched this phase). Missing values default to `""`
   (string fields) or `None` (`bpm`) — an existing, pre-Phase-10 provider
   convention.
2. `JobService` (unchanged) stores this under
   `job.result["metadata"]` when a job completes; `jobs.result_json` is a
   plain JSON text column, already durable and already 1:1 with the Version
   the job produced.
3. **New**: `app/jobs/repository.py::_version_metadata_from_result(result)`
   reads `result["metadata"]`, extracts exactly `bpm`, `genres`, `key_scale`,
   `time_signature`, normalizes `""` → `None` (ACE-Step's "missing" spelling
   unified to one spelling), and returns `None` entirely (not an empty
   object) when nothing was reported at all. Both
   `InMemoryJobRepository.list_version_entries()` and
   `SqliteJobRepository.list_version_entries()` call this and attach the
   result to the new `VersionEntry.metadata` field.
4. **New**: `app/songs/models.py::VersionMetadata` is the provider-neutral
   domain type (`bpm: Optional[float]`, `genres: Optional[str]`,
   `key_scale: Optional[str]`, `time_signature: Optional[str]`) — it carries
   nothing else, by construction, so it cannot leak `audio_url`, `prompt`,
   `lyrics`, or any other field.
5. `app/api/schemas.py::song_details_response()` builds a
   `VersionMetadataResponse` field by field from `entry.metadata` (or leaves
   `VersionResponse.metadata = None`), exactly matching the codebase's
   existing "never copy-then-delete, build field by field" convention.

Different provider results have different shapes only insofar as a future
provider might not populate `metadata` at all — that already degrades
correctly to `None`, since nothing about the extraction assumes any specific
provider produced the data (`GenerationResult.metadata` is already the
provider-neutral contract, see `app/providers/base.py`).

A failed job never has `result` set (`Job.result` is only populated on
completion, unchanged), so a Version whose job failed or is still running
naturally has `metadata = None` through the same code path — no special
case was needed.

## 5. API changes

`GET /api/songs/{song_id}` (and therefore `SongDetailsResponse`) gains one
new optional field per version:

```jsonc
"metadata": {
  "bpm": 92,               // or null
  "genres": "Pop",         // or null
  "key_scale": "A minor",  // or null
  "time_signature": "4/4", // or null
  "source": "provider"
}                            // or the whole object is null
```

No field was removed or renamed; `VersionResponse`'s prior 14 fields are
unchanged. No new endpoint was added or considered necessary — the
Comparison view (§6) reads the same `GET /api/songs/{id}` response the
existing Song Details page already fetches in full, since it already
contains every Version.

## 6. Comparison architecture

```
GET /api/songs/{id}   (existing, now richer)
        |
        v
SongDetailsView (existing)
        |
        +--> Provider Metadata section  (new, reads active version's metadata)
        |
        +--> "Compare Versions" toggle  (new)
                    |
                    v
             VersionComparison (new component)
               - Version A selector \  both existing NativeSelect,
               - Version B selector /  populated from `details.versions`
               - VersionColumn "a" -> existing AudioPlayer + metadata table
               - VersionColumn "b" -> existing AudioPlayer + metadata table
               - Descriptive diff table (arithmetic string comparison only)
```

All state (`comparing`, the two selected version ids) is local `useState` in
`SongDetailsView`/`VersionComparison` — no new state-management library, no
routing change, no new endpoint.

## 7. Player reuse

Each `VersionColumn` mounts one `AudioPlayer` (`key={version.id}`), exactly
as the single-version view already does — two independent WaveSurfer
instances, two independent downloads, two independent play/pause/seek
states. No synchronization, crossfade, or shared transport was built (out of
scope, §22 of the audit). A version with no stored audio shows the same
"Audio is temporarily unavailable" message the single-version view already
uses; the other side is unaffected.

## 8. Security

- Every version compared comes from the one `GET /api/songs/{id}` response
  the page already loaded — there is no new endpoint or parameter that
  accepts an arbitrary version id, so there is no new cross-Song attack
  surface to defend (verified, not merely asserted: `list_version_entries`
  is scoped by `song_id` in its `WHERE` clause, unchanged and re-tested).
- `VersionMetadata`/`VersionMetadataResponse` are built with an explicit
  4-field allowlist at the earliest possible point (inside the repository,
  before the object ever exists) — a raw `result_json` dict is never passed
  further than that one extraction function, and the API layer builds its
  response field by field, never `**dict`-style. `test_provider_metadata.py`
  proves both the extraction helper and the full HTTP response reject/never
  emit provider transport fields (`audio_url`, `prompt`, `lyrics`, task ids,
  internal paths) even when a test deliberately puts them in the input.
- Malformed provider data (wrong type for `bpm`, non-dict `metadata`, a
  legacy Job with no `metadata` key at all) is handled by dropping the
  offending field to `None`, never by raising — verified by parametrized
  tests covering bools, lists, dicts, and strings in place of expected types.

## 9. Testing

**Backend** (`backend/tests/songs/test_provider_metadata.py`, 30 tests):
the extraction helper in isolation (all-present, partial, absent, malformed
bpm, malformed strings, transport-field leak resistance); through the
domain/repository (a Version's own metadata, two sibling versions never
swapped, a version whose job never completed, a version with an empty
provider metadata dict, cross-Song isolation); through the full HTTP API
(shape with `source: "provider"`, null-when-absent, no leak of the full
`result_json` or provider internals, playback still works when metadata is
absent, backward-compatible field set). One pre-existing test
(`test_domain.py::test_the_song_domain_does_not_depend_on_any_provider`)
caught an early docstring wording mistake (mentioning "ACE-Step" by name in
the provider-neutral `app/songs/models.py`) — fixed before completion, a
real instance of the provider-independence rule doing its job.

Full existing backend suite after this phase: **512 passed, 10 deselected
(smoke)** — zero regressions (one pre-existing strict field-set assertion in
`test_song_api.py` was intentionally updated to include the new `metadata`
key, annotated as such, per this project's "never silently weaken a test"
rule).

**Frontend**: `version-comparison.test.tsx` (11 tests: default A/B
selection, each side's own metadata never swapped, each player bound to its
own audio URL — checked per-column, not just "both URLs appear somewhere",
same-version rejection with no players/metadata rendered, descriptive diff
with no score/ranking language, `data-differs` distinguishing changed vs.
identical fields, per-side unavailable-audio handling, duration from the
existing formatter, switching one side leaves the other untouched,
accessible labels, long genre strings). `song-details.test.tsx` gained 7
tests for the Provider Metadata section (present, partial, fully absent,
correct-on-switch, leak-free) and the Compare Versions toggle (hidden below
two versions, opens/closes an accessible panel). Two pre-existing tests'
leak-check regexes (`song-details.test.tsx`, `version-actions.test.tsx`)
were narrowed from the bare word `provider` to `provider_job_id`, because
"Provider Metadata"/"Provider-reported" is now intentional, required
disclosure copy (§7 of the governing prompt) — annotated inline as an
intentional contract change, not a weakened check (the check still fails on
any real internal provider identifier).

Full existing frontend suite after this phase: **337 passed** (Vitest),
`tsc --noEmit` clean, `eslint .` clean, `next build` clean.

## 10. E2E

Real-GPU backend smoke test:
`backend/tests/test_provider_metadata_smoke.py` — two real ACE-Step
generations of the same Song through the full HTTP stack, asserting each
Version's metadata (when present) has the correct shape
(`{bpm, genres, key_scale, time_signature, source}`, `source == "provider"`,
correct types, no empty-string leakage) and that nothing internal leaks.
Values are not hardcoded, per the governing prompt's explicit instruction,
since the provider's own output varies. Run against a live ACE-Step server
(RTX 5060 Ti): **1 passed**. The full existing smoke suite was re-run
afterward: **11 passed** — no regression in
Create/Extend/Remix/Repaint/Director/Projects/Song-Management real-GPU
flows.

Real Playwright E2E, appended to `frontend/e2e/create-song.spec.ts`:
"Provider metadata + Compare Versions" — two real generations of one Song,
opens Song Details, checks the Provider Metadata section is present and
disclosed, switches the active version and confirms metadata updates (not
stale), opens Compare Versions, selects Version A/B by their real ids,
verifies each comparison column's `AudioPlayer` is bound to that version's
own real `/api/jobs/{id}/audio` URL (never the other side's), actually plays
Version A's real audio, checks the descriptive diff table contains no
score/ranking language, and verifies selecting the same version for both
sides shows the rejection message and hides the columns. **1 passed**
(~25–28s) against the real stack. Full existing E2E suite was re-run for
full regression (result recorded in the final report).

## 11. Mutation testing

All 10 specified mutations were applied to a backed-up copy of the affected
file, confirmed to break the relevant test(s), then reverted and the
relevant suite re-confirmed green:

1. Remove BPM mapping (`bpm=None` hardcoded in the extraction helper) —
   caught (11 backend tests failed).
2. Map Version A's metadata onto Version B in `VersionColumn` — caught
   (2 frontend tests failed).
3. Expose the entire raw provider metadata dict, bypassing the allowlist —
   caught (24 backend tests failed; the type mismatch alone would have
   broken the response, on top of the dedicated leak tests).
4. Allow same-Version comparison (`sameVersion` hardcoded to `false`) —
   caught (the "no such element" failure on the now-never-rendered
   validation message, plus the columns rendering when they shouldn't).
5. Remove cross-Song Version scoping (drop the `WHERE v.song_id = ?` clause
   in `list_version_entries`) — caught (the dedicated cross-Song isolation
   test).
6. Swap the two comparison players' audio URLs — caught (2 frontend tests;
   this also prompted strengthening the URL-binding test to check
   per-column rather than "both URLs exist somewhere", which had been too
   weak to catch a swap on its own).
7. Ignore missing metadata (never return `None` from the extraction helper,
   even when every field is empty) — caught (5 backend tests failed).
8. Hardcode metadata in the frontend (BPM literal `100` regardless of the
   actual version) — caught (2 frontend tests failed).
9. Remove metadata from the API response (`metadata=None` hardcoded in
   `song_details_response`) — caught (2 backend tests, one via a TypeError
   from the now-`None` value where a dict was expected).
10. Collapse the comparison to a single version (Version B silently resolves
    to Version A's id) — caught (8 frontend tests failed).

Every mutation was reverted and the corresponding full suite (backend 512,
frontend 337) re-confirmed green before moving to the next one.

## 12. Known limitations

- **In empirical testing against a live ACE-Step server, plain (non-Director)
  Create Song generations consistently returned no bpm/genres/key_scale/
  time_signature in ACE-Step's own result payload**, even though ACE-Step's
  LM visibly computes these values internally during generation (confirmed
  in the server's own logs). Tunora surfaces exactly what the provider
  returns and never fabricates a value, so in practice, ordinary (non-AI
  Song Director) generations currently show "Not available" for this
  metadata today. This is a characteristic of the current ACE-Step
  deployment's plain-generation result shape, not a defect in this phase's
  plumbing — the plumbing was verified correct with realistic synthetic
  provider payloads (30 unit tests) and behaves safely with real null data
  (the real-GPU test and E2E test both pass cleanly against this actual
  behavior). Modifying ACE-Step's own generation payload is out of scope
  (§45 of the governing prompt: do not modify the ACE-Step integration
  unless directly required), and this is a provider-side characteristic, not
  a Tunora requirement.
- Provider metadata is never independently verified; the UI labels it
  "Provider-reported" everywhere it appears, per the governing prompt's
  explicit honesty requirement.
- The Compare Versions selectors always default to the two most recent
  versions (or the only version twice, if just one exists — though the
  toggle itself is hidden below two versions, so this default is never
  actually shown to a user in that state).
- Simultaneously mounting two `AudioPlayer` (WaveSurfer) instances was
  proven correct against the real stack (E2E) and via synchronous DOM
  attribute checks in unit tests; one unit-test-only quirk was found and
  worked around (mocking a dynamically-`import()`-ed module twice in the
  same React commit is not always deterministically intercepted by Vitest's
  mock registry) — this is a test-infrastructure detail, not a product
  behavior, and does not affect the real browser (confirmed by the real
  Playwright E2E test passing).

## 13. Deferred capabilities

Per the accepted audit and this phase's explicit out-of-scope list: RMS,
peak, LUFS, sample rate, channels, codec, bitrate, spectrograms,
synchronized/linked playback, crossfade, audio similarity/diff scoring,
audio fingerprinting, audio embeddings, independent BPM/key/genre/
time-signature recalculation, stem separation, mastering, advanced audio
editing. None of these were started; all remain exactly where the Phase 10
audit left them, pending a future phase's explicit instruction.
