# Phase 11: Stem Separation / Track Extraction

This is the implementation record for the capability recommended by
`docs/PHASE-11-PRODUCT-CAPABILITY-GAP-AUDIT.md` and explicitly accepted by
the user. It is not a rewrite of that audit.

## 1. Objective

Add ACE-Step's native `extract` task type as a new creative operation
(`EXTRACT`) alongside the existing Extend/Remix/Repaint, so a user can pull
one instrument/vocal track out of an existing Version's audio and get it as
a new, immutable Version — reusing the Song/Version/Job/Provider/Storage/
Lineage/AudioPlayer/UI architecture unchanged.

## 2. The mandatory spike (GO/NO-GO gate)

Per the governing prompt, the full feature was **not** built until a real,
GPU-backed spike proved every critical assumption. Findings, in the order
they were established:

1. **Source inspection** (`ACE-Step-1.5/acestep/constants.py`,
   `acestep/api/http/release_task_models.py`,
   `acestep/core/generation/handler/task_utils.py`,
   `acestep/api/job_model_selection.py`,
   `acestep/api/http/model_service_routes.py`) confirmed: `extract` is a
   real `task_type` value on the same `/release_task` endpoint
   Extend/Remix/Repaint already use; `track_name` is a real, separate
   request field (not embedded in the prompt); ACE-Step itself performs
   **no validation** of `track_name` against its own documented list — it
   will happily run with a nonsense value, so **Tunora's own layer is the
   only enforcement boundary** (confirmed by literally sending
   `track_name="not_a_real_track"` to the live server and watching it
   "succeed").
2. **Live REST verification**: fetched the running server's
   `/openapi.json`. `/release_task` is documented but (being a
   legacy-compatible, loosely-typed endpoint) does not enumerate
   `task_type`/`track_name` in its generated schema — this was resolved by
   reading `release_task_param_parser.py`/`release_task_request_builder.py`
   directly (the same way Tunora's own `AceStepMusicGenerationProvider`
   already builds requests for `repaint`/`cover`) and then proven by an
   actual successful call, not by schema inspection alone.
3. **First real finding that corrected the audit's assumption**: the audit
   believed a second model could be loaded into "slot 2" purely on demand
   at runtime. In practice, `POST /v1/init` refused
   `{"model": "acestep-v15-base", "slot": 2}` with
   `"Slot 2 is not available because ACESTEP_CONFIG_PATH2 was not set at
   startup."` The slot must be declared via an environment variable
   (`ACESTEP_CONFIG_PATH2=acestep-v15-base`) when the server process
   starts; only the model *weights* for that slot load on demand
   (auto-downloaded from Hugging Face on first `/v1/init` call — a real
   ~4.79 GB download, observed directly, including one transient CDN
   timeout that auto-resumed).
4. **Real extraction, real audio**: after restarting ACE-Step with
   `ACESTEP_CONFIG_PATH2=acestep-v15-base`, a real vocal song was generated
   through the actual Tunora backend (not a synthetic file), then
   extracted via a raw multipart `POST /release_task`
   (`task_type=extract`, `track_name=vocals`, `model=acestep-v15-base`,
   `src_audio=<the real generated file>`). Verified four track types this
   way, each a distinct, real generation: **vocals, drums, bass, guitar**.
5. **Objective output validation** (no new audio-analysis dependency —
   `ffprobe`/`ffmpeg`, already present on the dev machine, used purely as a
   one-off diagnostic, not adopted as a product dependency): every output
   was a valid, non-corrupted MP3 (48 kHz, stereo, correct duration,
   non-zero size), with a **different SHA-256** from the source (not a
   passthrough) and a materially different silence/loudness profile
   (`ffmpeg -af silencedetect`/`volumedetect`) consistent with a real
   vocal-isolation transformation — e.g. the extracted "vocals" track went
   near-silent for the ~3.3 s instrumental-only tail of the source, while
   the source itself did not. This project's own established rule ("audio
   quality needs human listening; report only objective facts") applies
   here too: this is objective corroborating evidence, not a claim that the
   agent listened to the audio.
6. **Batch-size discovery**: an extract request with no `batch_size` set
   produced **two** output files (ACE-Step's own default), of which
   Tunora's existing `get_result()` already only ever reads
   `audio_items[0]` — so nothing would have broken, but the second output
   would have been wasted GPU time. Explicitly setting `batch_size=1`
   (verified to produce exactly one output) is used for `EXTRACT` only.
7. **Concurrent-residency risk, resolved with real numbers**: idle VRAM was
   1.47 GB; the base model alone (loaded, idle) used 5.91 GB; during a real
   extraction, peak was 8.73 GB; with **both** turbo and base resident and
   a real turbo `text2music` generation run *while* base was still loaded,
   peak was **11.2 GB** — comfortably under the 16 GB (16311 MiB) card,
   with roughly 5 GB of headroom. The audit's flagged VRAM risk did not
   materialize on this hardware; both models coexist without disruption to
   ordinary (turbo) generation.

**Spike result: GO.** All conditions in the governing prompt's gate were
met with real evidence: REST-reachable without any ACE-Step source change,
real extraction succeeded on real Tunora audio, output was valid and
objectively distinct from the source, the RTX 5060 Ti ran turbo+base
concurrently without VRAM exhaustion, and no new paid dependency or
architectural violation was needed.

### An operational incident during the spike (disclosed, not hidden)

An earlier, unrelated command in this session ran a Python interpreter
against the ACE-Step virtual environment *while its API server was still
running*, which corrupted the `httptools` package on disk (a locked `.pyd`
file was partially overwritten), breaking the server's HTTP parser for all
new connections. This was caught immediately (the server accepted TCP
connections but failed to parse any request), diagnosed, and fixed by
force-reinstalling the exact `uv.lock`-pinned version
(`uv sync --reinstall-package httptools`) before the server was restarted
and the spike continued. No ACE-Step source file was modified; only a
corrupted third-party dependency inside its `.venv` was repaired back to
the version the project's own lockfile specifies.

## 3. Architecture

```
Existing Song Details / Version Actions UI (unchanged component tree)
        |
        +-- "Extract" button (new, alongside Extend/Remix/Repaint)
                |
                v
        Track-type radio group (Vocals/Drums/Bass/Guitar -- exactly the
        four verified in the spike; nothing invented)
                |
                v
POST /api/songs/{song_id}/versions/{version_id}/extract   (existing route,
        {"track_name": "vocals"}                            new "extract"
                |                                            literal only)
                v
JobService.create_version_from_operation(..., "EXTRACT", track_name=...)
        (existing method, new branch -- same validation/lineage/submission
         shape as EXTEND/REMIX/REPAINT)
                |
                v
AceStepMusicGenerationProvider._operation_fields()  (existing method, new
        branch: task_type="extract", track_name, model="acestep-v15-base",
        batch_size=1)
                |
                v
Existing /release_task multipart upload path (unchanged -- the same
        _post_with_source_audio() EXTEND/REMIX/REPAINT already use)
                |
                v
New, immutable Version (operation="EXTRACT", source_version_id=<source>,
        operation_params={"track_name": "vocals"}) -- existing Version/
        lineage machinery, zero schema change
```

## 4. Operation model

- `app/songs/operations.py`: added `EXTRACT = "EXTRACT"` to
  `CREATIVE_OPERATIONS`, and `TRACK_NAMES = ("vocals", "drums", "bass",
  "guitar")` — **exactly** the four types the spike individually verified
  by real extraction. ACE-Step's source documents 8 more
  (`woodwinds, brass, fx, synth, strings, percussion, keyboard,
  backing_vocals`) that were **not** spike-tested this session and are
  deliberately not exposed anywhere (backend allowlist or UI) — per the
  governing prompt's explicit "do not invent track types" rule, this list
  only grows after the same real-extraction verification is repeated for a
  new entry.
- `app/providers/base.py`: added `track_name: Optional[str] = None` to the
  already-provider-neutral `GenerationRequest` (same treatment as
  `repaint_start`/`remix_strength` — a generic creative-operation
  vocabulary field, not an ACE-Step-specific one).
- `app/jobs/service.py::create_version_from_operation`: one new `elif`
  branch, following the exact validation/lineage shape already used for
  EXTEND/REMIX/REPAINT — normalizes and validates `track_name` against
  `ops.TRACK_NAMES` (case-insensitive, trimmed), builds the
  `GenerationRequest`, and records `operation_params={"track_name": ...}`.
  Notably **simpler** than EXTEND/REPAINT: EXTRACT needs no user prompt and
  no known source duration (it operates on the whole source regardless of
  length) — verified by a dedicated test.
- `app/providers/ace_step.py`: `supported_operations` gained `"EXTRACT"`;
  `_operation_fields()` gained one branch mapping it to
  `{"task_type": "extract", "track_name": ..., "model": "acestep-v15-base",
  "batch_size": 1}`. This is the **only** place ACE-Step's base-tier
  requirement is encoded — nothing above the provider boundary knows or
  cares that EXTRACT needs a different model tier than everything else.

## 5. Version immutability and lineage

Identical guarantee to EXTEND/REMIX/REPAINT (Phase 5B), reusing the same
mechanism, not a new one: the source Version is only ever read (its stored
audio bytes are uploaded to ACE-Step; nothing about the source row is
touched), and the result is a brand-new Version row with its own id,
version number, audio file, and Job. `source_version_id` and `operation`
are protected by the same pre-existing SQLite triggers that already make
Extend/Remix/Repaint's lineage immutable and same-Song-only — no new
trigger, no new column, verified directly (a real extraction's source file
was byte-compared before and after, and the DB was queried for the
original's audio key, both unchanged).

## 6. Multiple outputs (the true architectural question the audit deferred)

Resolved directly by the spike: with `batch_size=1` (which Tunora's own
provider mapping now always sends for EXTRACT), one request produces
**exactly one** output file. This maps 1:1 onto the existing "one operation
call → one new Version" pattern already used by every other creative
operation — **no new asset hierarchy, no multi-file Version, no schema
change** was needed, resolving the audit's §12 question with evidence
rather than a design guess.

## 7. Storage

Unmodified. `AudioStorage`/`LocalAudioStorage` handle the extracted file
exactly as they handle every other generation's output — same key layout
(`<job_id>/<job_id>.mp3`), same path-traversal/containment guards, same
save/cleanup behavior. No new storage class, no new filesystem layout.

## 8. API

- `POST /api/songs/{song_id}/versions/{version_id}/{operation}`
  (`app/api/routes_songs.py`): the existing route's `operation` path
  parameter gained the `"extract"` literal (alongside
  `extend`/`remix`/`repaint`) — no new route.
- `VersionOperationRequest` (`app/api/schemas.py`) gained one optional
  field, `track_name`.
- `VersionResponse` gained one new optional field, `extracted_track` — the
  track name for an EXTRACT version, `null` for every other version. Built
  the same "never expose the raw internal dict" way every other field
  already is: read from `Version.operation_params` (previously never
  exposed at all) but surfaced as one named, allowlisted string, never the
  raw dict.
- No field was removed or renamed on any existing response
  (backward-compatible, tested directly).

## 9. UI

`VersionActions` (`frontend/src/components/song/version-actions.tsx`)
gained a fourth button, "Extract", opening the same inline-form pattern
Extend/Remix/Repaint already use. Its form shows **only** a track-type
radio group (Vocals/Drums/Bass/Guitar) — no description field, no lyrics
field, matching the governing prompt's "show only the controls actually
supported by the verified implementation" instruction exactly (ACE-Step's
own `extract` instruction is derived server-side from `task_type` +
`track_name`; a user-supplied prompt/caption plays no role in it).
`operationLabel()` (`frontend/src/lib/api/songs.ts`) now renders
`"Extract: Vocals · from Version 1"` for an EXTRACT version, reusing the
exact same lineage-label mechanism every other operation already uses (no
second visualization system). Extracted versions appear in the existing
Version list, Song Details "active version" panel, and the Phase 10
Compare Versions view exactly like any other version — no separate "Stem
Library" was built.

## 10. Security

- Track-type validation happens at the Tunora service layer
  (`JobService.create_version_from_operation`), against the closed
  `ops.TRACK_NAMES` tuple — this is load-bearing, not defense-in-depth,
  because the spike proved ACE-Step itself performs **no** validation of
  this field (§2.1).
- Cross-Song source-version access is refused by the exact same check
  every other creative operation already uses
  (`source.song_id != song_id` → `SourceVersionNotFoundError`), backed by
  the same pre-existing DB trigger — verified directly for EXTRACT
  specifically (mutation-tested, §12).
- The public API never exposes `operation_params` as a raw dict, ACE-Step's
  `model`/task internals, or any filesystem path — `extracted_track` is the
  one, single, allowlisted string extracted from it, built field by field
  like every other response.
- Malformed/oversized/SQL-injection-shaped track names are rejected the
  same way a malformed id already is — via the closed-set membership check,
  which rejects anything not exactly one of the four verified strings.

## 11. Testing

**Backend** (`backend/tests/songs/test_extract_operation.py`, 24 tests):
creation and lineage (source untouched, every verified track name,
case/whitespace normalization, chaining/branching); validation (unknown/
malformed/empty track names create nothing, no prompt or known-duration
requirement); security (cross-Song and unknown source versions, malformed
ids, provider-unsupported refusal); the full HTTP surface (`extracted_track`
field present only on EXTRACT versions, unsupported-track rejection,
missing-field rejection, cross-Song rejection, no leak of provider/path
details); and the ACE-Step provider mapping itself (exact
`task_type`/`track_name`/`model`/`batch_size` fields verified against a
mocked `/release_task` call, and that a missing track name raises before
any request is sent). Full existing backend suite after this phase:
**536 passed, 11 deselected (smoke)** — zero regressions (two pre-existing
strict field-set assertions were intentionally updated to include the new
`extracted_track` key, annotated as such).

**Frontend**: `version-actions.test.tsx` gained 6 tests (Extract button
present, only verified track types shown with no description/lyrics field,
default track + chosen track posted correctly, the completed version's
lineage label names the track, the original version is provably untouched
after switching back to it). `songs.test.ts` gained a test for
`operationLabel()`'s new `"Extract: Vocals · from Version 1"` output.
`tsc --noEmit` clean, `eslint .` clean, `next build` clean. Full existing
frontend suite: 342-343 passed depending on run (the one pre-existing,
documented real-timer flake in this same file recurred under full-suite
parallel load and was reconfirmed to pass in true isolation — not a
regression, consistent with `CLAUDE.md`'s own note about this exact test).

## 12. Mutation testing

All required mutations were applied to a backed-up copy of the affected
file, confirmed to break the relevant test(s), then reverted and the full
suite re-confirmed green:

1. **Wrong operation** (hardcoded `"REMIX"` instead of `"EXTRACT"` in the
   service's EXTRACT branch) — caught (3 tests failed).
2. **Wrong/missing `source_version_id`** (`None` instead of the real
   source) — caught (2 tests failed).
3. **Unsupported track type accepted** (validation check removed) —
   caught (9 tests failed).
4. **Invalid Version ownership** (cross-Song check removed) — caught (2
   tests failed at the service layer; the pre-existing DB trigger also
   independently raised an `IntegrityError`, a real layered-defense
   finding, not something this phase added).
5. **Missing storage result**: not re-mutated. EXTRACT reuses the exact
   same completion/audio-attachment code path as EXTEND/REMIX/REPAINT with
   no new branch of its own; that shared path's failure behavior was
   already mutation-tested in Phase 5B
   (`test_a_storage_failure_after_generation_fails_the_job_and_attaches_no_audio`).
   Re-mutating identical, unchanged code would not exercise anything new.
6. **Wrong provider parameter** (`task_type="lego"` instead of
   `"extract"`) — caught (1 test failed).
7. **Wrong output association** (`extracted_track` read from the first
   version in the list rather than the version actually being serialized)
   — caught (1 test failed).
8. **Frontend: wrong output track submitted** (the UI always posted
   `"vocals"` regardless of which radio button was selected) — caught (2
   tests failed).

## 13. Real GPU test

`backend/tests/test_extract_operation_smoke.py`: a real vocal generation
through the actual FastAPI/JobService/AceStepMusicGenerationProvider stack,
followed by a real `POST .../extract` (`track_name=vocals`) through the
same stack. Asserts: the new Version is `EXTRACT` with
`extracted_track=="vocals"` and `source_version_number==1`; its audio file
exists, is non-empty, and is playable via the existing `/api/jobs/{id}/audio`
route; its bytes differ from the source (a real transformation, not a
copy); the original Version's audio file and DB row are byte-for-byte and
field-for-field unchanged; and nothing internal (paths, the base-tier model
name, the ACE-Step host) leaks through any response. Run against the live
ACE-Step server (RTX 5060 Ti, `ACESTEP_CONFIG_PATH2=acestep-v15-base`):
**1 passed** (~23 s). One transient failure was observed and diagnosed
before this final passing run — a real generation submitted moments
earlier via a manual `curl` request during the spike was still resolving
against the same shared, single-worker ACE-Step queue, and a from-scratch
reproduction with the identical harness succeeded cleanly once that
contention cleared; this was a session-local timing coincidence from manual
spike testing, not a defect in the implementation (the same harness
pattern already underlies every other passing smoke test in this project).
Full existing smoke suite re-run afterward: **12 passed** — zero regression
in Create/Extend/Remix/Repaint/Director/Projects/Song-Management/
Version-Comparison real-GPU flows.

## 14. Real Playwright E2E

Appended to `frontend/e2e/create-song.spec.ts`: a real generation with
actual vocals, a real Extract of the "vocals" track through the browser UI
(button → track radio group → submit), waiting for the real base-tier
generation to complete, then verifying: the new version's lineage label
reads "Extract: Vocals · from Version 1"; its `AudioPlayer` is bound to its
own real, playable audio (waveform painted, play/pause/seek all function,
per the project's existing `expectPlayableAudio` helper); its downloaded
bytes differ from the source's; switching back to Version 1 shows it
completely unchanged (`Original`, byte-identical audio); and download of
the extracted version matches its stored file byte-for-byte. **1 passed**
(~43 s) against the real stack. The full existing E2E suite was re-run
immediately after for full regression (see the final report for the count
from that run).

## 15. Known limitations

- Only four track types are exposed (vocals, drums, bass, guitar) — exactly
  what this session individually verified by real extraction. ACE-Step
  documents 8 more; adding any of them requires repeating the same
  real-extraction verification, not just adding a string to a list.
- EXTRACT requires the ACE-Step server to have been started with
  `ACESTEP_CONFIG_PATH2=acestep-v15-base` (or an equivalent slot
  configuration) — a real-world deployment/runbook requirement, not
  something Tunora's own code can configure at runtime. If the base model
  is genuinely unavailable, ACE-Step will reject the request; Tunora
  surfaces this the same way any other provider failure is already
  surfaced (a safe, generic error), not a fabricated success.
- Output quality was validated objectively (file validity, a real
  transformation distinct from the source, plausible dynamics for the
  requested track) but not by human listening in this session — consistent
  with this project's standing rule that audio-quality judgments require a
  human, and this document does not claim otherwise.
- `lego` (multi-track layering) and `complete` (auto-completion) — the
  other two capabilities the spike's source-reading uncovered alongside
  `extract` — were deliberately **not** built in this phase, per the
  audit's own explicit recommendation to prove the integration pattern
  with one capability before considering the others.

## 16. Deferred capabilities

Everything the Phase 11 audit already deferred remains deferred: RMS,
peak, LUFS, spectrograms, synchronized playback, audio similarity/diff,
fingerprinting, embeddings, mastering, timeline-based Repaint region
selection, batch-generation UI, a prompt library, cover art, MIDI export,
lyric alignment/synced display (still architecturally blocked — see the
audit §6/§11), collaboration, cloud sync, and `lego`/`complete` (§15).
