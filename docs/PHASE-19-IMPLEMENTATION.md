# Phase 19: Validation and Operability Hardening (no new product feature)

## 1. Executive summary

Phase 19 set out to close four open questions and one visibility gap. Two are closed by measurement, two need a **human listener** that this environment does not have, and one needs a **real Safari** that does not exist here. They are reported as NOT VALIDATED, not as passes.

| Question | Status |
|---|---|
| A. Safari FLAC playback | **NOT VALIDATED** (no real Safari; manual procedure written) |
| B. MP3 chain vs FLAC chain, audible? | **NOT VALIDATED** (blind kit built; needs a human). Technical evidence PARTIALLY CONFIRMED and one earlier claim corrected |
| C. Extract stem quality | **NOT VALIDATED by listening**; instrument measurements raise concerns (inconsistent across songs) |
| D. RTX 5060 Ti operating envelope | **CONFIRMED** for the tested envelope (single active generation, up to 180 s, both models resident); observed peak 15,775 MiB of 16,311 MiB |
| E. Read-only storage visibility | **CONFIRMED** (developer script, no product code) |

No product feature, endpoint, dependency, migration or ACE-Step change was added.

## 2. Starting git state

Branch `feature`, `HEAD` = `origin/feature` = `277e55cef84adf1e43028fda0ebf3d52f645d969` ("Use FLAC for new audio versions", Phase 17, pushed at the user's request during Phase 18). Pre-existing unrelated items left untouched: the `CLAUDE.md` edit and the `ACE-Step-1.5` submodule marker. `docs/PHASE-18-PRODUCT-CAPABILITY-GAP-AUDIT.md` was still untracked and is committed with this phase. ACE-Step `ca1e85f` = upstream HEAD (`git ls-remote`).

## 3. Open-source and reuse audit

OpenSource Radar (`.../explore/?category=ai-music`, rendered with headless Chromium because the page is client-side) still lists the same 23 repositories as in Phase 18 (no new or removed entries). Tracked candidates re-checked on GitHub: YuE2-Studio 164 stars MIT, acestep.cpp 424 MIT, remiqora 125 MIT, ACE-Step 12.9k MIT (upstream HEAD unchanged). Nothing new changes the Phase 18 conclusions.

Tooling decisions (REUSE before BUILD):

| Need | Considered | Decision |
|---|---|---|
| GPU sampling | `nvidia-smi` (installed), gpustat/nvitop (extra dependencies) | REUSE `nvidia-smi`; a 40-line sampler thread in a script |
| Audio measurement | ACE-Step's existing venv (numpy 2.3.5, scipy 1.17.0, soundfile 0.13.1, httpx) | REUSE; no Tunora dependency added |
| MP3 copy of a lossless master, decoding for measurement | local `ffmpeg` (GPL developer build; used only in developer scripts, never called by Tunora, not distributed) | REUSE as a dev tool |
| Listening | OS/browser players | REUSE; only a randomized file kit and a response sheet were built |
| Storage report | stdlib `pathlib`/`sqlite3` reading the existing layout `<root>/<job>/<job>.<ext>` | BUILD (about 90 lines, read-only), no OSS fits a Tunora-specific layout |
| Safari | cloud browser services | REJECTED (would manufacture, not establish, a pass) |

## 4. Safari validation: NOT VALIDATED

- Real Safari needs macOS or iOS/iPadOS; the only machine here is Windows and no Apple device is reachable from this session.
- Tested instead: Chromium 153 and Firefox (Playwright build 1543) both PASS for a real FLAC Version (play, seek, pause, resume, waveform painted, download `.flac`, reload). Playwright WebKit on Windows FAILS: the Play button never becomes enabled, `audio playback failed MediaError`. It fails MP3 as well (Phase 17), so it is not evidence about FLAC or about Safari.
- The exact manual procedure (LAN access to a production build, per-step checklist, what to record, rollback if FLAC fails) is in `docs/validation/README.md`.

## 5. MP3 vs FLAC methodology

Real ACE-Step, one 20 s vocal pop master (lossless FLAC). **MP3 lineage** (the old pipeline): master -> 128 kbps MP3 -> three consecutive Repaints of 12-18 s, each uploading the previous MP3 and producing MP3. **FLAC lineage**: the same master -> three Repaints producing FLAC. Same prompt, region and operation. Measurements are on the **first 10 s, which no Repaint touches**, decoded to 48 kHz. A blind kit was written outside the repository (`I:\Tunora-validation\mp3_vs_flac`): 6 trials, randomized A/B order and neutral labels, two identical-pair catch trials, level matched to within 0.2 dB by gain only (no normalization or compression), sheet categories NOT NOTICEABLE / SLIGHT / MODERATE / CLEAR.

## 6. MP3 vs FLAC results

**Human listening evidence: none. Result: NOT VALIDATED (blocked; requires a listener).** The kit is ready and the procedure is in `docs/validation/README.md`.

**Technical evidence (instrument measurements, not listening):**

| File (untouched 0-10 s) | Level change vs master | SNR vs master after level match | Share of energy above 16 kHz |
|---|---|---|---|
| lossless master | 0 | reference | 0.0007 |
| MP3 source (generation 0) | -0.36 dB | 18.2 dB | 0.0000 |
| MP3 chain gen 1 / 2 / 3 | -1.81 / -1.72 / -3.19 dB | 16.9 / 15.9 / 15.3 dB | 0.0000 |
| FLAC chain gen 0 (the master) | 0 | exact | 0.0007 |
| FLAC chain gen 1 / 2 / 3 | -0.65 / -1.65 / -2.65 dB | 84.3 / 80.3 / 78.2 dB | 0.0007 |

- The MP3 lineage carries codec error from the first encode (18 dB) that deepens slowly per derived Version and has no content above 16 kHz; the FLAC lineage's untouched region keeps the master's waveform up to a global gain, and keeps the >16 kHz band (about 0.07 % of the energy).
- **Correction of an earlier statement:** Phase 17 reported the FLAC chain "bit-exact (126.6 dB)". That held for the 10 s instrumental clip measured then. On this vocal clip the untouched region is the same waveform **scaled by a per-generation gain** (level drops 0.65, 1.65, 2.65 dB), because ACE-Step peak-normalizes every output (`enable_normalization = True`, `normalization_db = -1.0`, `acestep/inference.py:135-136`) and the regenerated section's peak changes the whole file's gain. The drift happens in both lineages and is independent of the format. The correct statement is: FLAC preserves the untouched waveform up to a global gain (78-84 dB after level matching); MP3 does not (15-18 dB).
- SNR is not perceptual. Whether 15-18 dB codec error at 128 kbps, or missing >16 kHz content, is audible is exactly what the blind kit is for.

**Classification: audible benefit NOT VALIDATED; technical difference PARTIALLY CONFIRMED (one clip, one operation).**

## 7. Extract stem methodology

Real Tunora Extract jobs (base model, verified by the Phase 14 check) on one 30 s vocal pop Song, and two additional real songs extracted directly through ACE-Step (an acoustic ballad and a rock song). Instrument measurements per stem (level, silence, band energy, spectral centroid, onset rate, stereo correlation, correlation with the mix, share of the mix's energy, sum-of-stems vs mix) and a blind stem kit in `I:\Tunora-validation\stems` (five shuffled unlabeled files, sheet with CLEAN / USABLE / PARTIALLY USABLE / POOR / UNUSABLE). Only stems ACE-Step actually returned (vocals, drums, bass, guitar) were used.

## 8. Extract stem results

**Human listening evidence: none. Result: NOT VALIDATED (blocked; requires a listener).** No usefulness rating is claimed.

Instrument measurements (30 s pop mix; mix: 66 % of energy below 250 Hz, 29.7 % in 300-3400 Hz):

| Stem | <250 Hz | 300-3400 Hz | Strongest peak | Correlation with mix | Stereo corr. |
|---|---|---|---|---|---|
| vocals | 97.9 % | **0.6 %** | 100 Hz | 0.36 | 0.99 |
| drums | 84.8 % | 9.4 % | 70 Hz | 0.47 | 0.93 |
| bass | 99.2 % | 0.1 % | 100 Hz | 0.46 | 0.99 |
| guitar | 93.1 % | 5.4 % | 100 Hz | 0.58 | 0.97 |

Also: the four stems sum to the mix with only 2.0 dB SNR (they are generated content, not an additive decomposition), each is peak-normalized to -1 dBFS, and vocals/bass/guitar share the same dominant 100 Hz component (pairwise correlations 0.44-0.57).

Vocal-band (300-3400 Hz) share of the "vocals" stem across three songs: pop mix 0.6 % (mix 29.7 %), acoustic ballad 16.1 % (mix 35.1 %), rock 88.5 % (mix 20.9 %). On the rock song the stems look plausible by these numbers; on the pop and ballad songs the "vocals" stem does not look like a voice by the same measure. These are indicators of **inconsistent extraction quality**, not a verdict: only a listener can tell whether the stems are usable.

**Classification: NOT VALIDATED (listening); measurements raise a concern that Extract quality varies a lot by song.**

## 9. GPU measurement methodology

`docs/validation/gpu_envelope.py` starts a throwaway backend (own DB/storage, port 8010) on the running ACE-Step server (both models loaded by the launcher configuration: turbo primary plus base second slot, 1.7B LM) and runs real Tunora operations while a thread samples `nvidia-smi` `memory.used` and `utilization.gpu` every 0.5 s. **Every peak below is an observed sampled maximum, not a guaranteed absolute hardware peak.** System free RAM was read after each operation. Concurrency: two Creates submitted at once. Recovery: a 60 s Create with the backend killed and restarted mid-job. Older runs (Phase 14-18) are consistent with these numbers.

## 10. GPU results (RTX 5060 Ti, 16,311 MiB; both ACE-Step DiT models + LM resident)

| Operation | Result | Seconds | Before MiB | Observed peak MiB | After MiB | Max GPU util |
|---|---|---|---|---|---|---|
| Create 10 s | COMPLETED | 15.8 | 13,214 | 15,423 | 12,281 | 98 % |
| Create 30 s | COMPLETED | 15.2 | 13,131 | 15,355 | 12,283 | 98 % |
| Create 60 s | COMPLETED | 15.6 | 13,132 | 15,370 | 12,279 | 98 % |
| Create 180 s | COMPLETED | 27.5 | 13,127 | 15,370 | 12,266 | 100 % |
| Extend +30 s | COMPLETED | 12.5 | 12,274 | 15,716 | 12,038 | 99 % |
| Remix | COMPLETED | 9.4 | 12,037 | 14,503 | 11,707 | 100 % |
| Repaint 10-20 s | COMPLETED | 9.3 | 11,707 | 14,171 | 12,120 | 98 % |
| Extract vocals / drums / bass / guitar | COMPLETED x4 | 9.4-10.0 | 12,113-12,140 | 14,577-14,604 | 12,113-12,140 | 94-100 % |
| Another Take | COMPLETED | 15.6 | 12,990 | 14,933 | 12,055 | 98 % |
| Extract drums from a 180 s Version | COMPLETED | 18.3 | 12,055 | **15,775** | 11,875 | 100 % |
| Repaint 60-90 s of a 180 s Version | COMPLETED | 24.5 | 11,878 | 15,773 | 12,055 | 100 % |
| 2 concurrent Creates (30 s) | both COMPLETED | 15.3 / 30.5 | 12,915 | 14,682 | 12,111 | 97 % |
| 60 s Create, backend killed and restarted (Phase 16) | COMPLETED | 18.4 | 12,961 | 14,673 | 12,112 | 98 % |

Cold start: everything stopped 964 MiB; ACE-Step healthy 8 s after launch at 1,144 MiB with **no model loaded**; the first request loads both models lazily (47 s for a 10 s clip, observed peak 14,122 MiB) and leaves 10,799 MiB idle (steady-state idle later reads 11.9-13.3 GB as the allocator caches). Free system RAM during the runs was 1.5-5.1 GB of 31.6 GB (the development machine also runs the other servers).

**SAFE (observed):** one active generation at a time; both models loaded; durations 10, 30, 60 and 180 s; Create, Extend, Remix, Repaint, Extract (all four tracks), Another Take; backend restart recovery; two queued jobs (ACE-Step ran them one at a time: `max running = 1`, the second finished 15 s after the first).
**KNOWN RISK ZONE:** the observed peak leaves only about 536 MiB (16,311 - 15,775) of headroom, and the sampler can miss spikes; any additional GPU-resident model (image, ASR, transcription) is not viable beside ACE-Step in this configuration; three or more queued jobs, batch sizes above 1 and durations above 180 s were not tested; long soak runs were not tested.

## 11. Storage report

`backend/scripts/storage_report.py` (standard library, read-only, opens the database read-only, prints only relative keys) with 6 tests in `backend/tests/test_storage_report.py`; no endpoint, no delete, no quota. On the developer's own library: 13 MP3 files, 16.4 MB, 1.3 MB average. On the FLAC envelope run: 17 FLAC files, 102.2 MB, 6.0 MB average, largest 20.1 MB (a 180 s Version); projection at 2.4 versions per song: 100 songs 1.4 GB, 1,000 songs 14.3 GB, 10,000 songs 142.6 GB (estimates at the current average file size, not a forecast). Earlier measurement: a 3-minute pop clip is 21.5 MB as FLAC.

## 12. Test results (final code)

- Backend `pytest -m "not smoke"`: **636 passed** (630 before, +6 storage-report tests).
- Real-GPU smoke: **13 passed**.
- Playwright (real stack, real GPU): **19 passed**.
- TypeScript clean; ESLint 0 errors (1 pre-existing warning); `next build` passes.
- Vitest: **366 passed, 1 failed** in full-suite runs: `version-actions.test.tsx > selects the new version, moves Latest ...`, the known real-timer race documented in `CLAUDE.md`. It passed 3 of 3 when the file was run alone (29/29), and it fails identically in a full run on a clean checkout of `277e55c` (no Phase 19 change) in the same machine state, so it is not caused by this phase; it appears to depend on machine load (ACE-Step and other servers resident). Not fixed here (no frontend change in scope).

## 13. Known limitations

- Safari, the MP3 vs FLAC listening test and the Extract stem listening are NOT VALIDATED (they need a person and an Apple device); the kits and procedures are ready.
- One clip and one operation for the MP3/FLAC measurements; three songs for the stems.
- GPU peaks are sampled at 0.5 s; single-machine, single-GPU evidence.
- The chain experiment used ACE-Step directly with the same calls Tunora's provider makes (Tunora cannot import an external MP3 as a Version), so it reproduces the old pipeline rather than running Tunora's retired code.
- ACE-Step peak-normalizes outputs, so a derived Version's loudness drifts by about a dB per generation in either format.

## 14. Evidence that no unrelated features were added

Added files only: `docs/validation/` (README, three developer scripts' worth of tooling: `gpu_envelope.py`, `audio_validation.py`, and result JSON files), `backend/scripts/storage_report.py` (read-only developer script), `backend/tests/test_storage_report.py`, the Phase 18 and Phase 19 documents and a short note in `docs/TUNORA-SERVICE-MANAGEMENT.md`. No change to `backend/app`, `frontend/src`, dependencies, `pyproject.toml`, `package.json`, the database schema, the API or ACE-Step.

## 15. Evidence table

| Area | Result | Evidence | Confidence |
|---|---|---|---|
| Chromium FLAC | PASS | Playwright: play, seek, pause, resume, waveform, download `.flac`, reload | High |
| Firefox FLAC | PASS | same checks (Playwright Firefox build) | Medium (one build) |
| Safari FLAC | NOT VALIDATED | no Apple device; Windows WebKit fails MP3 too | n/a |
| MP3 vs FLAC audible | NOT VALIDATED | blind kit built, no listener | n/a |
| MP3 vs FLAC technical | PARTIALLY CONFIRMED | level-matched SNR 15-18 dB vs 78-84 dB, one clip | Medium |
| Extract vocals | NOT VALIDATED (listening); concern | vocal-band share 0.6 % / 16 % / 88 % across three songs | Low-Medium |
| Extract drums / bass / guitar | NOT VALIDATED (listening) | measurements only | Low |
| GPU Create | CONFIRMED | 10-180 s COMPLETED, peak 15,423 MiB max | Medium-High |
| GPU Extend | CONFIRMED | peak 15,716 MiB | Medium |
| GPU Remix | CONFIRMED | peak 14,503 MiB | Medium |
| GPU Repaint | CONFIRMED | 14,171 MiB (30 s), 15,773 MiB (180 s) | Medium |
| GPU Extract | CONFIRMED | 14,604 MiB (30 s), 15,775 MiB (180 s) | Medium |
| GPU Another Take | CONFIRMED | 14,933 MiB | Medium |
| GPU concurrency | CONFIRMED for 2 jobs | ACE-Step serialized them | Medium |
| Storage | CONFIRMED | script + tests + two real reports | High |

## 16. Final decision

| Open question | Classification |
|---|---|
| Safari FLAC | NOT VALIDATED |
| Audible MP3 vs FLAC benefit | NOT VALIDATED (technical PARTIALLY CONFIRMED, claim corrected) |
| Extract stem quality | NOT VALIDATED (measurements show inconsistency) |
| GPU envelope | CONFIRMED (tested range), headroom about 536 MiB |
| Storage visibility | CONFIRMED |
| Everything else in scope | no failures |

**Recommended Phase 20: J. No new feature yet.** Two of the three quality questions need a person: run the two blind kits and the Safari checklist, then decide. Reasons: nothing measured here creates a new product gap by itself; the one new technical concern (Extract quality varies by song) could change the roadmap (label Extract as experimental, or investigate ACE-Step's extract settings) but cannot be judged without listening; the ecosystem scan (Phase 18) found nothing reusable; the GPU envelope forbids adding GPU-resident features. When the human results are in, the leading feature candidate remains **A. MP3/WAV export** (FLAC files are large to share), gated on an FFmpeg-licensing decision.
