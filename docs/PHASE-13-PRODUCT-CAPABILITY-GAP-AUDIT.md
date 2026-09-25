# Phase 13 Product Capability Gap Audit

Audit only. No application code, dependency, schema, API, UI or ACE-Step
change was made. Evidence labels: **VERIFIED** (read/queried this session),
**EXTERNAL** (public web/API lookup this session), **ESTIMATE** (derived,
labeled), **UNKNOWN** (not established).

## 1. Audit Status

Complete. The only intended repository change is this file (left uncommitted
and unpushed, per the phase rules). Prior audits (`PHASE-9/10/11/12-*`) were
used as a starting point but every load-bearing claim below was re-checked
against the current tree or a live lookup.

## 2. Repository / Git State (VERIFIED)

- Branch `feature`; `HEAD` = `origin/feature` = `fc02f0f` ("Add Timeline
  Repaint Region Selection") after `git fetch`. **Phase 12 is committed and pushed.**
- Recent history: `fc02f0f` (P12) ← `e4a1654` (Extract, P11) ← `f37091b` (Compare, P10) ← `87eba7e` (Song Mgmt, P9) ← `60ca97a`/`9df0776` (Director refine/plan).
- Working tree: `CLAUDE.md` modified (pre-existing, unrelated, untouched every phase) and the `ACE-Step-1.5` submodule reported dirty only because of its own untracked local files.
- Submodule pinned at `ca1e85f` (v0.1.7-69). `git ls-remote origin HEAD` inside it returns the **same** commit: upstream has not moved, so no new ACE-Step capability exists since Phase 12's audit.
- Migration state: `PRAGMA user_version` target 5 (unchanged since Phase 9).

## 3. Phase 12 Verification (VERIFIED)

| Item | Finding |
|---|---|
| WaveSurfer | 7.12.12 (`node_modules/wavesurfer.js/package.json`); installed plugins: envelope, hover, record, regions, spectrogram, timeline, zoom |
| Regions | `AudioPlayer` takes an optional `region` prop, registers `RegionsPlugin`, adds one region, unsubscribes/removes on cleanup |
| Flow | drag/resize → seconds → shared `repaintRegion` state (in `song-details.tsx`) → existing `repaint_start`/`repaint_end` → existing Repaint API → ACE-Step → new Version |
| Numeric fallback | Kept; it is what `validate()` and submit read, and the only keyboard path (Regions plugin has no keyboard handling) |
| Bounds | Single source of truth `REPAINT_MIN/MAX_SECONDS` (3/90) mirrored in `songs.ts`; backend re-validates |
| Tests | 359 Vitest, 536 backend (non-smoke), 18 Playwright specs incl. a real mouse-drag test and a keyboard/mobile test; real-GPU Repaint smoke passed |
| Known limits | No real touch-device check; no keyboard control of the region itself; one pre-existing E2E test flaked once under GPU load and passed on rerun |

Nothing was modified.

## 4. Current Product Capability Matrix (VERIFIED from code/docs)

| Area | Exists | Does NOT exist |
|---|---|---|
| Creation | Create Song: prompt, lyrics, instrumental/vocal, language (11 options incl. Kannada, Hindi, Tamil, Telugu), duration (30/60/120/180 s), seed (Advanced), title, Project | Prompt/preset saving; inference-steps, guidance, model-tier controls; audio format choice |
| AI assist | Song Director plan (`/v1/create_sample`), refinement (`/format_input`), both stateless and reviewable | Lyric authoring/refinement tools beyond the Director; structure-aware lyric editor |
| Generation | ACE-Step turbo via `MusicGenerationProvider`; jobs, polling, failure states, persistence, one output per job | Multiple outputs per job; queue UI; cancel |
| Versioning | Song → immutable Version → Job; lineage (`operation`, `source_version_number`); version history; latest marker | Branch tree view; version notes/labels; version delete |
| Creative ops | Extend, Remix, Repaint (numeric + timeline region), Extract (vocals/drums/bass/guitar, base tier) | `lego`, `complete`; other 8 extract track types unvalidated; multi-region repaint |
| Audio | Playback, waveform, seek, volume, MP3 download, Range/ETag route, local storage | WAV/FLAC/stems ZIP export; loudness info; trim/fade |
| Analysis | Provider-reported metadata (BPM, key, time signature, genre) shown with disclosure; A/B Version Comparison | Own analysis (LUFS, chords, beats); MIDI |
| Projects | Create/rename/delete, assign/remove Songs, filter | Project export; project-level operations |
| Library | Search, sort, favorite, rename, delete, project filter | Tags; bulk actions; export |
| Infrastructure | Local-first, SQLite, filesystem, FastAPI, Next.js 16, ACE-Step; backend has only 3 runtime deps (fastapi, uvicorn, httpx) | Any audio-DSP dependency (no librosa/soundfile/pyloudnorm installed despite being "locked-in" in CLAUDE.md); worker/queue |

## 5. Remaining Product Gaps

Journey check.

- **Beginner** (idea → generate → listen → save → improve → organize → export): every step works except *export* (one lossy MP3 per Version) and *improve-by-retry* — to get "another take" the user must re-type the Create form or use Remix, even though the Version already carries prompt/lyrics/language/seed.
- **Advanced** (create → version → extend → remix → repaint → extract → compare → refine): complete. Gap: no "another take of the same idea" branch; comparison only works between existing Versions.
- **Power user** (batch → experiment → compare → organize → export → reuse prompts → manage assets): missing batch/takes, prompt reuse, tags, bulk export.

Real gaps, ranked by how much of the journey they block:

1. Nothing lets a user generate **another take** of an existing Song's idea without retyping (§12-A).
2. **Export** is MP3-only. Worse, ACE-Step's native `audio_format` (`flac`, `wav`, `wav32`, `opus`, `aac`) is never sent by Tunora, and Extend/Remix/Repaint/Extract re-upload the source as `source.mp3` (`ace_step.py:344`), so every derived Version is a lossy re-encode of a lossy file (§12-B).
3. Prompt reuse, tags, bulk actions (absence-type gaps).
4. Cover art, MIDI, chords, mastering, lyric alignment (absence-type, each needs new model/dependency or is blocked).

## 6. ACE-Step Capability Audit (VERIFIED against vendored `ca1e85f`)

- `acestep/constants.py:76`: `TASK_TYPES = [text2music, repaint, cover, cover-nofsq, extract, lego, complete]`; turbo tier supports only the first four (`:82`), base tier all seven (`:89`).
- REST routes present (grep of `@app.get/post`): `/release_task`, `/query_result`, `/format_input`, `/create_random_sample`, `/v1/create_sample`, `/v1/init`, `/v1/reinitialize`, `/v1/models`, `/v1/stats`, `/v1/audio`, LoRA (`/v1/lora/*`), dataset and training routes. **No route for lyric timestamps/LRC, chord, MIDI, loudness, scoring or cover art.**
- `docs/en/API.md:205`: `batch_size` "max 8", default 2. `docs/en/API.md:144`: `audio_format` accepts `flac, mp3, opus, aac, wav, wav32`.
- Tunora side: `CreateJobRequest.batch_size` exists and is forwarded (`ace_step.py:206`), but the provider only ever reads `audio_items[0]` (`ace_step.py:144`), and creative ops force `batch_size: 1` (`:262`). Extra batch outputs would be computed and discarded. **`audio_format` is not sent anywhere.**
- `lego` and `complete` are base-tier only; Phase 11 deliberately deferred them. Not re-validated live in this audit (no GPU call was needed to answer the roadmap question).
- Conclusion: no capability changed since Phase 12. Two native features (`audio_format`, `batch_size`) are real and only partially wired.

## 7. GitHub OSS Reuse Audit (EXTERNAL, live GitHub API, 2026-09-24)

| Repo | License (SPDX) | Stars | Last push | Use here | Decision |
|---|---|---|---|---|---|
| katspaugh/wavesurfer.js | BSD-3-Clause | 10.4k | 2026-09-24 | Already used; also has an **Envelope** plugin (volume/fade automation) | REUSE (present) |
| csteinmetz1/pyloudnorm | MIT | 783 | 2026-01-04 | BS.1770 loudness (LUFS) | REFERENCE/ADAPT (needs numpy/scipy + soundfile; not installed) |
| librosa/librosa | ISC | 8.6k | 2026-09-24 | Beats/tempo/chroma/onsets | REFERENCE (heavy dependency tree) |
| spotify/basic-pitch | Apache-2.0 | 5.6k | 2025-11-13 | Audio→MIDI (code + bundled model) | REUSE candidate, deferred (TF/ONNX runtime cost UNKNOWN) |
| craffel/pretty-midi | MIT | 1.0k | 2026-02-18 | MIDI file writing | REFERENCE |
| adefossez/demucs | MIT | 3.2k | 2026-08-31 | Stem fallback | REFERENCE (native `extract` already covers it) |
| openai/whisper | MIT | 109k | 2026-08-31 | Transcription; weights Apache-2.0 on HF | REFERENCE (lyric-alignment ingredient) |
| m-bain/whisperX | BSD-2-Clause | 24k | 2026-08-30 | Word-level alignment | REFERENCE (sung vocals + Kannada quality UNKNOWN) |
| jianfch/stable-ts | MIT | 2.3k | 2026-05-30, **archived** | Whisper timestamps | REJECT (archived) |
| MontrealCorpusTools/Montreal-Forced-Aligner | MIT | 1.9k | 2026-08-20 | Forced alignment (speech) | REFERENCE (speech-trained, not singing) |
| MTG/essentia | **AGPL-3.0** | 3.7k | 2026-09-21 | Chords/key/beats | REJECT (copyleft, standing hard-reject) |
| aubio/aubio | **GPL-3.0** | 3.8k | 2026-04-10 | Beat/pitch | REJECT (GPL) |
| CPJKU/madmom | GitHub reports `NOASSERTION`; LICENSE file states code and data/model files carry separate licenses; project audit (`docs/LICENSE-AUDIT.md:53`) records models **CC BY-NC-SA 4.0** | 1.7k | 2026-03-20 | Chords/beats | REJECT (non-commercial models) |
| Tongyi-MAI/Z-Image | Apache-2.0 | 12k | 2026-02-09 | Image gen | REFERENCE (cover art) |
| QwenLM/Qwen-Image | Apache-2.0 | 8.4k | 2026-02-10 | Image gen | REFERENCE |
| black-forest-labs/flux2 | Apache-2.0 (code) | 2.7k | 2026-03-12 | Image gen code | REFERENCE; weights vary, see §8 |

No mature OSS "prompt/preset library" component fits (it is a one-table per-user CRUD in SQLite); this is a native BUILD if ever needed. No suitably licensed, packaged chord-recognition model was found: Hugging Face search for "chord" returned only small community fine-tunes (some Apache-2.0, all low-download, unvetted) and `Ubisoft/ubisoft-laforge-chord` marked `license:other`; a search for forced-alignment models returned nothing usable.

## 8. Hugging Face / Model Audit (EXTERNAL, HF API)

| Model | Weight license | Gated | Params (safetensors) | bf16 weight size (ESTIMATE = params × 2 B) |
|---|---|---|---|---|
| black-forest-labs/FLUX.2-klein-4B | apache-2.0 | no | 3.88 B | ~7.8 GB |
| Tongyi-MAI/Z-Image-Turbo | apache-2.0 | no | 6.15 B | ~12.3 GB |
| Qwen/Qwen-Image | apache-2.0 | no | 20.4 B | ~41 GB (needs quantization to be viable) |
| black-forest-labs/FLUX.2-dev | `flux-non-commercial-license` | auto-gated | 32.2 B | ~64 GB |
| openai/whisper-large-v3 | apache-2.0 | no | 1.54 B | ~3.1 GB |
| openai/whisper-small | apache-2.0 | no | 0.24 B | ~0.5 GB |

Correction to Phase 12's audit: FLUX.2 [dev] is under a **non-commercial** license (not merely "paid"); either way it is rejected. Code license, weight license and dataset license are separate: none of the datasets behind these models were audited (**UNKNOWN**), so "commercial-safe" is asserted only for the weights' stated license.

## 9. License Audit

| Component | Code | Weights/data | Gate result |
|---|---|---|---|
| WaveSurfer.js + plugins | BSD-3-Clause | n/a | Pass |
| pyloudnorm, pretty-midi, demucs, whisper, whisperX (BSD-2), MFA | MIT/BSD | Whisper Apache-2.0 | Pass |
| librosa | ISC | n/a | Pass |
| basic-pitch | Apache-2.0 | bundled, Apache-2.0 per project audit | Pass (runtime cost unknown) |
| Z-Image-Turbo, FLUX.2-klein-4B, Qwen-Image | Apache-2.0 | Apache-2.0 | Pass on license; fails/unknown on fit (§10) |
| Essentia | AGPL-3.0 | AGPL | **Fail** |
| aubio | GPL-3.0 | n/a | **Fail** |
| madmom | BSD code | CC BY-NC-SA 4.0 models | **Fail** (models) |
| FLUX.2 [dev] | Apache-2.0 code | non-commercial | **Fail** |
| stable-ts | MIT | n/a | Archived, reject |
| **FFmpeg on this dev machine** | The installed build is `ffmpeg-9.0.1-full_build-shared` (Gyan "full" builds enable GPL components) | n/a | Fine as an external dev tool; **must not be bundled/redistributed**. Project rule (CLAUDE.md) requires an LGPL-only build for anything shipped. |

## 10. GPU / VRAM Audit

Baseline (from Phase 11, not re-measured): ACE-Step turbo + base together peaked near 11.2 GB on the 16 GB RTX 5060 Ti. Anything else on GPU shares roughly 4-5 GB of headroom.

- FLUX.2-klein-4B: weights ~7.8 GB bf16 (ESTIMATE, excludes text encoder and activations). Coexistence with ACE-Step is **UNKNOWN** and probably requires unloading one model. Cover art needs its own spike.
- Z-Image-Turbo (~12.3 GB) and Qwen-Image (~41 GB) do not fit alongside ACE-Step without quantization/offload.
- Whisper-small (~0.5 GB) / large-v3 (~3.1 GB) could coexist; usefulness on sung Kannada is UNKNOWN.
- Everything CPU-side (pyloudnorm, librosa, FFmpeg): zero GPU.
- Candidates A and B below: **zero new GPU cost**.

## 11. Architecture Impact (summary)

Strongly preferred: zero new services/tables/dependencies. Candidates needing a new dependency: loudness (numpy/scipy/soundfile), MIDI (TF or ONNX), chords (no acceptable option), cover art (second model runtime), lyric alignment (torch + Whisper, plus unproven on singing). Candidates needing none: "New take" (A), lossless format (B), prompt library (needs one small table only).

## 12. Candidate Capability Analysis

### A. New take / Variations from a Version  (reclassifies "Batch Generation")

- **Problem**: The user likes an idea but wants a different rendition. Today: retype, or Remix (which needs a description and changes style).
- **What exists (VERIFIED)**: `VersionResponse` already returns `prompt`, `lyrics`, `language`, `instrumental`, `seed`, `duration`. `POST /api/jobs` with `song_id` creates the next Version of an existing Song (used by E2E `generateNextVersion` with `prompt`, `song_id`, `instrumental`, `duration`, `seed`). Seed is a supported field. Job tracking, pending-version UI and lineage already exist.
- **What is missing**: a UI action on Song Details ("Another take") that submits the source Version's spec with a fresh seed; a lineage label. **Batch via ACE-Step's `batch_size` is a worse fit**: Tunora reads only `audio_items[0]` (`ace_step.py:144`), so batch outputs would need a new one-job-to-N-Versions data model plus storage for up to 8 files per click. Composing N sequential ordinary jobs avoids all of that and inherits failure handling per take.
- **OSS**: none needed. **License**: n/a. **GPU**: same turbo call per take (serial). **Scope**: frontend-first; whether the Version should record `operation="ORIGINAL"` (lineage-free) or a new `TAKE` operation is an open design question — the former needs zero migration, the latter needs an additive migration and provider/service branches. **Risks**: storage growth; user-triggered N jobs queued on a single-worker ACE-Step. Proceed to implementation audit: **Yes**.

### B. Lossless output format (FLAC/WAV) and cleaner derived Versions

- **Problem**: Only lossy MP3 is produced, and every Extend/Remix/Repaint/Extract input is that MP3 re-uploaded as `source.mp3`, compounding loss. Export options are absent.
- **What exists (VERIFIED)**: ACE-Step natively supports `audio_format` (`API.md:144`); `filenames.py` already whitelists `.wav/.flac` and maps `audio/wav`/`audio/flac`; the download button derives label/size from the stored resource.
- **What is missing**: Tunora never sends `audio_format`; the upload filename/MIME is hard-coded `source.mp3`/`audio/mpeg`.
- **OSS**: none needed. **License**: n/a. **GPU**: none (encoding is CPU). **Scope options**: (1) a provider-level setting (env such as `ACE_STEP_AUDIO_FORMAT`) — no migration, no UI, global; (2) per-Version format stored in the immutable spec — needs an additive migration and a Create-form control. **Risks**: FLAC ~3-5x MP3 size (ESTIMATE); WaveSurfer downloads and decodes the whole file, so long FLAC/WAV files raise browser memory; existing MP3 Versions stay MP3; quality benefit for derived Versions is plausible but **not measured**. Proceed to implementation audit: **Yes, as a spike-gated candidate**.

### C. Prompt / Lyrics Library

Real absence-type gap. New table + CRUD + UI; no fitting OSS. Value moderate, no urgency evidence. Deferred; a native BUILD only.

### D. Cover Art

Apache-2.0 weights exist (FLUX.2-klein-4B best-sized). Requires a second GPU runtime beside ACE-Step (coexistence UNKNOWN), new storage/relationship, and image-quality judgment. Highest architectural cost. Deferred pending its own VRAM spike.

### E. Mastering / Loudness

Analysis-only (LUFS/peak/clipping) via pyloudnorm (MIT) or an FFmpeg `ebur128` pass is low-risk but would add numpy/scipy/soundfile to a 3-dependency backend, or lean on an FFmpeg build that is not currently bundled/LGPL-verified. Value is low without a mastering action. Deferred.

### F. MIDI / Chords / Musical analysis

MIDI: basic-pitch is well licensed but adds a heavy ML runtime for a niche persona. Chords/beats/key: every strong option (Essentia AGPL, aubio GPL, madmom NC models) fails the license gate; librosa (ISC) could give chroma but chord *labeling* would be a from-scratch BUILD with unproven accuracy. Rejected/deferred. ACE-Step already reports BPM/key/time signature, which Tunora shows.

### G. ACE-Step advanced (`lego`, `complete`)

Base-tier only (extra VRAM as in Phase 11), no product demand evidence, semantics unvalidated on Tunora's flow. Defer until a persona need appears. A live validation was intentionally not run: nothing in this audit depends on it.

### H. Lyrics / vocal workflow

Timing/alignment: ACE-Step exposes no REST route for it (LRC lives only in the Gradio layer; verified again via route list), so it is blocked without patching the vendored submodule (prohibited). External alignment (Whisper/whisperX) targets speech; accuracy on sung and Kannada vocals is UNKNOWN. Multilingual generation already works through the language selector (Kannada included), but generation *quality* for Indian languages is a model limitation that only human listening can judge. Do not claim sync is feasible. Deferred/rejected for now.

### I. Audio editing

Trim/fade/crossfade/multi-region turn Tunora into a DAW; the Phase 12 prompt already excluded this. WaveSurfer's Envelope and Regions plugins could support it visually, but rendering edits still needs server-side DSP and a new immutable-Version story. Out of MVP.

### J. Publishing / Export

Splits into (1) format (candidate B), (2) stems ZIP / project export (needs a ZIP builder and route; stdlib `zipfile` suffices, no OSS needed), (3) metadata/cover-art embedding (depends on D). Only (1) is small and self-contained.

### K. Additional gaps found

- **Queue/cancel visibility**: single-worker ACE-Step with no cancel; matters more if A ships. Note for A's audit.
- **Dependency drift in project docs**: CLAUDE.md lists soundfile/librosa/FFmpeg LGPL as locked-in audio tooling, but none is in `backend/pyproject.toml`; the only FFmpeg present is a GPL "full" build. Any audio-analysis phase must resolve this first.

## 13. Candidate Decision Matrix

| Candidate | User value | Product gap | OSS availability | License clarity | ACE-Step fit | Architecture fit | GPU impact | Complexity | Security | Testability | Reuse | Key blockers | Recommendation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A. New take / variations | Strong | Strong | n/a (native) | n/a | Strong (existing task, seed) | Strong (no infra) | None new | Low | Low | Strong | Very strong (`song_id`+seed, spec already exposed) | lineage-label decision; queue depth | **Proceed to implementation audit** |
| B. Lossless format | Moderate-Strong | Moderate | n/a (native) | n/a | Strong (documented param) | Strong | None | Low-Moderate | Low | Moderate (needs size/decode checks) | Strong | must verify ACE-Step returns valid FLAC/WAV via REST and that the player decodes it; MIME/upload hard-coding | Spike-gated candidate |
| C. Prompt library | Moderate | Moderate | Weak (none fits) | n/a | n/a | Good (1 table) | None | Low-Moderate | Low | Strong | Low (native build) | no demand evidence | Defer |
| D. Cover art | Low-Moderate | Moderate | Moderate | Strong (Apache-2.0 weights) | None | Weak (2nd model runtime) | High/UNKNOWN | High | Moderate | Weak | Moderate | VRAM coexistence, image quality | Defer |
| E. Loudness | Low | Weak | Strong (pyloudnorm) | Strong (MIT) | None | Moderate (new deps) | None | Low | Low | Strong | Strong | deps, no action to attach | Defer |
| F. MIDI/Chords | Low-Moderate | Weak | Weak (licenses) | Fail for chords | None | Weak | Low-Moderate | High | Low | Weak | Weak | GPL/AGPL/NC, runtime weight | Reject/defer |
| G. lego/complete | Moderate (niche) | Weak | n/a | n/a | Moderate (base tier) | Moderate | Base-tier VRAM | Moderate | Low | Moderate | Strong | no validated semantics | Defer |
| H. Lyric alignment | Moderate-Strong if feasible | Strong | Weak | Mixed | **Blocked** | Weak | Low-Moderate | High | Low | Weak | Weak | no REST route; singing accuracy UNKNOWN | Reject for now |
| I. Audio editing | Low-Moderate | Weak | Moderate (WaveSurfer) | Strong | None | Weak | None | High | Moderate | Weak | Moderate | scope creep, new DSP | Out of scope |
| J. ZIP/export beyond format | Low-Moderate | Moderate | n/a (stdlib) | n/a | n/a | Good | None | Moderate | Moderate (path/zip safety) | Moderate | Moderate | depends on B/D | Defer |

## 14. Recommended Next Implementation Candidate

**Candidate A: "Another take" from a Version (variations by seed), composed from existing endpoints.**

Evidence chain: the Version API already exposes every input needed (`VersionResponse`: `prompt, lyrics, language, instrumental, seed, duration`); `POST /api/jobs` with `song_id` already creates a new Version of the same Song (exercised by the existing E2E helper); seed is already an accepted field; pending-version/polling UI already exists from Phase 5B. No dependency, migration (if lineage stays as ORIGINAL), API contract change, or GPU cost is required, and it closes the largest journey gap (iterate on an idea without retyping) for all three personas. It also supersedes "Batch Generation": ACE-Step's `batch_size` cannot be used without a new data model, since Tunora reads only the first output.

## 15. Why Other Candidates Are Deferred

- **B (lossless format)**: valuable and small, but its central claim (derived Versions improve, FLAC plays in the current whole-file-decode player) is unmeasured; it should follow as its own spike rather than being bundled.
- **C**: absence-type, no friction evidence.
- **D**: highest architectural cost; VRAM coexistence unknown.
- **E/F**: new heavy dependencies for low value; license failures eliminate most chord tools.
- **G**: no demand evidence; base-tier VRAM.
- **H**: blocked by ACE-Step's REST surface and unproven on singing.
- **I/J**: scope creep into a DAW, or dependent on B/D.

## 16. Proposed Implementation Scope (for a later, separately approved phase)

**In scope**: an "Another take" action in `VersionActions`/`SongDetails` that submits the active Version's `prompt`, `lyrics`, `language`, `instrumental`, `duration` with a new random seed and `song_id`; reuse the existing pending-version/polling and lineage display; confirm the created Version becomes Latest and selected like other operations; optional "N takes" as N serial requests with a small cap (cap to be decided in the implementation audit).

**Out of scope**: ACE-Step `batch_size` outputs, new endpoints, new task types, prompt library, audio editing, any model/dependency.

**Reuse**: `createVersion`/job creation client, `VersionActions` panel pattern, pending-version banner, Version lineage labels. **External reuse**: none. **Adapt**: how lineage is labeled ("Take" vs "Original"). **Compose**: existing endpoints only. **Build**: one UI action and its tests. **Database**: none if ORIGINAL is reused; additive migration only if a `TAKE` operation is chosen (decision belongs to the next audit). **API**: existing. **UI**: `song-details.tsx`, `version-actions.tsx`. **GPU**: one turbo generation per take. **Testing**: Vitest for the payload (fresh seed, spec copied), backend regression unchanged, one real-GPU Playwright test (take creates a new distinct Version, source untouched), mutation checks on payload mapping. **Security**: no new surface; server-side validation and `song_id` pattern already exist.

## 17. Explicit Non-Goals

No implementation in this phase; no batch UI; no new dependency, model, migration, endpoint or ACE-Step change; no lyric-sync, chord, MIDI, mastering or cover-art work.

## 18. Risks / Unknowns

- Whether repeated takes with different seeds are audibly diverse enough (needs a human listen).
- Queue depth/latency with a single-worker ACE-Step when several takes are requested.
- Storage growth per take.
- Lineage representation (ORIGINAL vs new operation).
- Candidate B: whether ACE-Step's REST path returns valid FLAC/WAV and whether the player copes with larger files.
- Coexistence VRAM for any image/ASR model (all UNKNOWN, none measured).
- Dataset licenses behind the image and ASR weights were not audited.
- ACE-Step generation quality for Kannada and other Indian languages is unmeasured objectively.

## 19. Validation Plan (for Candidate A, at its own audit)

1. Confirm through the existing API that `POST /api/jobs` with `song_id` copies nothing implicitly and a new seed yields a distinct Version.
2. Unit tests for payload construction; component tests for pending/failed states.
3. One real-GPU Playwright test: create a Song, request a take, verify a new Version, different audio hash, different seed, source Version bytes unchanged.
4. Mutation tests: wrong seed reuse, missing `song_id`, wrong field mapping.
5. Regression: full Vitest, backend suite, and existing E2E specs.

## 20. Final Recommendation

Proceed to an **implementation audit for Candidate A ("Another take")**, after user approval. Keep Candidate B (lossless format) as the follow-up spike. Do not start batch generation through ACE-Step's `batch_size`, cover art, or any music-analysis dependency: each lacks either evidence of need, a fitting license, or a validated GPU/architecture story. No code changes are recommended in Phase 13 itself.
