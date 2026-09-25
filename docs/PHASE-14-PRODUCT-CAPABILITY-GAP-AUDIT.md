# Phase 14 Product Capability Gap Audit

Audit only. No application code, dependency, schema, API, UI or ACE-Step file was changed. Two
harmless read-only/probe calls were made to the already-running local ACE-Step server (a 10 s
format probe and one extract routing probe); their outputs stayed in the session scratch area.
Evidence labels: **VERIFIED** (read or executed this session), **EXTERNAL** (public lookup this
session), **VENDOR CLAIM** (model card statement, not measured), **ESTIMATE** (derived),
**UNKNOWN**.

## 1. Audit Status

Complete. The audit found one item that changes the roadmap: a silent model fallback that affects
the already-shipped Extract feature (§17). The Phase 13 candidate "lossless / FLAC" was freshly
validated and is real but is not the highest-value next step.

## 2. Repository / Git State (VERIFIED)

- Branch `feature`; after `git fetch origin feature`, `HEAD` = `origin/feature` = `df1545e0666a0f014a90a382a105f508d30bbc76`. **Phase 13 is pushed.**
- Recent history: `df1545e` (P13 Another Take) <- `fc02f0f` (P12) <- `e4a1654` (P11 Extract) <- `f37091b` (P10) <- `87eba7e` (P9).
- Working tree: only `CLAUDE.md` (pre-existing, unrelated) modified and the `ACE-Step-1.5` submodule marker; plus this new document.
- ACE-Step submodule `ca1e85f` (2026-08-29, `v0.1.8-21-gca1e85f`). `git ls-remote origin HEAD` returns the same SHA: upstream has not moved since Phase 12/13.
- Migration state: `LATEST_VERSION = 5` (unchanged since Phase 9).

## 3. Phase 13 Verification (VERIFIED)

- `ANOTHER_TAKE` is in `CREATIVE_OPERATIONS` (`app/songs/operations.py`), the route allowlist (`routes_songs.py:125`), `AceStepMusicGenerationProvider.supported_operations`, and 14 non-test references across backend/frontend.
- `_create_another_take` copies prompt/lyrics/language/instrumental/duration, forces `seed=None`, never copies `batch_size`, reads no source audio, refuses EXTRACT sources, and goes through `create_and_submit` (song-scoped numbering, lineage columns, same-song trigger).
- Tests: `tests/songs/test_another_take.py` (18), real-GPU `tests/test_another_take_smoke.py`, Vitest additions, and a real Playwright test. This session's earlier run: backend 554 passed, smoke 13 passed, Vitest 365 passed, Playwright 19/19.
- The Phase 13 seed finding was not just repeated: the implementation (`seed=None` -> `use_random_seed: true`, `ace_step.py`) and the recorded spike table in `docs/PHASE-13-IMPLEMENTATION.md` (same seed twice gave different sha256 and low correlation) are consistent with the code path. It applies to the tested deployment (turbo, 10 s instrumental) only.

## 4. Current Product Capability Matrix (VERIFIED from code)

| Area | Status | Notes |
|---|---|---|
| Create Song: prompt, lyrics, language (11), instrumental, duration (30/60/120/180 s), seed, title | EXISTS | `create-song-schema.ts` |
| AI Song Director (plan, refine) | EXISTS | ACE-Step 5Hz-LM via `/v1/create_sample`, `/format_input`; stateless |
| Generation lifecycle (jobs, polling, failure, persistence) | EXISTS | in-process BackgroundTasks; no cancel |
| Restart behavior of in-flight jobs | UNKNOWN | not re-audited this phase |
| Song / Version / history / lineage / operation / source | EXISTS | immutable snapshots, triggers |
| Extend, Remix, Repaint (numeric + timeline), Another Take | EXISTS | Extend/Remix/Repaint validated on the turbo tier |
| Extract (vocals, drums, bass, guitar) | PARTIAL | works end to end, but see §17: base model not guaranteed in the stock deployment |
| Playback, WaveSurfer waveform, seek, Range route, MP3 download, local storage | EXISTS | MP3 only in practice |
| Provider metadata (BPM, genre, key, time signature) and Version comparison | EXISTS | provider-reported only |
| Projects (create/rename/delete/assign/filter) | EXISTS | |
| Library (search, sort, favorites, rename, delete, project filter) | EXISTS | |
| Export beyond single-version MP3 download | MISSING | no WAV/FLAC, ZIP, stems bundle, project export |
| Batch/multiple outputs per generation | MISSING | `audio_items[0]` only |
| Prompt/preset reuse, tags, bulk actions | MISSING | |
| Own audio analysis (loudness, chords, beats), MIDI, cover art, lyric timing | MISSING | |
| Infrastructure | EXISTS | Next.js 16, FastAPI (3 runtime deps), SQLite, filesystem, ACE-Step, RTX 5060 Ti 16 GB |

## 5. Current User Journey

Idea -> prompt/lyrics -> plan (Director) -> generate -> listen -> **Another Take** -> Extend / Remix / Repaint (drag region) / Extract -> Compare -> organize (Projects, favorites) -> improve -> **export (weakest step)**. Every creation and iteration step exists. Export is one lossy 128 kbps MP3 per Version. The Extract step depends on a deployment detail (§17).

## 6. Remaining Product Gaps

1. **Extract may not be served by the model it was validated on** (correctness of a shipped feature; §17).
2. Export/quality: MP3 128 kbps only, and every derived operation re-uploads that MP3 (§7).
3. Multiple outputs per generation and comparison workflows (§8).
4. Absence-type gaps: prompt reuse, cover art, loudness info, MIDI, chords, lyric timing, audio editing (§9-§15).

## 7. Lossless / Native Audio Investigation

**ACE-Step (VERIFIED)**: `release_task_models.py:115-117`: `audio_format` accepts `flac, mp3, opus, aac, wav, wav32`, default `mp3`. `audio_utils.py:117-183`: MP3 is encoded via ffmpeg/libmp3lame with default **128k**, allowed bitrates 128/192/256/320k, but `mp3_bitrate` is **not exposed** on the REST models (no match in `acestep/api/http/*`), so over REST MP3 is fixed at 128k. FLAC/WAV use the soundfile backend, opus/aac use ffmpeg.

**Live probe (VERIFIED, 10 s, seed 7, same prompt, direct to the running server):**

| Format | Bytes | Codec / rate | Content-Type |
|---|---|---|---|
| mp3 | 160,940 | mp3, 48 kHz, stereo, 128 kb/s | audio/mpeg |
| flac | 824,810 (5.1x) | flac, 48 kHz, stereo | audio/flac |
| wav | 3,840,088 (23.9x) | pcm_f32le, 48 kHz, stereo | audio/wav |

Linear ESTIMATE for a 3 min song: mp3 ~2.9 MB, flac ~14.8 MB, wav ~69 MB.

**Tunora (VERIFIED)**: the provider never sends `audio_format`. Storage is nearly format-agnostic (`filenames.py` whitelists `.wav/.flac/.opus/.aac`, `media_types.py` maps flac/opus/aac, the Range route serves any stored file). The hard couplings are (a) `ace_step.py:347` uploads every derived-operation source as `("source.mp3", ..., "audio/mpeg")` regardless of the real format, and (b) `format-bytes.ts` labels only known MIME types ("Download MP3", otherwise "Download audio"). Extend/Remix/Repaint/Extract all upload the stored file as source, so today they feed a 128 kbps MP3 into the model and encode the result to another 128 kbps MP3.

**Which problem is it?** Generation output (A) and derived-version source quality (B/C) are real and share one fix; download/export (E) benefits. Browser playback (D) is not a problem: WaveSurfer decodes the whole file to float PCM regardless of container, so decoded memory is format-independent (3 min at 48 kHz stereo float32 is about 69 MB ESTIMATE); only transfer size grows. The audible benefit for derived Versions is **UNKNOWN**: the model also round-trips audio through its own VAE, so a lossless source removes one lossy layer, not all. It needs a listening test, which this audit cannot substitute.

**Complexity**: (1) provider-level env default (no migration, global) or (2) per-Version format in the immutable spec (additive migration + Create-form control). Both need the upload filename/MIME fix and the download label. Backward compatible (old MP3 Versions stay valid). CPU cost: encoding only, no GPU. Storage: about 5x for FLAC.

**Verdict**: real, low-risk, no OSS needed (native ACE-Step feature). Second priority; see §25.

## 8. Batch Generation Investigation

- ACE-Step (VERIFIED): `docs/en/API.md:205` `batch_size` max 8 default 2; `gpu_config.py` tier5 (12-16 GB) max batch 4 with or without LM; tier6a (16-20 GB) 4 with LM / 8 without, with an in-code empirical note "60 s, turbo: noLM-4 -> 13.3 GB, LM-2 -> 11.9 GB, LM-4 -> ~13.5 GB". `/v1/stats` (live): queue max 200, average job 11.7 s over 52 jobs.
- Tunora (VERIFIED): `get_result` reads only `audio_items[0]` (`ace_step.py:144`); creative operations force `batch_size: 1`; a Job maps to exactly one Version. Using `batch_size` would require a one-job-to-N-Versions (or grouped-jobs) model, N audio files per click, and a new progress model.
- Decision: **Another Take (Phase 13) already covers "another idea rendition" without any of this.** Batch remains DEFER; the incremental value over serial takes is speed, not capability, and 13.3-13.5 GB peaks leave little headroom next to a second model.

## 9. Prompt Library Investigation

GitHub search for prompt libraries returned only tiny music-prompt lists (`Anil-matcha/awesome-minimax-music-3-prompts` NOASSERTION 9 stars, `musegen/awesome-music-prompts` MIT 0 stars); no mature component fits. The need is a per-user record (prompt/lyrics/language/duration) which Tunora already stores per Version (`VersionResponse` exposes them). Value is UI-level reuse ("start from this Version"), which the Create form could take as a query parameter. No demand evidence. **BUILD-small, DEFER.**

## 10. Cover Art Investigation

| Model | Code / weight license | Params (HF) | VRAM statement |
|---|---|---|---|
| FLUX.2-klein-4B (`black-forest-labs/FLUX.2-klein-4B`) | Apache-2.0 / Apache-2.0 | 3.88 B | VENDOR CLAIM "as little as 13GB VRAM" |
| Z-Image-Turbo (`Tongyi-MAI/Z-Image-Turbo`) | Apache-2.0 / Apache-2.0 | 6.15 B | VENDOR CLAIM "fits comfortably within 16G VRAM consumer devices" |
| Qwen-Image (`Qwen/Qwen-Image`) | Apache-2.0 / Apache-2.0 | 20.4 B | not verified; bf16 weights alone ~41 GB (ESTIMATE) |
| FLUX.2-dev | `flux-non-commercial-license` | 32.2 B | REJECT (non-commercial) |

Measured now: the idle ACE-Step (turbo + 1.7B LM) holds **8,408 MiB of 16,311 MiB**; a 13-16 GB image model cannot coexist and would need sequential load/unload, a second runtime (diffusers) and its own spike. Dataset licenses behind these models were not audited (UNKNOWN). Also needs a storage/relationship design (Song vs Version). **DEFER.**

## 11. Loudness / Mastering Investigation

- Licenses (EXTERNAL, GitHub API): `csteinmetz1/pyloudnorm` MIT (last push 2026-01-04; PyPI 0.2.0 requires scipy, numpy); `librosa/librosa` ISC; `jiaaro/pydub` MIT; `PyAV-Org/PyAV` BSD-3-Clause.
- **FFmpeg re-check (VERIFIED)**: the only FFmpeg on this machine is `ffmpeg 9.0.1-full_build-www.gyan.dev` at a WinGet path, built with `--enable-gpl --enable-version3` including libx264/libx265. It is locally installed, **not bundled** in the repo. **Tunora's own code and scripts do not reference ffmpeg/ffprobe at all** (grep across `backend/app`, `frontend/src`, `pyproject.toml`, start scripts is empty); only the optional ffprobe use in smoke tests (`shutil.which`). ACE-Step itself shells out to ffmpeg for MP3/AAC/opus export (`audio_utils.py`); that is ACE-Step's own dependency. So there is no redistribution problem today, but a GPL build must not become a bundled Tunora dependency; the project's LGPL-only rule (CLAUDE.md) is unverified on this machine.
- The backend has 3 runtime dependencies (fastapi, uvicorn, httpx); pyloudnorm would add numpy+scipy+a decoder. Loudness information alone has no action attached. **DEFER.**

## 12. MIDI / Musical Structure Investigation

`spotify/basic-pitch` Apache-2.0 (last push 2025-11-13), `craffel/pretty-midi` MIT, `Music-and-Culture-Technology-Lab/omnizart` MIT (code; weights license UNKNOWN). All add heavy ML runtimes for a niche persona and no ACE-Step tie-in. **DEFER.**

## 13. Chord Detection Investigation

Current licenses (EXTERNAL): Essentia AGPL-3.0, essentia.js AGPL-3.0, aubio GPL-3.0, madmom code BSD with separately licensed models (project audit `docs/LICENSE-AUDIT.md:53`: CC BY-NC-SA 4.0), librosa ISC (features only, no chord labeler), `CPJKU/beat_this` MIT (beats; weight license UNKNOWN), `mir-aidj/all-in-one` MIT (last push 2024-05-09; weights UNKNOWN). No commercially clean, maintained chord recognizer was verified. **REJECT/DEFER.**

## 14. Lyric Alignment Investigation

- **REST capability (VERIFIED)**: no lyric-timestamp/LRC route exists in `acestep/api` or `api_server.py` (route list shows only release_task/query_result/format_input/create_sample/models/init/lora/dataset/training); LRC generation lives in the Gradio layer (`lyric_timestamp.py`, `lrc_utils.py`). Model capability may exist, but it is not reachable without patching the vendored submodule (prohibited).
- External: `openai/whisper` MIT (weights Apache-2.0), `m-bain/whisperX` BSD-2 (its alignment models carry their own licenses: UNKNOWN), `jianfch/stable-ts` MIT but **archived**, `MontrealCorpusTools/Montreal-Forced-Aligner` MIT (speech-trained). Accuracy on sung Kannada/other Indian-language vocals is UNKNOWN. Product feasibility is unproven. **REJECT for now.**

## 15. Audio Editing Investigation

WaveSurfer 7.12.12 ships `regions`, `envelope`, `timeline`, `zoom`, `hover`, `record`, `spectrogram` plugins (VERIFIED, `node_modules`). They can draw and drag regions or envelopes, but rendering trim/fade/crossfade needs server-side DSP and a new immutable-Version story. Outside the MVP (a DAW); **not recommended.**

## 16. Export Investigation

Not a separate technical problem: single-file format is Candidate A (§7). ZIP/project export can use stdlib `zipfile` (no OSS) but only adds value after A (lossless) and stems exist as Versions. Metadata/cover-art embedding depends on §10. **Fold into A's follow-up; do not duplicate.**

## 17. Extract / Stem Investigation

**Current (VERIFIED)**: Tunora exposes 4 track types (`TRACK_NAMES` = vocals, drums, bass, guitar); ACE-Step lists 12 (`constants.py:153`: woodwinds, brass, fx, synth, strings, percussion, keyboard, guitar, bass, drums, backing_vocals, vocals). Phase 11 spike-verified the 4 exposed ones on the **base** model (`acestep-v15-base`).

**New finding, verified in source and live:**

1. `provider._EXTRACT_MODEL = "acestep-v15-base"` is sent as `model` for every extract request.
2. ACE-Step's `select_generation_handler` (`acestep/api/job_model_selection.py:120-215`): if the requested model is not the primary and no second/third handler is initialized, and `ACESTEP_ON_DEMAND_MODEL_LOAD` is not enabled (default `false`, line 39), it **logs and silently uses the primary handler**.
3. The launcher (`tunora-services.ps1:91`) starts `acestep.api_server` with no `ACESTEP_CONFIG_PATH2` (grep across the launch scripts, `docs/TUNORA-SERVICE-MANAGEMENT.md`, `ACE-Step-1.5/.env` finds none; user/machine/process environment variables are also unset). `docs/PHASE-11-IMPLEMENTATION.md` §15 records the variable as a required runbook step, but nothing enforces it.
4. Live server state: `/v1/model_inventory` shows `acestep-v15-base` `is_loaded: false`; `/v1/models` lists only turbo.
5. **Live probe**: a raw `task_type=extract`, `track_name=drums`, `model=acestep-v15-base` request with a real source file succeeded in 1.64 s, and the result item reports `"dit_model": "acestep-v15-turbo"`. Turbo's supported task list (`TASK_TYPES_TURBO`) does not include `extract`.

So on the stock `start-tunora.ps1` deployment, Extract is accepted and returns audio, but it is served by the turbo handler, not the validated base model. The objective E2E checks (valid file, differs from the source, plays) pass either way, so this was invisible. Whether that output is a real stem is **UNKNOWN** (not listened to or analyzed); the risk is a shipped feature that silently degrades. The result item exposes `dit_model`, so the provider can detect this without any ACE-Step change.

Expanding to the other 8 track types remains blocked on the same per-track real-extraction verification and is not recommended before this is fixed.

## 18. Fresh ACE-Step Audit (VERIFIED)

- Commit `ca1e85f` = upstream HEAD (`git ls-remote`); tag distance `v0.1.8-21`. No new task types or capabilities since Phase 12/13.
- `TASK_TYPES` = text2music, repaint, cover, cover-nofsq, extract, lego, complete; turbo supports the first four, base all seven (`constants.py:76-89`; live `/v1/model_inventory` agrees).
- REST routes: `/release_task`, `/query_result`, `/format_input`, `/create_random_sample`, `/v1/create_sample`, `/v1/init`, `/v1/reinitialize`, `/v1/models`, `/v1/model_inventory`, `/v1/stats`, `/v1/audio`, LoRA and dataset/training routes. No lyric-timing, chord, MIDI, loudness or scoring routes.
- `audio_format`, `batch_size`: see §7-§8. `lego` and `complete` remain base-tier only, unused, unvalidated in Tunora.
- Result items carry `dit_model`, `lm_model`, `seed_value`, `generation_info` (live).
- Live: turbo + 1.7B LM loaded, 8,408 MiB used of 16,311 MiB idle.

## 19. GitHub OSS Audit (EXTERNAL, GitHub API 2026-09-25)

| Repo | License | Stars | Last push | Decision |
|---|---|---|---|---|
| katspaugh/wavesurfer.js | BSD-3-Clause | 10.4k | 2026-09-24 | REUSE (present) |
| csteinmetz1/pyloudnorm | MIT | 783 | 2026-01-04 | REFERENCE |
| librosa/librosa | ISC | 8.6k | 2026-09-24 | REFERENCE |
| spotify/basic-pitch | Apache-2.0 | 5.6k | 2025-11-13 | REFERENCE (defer) |
| craffel/pretty-midi | MIT | 1.0k | 2026-02-18 | REFERENCE |
| Music-and-Culture-Technology-Lab/omnizart | MIT | 2.0k | 2026-05-31 | REFERENCE (weights unknown) |
| CPJKU/beat_this | MIT | 399 | 2026-05-28 | REFERENCE (weights unknown) |
| mir-aidj/all-in-one | MIT | 850 | 2024-05-09 | REFERENCE (stale) |
| openai/whisper | MIT | 109k | 2026-08-31 | REFERENCE |
| m-bain/whisperX | BSD-2-Clause | 24k | 2026-08-30 | REFERENCE |
| jianfch/stable-ts | MIT | 2.3k | 2026-05-30, archived | REJECT |
| MontrealCorpusTools/Montreal-Forced-Aligner | MIT | 1.9k | 2026-08-20 | REFERENCE |
| adefossez/demucs | MIT | 3.2k | 2026-08-31 | REFERENCE (native `extract` covers it) |
| MTG/essentia, MTG/essentia.js | AGPL-3.0 | 3.7k / 868 | 2026-09-21 / 2025-12-10 | REJECT |
| aubio/aubio | GPL-3.0 | 3.8k | 2026-04-10 | REJECT |
| CPJKU/madmom | code BSD; models CC BY-NC-SA | 1.7k | 2026-03-20 | REJECT |
| jiaaro/pydub, PyAV-Org/PyAV | MIT, BSD-3-Clause | 9.8k, 3.3k | 2026-03-19, 2026-09-23 | REFERENCE (only if DSP is ever needed) |
| Tongyi-MAI/Z-Image, QwenLM/Qwen-Image, black-forest-labs/flux2 | Apache-2.0 (code) | 12k, 8.4k, 2.7k | 2026-02 to 03 | REFERENCE (cover art, deferred) |

None of the deferred capabilities has a reusable, licence-clean, product-ready component; the recommended candidates need no external OSS.

## 20. Hugging Face Audit (EXTERNAL, HF API + model cards)

See §10 table. Also `openai/whisper-large-v3` Apache-2.0 (1.54 B params), `openai/whisper-small` Apache-2.0 (0.24 B). Weight and code licenses were read separately; dataset licenses were not audited (UNKNOWN) for any model. HF searches for "chord" returned only unvetted community fine-tunes with low downloads; "forced alignment" returned nothing usable.

## 21. License Audit

Pass (permissive): WaveSurfer, pyloudnorm, librosa, pretty-midi, basic-pitch, whisper, whisperX (code), demucs, PyAV, pydub, Z-Image, FLUX.2-klein-4B, Qwen-Image (code and weights as declared). Fail/reject: Essentia and essentia.js (AGPL), aubio (GPL), madmom models (CC BY-NC-SA), FLUX.2-dev (non-commercial). Unresolved (do not adopt): omnizart / beat_this / all-in-one weights, whisperX alignment-model weights, all dataset licenses. Local FFmpeg is a GPL build: dev-machine only, not a Tunora dependency (§11).

## 22. GPU / VRAM Audit

Measured: 8,408 MiB idle with turbo + LM 1.7B (this session); Phase 11 measured 8.73 GB peak for extraction and **11.2 GB with turbo and base both resident** (`docs/PHASE-11-IMPLEMENTATION.md:81-83`); ACE-Step's own notes give 13.3-13.5 GB at batch 4. Image models (~13 GB vendor claims) cannot coexist and would need unloading. Whisper-small is small (~0.5 GB weights ESTIMATE) but unproven on singing. Everything else considered is CPU-side.

## 23. Architecture Impact

- **Extract fix**: config (service script env var and/or on-demand flag) plus a provider check of `dit_model`; no migration, endpoint, dependency, model download beyond the already-used base weights, or new service.
- **Lossless**: provider setting + upload filename/MIME + download label; migration only in the per-Version variant.
- Batch: new data model (grouped jobs/Versions). Cover art: second runtime. Loudness/MIDI/chords/lyrics: new Python dependency stacks. Prompt library: one table + CRUD.

## 24. Candidate Decision Matrix

| Candidate | User problem | Current gap | Existing OSS | License | ACE-Step fit | Architecture fit | GPU impact | Complexity | Security impact | Testing complexity | Reuse strategy | Key risks | Recommendation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **K. Extract model correctness** | Extract must run on the model it was validated on | Strong (proven live) | n/a | n/a | Strong (`dit_model`, slot config) | Strong | Base resident with turbo: 11.2 GB measured | Low | Low | Moderate (needs real GPU + base) | ADAPT provider check + ops config | base download/first load time; extraction quality still needs listening | **Recommend** |
| A. Lossless / native format | Better source/export quality | Moderate | n/a (native) | n/a | Strong | Strong | None | Low-Moderate | Low | Moderate | ADAPT provider + upload + label | ~5x storage; audible benefit unmeasured | Second |
| B. Batch generation | Faster exploration | Weak (Another Take exists) | n/a | n/a | Moderate | Weak (new model) | 13.3-13.5 GB peak at batch 4 | High | Low | High | BUILD | data model, storage, queue | Defer |
| C. Prompt library | Reuse ideas | Weak | none fits | n/a | n/a | Good | None | Low-Moderate | Low | Strong | BUILD-small | no demand evidence | Defer |
| D. Cover art | Visuals | Moderate | Apache models | Strong | none | Weak | High/no coexistence | High | Moderate | Weak | COMPOSE new runtime | VRAM, quality | Defer |
| E. Loudness | Level info | Weak | pyloudnorm MIT | Strong | none | Moderate | None | Low | Low | Strong | REFERENCE | new deps, no action | Defer |
| F/G. MIDI, chords | Musical analysis | Weak | licence failures / heavy | Mixed | none | Weak | Low-Mod | High | Low | Weak | none | GPL/AGPL/NC | Reject/defer |
| H. Lyric alignment | Synced lyrics | Strong if feasible | Whisper family | Mixed | Blocked (no REST route) | Weak | Low-Mod | High | Low | Weak | none | accuracy UNKNOWN | Reject for now |
| I. Audio editing | Trim/fade | Weak | WaveSurfer plugins | Strong | none | Weak | None | High | Moderate | Weak | none | DAW scope | Not recommended |
| J. Export/ZIP | Get files out | Moderate | stdlib | n/a | n/a | Good | None | Moderate | Moderate | Moderate | fold into A | depends on A | Fold into A |

## 25. Recommended Phase 14 Candidate

**Candidate K: Extract model correctness ("Extract runs on the base model, or fails visibly").**

Why: it is the only gap with hard evidence of an existing shipped feature misbehaving. Live, an extract request for `acestep-v15-base` is answered by `acestep-v15-turbo` (`dit_model` in the result item), in source it is the documented silent fallback, and the default launcher never configures the second model slot. It is not a new capability, it makes the Phase 11 capability trustworthy, and it is small: configuration plus a provider check against a field ACE-Step already returns. It fits the architecture (modular monolith, no dependency, no DB), needs no new model (the base weights were already downloaded in Phase 11) and the GPU cost is already measured (11.2 GB peak). Lossless output (A) is the natural Phase 15 candidate; it improves quality but no shipped behavior is wrong without it.

## 26. Deferred Candidates

Lossless/native format (A, next), batch (B: Another Take covers the workflow; needs a new data model), prompt library (C: no demand evidence), cover art (D: VRAM), loudness (E: no action), MIDI/chords (F/G: licences/weight), lyric alignment (H: no REST route), audio editing (I: DAW scope), export (J: depends on A).

## 27. Proposed Implementation Scope (Candidate K)

**In scope**
- Start ACE-Step with the base model available for `extract` (set `ACESTEP_CONFIG_PATH2=acestep-v15-base` in the ACE-Step launch command in `tunora-services.ps1`, or evaluate `ACESTEP_ON_DEMAND_MODEL_LOAD` against the single-worker constraints; the choice is decided by a spike measuring startup time and VRAM).
- In `AceStepMusicGenerationProvider`, for EXTRACT read the result item's `dit_model` and fail the job with a safe, generic message if it is not the base model (never silently succeed on turbo).
- Startup/health guidance in `docs/TUNORA-SERVICE-MANAGEMENT.md`; update Phase 11's runbook note.
- Real-GPU validation that extraction with the base model is served by base (`dit_model`), plus a repeat of the objective Phase 11 checks.

**Out of scope**: new track types, `lego`/`complete`, batch, format changes, UI changes, ACE-Step edits, new dependencies.

**Reuse - existing Tunora**: `AceStepMusicGenerationProvider`, `ProviderResponseError` path, existing job failure handling, service scripts, Phase 11 tests. **Reuse - external**: none. **Adapt**: provider result parsing (one extra field). **Compose**: launcher env + provider check. **Build**: nothing new. **API/DB/UI/Storage**: unchanged (a failed extract shows the existing safe error). **GPU**: base resident beside turbo, measured 11.2 GB peak; idle baseline to be re-measured. **Security**: no new input; never expose `dit_model` paths or provider internals in responses. **Testing**: respx unit tests for the fallback rejection and the success case, real-GPU smoke with the base slot configured, an E2E that the Extract flow still works, and a negative real test (stack without the slot) that fails visibly. **Migration/compatibility**: no data migration; existing Extract Versions produced before the fix are labeled UNKNOWN provenance (their model was never recorded).

## 28. Risks / Unknowns

- Whether the current turbo-served extract outputs are acceptable stems (not analyzed; needs listening).
- Startup/VRAM/latency cost of keeping base resident permanently versus on-demand loading (spike required).
- Why the Phase 11 doc listed the slot variable as a runbook step while the launcher never set it (process gap, cause not established).
- Audible benefit of lossless sources (A); dataset licenses of all models; sung-vocal alignment accuracy; restart behavior of in-flight jobs was not re-audited.

## 29. Validation Plan (for K, at its own audit/implementation)

1. Reproduce the fallback with the unmodified launcher (done in this audit; repeat in the test).
2. Configure the base slot, restart, confirm `/v1/model_inventory` `is_loaded` and that an extract result reports `dit_model: acestep-v15-base`.
3. Unit tests for accept/reject on `dit_model`; regression of all extract tests.
4. Real-GPU extract of all four exposed tracks with objective checks from Phase 11.
5. Measure peak VRAM with turbo + base + LM and compare with the 11.2 GB record.
6. Full backend, frontend and Playwright regression; one commit; no push until approved.

## 30. Final Recommendation

Proceed to an implementation audit/phase for **Candidate K (Extract model correctness)**, then **Candidate A (lossless / native audio format)** as Phase 15. Do not start batch generation, cover art, mastering, MIDI/chords or lyric alignment: each lacks evidence of need, a clean licence, or a REST/GPU-feasible path. No code changes were made in Phase 14.
