# Phase 20 Product Capability + Ecosystem Audit

Audit only: no application code, test, dependency, database, configuration, UI or ACE-Step file was changed. Search date **2026-09-26**. Probes ran in scratch files outside the repository. Evidence labels: **VERIFIED** (read or executed this session), **EXTERNAL** (public lookup this session), **VENDOR CLAIM**, **ESTIMATE**, **UNKNOWN**.

## 1. Executive Summary

- **Human validation from Phase 19 has not been done**: no recorded Safari result, no blind MP3-vs-FLAC answers, no blind stem ratings. All three stay NOT VALIDATED and nothing here converts measurements into listening conclusions.
- The ecosystem is unchanged: OpenSource Radar shows the same 23 repositories as Phase 18 (only YuE2-Studio's numbers moved); ACE-Step upstream HEAD is still `ca1e85f` (2026-08-29) with no new release since v0.1.8 (2026-05-18).
- **One finding changes the roadmap: MP3 and WAV export no longer needs FFmpeg.** `soundfile` 0.13.1 (BSD-3-Clause, already present in ACE-Step's environment) with its bundled libsndfile 1.2.2 converted a FLAC to 48 kHz stereo MP3 (VBR ~155 kbps, or 322 kbps CBR at maximum quality, with ID3 tags) and to 16-bit WAV in 0.01-0.09 s per 10 s of audio. The FFmpeg licensing gate that Phases 15-19 attached to export is therefore removable.
- **Recommended Phase 21: on-demand MP3/WAV export** (FLAC stays canonical; nothing stored). Reasons: it is a real completeness gap (download is FLAC only, about 7x MP3), it is independent of the unresolved listening questions, it needs no GPU, and it also gives Safari a fallback if FLAC playback fails there. Human validation stays a parallel, non-code task.

## 2. Git State (VERIFIED)

Branch `feature`, `HEAD` = `origin/feature` = `c4bf19d6867821cfacb62521475a78d3d175a626` ("Validate Phase 19 Operability"), after `git fetch origin`. Working tree: the pre-existing `CLAUDE.md` edit and the `ACE-Step-1.5` submodule marker (untouched) plus this document. Recent history: `c4bf19d` (P19) <- `277e55c` (P17 FLAC) <- `a33a388` (P16 recovery) <- `f0fd87f`/`956f817` (P14) <- `df1545e` (P13).

## 3. Current Tunora Capability Map (from code and phase records)

| Area | State |
|---|---|
| Create Song: prompt, lyrics, 11 languages, instrumental/vocal, 30-180 s, seed, title | EXISTS |
| AI Song Director plan + refine (ACE-Step 5Hz-LM) | EXISTS |
| Jobs: lifecycle, progress, failure, **restart recovery** (Phase 16, unknown ACE-Step ids fail visibly) | EXISTS |
| Song / Version (immutable) / lineage / provider metadata | EXISTS |
| Extend, Remix, Repaint (numeric + timeline drag), Another Take | EXISTS |
| Extract (vocals, drums, bass, guitar) with **base-model enforcement** (`dit_model`, Phase 14) | EXISTS (quality unvalidated) |
| Audio: **FLAC canonical for new Versions**, MP3 compatibility, `TUNORA_AUDIO_FORMAT` rollback, playback (WaveSurfer), waveform, Range, download of the stored file | EXISTS |
| Library (search/sort/favorite/rename/delete), Projects, Compare Versions (two players + metadata) | EXISTS |
| Storage: local filesystem; `backend/scripts/storage_report.py` (read-only) | EXISTS |
| Operability: service scripts (base model slot configured), GPU envelope tool and measurements | EXISTS |
| Export beyond the stored file; batch; prompt library; cover art; loudness/mastering; MIDI; chords; lyric timing; editing; Version-level delete; job cancel (ACE-Step has no cancel route) | MISSING |

API surface today for Songs: list, get, patch (rename/favorite), delete Song, and one operation route; there is no Version delete and no export route (`routes_songs.py`).

## 4. Phase 19 Validation Status

Delivered and confirmed: GPU envelope (both models resident, single active generation, 10-180 s, six operations, two queued jobs, recovery; highest observed peak **15,775 MiB of 16,311 MiB**, about 536 MiB headroom; sampled maxima, not guaranteed hardware peaks), storage report, Chromium and Firefox FLAC playback, and the correction that ACE-Step peak-normalizes every output (`enable_normalization=True`, `normalization_db=-1.0`), which shifts the level of derived Versions by about a dB per generation in either format.

## 5. Human Validation Status

Searched the repository (`docs/`, `docs/validation/`, git history since Phase 19) and `I:\Tunora-validation`: no recorded results and no new files after the kits were written.

| Item | Status |
|---|---|
| A. Real Safari FLAC test | **NOT VALIDATED** (procedure in `docs/validation/README.md`) |
| B. Blind MP3 vs FLAC listening | **NOT VALIDATED** (kit ready, unanswered) |
| C. Blind Extract stem listening | **NOT VALIDATED** (kit ready, unrated) |

## 6. OpenSource Radar Findings (EXTERNAL)

Radar (`.../explore/?category=ai-music`, rendered with headless Chromium) still reports **23 repositories**; compared with the Phase 18 capture, **no repository appeared or disappeared** and only `timoncool/YuE2-Studio` changed (116 -> 163 stars in the 7-day window, momentum 48.3 -> 48.7). Answer to the standing question: nothing new has appeared or gained momentum that changes Tunora's options; the Phase 18 conclusions on YuE2 (non-commercial weights, 24 GB VRAM), `acestep.cpp`, `audio.cpp`, `remiqora`, `music-to-midi` and the ComfyUI/awesome-list entries stand.

| Candidate | Capability | License | Weights | GPU | Local | Maintenance | Fit | Decision |
|---|---|---|---|---|---|---|---|---|
| YuE2 / YuE2-Studio | songs with an editable score | Apache-2.0 / MIT | CC BY-NC 4.0 | 24 GB (README) / 6 GB engine claim | yes | very active | NOT SUITABLE | REJECT / REFERENCE |
| acestep.cpp | ACE-Step in C++/GGUF | MIT | GGUF of MIT models (verify) | ~7.7 GB weights (VENDOR CLAIM) | yes | active | LIMITED FIT (second provider, unproven parity) | REFERENCE |
| remiqora | studio around ACE-Step, Demucs, MuScriptor, DAW | MIT | mixed | shares ACE-Step's GPU | yes | active | NOT SUITABLE | REFERENCE |
| music-to-midi | audio -> MIDI app | MIT | mixed/UNKNOWN | UNKNOWN | yes | active | NOT SUITABLE | REFERENCE |
| audio.cpp, sglang-omni, TTS-WebUI, theDAW, ComfyUI nodes, lists | engines/UIs/lists | Apache-2.0/MIT | n/a | n/a | yes | active | NOT SUITABLE | REFERENCE |

## 7. GitHub Findings (EXTERNAL, GitHub API 2026-09-26)

| Repo | License | Stars | Last push | Note |
|---|---|---|---|---|
| ace-step/ACE-Step-1.5 | MIT | 12.9k | 2026-09-03 (default branch 2026-08-29) | 154 open issues; 0 mention "stem", 1 "separation", 30 "batch" |
| bastibe/python-soundfile | BSD-3-Clause | 861 | 2026-07-14 | documents MP3 writing (`bitrate_mode`, `compression_level`) and ships libsndfile in wheels |
| libsndfile/libsndfile | LGPL-2.1 | 1.7k | 2026-09-01 | the bundled C library |
| PyAV-Org/PyAV | BSD-3-Clause | 3.3k | 2026-09-23 | wheels bundle FFmpeg; the bundled build's GPL/LGPL configuration is UNKNOWN |
| jiaaro/pydub | MIT | 9.8k | 2026-03-19 | needs an ffmpeg executable |
| csteinmetz1/pyloudnorm | MIT | 783 | 2026-01-04 | loudness meter, no update in 9 months |
| spotify/basic-pitch | Apache-2.0 | 5.6k | 2025-11-13 | audio -> MIDI, ~10 months since last push |
| adefossez/demucs | MIT | 3.3k | 2026-08-31 | README: needs at least 3 GB GPU RAM, about 7 GB with default arguments |
| nomadkaraoke/python-audio-separator | MIT | 1.4k | 2026-08-27 | wraps many separation models with varying licenses |
| ZFTurbo/Music-Source-Separation-Training | MIT | 1.6k | 2026-09-09 | training framework; weights vary |
| m-bain/whisperX | BSD-2-Clause | 24.3k | 2026-08-30 | alignment models carry their own licenses |
| SYSTRAN/faster-whisper | MIT | 25.6k | 2025-11-19 | transcription |

## 8. Hugging Face Findings (EXTERNAL, HF API)

Code, weight and dataset licenses are separate; dataset licenses were not audited (UNKNOWN).

| Model / family | Weight license | Note |
|---|---|---|
| ACE-Step 1.5 and XL turbo/base (`acestep-v15-xl-*`, 4.99 B params) | MIT | XL: 16 GB works only with CPU offload (model card, VENDOR CLAIM): YELLOW/RED beside the base slot |
| YuE2-3B, SheetSage2, MERT-v2 | **cc-by-nc-4.0** | REJECT |
| `MahmoudAshraf/mms-300m-1130-forced-aligner` (2.6M downloads), ctc_forced_aligner repos | **cc-by-nc-4.0** | REJECT (lyric alignment) |
| openai/whisper-large-v3, Qwen3-ASR-0.6B | apache-2.0 | transcription only, not sung-lyric alignment |
| HT-Demucs conversions (GGUF/ONNX/CoreML, community) | mit (community tags) | original weights' license not stated in the README lines checked: UNKNOWN |
| BS/Mel-Band RoFormer stem models | mixed: apache-2.0, mit, cc-by-nc-4.0, gpl-3.0 | model-by-model check required |
| Basic Pitch conversions (`cstr/basic-pitch-GGUF`, LiteRT, ONNX) | apache-2.0 | small, CPU-capable |
| Stable Audio 3 | `other` (community license, gated) | REFERENCE |
| MiniMax-Music3 | none declared | REJECT |

## 9. ACE-Step Findings (VERIFIED)

Vendored `ca1e85f` = upstream default-branch HEAD (`git ls-remote`, last commits all 2026-08-29); latest release v0.1.8 (2026-05-18). No new REST route, task type, parameter or output format since Phase 17: task types text2music/repaint/cover/cover-nofsq (turbo) plus extract/lego/complete (base); `audio_format` flac/mp3 usable, opus/aac write no file; `mp3_bitrate` not exposed over REST; output peak normalization on by default; `batch_size` up to 4 (12-16 GB tier) or 8 (16-20 GB tier). The XL family is the only newer capability (config-selectable, VRAM-limited). No upstream issue signal exists for stem quality.

## 10. License Audit

Pass: ACE-Step (MIT), `soundfile` (BSD-3-Clause) with bundled libsndfile (LGPL-2.1, dynamically loaded from the wheel; wheels carry a licensing note per the project changelog), Demucs code (MIT), Apache-2.0 Whisper/Basic Pitch/Qwen3-ASR. Fail/flagged: YuE2 family and MMS aligners (CC BY-NC 4.0), YourMT3 (GPL-3.0), Stable Audio 3 (community license), MiniMax-Music3 (undeclared), Essentia (AGPL), aubio (GPL). Unresolved: original HT-Demucs weight terms, RoFormer weights per model, PyAV's bundled FFmpeg configuration, LAME/mpg123 components inside libsndfile (LGPL by general knowledge, not re-verified here), all dataset licenses. **FFmpeg on this machine:** `ffmpeg 9.0.1 full_build (gyan.dev)`, configuration includes `--enable-gpl --enable-version3 --enable-libmp3lame --enable-libx264 --enable-libx265`; it is a developer-local install, not referenced by Tunora code (0 files) and not redistributed.

## 11. GPU Audit (RTX 5060 Ti 16,311 MiB; hard constraint)

Measured (Phase 19): both ACE-Step models resident, single active generation, highest observed peak 15,775 MiB, headroom about 536 MiB; two queued jobs run one at a time. Classification of candidate model workloads beside ACE-Step:

| Workload | Claimed need | Class |
|---|---|---|
| MP3/WAV conversion (soundfile) | CPU only | GREEN |
| Basic Pitch (MIDI), Whisper-small class ASR | small / CPU | GREEN (CPU) |
| Demucs on GPU | 3-7 GB (README) | RED beside ACE-Step; CPU run possible, speed UNKNOWN |
| Cover-art models (FLUX.2-klein-4B, Z-Image-Turbo) | ~13-16 GB (VENDOR CLAIMS) | RED |
| ACE-Step XL | 16 GB only with CPU offload | YELLOW/RED |
| YuE2 | 24 GB | RED |
| acestep.cpp | ~7.7 GB of weights (VENDOR CLAIM) | YELLOW: would replace, not join, the current engine |

## 12. Security Audit

Nothing was integrated, so this is review-level. Observed flags: the large apps (`music-to-midi`, `YuE2-Studio`, `remiqora`, ChordMiniApp) download models, run subprocess pipelines and some call cloud services (Firebase, Music.ai): unsuitable for a local-first core. `python-audio-separator` downloads model files at runtime. A conversion endpoint (Phase 21) would decode files that only ACE-Step produces (no client upload), but decoding is CPU and memory bound (about 69 MB float32 for 3 minutes, ESTIMATE), so it needs a concurrency limit and the same trusted-path resolution as the audio route. Tunora still has no content validation of stored audio (unchanged since Phase 17).

## 13. Product Gap Matrix

| Priority | Capability | User value | Current gap | OSS candidate | License | GPU | Architecture fit | Effort | Decision |
|---|---|---|---|---|---|---|---|---|---|
| 1 | MP3/WAV export | Moderate (sharing; Safari fallback) | real: download is FLAC only | soundfile (BSD) + libsndfile (LGPL) | acceptable, needs notice | none | STRONG FIT (read-only route, canonical unchanged) | Low-Moderate | STRONG FIT |
| 2 | Human validation (Safari, listening) | High (closes unknowns) | open since Phase 19 | none | n/a | none | n/a | Low (people) | parallel task |
| 3 | Extract quality | Unknown | measurements inconsistent; no listening | Demucs (MIT code) | weights UNKNOWN | RED on GPU | LIMITED FIT | Moderate | DEFER (blocked by validation) |
| 4 | Version-level delete / storage management | Moderate | storage growth 7x | none | n/a | none | POSSIBLE FIT | Low-Moderate | DEFER (no demand evidence) |
| 5 | Batch generation | Low-Moderate | Another Take exists | ACE-Step `batch_size` | MIT | headroom | LIMITED FIT | High | DEFER |
| 6 | Loudness analysis | Low | none observed | pyloudnorm (MIT) | ok | none | POSSIBLE FIT | Low | DEFER |
| 7 | MIDI | Low | none observed | Basic Pitch (Apache-2.0) | ok | CPU | LIMITED FIT | Moderate | DEFER |
| 8 | Prompt library | Low | none observed | none | n/a | none | POSSIBLE FIT | Low | DEFER |
| 9 | Cover art | Low | none observed | Apache-2.0 image models | ok | RED | NOT SUITABLE | High | DEFER |
| 10 | Chords, lyric timing | Low-Moderate | blocked | none acceptable | NC / unclear | varies | NOT SUITABLE | High | REJECT for now |

## 14. Reuse / Adapt / Compose / Reference / Reject Decisions

| Candidate | Decision | Why |
|---|---|---|
| soundfile (+ bundled libsndfile) for MP3/WAV export | **COMPOSE** (existing Tunora storage/route + soundfile) | verified locally, BSD wrapper, no FFmpeg, no GPU |
| FFmpeg (local GPL build) | REFERENCE (dev tool only) | do not ship; would need an LGPL build |
| PyAV | REFERENCE | bundled FFmpeg build configuration UNKNOWN |
| pydub | REJECT | needs an ffmpeg executable |
| Demucs, python-audio-separator, RoFormer models | REFERENCE | weights unclear/VRAM red; decision blocked by validation |
| pyloudnorm | REFERENCE | no product action attached |
| Basic Pitch | REFERENCE | no demand; stale repo |
| Whisper / whisperX | REFERENCE | not sung alignment; aligner weights NC |
| MMS forced aligners | REJECT | CC BY-NC 4.0 |
| YuE2 family, Stable Audio 3, MiniMax | REJECT | license/VRAM |
| acestep.cpp, ACE-Step XL, remiqora, YuE2-Studio, music-to-midi, ChordMiniApp | REFERENCE | see sections 6, 8, 11 |

## 15. MP3/WAV Export Audit

Probe (VERIFIED, scratch files): `soundfile` 0.13.1 on libsndfile 1.2.2 lists MP3 (MPEG Layer I/II/III), converted a 10 s 48 kHz stereo FLAC in memory:

| Output | Time | Size | Result (ffprobe) |
|---|---|---|---|
| MP3 default | 0.08 s | 194 KB | mp3, 48 kHz, 2 ch, ~155 kbps |
| MP3 `compression_level=0.0`, CBR | 0.09 s | 402 KB | ~322 kbps |
| MP3 VBR `compression_level=0.2` | 0.09 s | 246 KB | ~197 kbps |
| MP3 CBR `compression_level=0.9` | 0.07 s | 70 KB | 56 kbps |
| WAV PCM_16 | 0.01 s | 1.92 MB | pcm_s16le, 48 kHz, 2 ch |
| MP3 with tags (title, artist) | ~0.1 s | | ID3 tags present |

Answers to the audit questions:
1. **FLAC stays canonical:** yes; export reads the stored file.
2. **MP3 on demand:** yes, about 0.1 s per 10 s (about 1.6 s for 3 minutes, ESTIMATE).
3. **WAV on demand:** yes, 16-bit PCM is lossless for a 16-bit FLAC (WAV float32 is unnecessary).
4. **Stored or temporary:** temporary (stream from memory or a temp file); no storage growth; caching can be a later decision.
5. **Reuse FFmpeg:** possible but unnecessary.
6. **Installed FFmpeg:** gyan.dev full build 9.0.1, `--enable-gpl` (section 10).
7. **Redistribution:** none today; the soundfile path avoids adding it.
8. **Licensing:** soundfile BSD-3-Clause; libsndfile LGPL-2.1 shipped as a shared library in the wheel (the project added a licensing note); Tunora would add a third-party notice. No GPL is introduced.
9. **Other permissive libraries:** soundfile is the one that fits; pydub needs ffmpeg; PyAV's bundled build is UNKNOWN.
10. **Bitrate / sample rate / channels / metadata:** bitrate controllable via `compression_level` and `bitrate_mode`; 48 kHz stereo preserved; ID3 title/artist writable; a Tunora filename/title mapping is a design item.
11. **Without changing Version storage:** yes.
12. **Outside the generation pipeline:** yes (a new read-only route beside the existing audio route).
13. **Browser compatibility:** improves it: MP3 and 16-bit WAV play everywhere, including as a Safari fallback.
14. **Storage impact:** none for temporary export; memory about 69 MB for a 3-minute decode per active export (ESTIMATE): bound concurrency.
15. **Security impact:** one new GET route resolved from a job id through the trusted storage path (no client path), attachment headers, concurrency limit; decoding only ACE-Step-produced files.

New runtime dependencies this implies for the backend: `soundfile` plus its requirements `numpy` and `cffi` (the backend has 3 runtime dependencies today). That is the honest cost of the decision and needs approval in Phase 21.

## 16. Extract Quality Audit

No upstream signal (0 open issues mention "stem"; 1 mentions "separation"), no recorded listening results, Phase 19 measurements inconsistent across songs (the "vocals" stem held 0.6 % / 16 % / 88 % of its energy in the voice band on three songs; stems sum to the mix at only 2 dB SNR, consistent with generated rather than separated audio). Alternatives (Demucs MIT code with unstated original-weight terms and a 3-7 GB GPU claim; RoFormer models with mixed weight licenses) cannot be adopted on this evidence. **Quality decision remains blocked by missing human validation.**

## 17. Batch Audit

ACE-Step `batch_size` maxes at 4 (12-16 GB tier) or 8 (16-20 GB tier) with in-code notes of 13.3-13.5 GB at batch 4; Tunora's provider consumes only `audio_items[0]`, one Job maps to one Version, creative operations force batch 1. Batch would need one-job-to-N-Versions, partial-failure and recovery semantics and new UI, and the measured headroom (about 536 MiB) leaves no margin. Another Take already covers "another rendition". No demand evidence. DEFER.

## 18. Cover Art Audit

Apache-2.0 image models exist (FLUX.2-klein-4B, Z-Image-Turbo, Qwen-Image) but need about 13-41 GB (VENDOR CLAIMS / parameter-count estimates) against a 536 MiB headroom: RED, would require unloading ACE-Step and a second runtime. No demand evidence. DEFER.

## 19. Prompt Library Audit

GitHub/Radar show only small prompt lists; nothing mature or reusable. Tunora already stores prompt, lyrics, language, duration and seed per Version. No demand evidence. DEFER (would be a small native feature).

## 20. Loudness / Mastering Audit

Three different capabilities: **analysis** (pyloudnorm MIT could measure LUFS/peak; no product action attached), **normalization** (ACE-Step already peak-normalizes every output to -1 dBFS by default, which also causes about 1 dB level drift per derived generation), **mastering** (out of scope). No demand evidence. DEFER.

## 21. MIDI / Chord / Lyric Audit

MIDI: Basic Pitch (Apache-2.0, small, CPU-capable, repo idle since 2025-11); MIDI tools that build on it or on GPL/unknown-weight transcription models are REFERENCE. Chords: no permissively licensed, commercially clear, maintained model verified. Lyric timing: ACE-Step has no REST route; MMS/CTC aligners are CC BY-NC 4.0; Whisper family transcribes but does not align sung lyrics, Indian-language sung accuracy UNKNOWN. All DEFER/REJECT.

## 22. Build-Nothing Assessment

Considered seriously: human validation is absent and Extract quality is blocked. But the export capability does not depend on those answers, has a verified reuse path, needs no GPU, and removes a Safari risk, so building nothing would leave a real gap open for no evidence-based reason. The unresolved validations continue in parallel as non-code work and must not be forgotten.

## 23. EXACTLY ONE Recommended Next Phase

**PHASE 21: On-demand MP3/WAV export (COMPOSE; FLAC stays canonical).**

## 24. Why That Phase

- **Real gap:** Version download is the stored file only (FLAC about 7x MP3: a 3-minute pop clip is 21.5 MB).
- **Reuse:** existing storage and audio-route patterns plus `soundfile` (BSD-3-Clause), verified working here without FFmpeg; the FFmpeg licensing gate is removed.
- **Architecture:** a read-only route beside `GET /api/jobs/{id}/audio`; Version, storage and generation untouched; no migration.
- **GPU:** none (CPU, milliseconds).
- **Risk control:** independent of the open listening questions; also a fallback path if Safari cannot play FLAC.
- **Phase 21 scope sketch (not to be implemented now):** MP3 (quality choice such as 192/320 kbps CBR) and WAV 16-bit downloads generated on demand from the stored file with ID3 title, exact response headers, filename allowlist, concurrency limit, a "Download as" control in the existing Download UI, backend and Playwright tests, real-browser download checks, and a third-party-license notice; explicit approval of the `soundfile`/`numpy`/`cffi` dependencies first.

## 25. Explicitly Deferred Capabilities

Extract expansion and any stem-separation replacement (blocked by listening), batch, prompt library, cover art, loudness/mastering, MIDI, chords, lyric timing, audio editing, Version-level delete and storage management (revisit if storage growth becomes a complaint), `acestep.cpp`/XL spikes (only if VRAM or quality becomes a demonstrated problem).

## 26. Risks

- Safari FLAC, audible FLAC benefit and Extract quality remain unvalidated; a bad Extract or Safari result could change priorities after Phase 21.
- Adding `soundfile` adds `numpy` and `cffi` and a bundled LGPL library that needs notices; export decoding costs memory (about 69 MB per 3-minute export, ESTIMATE).
- GitHub API rate limits (60/hour unauthenticated) constrained this audit's breadth; candidates not re-fetched are marked.
- Radar reflects a snapshot that barely changed since Phase 18; trend signals age quickly.
- GPU headroom is about 536 MiB from sampled measurements that can miss spikes.

## 27. Evidence vs Assumptions

**Evidence (verified this session):** git state; absence of recorded human results; Radar diff; ACE-Step upstream HEAD/release; soundfile conversion probe and its outputs; exact local FFmpeg configuration and its non-use by Tunora; GitHub/HF metadata quoted above; Phase 19 GPU measurements.
**Assumptions / not established:** any audible difference or stem usability; Safari behavior; original HT-Demucs weight terms; LAME/mpg123 licenses inside libsndfile; PyAV's FFmpeg build; vendor VRAM claims; demand for any deferred capability; conversion time and memory for 3-minute files (extrapolated).
