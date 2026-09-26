# Phase 17 Product Capability Gap Audit: Lossless / Native Audio Pipeline

Audit only. No application code, configuration, startup script, dependency, schema, audio format or ACE-Step file was changed. All probes ran against the local ACE-Step server and used scratch scripts and files outside the repository. Evidence labels: **VERIFIED** (read or executed this session), **EXTERNAL** (public lookup), **ESTIMATE** (derived, labeled), **UNKNOWN**.

## 1. Executive Summary

**Decision: IMPLEMENT PHASE 17**, with a narrow scope: new Versions are generated as **16-bit FLAC**, existing MP3 Versions stay untouched, no migration, no new dependency, no new UI.

Evidence, all measured this session:
- ACE-Step really produces FLAC and WAV through the existing `/release_task` path (`audio_format`), with no latency change (mp3 13.1 s, flac 12.7 s, wav 12.2 s for the same 10 s clip). It does **not** produce Opus or AAC in this deployment: it reports success but writes no file.
- ACE-Step decodes uploaded source audio by content, not by filename: FLAC bytes named `source.mp3` / `audio/mpeg` (what Tunora's provider hard-codes) were accepted and behaved identically to a proper `.flac` upload.
- In Repaint the untouched region of the output is a **bit-exact copy** of the source: 126.6 dB SNR (16-bit rounding floor) through three consecutive Repaints on a FLAC chain. On the MP3 chain that region is only 24.1 dB against the lossless original at generation 0 and keeps decaying (23.5, 23.2, 22.9 dB after 1, 2, 3 Repaints), because each derived Version re-encodes 128 kbps MP3.
- Tunora's storage, media-type, Range and download code already handle `.flac`/`.wav`; the frontend already maps FLAC and WAV labels. Two small mismatches were found (below).
- Cost: about 5x storage for FLAC. No GPU, CPU-latency or dependency cost.
- Not established: whether the MP3 loss is *audible* (SNR is not perceptual, no listening was done), and Firefox/Safari playback (not runnable locally).

## 2. Current Architecture

Next.js 16 + FastAPI + SQLite + local filesystem + ACE-Step; jobs run in-process with polling (Phase 16 resumes unfinished jobs after a backend restart). Baseline verified: `HEAD` = `origin/feature` = `a33a3884f47ccba6dd2a0092d509199f7ef2d310` (Phase 16); Phase 16 recovery present (`main.py:39`, `service.py:350` `recover_unfinished_jobs`, `register_recovered_job`) and 36 recovery/Extract-model tests pass; the Phase 14 `dit_model` check is intact (`ace_step.py:168`). Working tree: pre-existing `CLAUDE.md` edit and submodule marker only, plus this document. ACE-Step submodule `ca1e85f` = upstream HEAD.

## 3. Current Audio Pipeline (VERIFIED from code)

```
Create Song -> POST /api/jobs -> JobService.create_and_submit
   -> AceStepMusicGenerationProvider.generate: JSON POST /release_task (no audio_format => ACE-Step default mp3)
   -> ACE-Step encodes MP3 128 kbps via an ffmpeg subprocess (audio_utils.py:175-185) -> temp file
   -> poll -> get_result -> JobService: guess_media_type(path) -> LocalAudioStorage.save(<job-id>/<job-id>.mp3)
   -> Version.audio {key, filename, media_type, size}  -> GET /api/jobs/{id}/audio (FileResponse, Range, ETag)
   -> WaveSurfer (fetch -> decodeAudioData + media element)  /  Download (fetch + Blob + <a download>)

Extend / Remix / Repaint / Extract:
   stored file (mp3) --read bytes--> multipart src_audio, filename "source.mp3", type "audio/mpeg" (ace_step.py:347)
   -> ACE-Step torchaudio.load(...) -> generation -> mp3 128 kbps -> stored as new Version (same path as Create)
Another Take: text-to-music from the source's prompt/lyrics/language/duration; no source audio.
```

Per operation today: source format mp3 (stored) -> provider input mp3 (hard-coded name/type) -> provider output mp3 -> stored mp3 -> playback mp3 -> download mp3 (label "MP3"). Lineage columns (`operation`, `source_version_id`, `operation_params`) do not involve format.

## 4. ACE-Step Findings (VERIFIED)

- Commit `ca1e85f`, `git ls-remote` upstream HEAD identical.
- **`/openapi.json` is not authoritative here:** `/release_task` has an empty `requestBody` and no `audio_format`/`mp3_bitrate` schema property (loosely typed endpoint). The real contract is the parser: `release_task_request_builder.py:84` `audio_format=parser.str("audio_format", "mp3")`, model description "flac, mp3, opus, aac, wav, wav32. Default: mp3" (`release_task_models.py:115-117`). The library default is FLAC "for fast saving" (`inference.py:260`), but the REST default is mp3.
- `mp3_bitrate` (128/192/256/320k) exists only in `audio_utils.py`/`inference.py`; **no REST parameter reaches it**, so REST MP3 is fixed at 128 kbps.
- MP3 export needs an `ffmpeg` executable on PATH (`audio_utils.py:175-185` raises "ffmpeg executable not found ... to export MP3"). FLAC/WAV use `soundfile` (`audio_utils.py:285-308`) and need no ffmpeg.
- Uploaded `src_audio` is loaded with `torchaudio.load` (`audio_utils.py:375`), i.e. content-sniffed.
- Model tiers unchanged: turbo (text2music, repaint, cover, cover-nofsq) and base (adds extract, lego, complete).

## 5. Real Audio Format Probe (VERIFIED, real GPU, same prompt, seed 7, 10 s, en, instrumental)

| Requested | Result | Time | File | Codec / container | Bit depth | Rate / ch | Duration | Bytes | Served type |
|---|---|---|---|---|---|---|---|---|---|
| mp3 | OK | 13.1 s | .mp3 | mp3 | (lossy) | 48 kHz / 2 | 10.000 | 160,940 (128.75 kb/s) | audio/mpeg |
| flac | OK | 12.7 s | .flac | flac | 16-bit | 48 kHz / 2 | 10.000 | 874,421 (this run; 813-874 kB over 6 runs) | audio/flac |
| wav | OK | 12.2 s | .wav | wav / pcm_f32le | 32-bit float | 48 kHz / 2 | 10.000 | 3,840,088 | audio/wav |
| wav32 | OK | 12.5 s | .wav | wav / pcm_f32le | 32-bit float | 48 kHz / 2 | 10.000 | 3,840,088 | audio/wav |
| opus | **no file** | n/a | none | n/a | n/a | n/a | n/a | 0 | log: "Failed to save audio file: Unknown format: 'OPUS'" |
| aac | **no file** | n/a | none | n/a | n/a | n/a | n/a | 0 | log: "Unknown format: 'AAC'" |

Notes: `wav` and `wav32` produce the same 32-bit-float WAV. For opus/aac ACE-Step reports job status 1 (success) but the result item has no `file`; Tunora's provider would fail such a job visibly ("succeeded but returned no audio file path"). The first request includes model load (an earlier mp3 run took 50 s), so only the warmed timings above are comparable. SHA-256 values differ between runs and are not evidence of anything: fixed seeds are not byte-deterministic in this stack (Phase 13). FLAC size varies by run (813,556-874,421 B for the same 10 s prompt), so it is content dependent; only an instrumental synth loop was measured (vocal-heavy material UNKNOWN).

## 6. Derived Version Analysis (VERIFIED, real GPU)

Method: lossless original (16-bit FLAC, 10 s). Repaint 6-9 s with the same prompt and seed; outputs decoded to 48 kHz mono and compared with the original over the **untouched first 5 s** (SNR, correlation, RMS difference, peak difference). Input MP3 was made with libmp3lame 128k written to a real file (a piped MP3 lacks the gapless header, and the first attempt misaligned by the encoder delay: those numbers were discarded).

**A. How ACE-Step interprets `src_audio`:**

| Upload | Untouched-region SNR | corr | RMS diff | Peak diff |
|---|---|---|---|---|
| FLAC, `source.flac`, audio/flac | 126.6 dB | 1.0000 | 0.00 dB | 0 |
| FLAC bytes named `source.mp3`, audio/mpeg (Tunora's hard-coded name) | 126.6 dB | 1.0000 | 0.00 dB | 0 |
| WAV float32, `source.wav` | 75.8 dB | 1.0000 | 0.00 dB | 0 (float source vs 16-bit FLAC output) |
| MP3 128k, `source.mp3` | 28.0 dB | 0.9992 | +0.04 dB | +185 |

Extract (base model, `dit_model` acestep-v15-base) accepted both a FLAC and an MP3 source (6.5 s / 6.3 s).

**B. Compounding across three consecutive Repaints (output format matches input: MP3 chain vs FLAC chain):**

| Generation | MP3 chain (Tunora today) SNR / corr | FLAC chain SNR / corr |
|---|---|---|
| 0 (the source) | 24.1 dB / 0.9992 | 126.6 dB / 1.0000 |
| 1 | 23.5 dB / 0.9988 | 126.6 dB / 1.0000 |
| 2 | 23.2 dB / 0.9983 | 126.6 dB / 1.0000 |
| 3 | 22.9 dB / 0.9981 | 126.6 dB / 1.0000 |

**C. Remix (cover 0.7):** correlation with the original 0.35 (mp3 source) vs 0.32 (flac source): both regenerate the content; no measurable source-format effect (stochastic differences dominate).

**Model/VAE loss vs MP3 codec loss vs FLAC compression (explicitly separate):** FLAC is a lossless container: it removes only the *additional* lossy MP3 layer. In Repaint/Extend the unpainted region is copied through bit-exactly (FLAC chain), so ACE-Step's VAE/diffusion does not degrade that region; any loss there is the codec's. In the *regenerated* region (and in Create, Remix, Another Take) the audio is model output and FLAC cannot make it better than the model produced; FLAC merely stops MP3 from degrading it further. FLAC from ACE-Step is 16-bit, so the model's float output is quantized to 16 bits (a WAV float32 preserves more headroom at 24x MP3 size). **Not established:** whether the 22.9-24.1 dB fidelity of MP3 is audible: no listening test and SNR is not perceptual.

## 7. Browser Compatibility

- **Chromium 153 (VERIFIED locally, Playwright):** `AudioContext.decodeAudioData` decoded the MP3, FLAC and 32-bit-float WAV probe files: 10.000 s, 48 kHz, 2 ch each; decode 91 / 17 / 23 ms.
- **Firefox and Safari: not run.** The Firefox/WebKit builds installed for Playwright predate the installed Playwright version (launch failed with a protocol/executable mismatch; nothing was downloaded, per the audit rules). EXTERNAL (MDN Web audio codec guide): FLAC supported in Chrome, Edge, Opera, Firefox 51+ (58+ mobile), Safari 11+; MP3 supported everywhere (Firefox via platform libraries before 71); WAV is not listed separately, PCM is broadly supported. IEEE-float WAV in Firefox/Safari is UNVERIFIED: a reason to prefer 16-bit FLAC over `wav`.
- **WaveSurfer 7.12.12 (VERIFIED, source):** `fetch` -> `arrayBuffer` -> `AudioContext.decodeAudioData` (`decoder.js`) for the waveform, plus a media element fed from a Blob for playback. Both use the browser's own codecs, no format-specific code; no new player library is needed.

## 8. Storage Analysis (measured sizes; projections labeled)

Measured rates from the probe: mp3 16.1 kB/s, flac about 82 kB/s (813-874 kB per 10 s), wav float32 384 kB/s. Ratios 5.1x and 23.9x.

ESTIMATE, assuming a 120 s song and 3 Versions per song (Another Take/Extend/Remix/Repaint/Extract each add a Version; both assumptions are illustrative):

| Library | MP3 | FLAC | WAV (float32) |
|---|---|---|---|
| per Version (120 s) | 1.9 MB | ~9.9 MB | 46 MB |
| 100 songs (300 Versions) | 0.58 GB | ~3.0 GB | 13.8 GB |
| 1,000 songs (3,000) | 5.8 GB | ~30 GB | 138 GB |
| 10,000 songs (30,000) | 58 GB | ~300 GB | 1.4 TB |

FLAC size on vocal-heavy material may differ (UNKNOWN). Extract stems add Versions of similar size.

## 9. OSS / GitHub Audit (EXTERNAL, GitHub API and PyPI, 2026-09-26)

| Project | License | Stars | Last push | Role | Decision |
|---|---|---|---|---|---|
| bastibe/python-soundfile (PyPI `soundfile` 0.14.0) | BSD-3-Clause (wraps libsndfile, LGPL-2.1) | 860 | 2026-07-14 | FLAC/WAV read-write; what ACE-Step already uses | REFERENCE (Tunora needs no encoding: it stores ACE-Step's file) |
| libsndfile/libsndfile | LGPL-2.1 | 1.7k | 2026-09-01 | C library behind soundfile | REFERENCE |
| xiph/flac | GFDL-1.3 (docs; codec BSD-style per project) | 2.4k | 2026-07-19 | reference FLAC encoder | REFERENCE |
| librosa/librosa | ISC | 8.6k | 2026-09-24 | analysis | not needed |
| jiaaro/pydub | MIT | 9.8k | 2026-03-19 | conversion via ffmpeg | not needed now |
| beetbox/audioread | MIT | 538 | 2026-04-09 | decoding via backends | not needed |
| pytorch/audio | BSD-2-Clause | 2.9k | 2026-09-25 | ACE-Step's own dependency | not a Tunora dependency |
| PyAV-Org/PyAV | BSD-3-Clause | 3.3k | 2026-09-23 | bundled FFmpeg bindings (wheel license depends on the FFmpeg build) | REFERENCE for future export |
| quodlibet/mutagen | **GPL-2.0-or-later** | 2.0k | 2026-08-20 | tag writing | REJECT (GPL) for a distributed product |
| kkroening/ffmpeg-python | Apache-2.0 | 11k | 2024-08-04 | ffmpeg CLI wrapper | not needed |

Conclusion: native/provider capabilities suffice. Recommended implementation adds **no** library: it asks ACE-Step for FLAC and stores the returned file, both already supported by `LocalAudioStorage`.

## 10. Hugging Face Audit

Not relevant: no model or weights are involved in a container-format change; there are no dataset or weight license questions for this candidate.

## 11. License Analysis

- ACE-Step (MIT code, Apache-2.0 weights per project record) is unchanged. `soundfile`/libsndfile (BSD/LGPL) are ACE-Step-side dependencies already in its environment.
- **FFmpeg (VERIFIED):** the only FFmpeg here is a developer-local WinGet install (`ffmpeg 9.0.1 full_build`, `--enable-gpl`). Tunora's backend and frontend source do not reference it (0 files), it is not bundled, not redistributed and not a Tunora runtime dependency. It **is** a runtime dependency of ACE-Step's MP3 export (`audio_utils.py:175`), i.e. of the current MP3 pipeline; a FLAC pipeline removes that dependency from the output path. The GPL build matters only if FFmpeg is ever shipped or invoked from Tunora's distribution; then an LGPL build (project rule) would be required. Future MP3/WAV *export* by conversion would raise that question; this phase does not.
- Rejected on license: mutagen (GPL-2.0-or-later).

## 12. Security Analysis (VERIFIED)

- Path/extension handling: `safe_audio_filename` whitelists extensions (`.mp3 .wav .flac .ogg .opus .aac`), stored names are `<job-id>.<ext>`, nothing client-supplied builds a path (unchanged).
- **No content validation:** a scratch run against Tunora's real storage/API code stored and served a random 5,000-byte `garbage.wav` and an MP3 renamed `spoof.flac` as `audio/wav` / `audio/x-flac` with 200 and 206 Range responses. Files come only from ACE-Step, not from clients, so the exposure is low; a corrupt file would surface as the existing player error state. A cheap magic-byte check (`fLaC`, `RIFF`) is optional hardening, not a blocker.
- Oversized audio / storage exhaustion: FLAC makes each Version about 5x larger; there is no quota today (unchanged risk, larger blast radius). MIME sniffing: responses use the stored media type; unchanged.

## 13. Performance Analysis (VERIFIED where measured)

Latency unchanged: 13.1 / 12.7 / 12.2 s (mp3 / flac / wav). GPU memory unaffected (encoding happens after generation on CPU). FLAC avoids the ffmpeg subprocess encode. Upload of a FLAC source is a local loopback copy (0.8 MB per 10 s). Browser: the player downloads the whole file once and decodes it; decode time is small (17-23 ms for 10 s) and decoded PCM memory is format-independent; transfer grows about 5x (about 15 MB for 3 minutes, local).

## 14. Version / Lineage Impact

`VersionAudio` already stores `filename`, `media_type` and `size_bytes`, and the API exposes them (`audio_url`, `filename`, `media_type`, `size_bytes`). The format is therefore **inferable from stored data; no migration and no new column are needed**. The immutable generation spec does not record a requested format; that is acceptable because the resulting file's own type is the provenance. Lineage, `operation_params` and `source_version_id` are format-independent.

## 15. Existing Version Compatibility

Never migrate destructively. New Versions become FLAC; existing MP3 Versions keep working unchanged: storage, Range, playback (MP3 everywhere) and download (label "MP3") are per-file. Mixed lineages work because ACE-Step sniffs content: MP3 source -> FLAC output was accepted; the preserved region simply carries the MP3's loss without further compounding. Extract, Another Take, Library and Compare are format-agnostic. Optional later: convert on demand for export, never rewrite stored files.

## 16. Creative Operation Matrix (verified)

| Operation | Current source | Current output | Lossless source possible? | Lossless output possible? |
|---|---|---|---|---|
| Create | none | mp3 128k | n/a | Yes (flac verified) |
| Extend | stored mp3 | mp3 | Yes (repaint task; FLAC source verified) | Yes |
| Remix | stored mp3 | mp3 | Yes (accepted; no measurable quality change) | Yes (flac output verified) |
| Repaint | stored mp3 | mp3 | Yes (verified; untouched region bit-exact) | Yes |
| Extract | stored mp3 | mp3 | Yes (accepted on base) | Yes (flac output verified) |
| Another Take | none | mp3 | n/a | Yes |

(Extend is the repaint task over the appended region; it was not run separately with FLAC. Extract output as FLAC was requested and produced a file; stem quality still unverified.)

## 17. Phase 14 / 16 Compatibility (VERIFIED by code reading, no format change made)

- Phase 14: the expected-model map is keyed by provider task id and checks `dit_model`; independent of format.
- Phase 16: recovery uses the persisted `provider_job_id` and `request.operation`; the stored media type comes from the ACE-Step result path (`guess_media_type(result.audio_path)`), so a job submitted as mp3 before a deploy and recovered after it still completes as mp3; nothing format-related is persisted in the request. `operation`, `operation_params`, `source_version_id` unaffected.

## 18. Candidate Matrix

| Option | Quality | Storage | Browser support | Derived quality | Provider compat | Complexity | Dependency | License risk | Future mastering | Future stems/analysis | Migration risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A. MP3 canonical (today) | Weak (128k, compounds ~0.3 dB/gen) | Strong (1x) | Strong | Weak | Strong | none | ffmpeg needed by ACE-Step | GPL local build note | Weak | Weak | none |
| B. **FLAC canonical, 16-bit** | Moderate-Strong (exact copy of ACE-Step's 16-bit output; no codec loss) | Moderate (~5x) | Strong on Chromium (verified); Firefox/Safari per MDN (unverified) | Strong (bit-exact preserved region) | Strong (verified) | Low | none | none | Moderate (16-bit) | Strong | Low (additive) |
| C. WAV float32 canonical | Strong (float, no quantization) | Weak (24x) | Moderate (float WAV unverified outside Chromium) | Strong | Strong (verified) | Low | none | none | Strong | Strong | Low, but heavy |
| D. Provider-native + conversion at boundaries | as chosen native | as chosen | Strong if MP3 delivered | as native | Strong | Moderate-High | ffmpeg or a library for conversion | Moderate (GPL build if shipped) | Strong | Strong | Low |
| E. Dual: lossless canonical + derived MP3/export | Strong | Weak-Moderate (extra copies) | Strong | Strong | Strong | High | conversion tool | Moderate | Strong | Strong | Moderate |

## 19. Recommended Architecture

**Option B now, Option D/E later as a separate export phase.** The canonical stored audio for new Versions is the FLAC file ACE-Step returns. No conversion happens inside Tunora, so no FFmpeg or library is added. No UI option (product philosophy: the user never sees a format), no per-Version format field (inferable), no migration. Rollback lever: the provider's audio format is a single setting whose default becomes `flac` and which can be set back to `mp3` without code changes. WAV float32 is rejected as the default: 24x storage, unverified float-WAV support in Firefox/Safari, and no evidence that the extra headroom matters before mastering exists. The 16-bit limit of ACE-Step's FLAC output is documented as a known trade-off.

## 20. Implementation Scope if Approved

**In scope:** (1) provider sends `audio_format` (default flac, configurable to mp3) for every generation path (Create, Another Take and all four source-based operations); (2) derived-operation upload uses the stored file's real name and media type instead of the hard-coded `source.mp3`/`audio/mpeg` (functionally optional since ACE-Step sniffs, but correct and required to avoid lying about the type); (3) normalize the media type: on this machine Python's `mimetypes` reports `.flac` as `audio/x-flac` (VERIFIED), which `_EXTENSION_BY_MEDIA_TYPE` and the frontend `format-bytes.ts` (`audio/flac` -> "FLAC") do not know, so the download label would fall back to "Download audio"; map both spellings to `audio/flac`; (4) tests: provider payload (respx), mixed mp3/flac lineage, storage/Range for FLAC, recovery of a job across a format setting change, frontend label; (5) real-GPU validation and one E2E run with FLAC generation (create, play, download, Extend/Repaint/Extract/Another Take on a FLAC and on an old MP3 Version); (6) docs, including a manual Firefox/Safari playback check because it could not be automated locally.
**Out of scope:** MP3/WAV export or conversion, FFmpeg, per-song format choice or any UI, changing existing Versions, ZIP/stems export, mastering, quota, content validation (optional), Opus/AAC (not functional in this ACE-Step deployment).

## 21. Explicit Non-Goals

No batch, prompt library, cover art, loudness, MIDI, chords, lyric alignment, `lego`/`complete`, new Extract tracks, cancellation, or new dependencies.

## 22. Risks

- **Perceptual benefit unproven** (no listening; SNR only). The measured facts are exactness of preserved regions and non-compounding, not a proven audible improvement.
- **Firefox/Safari not tested locally**; MDN says FLAC is supported (Firefox 51+, Safari 11+). Mitigation: rollback setting and a manual check.
- **Storage about 5x** with no quota.
- **16-bit ceiling** of ACE-Step FLAC output (future mastering headroom).
- ACE-Step silently returns success without a file for opus/aac: if someone configures those, jobs fail visibly ("no audio file path"); document as unsupported.
- FLAC size on vocal-heavy songs unmeasured.
- The Chromium-only decode evidence and float-WAV uncertainty.

## 23. Decision

**IMPLEMENT PHASE 17** (narrow FLAC scope above), because the pipeline change is small (provider setting, one MIME normalization, one label), needs nothing new, is reversible by a setting, non-destructive to existing Versions, has no GPU or latency cost, removes ACE-Step's FFmpeg dependency from the output path, and stops the measured generation-by-generation degradation of derived Versions.

## 24. Next Phase Recommendation

After Phase 17: **Export/Publishing** (download as MP3/WAV via conversion) and its FFmpeg/license decision, then the earlier deferred list (batch, prompt library, cover art) only with new evidence. Still unresolved and independent of this phase: Extract stem quality needs a human listener.
