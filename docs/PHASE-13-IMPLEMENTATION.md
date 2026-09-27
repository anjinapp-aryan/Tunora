# Phase 13 — Another Take / Version Variation

Implementation record for the candidate recommended by
`docs/PHASE-13-PRODUCT-CAPABILITY-GAP-AUDIT.md` (Candidate A) and approved by the user.

## Objective

From an existing Version, generate another take of the same creative idea as a NEW Version of the
same Song. One request, one job, one audio output, one new Version. The source is never touched.

## Product Semantics

"Another Take" copies only the creative inputs of the source Version: `prompt`, `lyrics`,
`language`, `instrumental`, `duration`. It does a real, fresh text-to-music generation. It is not
a copy of the source audio, it does not read the source audio, and it does not inherit the
operation-specific parameters of the source (extend length, repaint range, remix strength, track).

- `duration` is the source spec's duration, falling back to the stored audio's duration when the
  spec had none.
- Another Take of an EXTRACT Version is refused (422): an extracted stem has no "same idea" to
  regenerate as a full song.
- Another Take of another Another Take chains normally.
- A source with no audio (still generating or failed) is allowed: nothing is read from its audio.

## Existing Components Reused

`JobService.create_version_from_operation` and `create_and_submit`; the existing operation route
`POST /api/songs/{song_id}/versions/{version_id}/{operation}`; the `Version` lineage columns
(`operation`, `source_version_id`, `operation_params`) and their immutability/same-song triggers;
song-scoped version numbering inside the creation transaction; `MusicGenerationProvider` and
`AceStepMusicGenerationProvider`; the pending-version banner and polling in `song-details.tsx`;
`VersionActions`; `AudioPlayer`; download; Version History; Compare Versions.

## Generation Flow

```
Song Details (Version N selected)
  -> [Another Take]                          VersionActions.startTake()
  -> POST /api/songs/{song}/versions/{N}/another_take   body {}
  -> JobService.create_version_from_operation("ANOTHER_TAKE")
       validate ids, same-song source, provider support, not EXTRACT
       -> _create_another_take: GenerationRequest(prompt, lyrics, language,
          instrumental, duration, seed=None, operation="ANOTHER_TAKE")
  -> create_and_submit  (Song + Version + Job in one BEGIN IMMEDIATE transaction, committed
       BEFORE the provider is called; version_number assigned there)
  -> AceStepMusicGenerationProvider.generate  (plain JSON POST /release_task, no source upload)
  -> ACE-Step -> complete_job -> AudioStorage
  -> existing pending UI -> new Version selected, playable, downloadable
```

## Why POST /api/jobs was not enough

`POST /api/jobs` with `song_id` does create the next Version of a Song, but always as `ORIGINAL`
with no `source_version_id`, and lineage is immutable after insert (DB trigger), so it could not
be added afterwards. The existing operation route is the project's lineage-carrying entry point;
Another Take only extends its allowlist (`Literal[... "another_take"]`). No new endpoint, route,
request model or response model was added.

## Seed Strategy

**Verified behavior (real GPU spike, ACE-Step turbo, 10 s instrumental, same prompt, through
Tunora's `POST /api/jobs`):**

| Run | Seed | Result |
|---|---|---|
| A | 123 | sha256 `968f2648…` |
| B | 123 | sha256 `ed644f39…` (NOT byte-identical to A) |
| C | 456 | `1a33793d…` |
| D | none | `a25e3110…` |
| E | none | `885c9b9d…` |

Decoded-waveform correlation (ffmpeg, mono 8 kHz): A/B +0.173; every other pair between -0.03 and
+0.05. So a fixed seed is **not deterministic** in this stack (Case C): the same seed did not
reproduce the audio, though the pair correlated weakly more than unrelated runs. Hence reusing the
source seed would neither reproduce nor reliably vary the result.

**Strategy:** Another Take always sends `seed = None`. The provider already maps `seed is None` to
ACE-Step `use_random_seed: true` (`ace_step.py::_build_release_task_payload`), so the existing
seed-generation mechanism is reused: no new random library, no new user-facing seed control, and
the general Create Song seed behavior is unchanged. The take's stored `seed` is therefore `null`
(random); the source keeps its own. `batch_size` is also never copied. Real-GPU result: two takes
of a seed-11 source produced three mutually different files (see below).

## Lineage

Same mechanism as Extend/Remix/Repaint/Extract: `operation = "ANOTHER_TAKE"`,
`source_version_id = <source>`, `operation_params = null` (no parameters). The operation constant
follows the existing upper-case allowlist (`app/songs/operations.py`); the URL segment is
`another_take` (the route upper-cases it). The API exposes `operation` and
`source_version_number` only; the UI label is "Another take · from Version N".

## Version Numbering

Unchanged: assigned per Song inside the creation transaction, `UNIQUE(song_id, version_number)`.
Take from V1 when V1..V3 exist yields V4. Verified by a concurrency test (5 simultaneous takes get
2,3,4,5,6) and by chained/branched lineage tests.

## API

No new endpoint. `another_take` was added to the operation allowlist of the existing route. The
request body is ignored for this operation (`{}` sent); client-supplied `prompt`, `lyrics`,
`track_name`, `extend_seconds` do not influence the take (tested). Errors reuse the existing
mapping: unknown/cross-song/malformed ids -> 404/422, unsupported -> 422, refused (EXTRACT) -> 422.
Responses contain no paths, provider task ids or raw results (tested).

## UI

`VersionActions` gets an **Another Take** button in the same row. Unlike the other operations it
needs no input, so it starts immediately instead of opening a panel (no `aria-expanded`). While
the request runs the button is disabled and reads "Starting…"; after acceptance the existing
pending banner replaces the actions, exactly as for the other operations. Failures use the same
fixed message ("Could not start this. Please try again.") and are shown in the same alert slot
(`data-testid="op-error"`), also when no panel is open. The pending banner now uses a shared
`operationName()` so it reads "(Another take)". No new component, modal, library or progress
system.

## Database

**No migration.** `versions.operation` is free `TEXT` (no CHECK); `PRAGMA user_version` unchanged.

## Storage

Unchanged: same `AudioStorage`, MP3 output, `GET /api/jobs/{id}/audio`, Range support, download.
No FLAC/WAV work.

## Backend changes

`operations.py` (constant + allowlist), `service.py` (`_create_another_take`, early branch before
the source-audio checks), `ace_step.py` (advertises `ANOTHER_TAKE`; treats it like `ORIGINAL`:
JSON post, `audio_duration` sent, no operation fields), `routes_songs.py` (allowlist).

## Security

Reused validation: id patterns, same-song source check (also enforced by a DB trigger), operation
allowlist (`Literal` on the route, `CREATIVE_OPERATIONS` in the service), provider capability
check. Tests cover cross-song source, unknown/malformed ids, unknown operation names
(`another-take`, `regenerate`, `variation`), ignored client fields, and response leakage. The
source Version and its audio are proven unchanged. No new input is accepted from the client.

## Unit Tests

Backend `tests/songs/test_another_take.py` (18): new Version, exactly one, source untouched (row
and audio bytes), input copying, seed/batch never reused, duration fallback, no source audio
needed, chain/branch numbering, concurrent numbering, spec copied from an extended source, EXTRACT
source refused, cross-song/unknown/malformed ids, unsupported provider, provider failure, HTTP
API behavior, ignored client fields, no leakage, ACE-Step payload mapping.
Frontend (`version-actions.test.tsx`, +6): button and accessible name, POST body/URL and pending
UI, keyboard start, double click makes one request, completion selects the take and keeps the
source, safe error and retry.

## Mutation Testing

Method as in earlier phases: apply one targeted mutation, run the relevant tests, confirm failure,
restore. 18 mutations: source seed reused, batch_size copied, wrong operation, lineage dropped,
new song instead of same song, lyrics swapped, language dropped, instrumental flipped, duration
fallback removed, EXTRACT source allowed, cross-song check skipped, provider uploads source audio
path, provider not advertising the operation, disabled-while-busy removed, wrong operation sent
by the UI, wrong version id sent, wrong operation passed to `onStarted`, busy guard removed.
**17 of 18 caught.** The survivor, removing `if (busy) return;` in `startTake`, is inert: the
button is `disabled={busy}` (that mutation is caught), a disabled button cannot fire a second
click, and inside one event tick the closure's `busy` is stale anyway so the guard could not
have helped. It is defense in depth, not a testable behavior.

## Real GPU Validation

`backend/tests/test_another_take_smoke.py` against the live ACE-Step server (real generation,
seed-11 source, then two takes). All jobs COMPLETED, all files exist, same Song, numbers 1-3,
lineage correct, source row and audio checksum unchanged after each take, takes have `seed=None`,
each take's bytes differ from every earlier version, `/audio` serves the stored bytes.

| Version | Operation | Seed | Duration | Format | Bytes | sha256 (first 16) |
|---|---|---|---|---|---|---|
| V1 `ver-7dfe6682…` | ORIGINAL | 11 | 10.0 s | mp3 | 160940 | `667fc57435180600` |
| V2 `ver-95d91b9c…` | ANOTHER_TAKE | none | 10.0 s | mp3 | 160940 | `bed6c8a66b1739d9` |
| V3 `ver-2fea27fa…` | ANOTHER_TAKE | none | 10.0 s | mp3 | 160940 | `958a9aeb76e15006` |

Identical byte size is expected (fixed-bitrate MP3 of the same length). Whether the takes sound
"different enough" is subjective and was not used as a pass criterion.

## Real Playwright Validation

`e2e/create-song.spec.ts`, "Another Take: a real new version of the same idea…", against the real
stack (Next.js, throwaway FastAPI backend, real ACE-Step on the GPU): real song -> Song Details ->
button fits 375/768 px and is keyboard-focusable -> one click sends exactly one request -> pending
-> Version 2 Latest with "Another take · from Version 1" -> API shows exactly one new Version, same
prompt/lyrics/language/instrumental, seed null, source record identical apart from `is_latest`,
exactly one new job -> new audio differs from the source, plays, downloads byte-for-byte -> Version
History lists both with lineage -> source selectable and playable -> source file checksum
unchanged -> no internal-path leak.

## Regression Results

- Backend `pytest -m "not smoke"`: **554 passed** (536 before, +18).
- Backend real-GPU smoke (`pytest -m smoke`, live ACE-Step): **13 passed**, including the new
  Another Take smoke and the existing Extend/Remix/Repaint, Extract, provider-metadata, Song
  Director, song-management and lifecycle smokes.
- Frontend Vitest: **365 passed / 21 files** (359 before, +6) on the final run; the pre-existing
  flake described below appeared on some earlier runs under load.
- `tsc --noEmit`: pass. ESLint: 0 errors, 1 pre-existing warning. `next build`: pass.
- Full Playwright suite (real stack, real GPU): **19 passed** (18 existing + the new Another Take
  test), including the Phase 12 drag-Repaint and keyboard tests and the Extend/Remix/Repaint,
  Extract and Compare tests.

## Known Limitations

- Pre-existing flake: `version-actions.test.tsx › selects the new version, moves Latest…` (a
  real-timer poll race asserting "Version 2 — Latest" right after the selection moves) fails
  intermittently under machine load. Reproduced on a clean checkout of `fc02f0f` (2 of 4 runs
  failed) so it is not caused by this phase; the new take test waits for the Latest marker and was
  stable across repeated runs.
- The take's seed is not recorded (`null`); a take cannot be reproduced by seed, and ACE-Step did
  not reproduce audio from a fixed seed in this stack anyway.
- No cap or queue on repeated takes: each click is a serial job on the single-worker ACE-Step.
- Pre-existing ESLint warning (unused `request` in a Phase 12 E2E test) left untouched.

## Deferred Work (NOT part of Phase 13)

Batch generation (ACE-Step `batch_size`), lossless output / FLAC / `audio_format`, prompt library,
cover art, mastering/loudness, MIDI, chord detection, lyric alignment, `lego`, `complete`.
