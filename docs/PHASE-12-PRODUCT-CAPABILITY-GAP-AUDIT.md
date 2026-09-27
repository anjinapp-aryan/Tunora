# PHASE 12 — PRODUCT CAPABILITY GAP + OSS REUSE AUDIT

Status: **AUDIT ONLY**. No application code, dependency, schema, API, or UI
was changed to produce this document; ACE-Step was not modified. See §21
and the final report for the git-state proof.

Research date: 2026-09-24. Evidence labels used throughout: **VERIFIED**
(read directly from this session's own source/log inspection or a live
fetch), **EXTERNAL CLAIM** (a web source, cited), **INFERRED** (a reasoned
conclusion from VERIFIED facts, not itself independently checked), **UNKNOWN**
(genuinely not established — never guessed).

---

## 1. Executive Summary

Tunora's product loop (Idea → AI Director → Generate → Version → Extend/
Remix/Repaint/Extract → Compare → Organize) is complete and real-GPU tested
through Phase 11 (**VERIFIED**: `git log`, all twelve `docs/PHASE-*` records
read this session). The evidence in this audit points to **Timeline Repaint
Region Selection** as the single highest-value, lowest-risk next capability:
it closes a gap Tunora's own Phase 9 audit already flagged ("no timeline UI
for Repaint region (numeric seconds)"), and — uniquely among every
candidate investigated — requires **zero backend change, zero API change,
zero database change, and zero new dependency**. ACE-Step's `repaint`
REST parameters (`repainting_start`/`repainting_end`) are already fully
implemented, tested, and real-GPU validated since Phase 5B; WaveSurfer.js's
**Regions** plugin (part of the npm package Tunora already depends on, BSD-3-
Clause, unused) natively provides drag-to-select, `minLength`/`maxLength`
constraints, and resize — a feature-for-feature match to Tunora's existing
`REPAINT_MIN_SECONDS`/`REPAINT_MAX_SECONDS` bounds. This is a pure
frontend UX composition of two things Tunora already fully owns.

Other candidates were investigated in comparable depth (Batch Generation UI,
Prompt Library, Cover Art, Mastering/Loudness, MIDI, Chord Detection,
`lego`/`complete`, Lyric Alignment) and are recorded below with their own
evidence — none combine equal user value with equal architectural minimalism.

## 2. Repository state (verified this session, not assumed)

```
git branch --show-current   -> feature
git log --oneline -20       -> e4a1654 Add ACE-Step Track Extraction   (HEAD)
                                f37091b Add Version Comparison
                                87eba7e Add Song Management
                                ... (Phases 1-8 below, unchanged)
git status --short          -> " M CLAUDE.md" (pre-existing, unrelated,
                                still uncommitted from an earlier /init) and
                                the ACE-Step-1.5 submodule's own pre-existing
                                untracked files (CLAUDE.md, test-generation.json)
git diff --stat              -> CLAUDE.md only, 23 insertions / 17 deletions
git submodule status         -> ca1e85fe9430179831e6bc6be790c332190a3866
                                 ACE-Step-1.5 (v0.1.7-69-gca1e85f) -- the
                                 SAME commit already inspected in the
                                 Phase 9/10/11 audits; no ACE-Step update
                                 has landed since
```

**Phase 11 push status**: contrary to this prompt's framing ("may not yet
be pushed"), `git fetch origin` + `git log origin/feature -3` shows
`origin/feature` is **already at `e4a1654`**, identical to local `feature`
— Phase 11 (and Phase 10, and Phase 9) are already on the remote. This
audit does not push anything regardless; noted here only because the
prompt's assumption did not match the actual, verified state, and this
document reports what was actually found rather than repeating the
assumption.

## 3. Phase 1–11 current capability (read from the actual docs and code, not the supplied summary)

Every phase doc from `docs/PHASE-1-DECISIONS.md` through
`docs/PHASE-11-IMPLEMENTATION.md` and `docs/PHASE-11-PRODUCT-CAPABILITY-GAP-AUDIT.md`
was read this session. Current schema: `backend/app/jobs/migrations.py`
confirms `LATEST_VERSION = 5` (Song/Version domain → lineage → Projects →
`is_favorite`; **VERIFIED**, no migration 6 exists — Phase 10 and 11 both
genuinely added zero schema). Current frontend routes (`frontend/src/app/`,
**VERIFIED** by listing): `/`, `/create`, `/jobs/[jobId]`, `/library`,
`/projects`, `/projects/[projectId]`, `/songs/[songId]` — no route for
prompt libraries, cover art, export, or any new capability exists yet.

| Capability | State |
|---|---|
| Create Song (manual + AI Director + AI Refinement) | Complete, real-GPU tested |
| Generate / Job lifecycle | Complete |
| Song / Version / lineage (immutable) | Complete |
| Extend / Remix / Repaint | Complete (numeric-seconds Repaint UI only — see §7) |
| Extract (Phase 11) | Complete — vocals/drums/bass/guitar only, base-tier model |
| Compare Versions (Phase 10) | Complete |
| Provider-reported metadata (bpm/genre/key/time-sig) | Complete, surfaced Phase 10 |
| Projects / Library / Favorite / Rename / Delete | Complete (Phases 6, 9) |
| Playback / Download | Complete, WaveSurfer-based |
| Batch generation | **Provider-native, Tunora backend already accepts `batch_size`, zero UI exposure** (§8, §12) |
| Timeline-based Repaint region | **Missing** — numeric seconds only (§7, §11) |
| Prompt library / templates | Missing |
| Cover art | Missing |
| Mastering / loudness | Missing (deferred explicitly in Phase 10's own audit) |
| MIDI / chords | Missing |
| Lyric synchronization | Missing, and architecturally blocked (Phase 11 §6/§11 re-confirmed this session, §9 below) |
| `lego` / `complete` (ACE-Step) | Available server-side, unused (Phase 11 deliberately deferred) |
| Collaboration / cloud sync | Missing, out of product vision (`docs/NON-GOALS.md`) |

## 4. Product capability matrix

| Capability | Current state | Existing implementation | Gap | User value | Candidate OSS | Complexity |
|---|---|---|---|---|---|---|
| Generation | Complete | `JobService`, `AceStepMusicGenerationProvider` | None | — | — | — |
| AI Director / Refinement | Complete | `app/director/` | None | — | — | — |
| Extend / Remix / Repaint | Complete | `app/songs/operations.py` | Repaint UI is numeric-only | Medium-High | WaveSurfer Regions (already a dep) | **Low** |
| Extract | Complete (4 tracks) | Phase 11 | 8 more ACE-Step track types unverified | Low-Medium | none needed (same provider) | Low (repeat the same spike per type) |
| Versioning / Lineage | Complete | `Version.operation`/`source_version_id` | None | — | — | — |
| Comparison | Complete | Phase 10 | None | — | — | — |
| Projects / Library / Favorites / Rename / Delete | Complete | Phases 6, 9 | None | — | — | — |
| Playback / Download | Complete | `AudioPlayer` (WaveSurfer) | None | — | — | — |
| Audio editing (trim/crop/fade) | Missing | — | No dedicated need observed | Low | Client-side, no OSS gap | Low if ever needed |
| Timeline editing | Missing | Repaint's backend already supports arbitrary regions | **UI-only gap** | High | WaveSurfer Regions | **Low** |
| Stem workflows | Partial (Extract) | Phase 11 | `lego`/`complete` unused | Medium | none (same provider) | Medium |
| Lyrics (entry/generation) | Complete | Create Song form, AI Director | None | — | — | — |
| Lyrics synchronization | Missing | — | ACE-Step's own LRC generation is Gradio-only, not REST (re-verified §9) | Medium-High | None reachable without patching ACE-Step | High (blocked) |
| Mastering / Loudness | Missing | — | No proven need (Phase 10 already deferred) | Low | pyloudnorm (MIT) | Low if ever prioritized |
| MIDI | Missing | — | Niche persona (producer) | Low-Medium | basic-pitch (Apache-2.0) | Medium |
| Chords | Missing | — | No mature, well-licensed OSS found (§10) | Low | None viable | High (BUILD only) |
| Batch generation | Provider-native, backend-accepted, UI-absent | `CreateJobRequest.batch_size` exists, unused by the UI | **UI-only gap**, but see §12 for real costs | Medium | none needed | Medium (VRAM/concurrency, storage of N results) |
| Prompt management | Missing | — | No fitting OSS (§10) | Medium (Persona A/B) | None fits; simple DB table is the answer | Low-Medium (new table+API) |
| Cover art | Missing | — | Needs a second generative model | Low-Medium | Apache-2.0 image models now exist (§10) | High (new model class) |
| Music video | Missing | — | Different capability class entirely | Low | — | Out of scope |
| Publishing / Sharing | Missing | — | Third-party platform integration | Low | — | Out of scope |
| Collaboration | Missing | — | Against product vision (local-first, single-user) | — | — | Out of scope |

## 5. User journey analysis

```
IDEA -> PROMPT/LYRICS -> AI DIRECTOR -> GENERATE -> REAL SONG -> PLAY -> SAVE
     -> LIBRARY -> EDIT -> EXTEND -> REMIX -> REPAINT -> EXTRACT -> COMPARE
     -> EXPORT/CREATE
```

Every stage through COMPARE is complete and real-GPU tested (**VERIFIED**).
**EXPORT/CREATE** today means exactly one thing: a plain MP3 download of one
Version (`DownloadButton`, `GET /api/jobs/{id}/audio`) — no batch/zip
export, no stem-bundle export exists (**VERIFIED**, `frontend/src/components/audio/`).
The one stage with a **directly observed** friction point (not inferred) is
**REPAINT**: its own operation already accepts an arbitrary time range, but
the UI requires typing start/end in seconds
(`frontend/src/components/song/version-actions.tsx`, **VERIFIED** this
session) rather than selecting a region on the waveform the user is already
looking at (the same waveform playback already renders). This is a real,
observed usability gap in an otherwise-complete stage of the journey, not a
speculative one.

## 6. Persona analysis

**Persona A — Beginner AI music creator.**
- Can do today (**observed**): describe a song, use the AI Director, play/
  save/organize it, iterate with Extend/Remix/Repaint/Extract, compare two
  versions.
- Blocked (**inferred**): picking a Repaint region by typing seconds while
  looking at a waveform is an unnecessary translation step for someone with
  no music-production background — they can *see* the part they want
  redone but must convert that to numbers.
- Would NOT be helped much by (**inferred**): batch generation (more
  choices to evaluate is not obviously easier for a beginner), MIDI,
  chords, mastering (all producer-facing).

**Persona B — YouTube / content creator.**
- Can do today (**observed**): generate background music, extend it to fit
  a video length, extract an instrumental via the vocals track's absence
  (Extract's "vocals" track can be discarded and any of drums/bass/guitar
  reused, though there is no single "everything-but-vocals" track type —
  see §8) or otherwise reuse existing generations across Projects.
- Blocked (**inferred**): fine-tuning exactly which few seconds of a
  generation get regenerated (e.g., a jarring transition at a specific cut
  point in an edit) again requires numeric guesswork against a waveform
  they can already see.
- Would be helped by (**external claim, competitive**, Phase 10/11 audits):
  a prompt/preset library for reproducing a consistent "channel sound"
  across many videos — a real, named gap, but a separate concern from
  timeline editing.

**Persona C — Independent music producer.**
- Can do today (**observed**): the full creative-operation set including
  real stem extraction (Phase 11) — the single most-requested pro-workflow
  gap this audit's Phase 11 predecessor found (competitor evidence: Suno,
  Udio, Stable Audio, Beatoven all now ship stems, **external claim**,
  already verified with dates in `docs/PHASE-11-PRODUCT-CAPABILITY-GAP-AUDIT.md` §7).
- Blocked (**observed**): the exact same numeric Repaint region problem, but
  more acutely — a producer editing to match another track's beat grid or a
  vocal phrase boundary needs sample-accurate selection, which a
  draggable, snappable waveform region supports far better than typing
  `4.2` / `7.8` into two text fields.
- Would be helped by (**inferred**, lower priority than Repaint): MIDI
  export (already a researched, licensed candidate — basic-pitch,
  Apache-2.0), for taking a generation into their own DAW as notation, not
  just audio.

Across all three personas, **Timeline Repaint Region Selection is the only
candidate identified as a direct blocker inside an already-shipped,
otherwise-complete feature** — every other gap is a *new* capability the
personas don't yet have any access to at all, which is a different (and, per
§31's anti-inflation rule, not automatically higher-value) kind of gap.

## 7. Current product gaps (see §4's matrix for the full list; the two most load-bearing for this audit's conclusion)

- **Repaint region selection is numeric-only.** `version-actions.tsx`
  (**VERIFIED**, read this session): `Input type="number"` for `Start
  (seconds)` and `End (seconds)`, validated against
  `REPAINT_MIN_SECONDS`/`REPAINT_MAX_SECONDS` (3–90 s, unchanged since
  Phase 5B). This was already flagged as a known limitation in
  `docs/PHASE-9-CAPABILITY-GAP-AUDIT.md` line 19 (**VERIFIED**, quoted
  there: *"Turbo model only; no timeline UI for Repaint region (numeric
  seconds)"*) — this audit did not invent the gap; it re-confirmed a
  previously documented one is still present two phases later.
- **Batch generation is fully backend-capable and fully UI-absent.** See
  §12 for the full cost/benefit analysis of why this was not selected
  despite being an even smaller nominal change.

## 8. ACE-Step capability audit (fresh, re-verified this session against the exact vendored commit)

The vendored submodule is unchanged since the Phase 9/10/11 audits
(`ca1e85f`, **VERIFIED** via `git submodule status`), so a full re-read of
`acestep/constants.py`, `acestep/api/http/release_task_models.py`,
`acestep/api/job_generation_setup.py`, `docs/en/API.md` (the vendored
project's own REST reference) was performed rather than assuming Phase
11's findings still hold verbatim — they do, with one new confirmation:

| Capability | Source location | REST reachable | Notes |
|---|---|---|---|
| `text2music`, `repaint`, `cover`/`cover-nofsq` | `TASK_TYPES_TURBO` | ✅ | Already fully used by Tunora (Original/Extend/Remix/Repaint) |
| `extract` | `TASK_TYPES_BASE` only | ✅ (base tier) | Used by Phase 11; 4 of 12 documented track types verified |
| `lego` (multi-track layering) | `TASK_TYPES_BASE` only | ✅ (base tier) | Not used; deliberately deferred by Phase 11 |
| `complete` (auto-completion) | `TASK_TYPES_BASE` only | ✅ (base tier) | Not used; deliberately deferred by Phase 11 |
| Batch generation | `GenerateMusicRequest.batch_size` (docs/en/API.md line 205: **"Batch generation count (max 8)", default 2**) | ✅, already a real REST field | **New confirmation this session**: `CreateJobRequest.batch_size` already exists in Tunora's own API schema (`app/api/schemas.py`) and is passed straight through when set (`app/providers/ace_step.py::_build_release_task_payload`), but **zero frontend code references it** (`grep` across `frontend/src` for `batch_size`/`batchSize` returns nothing, **VERIFIED**) — a real, already-half-wired gap. |
| LRC / lyric-timestamp generation | `acestep/core/generation/handler/lyric_timestamp.py`, wired only into `acestep/ui/gradio/events/results/lrc_utils.py` | ❌ **re-confirmed** — grepping `acestep/api/*.py` and `acestep/api/http/*.py` for any reference to it or `lrc` returns nothing this session, same as Phase 11's finding | Reaching it requires patching the vendored submodule's REST layer — explicitly out of bounds for this audit and, per the project's own rule, for any implementation phase without a dedicated decision to fork ACE-Step |
| Audio Understanding / Quality Scoring / Vocal2BGM / LoRA training | README feature table (**VERIFIED** this session, unchanged since Phase 9) | Partial/unclear without further source reading | Not investigated further this session — no persona/competitive pressure identified that would justify the research cost before a narrower candidate (Timeline Repaint) already clears the bar |

**No REST endpoint or task type exists for lyric synchronization, chord
detection, MIDI extraction, mastering, or cover art** — every one of those
capabilities, if built, would require either a new provider/model
(cover art, MIDI, chords) or patching the vendored submodule (lyrics),
never a small extension of the existing `AceStepMusicGenerationProvider`
the way Timeline Repaint does.

## 9. GitHub OSS audit (fresh searches this session)

| Category | Candidate | License | Activity | Notes | Decision |
|---|---|---|---|---|---|
| Timeline / waveform regions | `katspaugh/wavesurfer.js` **Regions plugin** | BSD-3-Clause ✅ (same package/license Tunora already depends on) | Active | `enableDragSelection()`, `minLength`/`maxLength` (seconds), `drag`/`resize` — a direct, native match for `REPAINT_MIN_SECONDS`/`MAX_SECONDS` (**EXTERNAL CLAIM**, verified via the plugin's own published API docs this session) | 🟢 **REUSE** |
| Stem separation fallback | `adefossez/demucs` | MIT ✅ (already confirmed via a direct LICENSE fetch in Phase 9) | Slow-maintained | Only relevant if ACE-Step's native `extract` is ever found insufficient — not re-researched this session, no new evidence changes Phase 11's conclusion | 🟡 REFERENCE (unchanged) |
| MIDI extraction | `spotify/basic-pitch` | Apache-2.0 (code + model, confirmed in Phase 1's own audit) | Active | Still the best-licensed candidate; no urgent product pressure found this session | 🟢 REUSE candidate, deferred |
| Chord detection | `CPJKU/madmom` (`DeepChromaChordRecognitionProcessor`) | Code BSD; **models/data CC-BY-NC-SA 4.0** (already hard-rejected, Phase 1) | Classified inactive (prior audits) | No new, better-licensed, actively-maintained alternative was found this session (**EXTERNAL CLAIM**: search results returned only madmom, Essentia — both already hard-rejected — and research-paper-only models with no packaged, licensed release) | 🔴 REJECT (unchanged); chord detection would be a from-scratch BUILD on librosa chroma features with no proven demand — not recommended |
| Mastering / loudness | `csteinmetz1/pyloudnorm` | MIT ✅ (confirmed Phase 10) | — | No new evidence changes Phase 10's DEFER | 🟡 REFERENCE (unchanged) |
| Prompt/preset management | Generic "AI prompt manager" tools (e.g. `Enterprise-DNA-OS/ai-prompt-manager`) | Mixed, not deeply audited (mismatched use case — see below) | — | These tools solve LLM-prompt-engineering workflows (versioning/sharing prompts across a team) — a different problem from "save this song description so I can reuse it," which is a simple per-user CRUD record Tunora's own SQLite already handles for every other entity (Song, Project) | 🔴 REJECT as a dependency; if ever built, it is a small, native BUILD (one table, no OSS needed) |

## 10. Hugging Face audit

Only cover art genuinely involves a new ML model class, so this is the one
area investigated on Hugging Face this session:

| Model | License (code) | License (weights) | VRAM (external claim) | Commercial use | Notes |
|---|---|---|---|---|---|
| Qwen-Image 2.0 (7B) | Apache-2.0 | Apache-2.0 | Not established this session (**UNKNOWN**) | ✅ per Apache-2.0 | 2K native resolution, released 2026-02-10 (**EXTERNAL CLAIM**) |
| Z-Image-Turbo | Apache-2.0 | Apache-2.0 | **UNKNOWN** | ✅ | Strong text rendering (posters/UI), not evaluated for photographic album-art quality |
| FLUX.2 [klein] 4B | Apache-2.0 | Apache-2.0 | ~13 GB (**EXTERNAL CLAIM**, unverified locally) | ✅ | FLUX.2 [dev]/9B variants require a **paid** commercial license — only the 4B klein variant is fully Apache-2.0 |

**Architectural note, not a rejection of the licenses**: even a fully
Apache-2.0, ~13 GB model is a **second generative model/runtime** alongside
ACE-Step on a single 16 GB GPU (Phase 11 already showed ACE-Step alone,
turbo+base concurrently, uses up to ~11.2 GB under real load) — running an
image model in the same process/session risks real VRAM contention that
was not measured this session (**UNKNOWN**, would need its own spike,
exactly as Phase 11 required one for `extract`). This is why cover art is
recorded as a real, now better-evidenced candidate (an update over earlier
phases' "not researched"), but not one that can be casually bundled into a
"small" phase — see §17.

## 11. License audit summary

| Item | Code license | Model/weight license | Commercial-compatible | Classification |
|---|---|---|---|---|
| WaveSurfer.js Regions plugin | BSD-3-Clause | N/A (no model) | ✅ | 🟢 REUSE |
| basic-pitch | Apache-2.0 | Apache-2.0 | ✅ | 🟢 REUSE (deferred) |
| pyloudnorm | MIT | N/A | ✅ | 🟡 REFERENCE (deferred) |
| Demucs (adefossez fork) | MIT | MIT (no separate clause, confirmed Phase 9) | ✅ | 🟡 REFERENCE (contingency only) |
| madmom | BSD (code) | **CC-BY-NC-SA 4.0** (models) | ❌ (models) | 🔴 REJECT |
| Essentia | AGPLv3 | AGPLv3 | ❌ (copyleft, standing hard-reject) | 🔴 REJECT |
| Qwen-Image 2.0 / Z-Image-Turbo / FLUX.2 klein 4B | Apache-2.0 | Apache-2.0 | ✅ | 🟡 REFERENCE (real candidates, not selected this phase — architectural fit unresolved, §10) |
| FLUX.2 [dev] / 9B klein | — | Requires a **paid** commercial license | ❌ for a zero-mandatory-cost product | 🔴 REJECT |

No candidate with an unresolved ("no license"/unknown) status is
recommended for adoption anywhere in this document.

## 12. Reuse / Adapt / Compose / Build decisions

- **REUSE**: WaveSurfer.js Regions plugin (already a dependency, unused);
  ACE-Step's existing `repainting_start`/`repainting_end` REST parameters
  (already implemented, tested, real-GPU validated since Phase 5B); the
  existing `REPAINT_MIN_SECONDS`/`MAX_SECONDS` bounds; the existing
  `VersionActions` Repaint form and validation flow.
- **ADAPT**: nothing needs adapting — this is the rare case where the
  backend needs literally no change.
- **COMPOSE**: Timeline Repaint Region Selection itself is a composition of
  the two REUSE items above — a draggable region on the waveform whose
  `start`/`end` (seconds) are handed to the *exact same* existing
  `createVersionOperation(..., "REPAINT", { repaint_start, repaint_end })`
  call the numeric form already makes.
- **BUILD (the true, minimal gap)**: only the UI wiring — rendering a
  `Regions` plugin instance on the existing waveform, converting a
  drag-created region into the two numbers the backend already expects,
  and replacing (or supplementing) the two `<Input type="number">` fields.
- **DEFER**: Batch generation UI, Prompt Library, Cover Art, Mastering/
  Loudness, MIDI, Chord Detection, `lego`/`complete`, Lyric Alignment — all
  recorded with their own evidence above/below, none combining equal user
  value with equal architectural minimalism this session.

## 13. Candidate capability analysis

**Timeline Repaint Region Selection** — see §17 for the full recommended-
phase writeup.

**Batch generation UI** — real, native, half-wired capability (§8), but
carries costs not present for Timeline Repaint: (a) storage — N audio files
per single "generation," multiplying disk usage per user action; (b)
concurrency — ACE-Step's queue is effectively serialized per Phase 11's own
observation of a single-worker queue; a UI that invites "generate 8 at
once" changes typical load in a way a single-region-edit never does; (c)
UI/data-model decisions Tunora hasn't made yet — do all 8 outputs become
sibling Versions of one Song? Does the user pick one to keep and discard
the rest, and if so does "discard" mean Phase 9's delete semantics apply
mid-batch? These are real design questions this audit does not resolve,
correctly leaving Batch Generation UI as a DEFER rather than folding it
into a "small" phase claim it would not actually deserve.

**Prompt Library** — real persona value (A, B) but is a **new** capability
requiring a new table + new CRUD API + new UI surface — a larger net-new
surface than Timeline Repaint's zero-backend-change composition, for a
less acutely observed gap (Repaint's clunkiness is inside an existing,
constantly-used feature; a missing prompt library is an absence, not a
friction point inside something already shipped).

**Cover Art** — newly well-evidenced OSS licensing (§10) but requires a
second model runtime with unmeasured VRAM interaction alongside ACE-Step —
a materially larger architectural decision than anything else in this
audit, correctly not attempted without its own dedicated spike (mirroring
exactly how Phase 11 required one before building Extract).

**Mastering/Loudness, MIDI, Chord Detection, `lego`/`complete`, Lyric
Alignment** — see §4/§8/§9/§11 for each; none surfaced new evidence this
session that would elevate them above Timeline Repaint.

## 14. Architecture fit

For **Timeline Repaint Region Selection**, checked against every listed
constraint:

| Constraint | Fit |
|---|---|
| New service? | ❌ No |
| Redis? | ❌ No |
| Another database? | ❌ No — SQLite schema is completely unchanged |
| Cloud GPU? | ❌ No — same local ACE-Step, same turbo tier already used for Repaint |
| New worker? | ❌ No — same `JobService`/`BackgroundTasks` polling |
| Modify ACE-Step? | ❌ No — the REST parameters already exist and are already used |
| Break Version immutability? | ❌ No — Repaint already creates a new immutable Version; nothing about that changes |
| New provider? | ❌ No |

This is the strongest architecture-fit result of any candidate examined —
identical in kind to Phase 10's Version Comparison (a pure composition of
already-existing, already-tested pieces), but with an even smaller surface
(no new API field is even needed, since `repaint_start`/`repaint_end`
already exist in `VersionOperationRequest`).

## 15. GPU / performance considerations

Zero new GPU cost: the underlying generation call is the **exact same**
`repaint` task type, same turbo-tier model, same VRAM profile already
measured and shipped since Phase 5B. No new model needs to load (unlike
Extract's base-tier requirement, or Cover Art's hypothetical second
runtime). The only "processing" this capability adds is client-side
JavaScript (WaveSurfer's own drag-region math), which runs in the browser,
not on the RTX 5060 Ti at all.

## 16. Security considerations

No new attack surface: the region's `start`/`end` values are computed
client-side from a drag gesture over audio the user already owns and is
already playing, then sent through the **exact same**
`repaint_start`/`repaint_end` fields the existing numeric form already
sends — which are already bounds-checked server-side
(`REPAINT_MIN_SECONDS`/`MAX_SECONDS`, `0 <= start`, `end <= source_duration`,
per `app/jobs/service.py`, unchanged). No new file upload, no new parameter
Tunora doesn't already validate, no new cross-Song surface (the operation
still only ever reads the one already-authorized source Version). If a
malicious client sends an out-of-range or malformed region directly to the
API (bypassing the UI), the existing validation already rejects it —
verified as already tested in Phase 5B's own test suite
(`test_repaint_rejects_bad_regions` in `backend/tests/songs/test_operations.py`,
**VERIFIED** this session by inspection).

## 17. Decision matrix

| Capability | User Value | Current Gap | OSS Availability | License | Architecture Fit | GPU Cost | Implementation Complexity | Risk | Decision |
|---|---|---|---|---|---|---|---|---|---|
| Timeline Repaint Region Selection | High, observed across all 3 personas | Real, previously documented (Phase 9) | Full match (WaveSurfer Regions, already a dependency) | BSD-3-Clause | Perfect — zero backend/DB/API change | None (same turbo call) | Low | Low | **RECOMMEND** |
| Batch generation UI | Medium | Real, half-wired | None needed (native) | — | Good, but unresolved data-model questions | Medium (N outputs) | Medium | Medium (storage/concurrency/UX decisions unmade) | DEFER |
| Prompt library | Medium (Persona A/B) | Real, absence-type | No fitting OSS; native BUILD | — | Good, but new table+API | Low | Low-Medium | Low | DEFER (bigger surface than Repaint for less acute value) |
| Cover art | Low-Medium | Real, absence-type | Newly viable, Apache-2.0 models exist | Apache-2.0 | Unresolved — second model runtime, VRAM untested | Unmeasured (UNKNOWN) | High | Medium-High (needs its own spike) | DEFER |
| Mastering/loudness | Low | Real, absence-type | pyloudnorm, MIT | MIT | Good | None | Low | Low | DEFER (no proven need, per Phase 10) |
| MIDI | Low-Medium (Persona C niche) | Real, absence-type | basic-pitch, Apache-2.0 | Apache-2.0 | Good | Low (CPU) | Medium | Low | DEFER |
| Chord detection | Low | Real, absence-type | None well-licensed | — | N/A | N/A | High (BUILD-only) | Medium | REJECT/DEFER |
| `lego`/`complete` | Medium (Persona C) | Real, provider-native, unused | None needed | Same as Extract | Good | Same as Extract (base tier) | Medium | Medium (Phase 11 deliberately deferred to prove the pattern first) | DEFER |
| Lyric alignment | Medium-High if reachable | Real, blocked | Native to ACE-Step but Gradio-only | — | **Blocked** — would require patching the vendored submodule | N/A | High | High | REJECT for now |

## 18. Recommended Phase 12

**Phase title**: Timeline Repaint Region Selection.

**Problem solved**: replacing numeric-seconds entry for the Repaint
operation's time range with a direct, visual, drag-to-select region on the
waveform the user is already viewing.

**Current limitation**: `version-actions.tsx`'s Repaint form requires
typing a start and end time in seconds into two plain number inputs,
verified against the source's duration only after submission.

**User workflow before**: listen to the version → estimate the section's
start/end in seconds by ear or by scrubbing the player → type two numbers
→ submit → discover after the fact if the guess was off.

**User workflow after**: listen to the version → drag directly on the
waveform to mark the section → (optionally fine-tune by dragging the
region's edges, snapped to the same `REPAINT_MIN_SECONDS`/`MAX_SECONDS`
bounds already enforced) → submit the same request as today.

**Why now**: it is the only candidate that is simultaneously a
previously-documented, still-present gap (Phase 9), observed as a direct
friction point across all three personas, and requires **zero** backend,
API, or database change — the purest possible composition of
already-owned, already-tested pieces this audit found.

**OSS projects reused**: WaveSurfer.js Regions plugin (BSD-3-Clause,
already part of the `wavesurfer.js` npm package Tunora depends on — not a
new package, just a new import from one already installed).

**OSS projects adapted**: none needed.

**Components composed**: the existing `AudioPlayer`/WaveSurfer instance
already rendered for the active version; the existing
`repaint_start`/`repaint_end` fields already in
`VersionOperationRequest`/`create_version_from_operation`; the existing
`REPAINT_MIN_SECONDS`/`MAX_SECONDS` bounds; the existing Repaint form's
submit/validation/error-handling flow.

**What must actually be built**: a thin UI layer only — registering the
Regions plugin on the existing waveform when the Repaint form is open,
translating a drawn region's `start`/`end` into the two numbers the
existing form state already holds (which can remain the source of truth,
so a user could still fine-tune numerically if they prefer), and visually
reflecting the existing min/max bounds as drag constraints.

**Expected dependencies**: zero new (a new import path within the
already-installed `wavesurfer.js` package).

**Database impact**: none.

**API impact**: none — `repaint_start`/`repaint_end` already exist and are
already fully validated.

**UI impact**: `frontend/src/components/song/version-actions.tsx` (the
Repaint form gains a visual region selector) and, if the region should be
drawn on the always-visible player rather than only inside the open form,
a small addition to `frontend/src/components/audio/audio-player.tsx` to
expose region events — scope of exactly which component owns the region
should be settled at implementation time by inspecting how tightly
`AudioPlayer` and `VersionActions` are already coupled, not decided by this
audit.

**GPU impact**: none — identical generation call to today's Repaint.

**Storage impact**: none — identical output shape to today's Repaint.

**Security considerations**: none new — see §16.

**Testing strategy**: unit/component tests for the region-to-seconds
conversion and for min/max clamping (frontend, Vitest); no new backend
tests should be needed since no backend code changes, though the
implementation phase should explicitly re-run the existing Repaint backend
test suite to confirm zero regression; a UI-level accessibility check for
keyboard-only region adjustment (WaveSurfer's Regions plugin supports
resize via drag; keyboard-equivalent interaction should be verified, not
assumed, since drag-only interactions are a common accessibility gap).

**Real-GPU requirement**: yes — a real Repaint generated via a
click-and-drag-created region, verifying the resulting audio actually
reflects the selected range, exactly as Phase 5B's own real-GPU Repaint
test already does for the numeric path; the new test should prove the UI
path produces the same correct `repaint_start`/`repaint_end` values a
human would have typed.

**E2E requirement**: yes — a real Playwright test that drags a region on a
real waveform (Playwright supports mouse drag gestures) and confirms the
resulting real generation's Version reflects the intended range, following
this project's established real-E2E-only convention (no mocked Repaint
flow already exists to extend safely without a real one alongside it).

**Main risks**: (1) drag-gesture testing in Playwright against a
canvas-rendered waveform is more finicky than the form-field interactions
every other E2E test in this project uses — this is a real testing-effort
risk, not a product risk; (2) deciding whether the numeric inputs should be
removed, kept as a fallback, or kept in sync with the visual region is a
small UX decision this audit intentionally leaves to the implementation
phase rather than prescribing.

**Explicit non-goals**: waveform editing beyond region selection (no trim/
cut/fade/multi-region composition); any change to what Repaint actually
does server-side; any new audio-analysis capability; Extend/Remix are
explicitly untouched — this phase is Repaint's region-selection UX only.

## 19. Explicit non-goals (for this audit and the recommended phase)

Batch generation UI, Prompt Library, Cover Art, Mastering/Loudness, MIDI,
Chord Detection, `lego`/`complete`, Lyric Alignment, collaboration, cloud
sync, music video, publishing/sharing integrations — all evaluated above
and none selected for Phase 12.

## 20. Deferred capabilities

Same list as §19, each already carrying a researched, licensed OSS path (or
an explicit "no viable OSS, BUILD-only, low priority" conclusion) so a
future audit does not need to re-research from scratch: WaveSurfer Regions
already covers a second potential future use (visual lyric-line/section
markers, if lyric alignment is ever unblocked); basic-pitch for MIDI;
pyloudnorm for loudness; Apache-2.0 image models (Qwen-Image 2.0,
Z-Image-Turbo, FLUX.2 klein 4B) for cover art, pending a dedicated VRAM
spike; no viable candidate for chord detection (BUILD-only, low priority);
`lego`/`complete` remain available on the same base-tier model Extract
already proved reachable, for whenever a dedicated phase is prioritized for
either.

## 21. Implementation readiness

This is an audit only. No application code, test, dependency manifest,
database schema, or ACE-Step file was modified to produce it. No commit was
created. No push was performed. `docs/PHASE-12-PRODUCT-CAPABILITY-GAP-AUDIT.md`
is the only artifact of this session.
