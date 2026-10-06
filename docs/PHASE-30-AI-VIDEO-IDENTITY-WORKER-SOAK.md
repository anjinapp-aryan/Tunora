# Phase 30 — AI Video Identity Consistency & Worker Soak (lab)

Lab / feasibility phase. **No Tunora production code, schema, API, UI, worker, queue or dependency was changed.**
All experiments ran in `I:\Tunora-validation\ai-video-feasibility\phase-30\`; small reproducibility files (scripts,
workloads with prompts and seeds, metrics, state files, logs — no media, no weights) are in
`docs/validation/phase-30/`. Inputs: `docs/AI-MUSIC-VIDEO-OSS-FEASIBILITY-AUDIT.md`,
`docs/PHASE-29-AI-VIDEO-FEASIBILITY-LAB.md` (commit `d4141e6`).

Dates: 2026-10-05 (audit, baseline, identity, failure injection, soak clips 1–22),
2026-10-06 (soak clips 23–50, ACE-Step hand-off, analysis). All numbers were **measured on this machine** unless
labelled EXTRAPOLATED / UNVERIFIED / NOT TESTED. Visual scores are the reviewer's judgement from multi-frame contact
sheets (paths in each section); the user's own viewing is still pending (see §30).

---

## 1. Executive Summary

- **Identity (Question A): yes, at keyframe level for 50 shots.** A fresh audit found one licence- and hardware-safe
  reference-image model that fits this machine: **FLUX.2-klein-4B (Apache-2.0)**. Using two self-consistent
  reference images of one fictional performer, 50/50 keyframes across 50 different locations, framings, poses and
  lights kept the same face, braid, costume and jewellery — scored **4/5 at checkpoints 10, 20, 30 and 50**, versus
  **2/5** for Phase 29's text-only method (Z-Image) on the same 10 shots. In the generated video, identity holds
  inside each clip (3.5–4/5); close-ups drift somewhat with strong expressions.
- **Worker reliability (Question B): yes for 50 real clips.** A lab controller running **one child process per shot**
  completed **50/50 FastWan clips (45 × 3.2 s + 5 × 5 s), 0 unrecovered failures**, across five controller runs. No
  hang, no crash, no invalid output, no cumulative RAM/VRAM growth, no leftover worker processes. Failure injection
  (exception, crash after load, hang with model resident, missing/invalid/corrupt output, disk full) produced exactly
  the expected PASS/FAIL pattern; resume worked after a planned stop, an **uncontrolled controller death** and a
  **deliberately orphaned worker**.
- **ACE-Step hand-off** works after the 50-clip soak: ready 27.6 s, generates, stops and releases VRAM in 9.1 s.
- **Found and fixed in the lab:** (1) the orphan-cleanup matched processes by command-line *text* and killed
  unrelated shells; (2) Windows idle sleep paused the job for 2 h 4 min and the wall-clock timeout then killed a
  healthy shot; (3) the interactive session's teardown killed a "detached" overnight runner; (4) one 5-second clip
  took 2.2× its normal time (83 % of its timeout budget).
- **Motion remains the limiting capability:** mean **3.1/5** over 10 categories — walking, arm movement, spins,
  bends and facial expression work; fast movement, leaps and prompted camera moves do not.
- **Quality gate: CONDITIONAL PASS. Production implementation: NOT APPROVED** (motion limits, supervisor/power
  behaviour, and no user quality verdict yet).

## 2. Phase 30 Objective

Answer with evidence: (A) can one AI performer stay recognisably the same across many independently generated
shots, and (B) can the AI-video worker survive a long multi-shot workload without hangs, leaks, process leaks,
corrupted outputs, disk exhaustion, unrecoverable failures or ACE-Step damage — on the RTX 5060 Ti 16 GB.

## 3. Phase 29 Baseline

Phase 29: Z-Image-Turbo keyframes + FastWan2.2-TI2V-5B (3-step DMD) clips + LGPL FFmpeg montage; ~39–42 min per
30 s; ~77 GPU-s per video-s; ~16 GB VRAM peak; heavy RAM pressure; one 2-hour silent hang in a long-lived worker;
faces changed between shots; athletic actions unreliable.

**E1 reproduction (same models/settings, new harness):** 6/6 valid — 3 Z-Image keyframes 48.2–52.1 s, 3 FastWan
clips 214.5–220.2 s (Phase 29: 218–226 s); VRAM back to baseline after every shot; RAM fell to 0.03 GB available
during the Z-Image load (same pressure as Phase 29). Environment confirmed before changing anything.

## 4. Fresh OSS / Model Audit (checked 2026-10-05, Hugging Face API + GitHub API + official cards)

| Candidate | Code licence | Weight licence | Size / VRAM | Fits this machine? | Decision |
|---|---|---|---|---|---|
| **FLUX.2-klein-4B** (`black-forest-labs/FLUX.2-klein-4B@e7b7dc2`, 394k downloads, 1,004 likes) | Apache-2.0 (Diffusers `Flux2KleinPipeline`) | **Apache-2.0** (LICENSE.md verified) | 4B; ~15.8 GB download (Diffusers folders); card: "~13GB VRAM" | yes (disk after freeing 9.4 GB) | **REUSE — primary** |
| Z-Image-Turbo text-only (Phase 29) | Apache-2.0 | Apache-2.0 | already installed | yes | **REUSE — baseline/secondary** |
| Z-Image-Edit | — | — | **not released** (HF 404) | — | UNKNOWN / not available |
| Qwen-Image-Edit-2509 / 2511 | Apache-2.0 | Apache-2.0 | 20B, **57.7 GB** repo | no (disk, RAM) | REJECT (hardware) |
| OmniGen2 (Apache-2.0, 4.1k★) | Apache-2.0 | Apache-2.0 | 31.3 GB | no (disk) | REJECT (hardware) |
| Phantom (subject-to-video) | Apache-2.0 | Apache-2.0 | 63 GB; Wan2.1 base, not FastWan | no | REJECT (hardware, different base) |
| Wan2.1-VACE-1.3B (reference-to-video) | Apache-2.0 | Apache-2.0 | 19 GB; 480p; different base | not without replacing FastWan | REFERENCE |
| FLUX.2-dev | — | **FLUX non-commercial** | — | — | **REJECT (licence)** |
| UNO, DreamO | Apache-2.0 | Apache-2.0 adapters **on FLUX.1-dev (non-commercial base)** | — | — | **REJECT (licence)** |
| InstantID, PuLID, IP-Adapter-FaceID, Stand-In | Apache-2.0 / MIT | require **insightface antelopev2: "non-commercial research purposes only"** | 1.9–4.9 GB | — | **REJECT (licence)** |
| InfiniteYou | — | **CC-BY-NC-4.0** | 43 GB | — | **REJECT (licence)** |
| Lynx (ByteDance) | — | gated / not accessible | — | — | UNKNOWN — not used |
| Character LoRA training (Z-Image / klein) | Apache-2.0 tooling | — | training time + VRAM unmeasured | not tested | REFERENCE (future, only if reference-editing proves insufficient) |
| Seed/prompt-only consistency | — | — | — | — | measured as baseline (Z-Image) — insufficient |

Worker-reliability capabilities: no OSS job-supervision library was needed; the lab harness uses Python stdlib
`subprocess` + `psutil` (BSD-3) + Windows `taskkill`, i.e. composition of existing primitives (§15).

## 5. Candidate Identity Approaches

| Candidate | Licence | Model licence | Identity quality (measured) | VRAM peak | RAM peak (process) | Speed (per image, own process) | RTX 5060 Ti | Windows | Recommendation |
|---|---|---|---|---|---|---|---|---|---|
| FLUX.2-klein-4B multi-reference edit | Apache-2.0 | Apache-2.0 | **4/5** (10, 20, 30, 50 shots) | 12.1–12.5 GB | 16.7–16.8 GB | 41.4–46.9 s (gen 28–31 s) | yes | yes | **PRIMARY** |
| Z-Image-Turbo text-only (Phase 29 method) | Apache-2.0 | Apache-2.0 | **2/5** (10 shots) | 13.7 GB | 21.0 GB | 46.7–52.0 s | yes | yes | secondary / rejected for identity |

## 6. Selected Approach

1. **Reference set (2 images):** a head-and-shoulders portrait generated by klein (text-to-image), then a full-body
   reference **derived from the portrait by klein reference-editing** so both show the same person. (The first
   attempt generated both independently; they showed two different faces and two braids instead of one — rejected
   and kept as `failures/rejected_ref_full_t2i.png`. Lesson: the reference set must itself be consistent.)
2. **Every shot keyframe:** klein edit with both references + an identity clause ("keep exactly the same face, skin
   tone, braid, costume, jewellery") + scene description; 4 steps, guidance 1.0, 704×1280.
3. **Every clip:** FastWan2.2-TI2V-5B image-to-video from that keyframe (Phase 29 configuration, unchanged).

## 7. License Assessment

| Component | Code | Weights | Commercial | Class |
|---|---|---|---|---|
| FLUX.2-klein-4B | Apache-2.0 | Apache-2.0 (LICENSE.md text verified); card's acceptable-use section forbids unlawful/abusive uses | allowed | 🟢 |
| Z-Image-Turbo, Wan2.2 TI2V-5B, FastWan2.2-TI2V-5B | Apache-2.0 | Apache-2.0 | allowed | 🟢 (training data undisclosed) |
| Beat This!, librosa, psutil, PIL | MIT / ISC / BSD-3 / MIT-CMU | MIT (Beat This!) | allowed | 🟢 |
| FFmpeg (Tunora approved build) | LGPL-3.0, libopenh264 | — | allowed | 🟢 |
| Poppins font (contact-sheet labels only) | SIL OFL 1.1 | — | allowed | 🟢 |
| All rejected candidates in §4 | | | | 🔴 / UNKNOWN — not used |

No component with an unknown or non-commercial licence was downloaded or executed. Downloaded in Phase 30: FLUX.2
klein Diffusers folders (transformer 7.75 GB, text encoder 8.05 GB, VAE 0.17 GB, configs/tokenizer). Klein's
text encoder was compared tensor-by-tensor with Z-Image's (both Qwen3-4B): 167/169 tensors of shard 2 identical, two
layer-35 MLP tensors differ — so klein's own encoder was used (correctness over the 5 GB saving).

## 8. Hardware Baseline (E0)

`docs/validation/phase-30/hardware/hardware-baseline.json`: Windows 11 Pro 10.0.26200; RTX 5060 Ti 16,311 MiB
(driver 591.86, compute 12.0); 1,764 MiB used idle; 31.64 GB RAM (17.6 GB available); CPU idle 4.1 %; disk free
C: 27.3 / D: 20.2 / I: 20.0 GB (5.1–5.8 GB on I: during the soak); Python 3.12.10; torch 2.7.1+cu128 (CUDA 12.8);
diffusers 0.40.0; transformers 5.18.0; accelerate 1.15.0; ACE-Step not running.

## 9. Identity Experiment Results

Same 50 shot specifications for every checkpoint (`jobs/shot_specs.json`): shots 1–10 = the real-song plan, 11–20 =
motion categories A–J, 21–50 = systematic combinations of 10 locations × 6 framings × 5 lights × 6 poses × 5 cameras.

| Checkpoint | Approach | Keyframes valid | Identity | Costume | Style | Overall | Sheet |
|---|---|---|---|---|---|---|---|
| 10 | klein reference-edit | 10/10 | **4** | 4 | 4 | **4** | `contact-sheets/ckpt10_identity_compare.jpg`, `ckpt10_face_crops.jpg` |
| 10 | Z-Image text-only | 10/10 | 2 | 3 | 4 | 3 | same sheet (bottom row) |
| 20 | klein | 20/20 | 4 | 5 | 4 | 4 | `ckpt20_identity.jpg` |
| 30 | klein | 30/30 | 4 | 5 | 4 | 4 | `ckpt30_identity_21_30.jpg` |
| 50 | klein | 50/50 | 4 | 5 | 4 | 4 | `ckpt50_identity_31_50.jpg`, `ckpt50_identity_all.jpg` |
| 1–10 clips (4 frames each) | klein → FastWan | 10/10 | 4 | 5 | 4 | 4 | `clips_s01_s10_frames.jpg` |
| 21–50 clips (mid frame) | klein → FastWan | 30/30 | 3.5–4 | 5 | 4 | 4 | `clips_s21_s50_midframes.jpg` |

Observed (not only scored): the reference face (round face, centre-parted hair, bindi, nose/brow shape) recurs in
every close-up (shots 3, 20, 21, 27, 33, 39, 45). Z-Image produced visibly different women and invented jewellery
(maang tikka) not in the description.

## 10. 10-Shot Results — PASS
klein 4/5 vs Z-Image 2/5 on identical specs; no drift.

## 11. 20-Shot Results — PASS
Identity 4/5. New limitation found: **pose collapse toward the reference stance** — shots 11, 14, 16, 19 share nearly
the same standing pose with hands together; prompts can override it (crouch in 18, close-up in 20).

## 12. 30-Shot Results — PASS
Identity 4/5 in 10 new environments (market, throne room, tea hills, beach, skyline, haveli, rain, fort, mandap).

## 13. 50-Shot Results — PASS (keyframes)
50/50 valid, identity 4/5, no catastrophic drift; pose repetition persists.

## 14. Motion Quality Results

Clips 11–20 (one per category), four frames each (`motion_A_H.jpg`, `motion_I_J.jpg`), plus song clips 1–10.

| Category | Clip | Observed | Score (0–5) |
|---|---|---|---|
| A walking | s11 | walks toward camera, natural gait | 4 |
| B turning | s12 | partial body turn, ends facing camera | 3 |
| C arm movement | s13 | clear flowing arm movement | 4 |
| D dance | s14 | hand-gesture choreography, little footwork | 3 |
| E spinning | s15 | full spin to back view, skirt flaring | 4 |
| F full-body | s16 | bends low and rises | 4 |
| G fast movement | s17 | moderate gestures, not fast | 2 |
| H leap/jump | s18 | starts crouched, never completes a leap (also shot 9 "leap" → arm dancing) | 2 |
| I camera movement | s19 | no orbit; frame 0 visibly darker than later frames | 1 |
| J close-up face | s20 | expressive singing → laugh, mouth/brow motion; identity softens with expression | 4 |

Mean **3.1/5**. No broken limbs, extra fingers or melted faces were seen in sampled frames; hands are soft at
704×1280. **Tunora must not claim "dance video capable"**: graceful/medium-energy performance is usable, energetic
dance, jumps and directed camera moves are not.

## 15. Worker Architecture Used in Lab

```
controller.py (one process, persistent state.json, metrics.jsonl)
  for each shot in workload:
     skip if COMPLETED and output re-validates
     disk pre-flight (min free GB)          -> BLOCKED_DISK + stop (state preserved)
     spawn shot_worker.py (own process group, stdout/stderr -> per-attempt log)
         sampler thread: device VRAM (nvidia-smi), worker-tree RSS, system available RAM (0.5 s)
         hard timeout = expected_seconds x 2.5  -> CTRL_BREAK, 15 s grace, taskkill /T /F, verify tree gone
     orphan scan (python.exe whose script argument is shot_worker.py) -> kill
     wait for VRAM to return within 300 MiB of pre-shot (max 30 s)
     validate output (ffprobe frames/size/duration, full decode with -xerror, blackdetect, freezedetect | PIL verify+size)
     record attempt; retry once; COMPLETED / FAILED
  on start: kill orphan workers, reset RUNNING shots (INTERRUPTED_BY_CONTROLLER_EXIT)
shot_worker.py: load one model (Z-Image | klein | FastWan), generate exactly one output, write result.json, exit
```
Expected times from Phase 29 measurements: clip 3.2 s = 225 s, clip 5 s = 460 s, keyframe = 60–90 s.

## 16. Worker Soak Results

`soak/soak_metrics.jsonl`, `metrics/soak_timeseries.csv`, `metrics/phase30_summary.json`.

| Item | Value |
|---|---|
| Workload | 50 real FastWan clips from klein keyframes (45 × 77 frames / 3.21 s, 5 × 121 frames / 5.04 s) |
| Result | **50/50 COMPLETED, 0 FAILED** |
| Attempts | 51 recorded (+3 interrupted by controller loss) — 1 invalid attempt = sleep-induced timeout (§19), recovered on retry |
| Controller runs | A (1–10, planned stop) → B (11–22, ended by session teardown) → C (23–25, resumed; planned kill at 26) → D (26–31, orphan cleanup; stopped by user) → E (32–50) |
| 3.2 s clip wall (incl. process start + load) | 214.1–254.0 s, mean 222.4, median 222.0 (n=45) |
| 5 s clip wall | 429.2, 437.9, 433.0, 532.1, **952.1** s (n=5) |
| Wall-time trend (3.2 s clips) | +0.02 s per shot (no slowdown over 50 shots) |
| Hangs / crashes / invalid outputs | **0 / 0 / 0** (excluding the sleep-induced timeout) |
| Orphan workers after exit | 0 real; 1 false positive caused by the matcher bug (§19) |
| Checkpoints | 10/10, 20/20, 29/30 → 30/30 after retry, 49/50 → 50/50 after retry |
| Disk | 242 MB of clips (4.75–7.56 MB each) |

**20-shot soak: PASS. 30-shot soak: PASS. 50-shot soak: PASS.**

## 17. Memory Results

| Measure | Value |
|---|---|
| Worker process RSS peak | 15.7–17.8 GB per clip (mean 16.2); slope **+0.003 GB/shot** (flat) |
| System RAM available after each shot | 18.1–24.1 GB; within-run slopes −0.004, +0.07, +0.36, −0.0001 GB/shot (A, B, C+D, E) — **no cumulative leak** |
| System RAM available during each clip | ~0.93 GB in 50/51 attempts (Windows low-memory floor), 0.01 GB once |
| Keyframe workers | klein 16.7–16.8 GB RSS; Z-Image 20.7–21.1 GB RSS (drives available RAM to 0.03 GB) |

**PEAK PRESSURE: high (system RAM at the OS floor during every clip). CUMULATIVE LEAK: none.**

## 18. VRAM Results

| Measure | Value |
|---|---|
| Peak per clip | 15,857–16,028 MiB (device) |
| After each shot | 381–1,656 MiB (desktop applications' share; worker process gone) |
| Recovery to ≤ pre-shot + 300 MiB | median 0.1 s, mean 2.4 s, max 30.2 s |
| Within-run after-shot trend | mixed sign (−20, +9, +22, +11 MiB/shot) and Run E ends **lower** than it started (1,700 → 1,367 MiB) — desktop fluctuation, not accumulation |
| GPU contexts left after worker exit | none (VRAM returns; no lab process alive — verified after soak, after kills, after the hang injection) |

Desktop applications hold ~3 GB of dedicated VRAM at times (dwm 1.27 GB, NVIDIA Overlay 0.78 GB, VS Code 0.41 GB,
Chrome 0.29 GB, Citrix 0.23 GB) — they share the 16 GB with the worker.

## 19. Hang/Timeout Results

- **No natural hang in Phase 30** (119 real model runs: 6 E1 + 62 keyframes + 51 clip attempts). The Phase 29 hang was
  not reproduced; its root cause stays UNVERIFIED.
- **Injected hang with the model resident** (`hang_after_load`, 2 attempts): killed exactly at the 100 s timeout
  (graceful CTRL_BREAK sufficed), process tree verified gone, VRAM back to 1,010 MiB in 0.1 s, next shot ran normally.
- **Timeout policy measured, and two weaknesses found:**
  1. *Wall-clock vs sleep:* Windows idle-slept the PC from 08:21:28 to 10:26:02 IST (Kernel-Power 42 / Power-
     Troubleshooter 1) during clip 30. On wake the elapsed time (8,032 s) exceeded the 562 s budget and a healthy shot
     was killed (recovered on retry). Fix verified in the lab: a `SetThreadExecutionState(ES_SYSTEM_REQUIRED)` helper
     — **0 sleep events** during the following 19-clip run. A production timeout must count awake time.
  2. *Budget too tight for 5 s clips:* clip 32 generated in 899.5 s vs 387–413 s for its neighbours (same peak
     memory; load 44 s vs 21–35 s) = **83 % of its 1,150 s budget**. Cause UNVERIFIED (candidates: desktop GPU
     contention / shared-memory spill, first heavy run after hours idle). Use ≥ 3.5× for 5 s clips.
- **Bug found by the soak:** the orphan matcher killed any process whose command line *contained* "shot_worker.py"
  (it killed the shells of a lab watcher at clip 11). Fixed to python processes whose script argument *is*
  shot_worker.py; regression test passes (`lab_selftest.py`). Production must track spawned PIDs, never names.

**HANG HANDLING: PASS.**

## 20. Failure Injection Results

`failures/fi_metrics.jsonl`, `failures/fi_state.json`:

| Shot | Injection | Attempt results | Final | Expected |
|---|---|---|---|---|
| fi_01 | — | valid 41.6 s | COMPLETED | ✓ |
| fi_02 | — | valid 41.8 s | COMPLETED | ✓ |
| fi_03 | exception ×2 | exit 1, exit 1 | FAILED | ✓ |
| fi_04 | — | valid | COMPLETED | ✓ |
| fi_05 | — | valid | COMPLETED | ✓ |
| fi_06 | crash after model load (attempt 1) | exit 3 (12.2 s) → valid 39.5 s | COMPLETED | ✓ |
| fi_07 | hang with model loaded ×2 | timeout at 100.8 s ×2 | FAILED | ✓ |
| fi_08 | missing output ×2 | exit 0 but `missing_output` ×2 | FAILED | ✓ |
| fi_09 | invalid output ×2 | `invalid_image` ×2 | FAILED | ✓ |
| fi_10 | corrupt MP4 (attempt 1) | `invalid_video:decode` (214.3 s) → valid 217.1 s | COMPLETED | ✓ |
| fi_11 | — | valid 47.3 s | COMPLETED | ✓ |
| disk | `--min-free-gb 999` | controller refused, shot `BLOCKED_DISK`, nothing generated; next normal run proceeded | preserved | ✓ |

7 completed / 4 failed — **exactly the predicted pattern; no failure spread to another shot.**

## 21. Resume Results

| Scenario | Evidence | Result |
|---|---|---|
| Planned stop after 10 (`--max-shots 10`) | Run B skipped 1–10 (re-validated, not regenerated), started at 11 | PASS |
| **Uncontrolled controller death** (session teardown at clip 23) | Run C: `reset_running clip_s23` (history `INTERRUPTED_BY_CONTROLLER_EXIT`), 22 completed untouched | PASS |
| **Controller killed, worker deliberately orphaned** (clip 26, `resume/hard_kill.log`) | Run D within 5 s: `orphan_worker_found` 23896 (forced kill), child gone, `reset_running clip_s26`, continued | PASS |
| User stop at clip 32 | Run E (next evening): reset 32, skipped 31 completed, finished 32–50 | PASS |
| Unplanned interrupt during identity keyframes | state left `kf_s01 RUNNING` (`failures/unplanned_interrupt_klein10_state.json`) | evidence of the case handled above |
| Detached "overnight" runner | **FAILED**: killed together with the interactive session (log stops at "started") | lesson: supervision must be an OS-level process, not a child of a tool/session |

No completed clip was ever regenerated or duplicated; output files and metadata stayed valid across all restarts.
Design note: an interrupted attempt counts toward `max_attempts` (2), so an interrupted-then-failed shot gets no
further retry — production should not count interruptions as attempts.

## 22. ACE-Step Handoff Results

| Run | VRAM before | Ready | First generation | Loaded idle | Peak | Stop → released | After |
|---|---|---|---|---|---|---|---|
| Phase 29 before video | 1,572 | 28.0 s | 49.9 s ✓ | 11,209 | 14,546 | 9.7 s | 1,632 |
| Phase 29 after video | 816 | 29.7 s | 52.6 s ✓ | 10,337 | 13,671 | 8.5 s | 760 |
| **Phase 30 after 50-clip soak** | 1,367 | **27.6 s** | **47.4 s ✓** | 10,875 | 14,219 | **9.1 s** | 1,295 |

**ACE-STEP HANDOFF: PASS** — AI-video work did not degrade ACE-Step availability.

## 23. Real Tunora Song Results

Song "I Will Rise" (`ver-53c1604d…`): 60.0 s MP3 48 kHz stereo; BPM 77 (ACE-Step metadata), 76.9 (Beat This!);
E♭ major, 4/4; lyrics with section tags; TimedLyrics reused from Tunora (chorus 37.19 s). Shots 1–10 follow the
Phase 29 bar-aligned plan (22.72–53.90 s, one shot per 3.12 s bar, verse→chorus at 38.30 s). **PASS.**

## 24. 30-Second Montage Results

Soak clips s01–s10 (klein identity) assembled with the Phase 29 montage script and the approved FFmpeg:
`outputs/e14_montage_9x16.mp4` — **1080×1920, 30 fps, 936 frames, 31.20 s, AAC 48 kHz 31.18 s, 30.6 MB**, 10/10
clips valid (0 black, 0 freeze), assembly 9.6 s. Identity across the montage 4/5, motion as §14 (shot 9 "leap" not
performed), beat cuts exact by construction. 16:9 was proven in Phase 29 with the same pipeline and was not
repeated. **30-SECOND MONTAGE: PASS** (technical); user viewing pending.

## 25. 60/120/180/300 Second Estimates

MEASURED per shot (3.2 s clip, separate processes): klein keyframe 42.6 s + FastWan clip 222.4 s = **265 s ≈ 4.4 min
per shot**, i.e. **≈ 85 GPU-seconds per finished video-second** (shots trimmed to 3.12 s bars). Disk ≈ 6.1 MB of
intermediates per shot. Failure rate on real work: 0 % unrecovered, 1/51 clip attempts timed out (power-sleep),
1/5 five-second clips used 83 % of budget.

EXTRAPOLATED (77 BPM bar shots, +10 % allowance for retries/outliers, ACE-Step stopped, PC kept awake):

| Song | Shots | Worker processes | GPU time | With +10 % | Intermediates | Final (HD) |
|---|---|---|---|---|---|---|
| 30 s | 10 | 20 | **≈ 44 min (measured: 10 kf + 10 clips)** | — | 61 MB | 31 MB (measured) |
| 60 s | ~19 | ~38 | ~1.4 h | ~1.5 h | ~0.12 GB | ~0.06 GB |
| 120 s | ~39 | ~78 | ~2.9 h | ~3.2 h | ~0.24 GB | ~0.12 GB |
| 180 s | ~58 | ~116 | ~4.3 h | **~4.7 h** | ~0.35 GB | ~0.18 GB |
| 300 s | ~97 | ~194 | ~7.1 h | **~7.9 h** | ~0.59 GB | ~0.30 GB |

Memory per shot does not grow with song length (process per shot; flat trends over 50 shots). The 50-clip soak
itself is the closest measured analogue: ~3.3 h of clip generation for 50 shots ≈ 2.6 min of video.

## 26. Disk Usage

Phase 30 outputs (measured): clips 242 MB, klein keyframes 65 MB, Z-Image keyframes 12 MB, references 3.5 MB,
montage 30 MB, failure-injection outputs 13 MB, logs/state 0.5 MB. Model cache now: Z-Image bf16 20.5 GB, Wan2.2
text encoder+VAE 14.2 GB, FastWan 10.0 GB, klein 15.8 GB. I: free 5.1–5.8 GB throughout — **disk for models is the
binding storage constraint**, not per-video output.

## 27. Performance Analysis

Per-process overhead is small and stable: klein load 10–12 s, FastWan load+encode ~21–44 s within 214–254 s.
Generation dominates. Keyframes are 16 % of per-shot time. Throughput is flat over 50 shots. The variance risk is
the 5-second clip (429–952 s); 3.2-second shots are predictable (214–254 s, σ small).

## 28. Reliability Analysis

Strong: process isolation, timeouts, validation, retry, disk pre-flight, checkpoint/resume and orphan cleanup all
behaved as designed under real and injected faults. Weak / to design properly before production: (1) timeouts must
use awake time; (2) the job must hold a system-required power request; (3) supervision must survive the UI/session
(OS-level ownership); (4) process identification by spawned PID, not command-line text; (5) interruptions should not
consume retry attempts; (6) a larger timeout factor for 5 s clips.

## 29. Identity Consistency Analysis

Identity is determined by the keyframe: FastWan image-to-video preserves the first frame and holds the face through
3–5 s of motion, softening during strong expressions. Reference-image editing (klein) carries a fixed face/costume
across 50 scenes; text alone (Z-Image) does not. Costs: pose diversity drops (reference-pose bias) and the video
model raises saturation/contrast relative to keyframes.

## 30. Known Limitations

- Energetic dance, leaps, fast motion and prompted camera moves are not reliable (§14).
- Pose collapse toward the reference stance in ~4 of 20 checked shots.
- Face softens/drifts in close-ups with strong expressions; first frame can differ in brightness from the rest.
- Single performer only; group choreography (as in the reference videos) not tested.
- System RAM at the OS floor during every clip; desktop GPU usage reduces headroom.
- 5-second clips have high time variance (one 2.2× outlier); 10-second clips are not feasible (Phase 29).
- The user has not yet given a quality verdict on Phase 29 or Phase 30 videos.

## 31. Rejected Approaches

Text-only identity (Z-Image) — measured 2/5. Independently generated reference images — inconsistent (two faces,
two braids). Long-lived inference worker — Phase 29 hang, replaced by process-per-shot. Detached child runner
launched from the interactive session — killed with the session. Name-based orphan matching — killed unrelated
processes.

## 32. Rejected OSS Models / Licenses

FLUX.2-dev (FLUX non-commercial); UNO and DreamO (built on FLUX.1-dev, non-commercial base); InstantID, PuLID,
IP-Adapter-FaceID, Stand-In (insightface antelopev2 non-commercial models); InfiniteYou (CC-BY-NC-4.0);
Qwen-Image-Edit-2509/2511, OmniGen2, Phantom (licence OK, too large for disk/RAM); Z-Image-Edit (not released);
Lynx (not accessible) — none was used.

## 33. Production Readiness Assessment

| Requirement | Evidence | Status |
|---|---|---|
| Identity | 50 shots at 4/5 (keyframes), clips 3.5–4/5 | **met** |
| Motion | 3.1/5; energetic dance not usable | **not met for "dance"; met for graceful performance** |
| Reliability | 50/50 clips, failure injection exact, 0 hangs | **met (lab)** |
| Resumability | 4 resume scenarios incl. orphaned worker | **met (lab)** |
| Resource control | no leak; peak RAM at OS floor; sleep/timeout/desktop-contention issues | **partly met** |
| Licence safety | all components 🟢 Apache/MIT/BSD/LGPL | **met** |
| User quality verdict | not given | **missing** |

**Production implementation: NOT APPROVED.**

## 34. Phase 30 Quality Gate

**B. CONDITIONAL PASS** — identity and worker reliability pass with evidence at 50 shots; motion capability, power/
supervisor behaviour, peak memory pressure and the absent user verdict are documented limitations.

## 35. Recommendation

Keep the composition that worked: **FLUX.2-klein-4B reference-edit keyframes → FastWan2.2-TI2V-5B clips → approved
FFmpeg montage**, executed by a **process-per-shot, checkpointed, resumable worker** with ACE-Step stopped. Position
the product honestly as "AI performance music video" (graceful performance, scenery, close-ups), not "dance video".
Do not build production until the user has judged the actual videos and the motion vocabulary is pinned down.

Architecture (recommended, evidence-backed, not implemented):

```
Tunora Song (Version) → Song analysis (ACE-Step BPM, Beat This! downbeats, TimedLyrics sections)
  → AI Video Plan → Character reference set (2 consistent images) → Shot plan (validated motion vocabulary)
  → Resumable Video Job (SQLite rows per shot: status, attempts, seed, prompt, output key, metrics)
  → OS-level supervisor (survives UI/session; holds ES_SYSTEM_REQUIRED; awake-time timeouts; spawned-PID tracking)
       → per shot: child process (klein keyframe) → validate → child process (FastWan clip) → validate → persist
  → stop/restart ACE-Step around the job → assembly with approved FFmpeg → VideoOutputProfile 9:16 / 16:9
```

## 36. Recommended Phase 31

**Phase 31 — AI Video User Review & Motion Vocabulary (lab).** Bounded: (1) the user scores the Phase 29 and Phase 30
montages and the 50-shot identity sheets; (2) build a validated motion vocabulary — measure, per action phrase, how
often FastWan performs it (≥ 5 seeds each) and keep only phrases with ≥ 80 % success; (3) only if the user requires
energetic dance, run a time-boxed licence-checked spike on one pose/motion-control option (e.g. Wan VACE pose
control, Apache-2.0) and measure fit on this GPU. Output: go/no-go for a production slice (30-second 9:16 AI Music
Video Preview) with the architecture in §35.

## 37. What MUST NOT Be Built Yet

Production AI-video API, database tables, UI, worker, queue or supervisor; a CharacterBible/identity service; any
custom identity, motion, pose or video model; LoRA training pipelines; ComfyUI integration; cloud GPU, Redis, Celery,
Kafka, Kubernetes or microservices; 3- or 5-minute generation as a product promise; any "dance video" claim.

---

## Required Final Decision

**Q1. Same performer across 20 independently generated shots?** Yes — 20/20 keyframes at identity 4/5 (klein
reference-edit); clips hold it.
**Q2. Across 30 shots?** Yes — 30/30 at 4/5.
**Q3. Across 50 shots?** Yes at keyframe level — 50/50 at 4/5; in clips 3.5–4/5. Where it weakens: close-ups with
strong expressions (face softens) and pose diversity (reference-stance repetition), not identity collapse.
**Q4. Best technique?** FLUX.2-klein-4B multi-reference editing from a self-consistent 2-image reference set.
**Q5. Rejected and why?** Text-only Z-Image (2/5); FLUX.2-dev, UNO, DreamO (non-commercial base); InstantID, PuLID,
IP-Adapter-FaceID, Stand-In (non-commercial face models); InfiniteYou (CC-BY-NC); Qwen-Image-Edit, OmniGen2, Phantom
(too large for this machine); Z-Image-Edit (unreleased); Lynx (inaccessible).
**Q6. Can the RTX 5060 Ti 16 GB sustain long-running generation?** Yes — 50 consecutive real clips, peak 16.0 GB each,
full recovery every time, flat throughput; with ACE-Step stopped and shots ≤ 5 s.
**Q7. Is system RAM a hard production blocker?** No, but it is the tightest resource: available RAM sits at the ~0.93 GB
OS floor during every clip (0.01 GB once) with no leak; other heavy apps must be closed; 64 GB would add margin.
**Q8. Does VRAM recover after every shot?** Yes — 51/51 attempts, median 0.1 s, max 30.2 s; no accumulation.
**Q9. Can a failed/hung shot be isolated?** Yes — injected exception, crash, hang (model resident), missing, invalid
and corrupt outputs each failed or retried alone; neighbours unaffected.
**Q10. Can the workload resume after controller restart?** Yes — planned stop, uncontrolled death, orphaned worker and
next-day restart all resumed without regenerating completed shots.
**Q11. Can ACE-Step reliably recover after AI-video generation?** Yes — after 50 clips: ready 27.6 s, generation
succeeded, VRAM released in 9.1 s.
**Q12. Measured average generation time per second of video?** ≈ 85 GPU-seconds per finished second (265 s per
3.12 s shot incl. keyframe and process start); 30 s ≈ 44 min.
**Q13. Measured failure rate per shot?** Real workloads: 0 unrecovered of 50 clips; 1/51 clip attempts timed out
(caused by system sleep); 0/62 keyframes and 0/6 baseline shots failed.
**Q14. Memory trajectory over 20/30/50 shots?** Flat: worker RSS slope +0.003 GB/shot; post-shot available RAM
22.2–24.1 GB (≤20), 18.8–24.1 (≤30), 18.1–24.1 (≤50) with within-run slopes ≈ 0; post-shot VRAM 381–1,656 MiB with
no monotonic growth.
**Q15. Realistic 3-minute estimate?** EXTRAPOLATED ≈ 4.3 h (≈ 4.7 h with allowance), ~116 worker processes, overnight
with the PC awake and ACE-Step stopped.
**Q16. Realistic 5-minute estimate?** EXTRAPOLATED ≈ 7.1 h (≈ 7.9 h), ~194 worker processes — not practical as a
normal user flow.
**Q17. Ready for production AI Music Video?** No.
**Q18. Missing evidence:** the user's quality verdict; a validated motion vocabulary (or a licence-safe motion-control
option) for the performance style Tunora will promise; a supervisor design that survives session loss and sleep with
awake-time timeouts (lab evidence shows both failure modes).
**Q19. Phase 31?** AI Video User Review & Motion Vocabulary (lab) — §36.
**Q20. Do NOT build yet:** §37.
