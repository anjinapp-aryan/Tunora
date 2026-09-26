# Phase 15 Product Capability Gap Audit

Audit only: no application code, dependency, schema, API, UI or ACE-Step file was changed. Probes
were made against the already-running local ACE-Step server and a throwaway backend on port 8010
with a scratch database; all outputs stayed in the session scratch area outside the repository.
Evidence labels: **VERIFIED** (read or executed this session), **EXTERNAL** (public lookup this
session), **VENDOR CLAIM**, **ESTIMATE**, **UNKNOWN**.

## 1. Audit Status

Complete. Two findings change the roadmap, both verified live:
1. **Backend restart orphans in-flight jobs** (a job stays QUEUED forever even though ACE-Step finished it; §19).
2. **A lossless source measurably changes what derived operations preserve** (§7-§8): 44.8 dB vs 22.8 dB fidelity of the untouched region.

## 2. Repository / Git State (VERIFIED)

- Branch `feature`; `HEAD` = `f0fd87f715f385c7ac8dd5fd18846f745cea6b6d`; `origin/feature` = `956f81772bc66153ef028f4f38d61ee56b751c0e` (after `git fetch origin feature`).
- **`HEAD != origin/feature`: HEAD is one commit ahead** (`f0fd87f`, the docs/test-hint follow-up to Phase 14, committed and not pushed).
- History: `f0fd87f` (P14 follow-up) <- `956f817` (P14 Extract model correctness, pushed) <- `df1545e` (P13 Another Take) <- `fc02f0f` (P12) <- `e4a1654` (P11) <- `f37091b` (P10) <- `87eba7e` (P9). Phase 13 and Phase 14 commits are present; Phase 14's main commit is pushed.
- Working tree: `CLAUDE.md` modified (pre-existing, untouched) and the `ACE-Step-1.5` submodule marker; plus this new document.
- Migration state `LATEST_VERSION = 5`, unchanged.

## 3. Phase 14 Verification (VERIFIED)

- `tunora-services.ps1:91` sets `$env:ACESTEP_CONFIG_PATH2 = 'acestep-v15-base'` for the ACE-Step window.
- `ace_step.py`: `generate()` records the expected model for EXTRACT task ids; `get_result()` (`:157-162`) raises `ProviderResponseError` unless the result item's `dit_model == "acestep-v15-base"`. 12 tests in `tests/test_ace_step_extract_model.py` (wrong, empty, null, missing, prefix-mismatch models rejected; job FAILED; no audio stored; API hides model details).
- After starting the stack with the launcher this session: `/v1/model_inventory` shows `acestep-v15-base` and `acestep-v15-turbo` both `is_loaded: true` once a request has run; both Extract and Another Take real-GPU smokes passed (2 passed).
- **Fresh VRAM measurement (1 Hz `nvidia-smi`, RTX 5060 Ti, 16,311 MiB):** idle right after start 1,954 MiB (nothing loaded); **both models loaded and idle 12,258 MiB** (Phase 14 recorded ~11.6 GB); **peak 15,675 MiB** (Phase 14: 14.9-15.3 GB). No ACE-Step code changed between the measurements, so the difference is run-to-run variance (allocator caching, load history). Peak headroom is about 0.6 GB. **Operational constraint, not a safe margin:** nothing else GPU-resident can be added alongside ACE-Step with both models, and sampling can miss spikes.
- Known limits carried over: base-served stem quality not listened to; older Extract Versions have unknown provenance; the expected-model map is in memory (interacts with §19).

## 4. Current Product Capability Matrix (VERIFIED from code)

| Area | Status | Evidence / note |
|---|---|---|
| Create Song: prompt, lyrics, 11 languages, instrumental/vocal, duration (30/60/120/180), seed, title | EXISTS | `create-song-schema.ts` |
| AI Song Director: plan, refine | EXISTS | 5Hz-LM via `/v1/create_sample`, `/format_input` |
| Job lifecycle, polling, failure handling, persistence | EXISTS | in-process BackgroundTasks + SQLite |
| Queue | PARTIAL | ACE-Step's own queue only (`/v1/stats`: max 200); no Tunora-level queue view |
| Job cancel | MISSING (technically blocked) | `jobs/models.py:22-23`: ACE-Step has no cancel endpoint |
| **Restart behavior of in-flight jobs** | **MISSING** | verified live (§19) |
| Song / Version / history / lineage / operations | EXISTS | 6 operations: Original, Extend, Remix, Repaint, Extract, Another Take |
| Timeline Repaint | EXISTS | WaveSurfer Regions + numeric fallback |
| Audio formats | PARTIAL | storage/media types accept flac/wav/opus/aac; nothing requests them, only MP3 is produced |
| Playback, waveform, Range route, download | EXISTS | download label "MP3" for `audio/mpeg`, otherwise "Download audio" |
| Provider metadata (BPM, genre, key, time signature), Version comparison | EXISTS | provider-reported only |
| Own analysis (loudness, RMS, peak, clipping, spectrogram, structure) | MISSING | no DSP dependency installed |
| Projects, Library (search, sort, favorites, rename, delete, filter) | EXISTS | |
| Export beyond one MP3 per Version (WAV/FLAC, stems bundle, ZIP, project, metadata, cover art) | MISSING | |
| Batch / multiple outputs per job | MISSING | `audio_items[0]` only (`ace_step.py:157`) |
| Prompt library, tags, bulk actions | MISSING | |
| Infrastructure | EXISTS | Next.js 16, FastAPI (3 runtime deps), SQLite, filesystem, ACE-Step, RTX 5060 Ti 16 GB |

## 5. Current User Journey

| Step | State |
|---|---|
| Idea -> prompt -> lyrics -> AI plan | works |
| Generate, listen | works (fails visibly on provider errors) |
| Another Take, Extend, Remix, Repaint (drag), Extract | works; Extract depends on the base slot (checked) |
| Compare, organize | works |
| Survive a backend restart mid-generation | **broken** (§19) |
| Cancel a long job | technically blocked |
| Export | partially works: one 128 kbps MP3 per Version |

Biggest friction: (1) a restart silently strands a job and its finished audio; (2) derived Versions compound MP3 loss; (3) export options.

## 6. Remaining Product Gaps

1. Orphaned jobs after a backend restart/crash (reliability, verified).
2. Lossy chain for derived Versions and one-format export (quality, measured).
3. Multiple outputs per generation, prompt reuse, cover art, analysis, MIDI/chords, lyric timing, editing (absence-type; §9-§16).
4. Unresolved validation gap: Extract stem quality needs a human listener (§17).

## 7. Lossless / Native Audio Investigation

- **Generation (VERIFIED, source):** `release_task_models.py:115-117`: `audio_format` in `flac, mp3, opus, aac, wav, wav32`, default `mp3`. `audio_utils.py:117-183`: MP3 via ffmpeg/libmp3lame, default 128k; allowed 128/192/256/320k, but `mp3_bitrate` is **not exposed** on the REST models (no reference in `acestep/api/http/*`), so REST MP3 is fixed at 128k. FLAC/WAV use soundfile; opus/aac use ffmpeg.
- **Live probe (10 s, seed 7, this session and Phase 14):** mp3 160,940 B (128 kb/s, 48 kHz stereo), flac 824,810 B (5.1x), wav 3,840,088 B (float32, 24x).
- **Tunora:** the provider never sends `audio_format`; `filenames.py`/`media_types.py` already map `.wav/.flac/.opus/.aac`; `format-bytes.ts` labels only known MIME types. Upload of every derived-operation source is hard-coded `("source.mp3", ..., "audio/mpeg")` (`ace_step.py`).
- **Version metadata:** the stored audio key/filename/media type already record the format (`VersionAudio`); the immutable spec does not record a requested format (only needed if the format becomes per-Version).
- **Playback (VERIFIED live):** Chromium 153 `AudioContext.decodeAudioData` decodes the MP3, FLAC and WAV probe files (10.000 s, 48 kHz, 2 ch each; decode 120/23/34 ms). WaveSurfer uses that decode path. Firefox and Safari were **not tested** (UNKNOWN). Decoded memory is format-independent (float PCM; about 69 MB for 3 min, ESTIMATE); only transfer size grows.
- **Download/Range:** `GET /api/jobs/{id}/audio` is a Starlette `FileResponse` with `guess_media_type`, which already maps `.flac`; Range works for any file (existing tests use MP3 only; FLAC not exercised live: UNKNOWN but low risk).
- **What "lossless" means here:** the FLAC/WAV file is bit-exact to the audio tensor ACE-Step decoded from its latents. It is lossless as a file, not as generation: the model's own VAE and diffusion are inherent to the output. FLAC therefore removes the 128 kbps MP3 encoding layer only. It does not "improve generation quality".
- **Cost:** about 5x storage for FLAC, 24x for float32 WAV (ESTIMATE for 3 min: ~2.9 / 14.8 / 69 MB); no GPU cost.

## 8. Derived-Version Source Quality Investigation

**ACE-Step accepts FLAC as `src_audio` (VERIFIED live):** repaint with a `.flac` upload (`audio/flac`) completed on the turbo handler.

**Objective experiment (harmless, 10 s, seed 7, Repaint 6-9 s, output `audio_format=flac`, same prompt and seed; mono 16 kHz, first 5 s, which is outside the painted region):**

| Comparison to the original lossless audio | SNR | Correlation |
|---|---|---|
| The 128 kbps MP3 source itself | 23.8 dB | 0.9992 |
| Repaint output made from the **FLAC** source | **44.8 dB** | 1.0000 |
| Repaint output made from the **MP3** source | **22.8 dB** | 0.9992 |

The untouched region of a derived output carries the source's fidelity: with a lossless source it stays close to the original, with an MP3 source it inherits the MP3's error. In Tunora's current chain each operation encodes a new 128 kbps MP3 on top of an already lossy source, so loss compounds with every derived Version. The model's VAE round trip is therefore **not** the dominant loss in the preserved region (44.8 dB in the FLAC case).

Limits of this evidence: SNR is not perceptual; whether 128 kbps loss or its compounding is audible is **UNKNOWN** (needs listening). One clip, one operation. Painted regions were not analyzed. The original-vs-derived comparison uses a lossless ground truth that Tunora would only keep if it stored lossless audio.

## 9. Batch Generation Investigation

- ACE-Step: `docs/en/API.md:205` `batch_size` max 8 (default 2); `gpu_config.py` tier5/tier6a limits (4/8) and the in-code note "noLM-4 -> 13.3 GB, LM-2 -> 11.9 GB, LM-4 -> ~13.5 GB". With both models resident (12.3 GB idle, 15.7 GB peak measured), batch headroom is small.
- Tunora: one Job -> one Version; `get_result` reads only `audio_items[0]` (`ace_step.py:157`); creative operations force `batch_size: 1`. Batch would need one-job-to-N-Versions (or grouped jobs), partial-failure semantics, N storage files, an aggregate progress model and new UI. Another Take (Phase 13) already provides the workflow serially. **DEFER.**

## 10. Prompt Library Investigation

GitHub search (Phase 14, unchanged) found no mature component (tiny prompt lists only). Tunora already stores prompt/lyrics/language/duration per Version and returns them in the API, so "start from this Version" is UI composition; a saved-prompt table would be a small native build. No demand evidence. **DEFER.**

## 11. Cover Art Investigation

| Model | Code / weights license | Params | Note |
|---|---|---|---|
| `black-forest-labs/FLUX.2-klein-4B` | Apache-2.0 / apache-2.0 | 3.88 B | VENDOR CLAIM "as little as 13GB VRAM" |
| `Tongyi-MAI/Z-Image-Turbo` | Apache-2.0 / apache-2.0 | 6.15 B | VENDOR CLAIM "fits within 16G VRAM" |
| `Qwen/Qwen-Image` | Apache-2.0 / apache-2.0 | 20.4 B | far above 16 GB unquantized (ESTIMATE) |
| `black-forest-labs/FLUX.2-dev` | code Apache-2.0 / license `other` (non-commercial) | 32.2 B | REJECT |

With ACE-Step at 12.3 GB idle and 15.7 GB peak (measured), an image model cannot coexist; it would require unloading ACE-Step models (extra minutes of reload) and a second runtime (diffusers). Dataset licenses unaudited (UNKNOWN). **DEFER.**

## 12. Mastering / Loudness Investigation

pyloudnorm MIT (783 stars, last push 2026-01-04, requires numpy+scipy), librosa ISC, both fine. **FFmpeg:** the local binary is `ffmpeg 9.0.1-full_build` (gyan.dev) with `--enable-gpl`; it is a **local development tool only**: no Tunora source under `backend/app` or `frontend/src` references ffmpeg (0 files), it is not bundled or redistributed, so there is no license problem today. If FFmpeg were ever a shipped dependency, an LGPL build would be required (CLAUDE.md rule). Actionable use of loudness numbers without a normalization/export action is weak. **DEFER.**

## 13. MIDI / Musical Structure Investigation

basic-pitch Apache-2.0 (5.6k stars, push 2025-11-13), omnizart MIT (weights UNKNOWN), pretty-midi MIT. Heavy ML runtimes for a niche use; no ACE-Step route. **DEFER.**

## 14. Chord Detection Investigation

Essentia AGPL-3.0, aubio GPL-3.0, madmom code BSD with CC BY-NC-SA models (`docs/LICENSE-AUDIT.md:53`; GitHub reports `NOASSERTION`), librosa ISC (features, no chord labeler), beat_this MIT (beats; weights UNKNOWN). No clean, maintained chord recognizer verified. **REJECT/DEFER.**

## 15. Lyric Alignment Investigation

- **REST capability (VERIFIED):** no lyric-timing/LRC route in `acestep/api` or `api_server.py` (route list unchanged); LRC generation is Gradio-only.
- **Model capability:** exists in ACE-Step's Gradio layer (`lyric_timestamp.py`), unreachable by REST without patching the submodule (prohibited).
- **External:** Whisper MIT (weights Apache-2.0), whisperX BSD-2 (alignment model licenses UNKNOWN), stable-ts MIT but **archived**, Montreal Forced Aligner MIT (speech). Accuracy on sung and Indian-language vocals UNKNOWN; speech alignment is not assumed equivalent. **REJECT for now.**

## 16. Audio Editing Investigation

Installed WaveSurfer 7.12.12 plugins: regions, envelope, timeline, zoom, hover, record, spectrogram. They draw regions/envelopes but trim/fade/crossfade need server-side DSP and a new immutable-Version story; Repaint already covers "change this part". Unnecessary DAW scope. **Not recommended.**

## 17. Extract Investigation

Exposed tracks: vocals, drums, bass, guitar (of 12 in `constants.py:153`). Model correctness is now enforced (§3). Remaining questions: (a) **stem quality of the base-served output has never been listened to: an unresolved human-listening validation gap**; (b) extract output is MP3 at 128k like everything else (§7); (c) VRAM cost is the both-models constraint in §24; (d) expanding to the other 8 tracks still needs per-track real-extraction verification. **No expansion recommended.**

## 18. Export / Publishing Investigation

Single-file format is Candidate A; ZIP/stems/project export use stdlib `zipfile` and only add value after format work; metadata/cover-art embedding depends on §11. Not a separate roadmap item.

## 19. New Capability Discovery

**Finding N1: backend restart orphans in-flight jobs (VERIFIED live).**
- Code: `POST` starts `run_until_terminal` as a FastAPI BackgroundTask; `GET /api/jobs/{id}` only reads the database (`routes_jobs.py:63-70`, `service.get`), and `lifespan` (`main.py:31-44`) performs no recovery. Nothing else ever polls a job.
- Experiment (throwaway backend and scratch DB): create a 10 s job, confirm QUEUED, kill the backend process, restart it. ACE-Step then completed the task (`/v1/stats`: `succeeded: 1`), yet for the next 2+ minutes `GET /api/jobs/{id}` still returned **QUEUED**. The finished audio is never attached and the UI would show "generating" indefinitely.
- Everything needed to resume exists: the persisted `provider_job_id`, `provider.get_status/get_result`, `poll_once`/`run_until_terminal`, and a status-filtered repository search.
- Interactions: the Phase 14 expected-model map is in memory, so a recovered EXTRACT job would skip the `dit_model` check unless the expectation is re-registered from the job's persisted operation. Behavior when **ACE-Step itself** restarted (task ids possibly lost; ACE-Step's `jobs/store.py` is "in-memory ... with JSON persistence helpers") was **not tested: UNKNOWN**.
- Affects correctness and wasted GPU work; dev workflows (stop/restart scripts) trigger it routinely.

Other observations: no job cancel (blocked, documented); no Tunora-visible queue depth; the project docs list soundfile/librosa/LGPL FFmpeg as "locked-in audio tooling" but none is installed (documentation drift, not a product gap).

## 20. Fresh ACE-Step Audit (VERIFIED)

- Submodule `ca1e85f` (2026-08-29, `v0.1.8-21`); `git ls-remote origin HEAD` = same SHA: no new upstream capability.
- `constants.py:76-89`: task types text2music, repaint, cover, cover-nofsq, extract, lego, complete; turbo supports the first four, base all seven (live `/v1/model_inventory` agrees).
- REST routes: `/release_task`, `/query_result`, `/format_input`, `/create_random_sample`, `/v1/create_sample`, `/v1/init`, `/v1/reinitialize`, `/v1/models`, `/v1/model_inventory`, `/v1/stats`, `/v1/audio`, LoRA/dataset/training. No cancel, lyric-timing, chord, MIDI, loudness route.
- `audio_format` yes; `mp3_bitrate` code-only (not REST); `batch_size` yes; `lego`/`complete` base-only, unused; result items expose `dit_model`, `lm_model`, `seed_value`, `generation_info`.
- Fixed seed non-determinism (Phase 13) and silent model fallback (Phase 14) remain the relevant behaviors.

## 21. GitHub OSS Audit (EXTERNAL, GitHub API 2026-09-26)

| Repo | License | Stars | Last push | Decision |
|---|---|---|---|---|
| katspaugh/wavesurfer.js | BSD-3-Clause | 10.4k | 2026-09-24 | REUSE (present) |
| csteinmetz1/pyloudnorm | MIT | 783 | 2026-01-04 | REFERENCE |
| librosa/librosa | ISC | 8.6k | 2026-09-24 | REFERENCE |
| spotify/basic-pitch | Apache-2.0 | 5.6k | 2025-11-13 | REFERENCE |
| Music-and-Culture-Technology-Lab/omnizart | MIT | 2.0k | 2026-05-31 | REFERENCE (weights unknown) |
| CPJKU/beat_this | MIT | 400 | 2026-05-28 | REFERENCE (weights unknown) |
| openai/whisper | MIT | 110k | 2026-08-31 | REFERENCE |
| m-bain/whisperX | BSD-2-Clause | 24k | 2026-08-30 | REFERENCE |
| jianfch/stable-ts | MIT | 2.3k | 2026-05-30, archived | REJECT |
| MTG/essentia | AGPL-3.0 | 3.7k | 2026-09-21 | REJECT |
| aubio/aubio | GPL-3.0 | 3.8k | 2026-04-10 | REJECT |
| CPJKU/madmom | code BSD; models CC BY-NC-SA | 1.7k | 2026-03-20 | REJECT |
| Tongyi-MAI/Z-Image, QwenLM/Qwen-Image, black-forest-labs/flux2 | Apache-2.0 (code) | 12k, 8.4k, 2.7k | 2026-02/03 | REFERENCE |

The two recommended candidates (job recovery, lossless format) need no external OSS: both are native to Tunora/ACE-Step.

## 22. Hugging Face Audit (EXTERNAL, HF API 2026-09-26)

See §11 table (weights licenses read from model metadata; FLUX.2-dev `other` = non-commercial). Whisper models Apache-2.0 (Phase 14). Code, weight and dataset licenses are separate; dataset licenses were not audited for any model (UNKNOWN).

## 23. License Audit

Pass: WaveSurfer, pyloudnorm, librosa, basic-pitch, Whisper, whisperX (code), Z-Image, FLUX.2-klein-4B, Qwen-Image (as declared). Fail: Essentia (AGPL), aubio (GPL), madmom models (NC), FLUX.2-dev (non-commercial). Unresolved (do not adopt): omnizart/beat_this/whisperX-alignment weights and all dataset licenses. Local FFmpeg GPL build: dev-only, not distributed, not a Tunora dependency.

## 24. GPU / VRAM Audit

| Measurement (RTX 5060 Ti 16,311 MiB) | Value |
|---|---|
| Just started, nothing loaded | 1,954 MiB |
| Both DiT models + LM loaded, idle (fresh) | 12,258 MiB |
| Peak during Extract + Another Take smoke (fresh) | 15,675 MiB |
| Phase 14 records | idle 11,633; peaks 14,862-15,298 MiB |
| Turbo-only peak (Phase 14) | 10,203 MiB |

Peak headroom about 0.6 GB. Any GPU-resident addition (cover art, alignment, MIDI) is not viable alongside ACE-Step in this configuration without unloading models. The candidates below need no GPU.

## 25. Architecture Impact

- **Job recovery:** startup hook in `JobService`/`lifespan` reusing `run_until_terminal`; no migration, dependency, endpoint, UI, GPU or infrastructure. Needs a provider hook to re-register the Extract model expectation.
- **Lossless:** provider `audio_format` setting (env, global) or per-Version format (additive migration); fix the hard-coded `source.mp3` upload name/MIME; download label; ~5x storage. No GPU.
- Others: batch (new data model), cover art (second runtime), loudness/MIDI/chords/alignment (new dependency stacks, or blocked).

## 26. Candidate Decision Matrix

| Candidate | User problem | Current gap | Existing OSS | License | ACE-Step fit | Architecture fit | GPU impact | Complexity | Security impact | Testing complexity | Reuse strategy | Risks | Recommendation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **R. Job recovery after restart** | jobs silently stranded | Strong (live) | n/a | n/a | Strong (task ids, `/query_result`) | Strong | None | Low-Moderate | Low | Moderate (restart simulation; real GPU) | COMPOSE existing poll loop | ACE-Step also restarted (UNKNOWN); Extract check re-registration | **Recommend** |
| A+B. Lossless format and lossless sources | quality chain, export | Strong (measured 44.8 vs 22.8 dB) | n/a (native) | n/a | Strong (FLAC source accepted live) | Strong | None | Low-Moderate | Low | Moderate | ADAPT provider/upload/label | 5x storage; audibility UNKNOWN; Firefox/Safari untested | Second (Phase 16) |
| C. Batch | faster exploration | Weak | n/a | n/a | Moderate | Weak | ~1-3 GB more at batch | High | Low | High | BUILD | data model | Defer |
| D. Prompt library | reuse ideas | Weak | none fits | n/a | n/a | Good | None | Low-Moderate | Low | Strong | BUILD-small | no demand | Defer |
| E. Cover art | visuals | Moderate | Apache models | Strong | none | Weak | not viable beside ACE-Step | High | Moderate | Weak | COMPOSE new runtime | VRAM | Defer |
| F. Loudness | level info | Weak | pyloudnorm | Strong | none | Moderate | None | Low | Low | Strong | REFERENCE | no action attached | Defer |
| G/H. MIDI, chords | analysis | Weak | licence/weights | Mixed | none | Weak | Low-Mod | High | Low | Weak | none | GPL/AGPL/NC | Reject/defer |
| I. Lyric alignment | synced lyrics | Strong if feasible | Whisper family | Mixed | Blocked (no REST) | Weak | Low-Mod | High | Low | Weak | none | accuracy UNKNOWN | Reject for now |
| J. Audio editing | trim/fade | Weak | WaveSurfer plugins | Strong | none | Weak | None | High | Moderate | Weak | none | DAW scope | Not recommended |
| K. Extract expansion | more stems | Weak | n/a | n/a | Base-tier | Moderate | both-models constraint | Moderate | Low | needs listening | per-track spike | quality unverified | Defer (listening gap first) |
| L. Export/ZIP | get files out | Moderate | stdlib | n/a | n/a | Good | None | Moderate | Moderate | Moderate | fold into A | depends on A | Fold into A |

## 27. Recommended Phase 15 Candidate

**Candidate R: resume unfinished jobs after a backend restart.**

- **Actual gap (verified):** killing the backend mid-generation left the job QUEUED for 2+ minutes while ACE-Step had completed it; no code path ever polls a job again.
- **User value:** no stranded "generating" states, no wasted GPU work, correct results after the routine restarts the launcher scripts encourage.
- **Reuse:** everything exists: persisted `provider_job_id`, `poll_once`/`run_until_terminal`, repository status search, provider `get_status/get_result`.
- **License/GPU/architecture:** no dependency, no GPU, no migration, no endpoint, no UI; modular monolith preserved.
- **Why not lossless first:** it is a quality improvement with a strong measurement, but it changes nothing that is broken today; R fixes something that is broken. Lossless is the natural Phase 16.

## 28. Deferred Candidates

Lossless/lossless sources (Phase 16), batch (data model, VRAM), prompt library (no demand), cover art (VRAM), loudness (no action), MIDI/chords (licences), lyric alignment (no REST route), audio editing (DAW scope), Extract expansion (listening gap), export (folded into lossless).

## 29. Proposed Implementation Scope (Candidate R)

**In scope:** on backend startup, find jobs that are not terminal and have a `provider_job_id`, and continue polling them with the existing `run_until_terminal`; jobs without a `provider_job_id` (never submitted) are failed visibly; a job the provider no longer knows becomes FAILED (existing `_fail` path); re-register the Extract model expectation for recovered EXTRACT jobs from the persisted operation (small provider hook), so the Phase 14 check still applies; avoid double-polling a job already being polled.
**Out of scope:** cancel, queue UI, new endpoints, migration, ACE-Step changes, any format work.
**Reuse - Tunora:** `JobService.poll_once/run_until_terminal`, repository search, `lifespan`, provider. **External OSS:** none. **Adapt:** `lifespan` startup, one provider method. **Compose:** existing pieces only. **Build:** the recovery loop (thin).
**API/DB/UI/Storage:** unchanged. **GPU:** none. **Security:** no new input; recovered jobs use only persisted server-side ids.
**Testing:** unit tests with the fake provider (resume completes, unknown job fails, unsubmitted job fails, no double polling, Extract check preserved); mutation checks; a real-GPU restart test (kill and restart the backend mid-generation, assert COMPLETED and audio attached); full regression.
**Compatibility:** existing databases work unchanged; old orphaned rows get resolved on the next start.

## 30. Risks / Unknowns

- Behavior when ACE-Step itself restarted while jobs were in flight (task-id persistence) not tested.
- Jobs from many restarts ago could be resumed after their results were cleaned up by ACE-Step; must fail cleanly.
- Perceptual value of lossless sources; Firefox/Safari FLAC playback; Extract stem quality (all need listening or other browsers).
- The 0.6 GB VRAM headroom for any future GPU addition.
- Fixed-seed non-determinism and the silent model fallback (both handled) show ACE-Step behaviors need probing, not assumption.

## 31. Validation Plan (Candidate R)

1. Reproduce the orphaned job on a throwaway backend (done here); 2. unit tests as in §29; 3. real-GPU restart test with a real generation and an Extract job; 4. mutation testing of the recovery decisions; 5. full backend/frontend/Playwright regression; 6. one commit, no push until approved.

## 32. Final Recommendation

Proceed to an implementation audit/phase for **Candidate R (resume unfinished jobs after restart)**, then **lossless output and lossless derived sources** as Phase 16. Do not start batch, cover art, mastering, MIDI/chords or lyric alignment. No code was changed in Phase 15.
