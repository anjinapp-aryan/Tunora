# Phase 29 — AI Video Feasibility Lab (real RTX 5060 Ti validation)

Lab phase. **No Tunora production code, dependency, schema, API, UI, renderer or storage was changed.** All
experiments ran in an isolated lab at `I:\Tunora-validation\ai-video-feasibility\` (own venv, own model caches).
Small reproducibility files (scripts, lab README, JSON metadata — no media, no weights) are copied into
`docs/validation/phase-29-ai-video/`. Input audit: `docs/AI-MUSIC-VIDEO-OSS-FEASIBILITY-AUDIT.md` (commit `60f9ede`).

Dates: 2026-10-03 (environment, song) and 2026-10-04 (all GPU runs). Every number in this document was
**measured on this machine** unless explicitly labelled EXTRAPOLATED, UNVERIFIED, NOT RUN or BLOCKED.

Human-judgement caveat: visual quality statements below come from inspecting extracted frames
(first/middle/last frame of every clip, contact sheets, full-resolution detail frames). Motion feel and
"does it feel like a music video" require watching the files; the user should view
`I:\Tunora-validation\ai-video-feasibility\outputs\final\e8_montage_9x16.mp4` and `e9_montage_16x9.mp4`.

---

## 1. Executive Summary

- **Yes, a real 31-second AI music video was generated locally from a real Tunora song, in both 9:16 and
  16:9**, on the RTX 5060 Ti 16 GB with 31.6 GB RAM, using only Apache-2.0/MIT/ISC components and Tunora's own
  LGPL FFmpeg. 10 beat-aligned shots, 10/10 clips valid, final MP4s 1080×1920 and 1920×1080, 31.2 s, exact audio.
- **The audit's primary model (Wan2.2 TI2V-5B at its official 50 steps) is not practical here**: first attempt
  crashed (access violation during CPU offload, system RAM exhausted); after two documented memory fixes a 2-second
  clip took **19.7–33.9 min**.
- **What made it work: FastWan2.2-TI2V-5B (FastVideo, Apache-2.0)**, a DMD-distilled TI2V-5B transformer run for
  3 steps without CFG, plus precomputed prompt embeddings and VAE tiling. A 3.2-second shot takes **~3.1–3.7 min**;
  a whole 31-second montage takes **~39–42 min of GPU time** (≈ 77 s of compute per second of video).
- **Limits found:** a single 10-second clip does not fit (one DMD step took 646 s; timed out twice); one
  long-lived worker **hung** after clip 5 (fixed operationally by one process per clip + timeout: 15/15 clean);
  costume/style consistency is strong but **faces vary between shots**; energetic actions (e.g. "leap") are often
  not performed.
- **GPU hand-off with ACE-Step works**, verified in both directions: stop → VRAM released in 8.5–9.7 s; restart →
  ready in ~30 s and generating again.
- **Wan-Dancer: BLOCKED** before execution (weights do not fit the remaining disk; global script hard-asserts 8 GPUs).
- Decision: short clips **PASS**; 30-s montage **CONDITIONAL** (technically complete, quality needs the user's
  viewing); RTX 5060 Ti **CONDITIONAL**; 3 minutes **CONDITIONAL** (overnight batch only, ~4–5 h extrapolated);
  5 minutes **FAIL** (not practical in this form).

## 2. Objective

Measure, on the actual development machine, whether Tunora can locally produce enough acceptable short AI clips
from a real Tunora song to assemble a convincing ~30-second AI music video (Phase 29 brief), and measure the costs
needed to judge 3- and 5-minute videos.

## 3. Hardware Environment (measured, E0)

| Item | Value | How measured |
|---|---|---|
| GPU | NVIDIA GeForce RTX 5060 Ti, 16,311 MiB, compute capability 12.0 (sm_120), power limit 180 W | `nvidia-smi` |
| Driver / CUDA | 591.86 / CUDA 12.8 runtime (torch build) | `nvidia-smi`, `torch.version.cuda` |
| Idle VRAM used by desktop | 572–1,632 MiB (varied with open apps) | `nvidia-smi` before runs |
| CPU | Intel Core Ultra 7 265K, 20 cores | `Win32_Processor` |
| RAM | 31.64 GB total; 12.6–23.4 GB available at run starts (other desktop apps) | `Win32_OperatingSystem` |
| Page file | 17 GB on C: | `Win32_PageFileUsage` |
| OS | Windows 11 Pro 10.0.26200 | `Win32_OperatingSystem` |
| Disk | I: 68.1 GB free at start → **11 GB free at end** (lab uses ~58 GB); D: 20.2, C: 19.1 | `df` / `Get-PSDrive` |

## 4. Software Environment

- Python 3.12.10 (uv 0.12.15), isolated venv `I:\Tunora-validation\ai-video-feasibility\.venv`.
- `torch 2.7.1+cu128`, `torchvision 0.22.1+cu128`, `torchaudio 2.7.1+cu128` — the same torch build ACE-Step uses on
  this GPU (sm_120 kernels present).
- `diffusers 0.40.0` (has `ZImagePipeline`, `WanPipeline`, `WanImageToVideoPipeline`), `transformers 5.18.0`,
  `accelerate 1.15.0`, `librosa`, `soundfile`, `psutil`, `beat_this 1.1.0` (git `CPJKU/beat_this@b95c8ab`).
- Encoding: Tunora's approved FFmpeg `n9.0.2` (`--enable-version3`, `--enable-libopenh264`, `--enable-libass`, no
  `--enable-gpl`/`--enable-nonfree`) at `I:\Tunora\backend\tools\ffmpeg\bin`; it also has `blackdetect`,
  `freezedetect`, `xfade`, `concat` (closes an audit open item). `diffusers.export_to_video`/imageio/moviepy were
  not used for any output.
- Caches confined to the lab (`HF_HOME`, `TORCH_HOME`). Reproduction: `docs/validation/phase-29-ai-video/README.md`.

## 5. Model Versions

| Model | Repo / revision | Format used | Disk |
|---|---|---|---|
| Z-Image-Turbo 6B | `Tongyi-MAI/Z-Image-Turbo@f332072aa78be7aecdf3ee76d5c247082da564a6` | HF repo ships the transformer in **fp32 (24.6 GB)**; re-saved locally as bf16 | 20.5 GB (bf16 copy) |
| Wan2.2 TI2V-5B | `Wan-AI/Wan2.2-TI2V-5B-Diffusers@b8fff7315c768468a5333511427288870b2e9635` | text encoder umt5-xxl (bf16, 11.4 GB), VAE (fp32, 2.8 GB), transformer re-saved bf16 (repo ships fp32 20 GB) | 9.4 + 14.2 GB |
| FastWan2.2-TI2V-5B (DMD) | `FastVideo/FastWan2.2-TI2V-5B-FullAttn-Diffusers@3e187042a324f6f5fb68fd22110a78725253de8f` | transformer folder only (bf16, 10.0 GB); text encoder/VAE from Wan2.2 | 10.0 GB |
| Beat This! | checkpoint `final0` (JKU cloud), sha256 `8c328b45…8eb8331` | — | 81 MB |
| Wan-Dancer | code `Wan-Video/Wan-Dancer@e6c87a94ec733230dac15b924c015f6e6501e618` | code only (weights not downloaded) | 91 MB |

Download facts: Z-Image 32.9 GB took ~2 sessions (HF anonymous throughput fell from ~33 MB/s to ~5 MB/s);
Wan2.2 34.2 GB took 52 min; FastWan transformer 10 GB ~12 min.

## 6. License Verification (checked 2026-10-04)

| Component | Code | Weights | Commercial | Source | Class |
|---|---|---|---|---|---|
| Z-Image-Turbo | Apache-2.0 (Diffusers pipeline) | Apache-2.0 (HF card) | allowed | huggingface.co/Tongyi-MAI/Z-Image-Turbo | 🟢 (training data undisclosed) |
| Wan2.2 TI2V-5B (Diffusers) | Apache-2.0 | Apache-2.0 (HF card) | allowed | huggingface.co/Wan-AI/Wan2.2-TI2V-5B-Diffusers | 🟢 (training data undisclosed) |
| FastWan2.2-TI2V-5B-FullAttn | FastVideo Apache-2.0 | Apache-2.0 (HF card); derivative of Wan2.2 (Apache-2.0); "data-free" DMD distillation per card | allowed | huggingface.co/FastVideo/FastWan2.2-TI2V-5B-FullAttn-Diffusers | 🟢 |
| Wan2.2-TI2V-5B-Turbo (quanhaol / yetter-ai) | — | **no license on the card** | unknown | HF API `cardData.license = null` | **UNKNOWN — not used, do not adopt** |
| Beat This! | MIT | MIT ("code and the published model weights are released under the MIT license") | allowed | github.com/CPJKU/beat_this | 🟢 |
| librosa / soundfile / psutil | ISC / BSD-3 / BSD-3 | — | allowed | PyPI | 🟢 |
| diffusers / transformers / accelerate | Apache-2.0 | — | allowed | GitHub | 🟢 |
| torch / torchvision / torchaudio | BSD-3 | — | allowed | pytorch.org | 🟢 |
| FFmpeg (Tunora approved build) | LGPL-3.0 (`--enable-version3`), libopenh264 BSD-2 | — | allowed | build configuration line | 🟢 |
| Wan-Dancer | Apache-2.0 | Apache-2.0 | allowed (training data undisclosed) | audit §7 | 🟢 (not run) |

No non-commercial component was used in any recommended path.

## 7. E0 Hardware Baseline

Recorded in §3. Additional facts: ACE-Step was not running at start (ports 8001/8000/3000 free); GPU free VRAM
14,469 MiB; `torch.cuda.get_device_capability(0) == (12, 0)`. **PASS.**

## 8. E1 Z-Image Results

Original fictional performer "Asha" (teal-and-gold lehenga, saffron dupatta, jasmine braid, red bindi, gold
jhumkas and bangles), defined once in `metadata/character.json`. Official settings: bf16, 9 steps, guidance 0,
documented `enable_model_cpu_offload()`. 23 images total (3 reference + 10 portrait + 10 landscape keyframes).

| Measure | Value |
|---|---|
| Load from HF fp32 repo | 33.0 s; process RSS **20.2 GB**; system available RAM fell to **0.01 GB** |
| Re-save as bf16 | 156.7 s |
| Load from local bf16 copy | 7.7–8.0 s (RSS 8.2 GB, grows to ~21 GB on first generation) |
| Generation, 704×1280 / 1280×704 | **23.5–36.2 s per image, mean 25.8 s** (first image of a process slowest) |
| Peak VRAM (device) | 14,670–14,877 MiB; torch 12.3 GB allocated, 13.1 GB reserved |
| Peak process RAM | 20.0–21.1 GB; system available RAM 0.6–3.4 GB during generation |
| Output | 704×1280 PNG, 0.99–1.21 MB each |
| Success | 23/23 |

Quality (frame inspection): anatomy correct, hands plausible (fingers resolved in mudras and raised hands), faces
clean, costume rendered exactly as described, compositions full-body and cinematic. **PASS.**

## 9. E2 Wan2.2 Results

Image-to-video from E1 reference 2 (rooftop), 704×1280, prompt and seed fixed, official 50 steps, guidance 5.0,
fp32 VAE, `enable_model_cpu_offload()`.

| Run | Frames / seconds | Result |
|---|---|---|
| E2 first attempt (also E2 rerun with `-X faulthandler`) | 49 / 2.04 s | **FAILED — process crash** (exit 139 / "Windows fatal exception: access violation") at denoise step 0. Native stack: `accelerate.hooks.offload → transformers .to()` while evicting the text encoder to CPU. Process RSS 22.5–23.2 GB, system available RAM **0.01–0.17 GB**. |
| 5 s (121 frames), 10 s (241 frames) with base model | — | NOT RUN with the base model (the 2 s case already failed / took 20–34 min, see E3). |
| 10 s (241 frames) with FastWan (best configuration) | 241 / 10.04 s | **FAILED — timeout.** One DMD step took **645.8 s** (vs ~60 s/step at 121 frames); killed at 900 s, retried, killed again (rc=124 twice). |

Base model load time: 27.5–32.7 s (from fp32 shards); 12.2–13.2 s from bf16 copies.

## 10. E3 Memory Optimization Results

One change at a time, same image/prompt/seed, 49 frames (2.04 s) at 704×1280.

| Config | Total | Denoise | Decode (derived) | Peak device VRAM | torch reserved | Peak RSS | Min avail RAM | Result |
|---|---|---|---|---|---|---|---|---|
| E2 baseline: base 50 steps, offload | crash | — | — | — | — | 22.5 GB | 0.01 GB | FAIL |
| E3a: + precomputed prompt embeddings (text encoder on GPU once, then dropped) | **2,034.6 s (33.9 min)** | 703 s (14.1 s/step) | ~1,330 s | 16,015 MiB | **29,872 MiB** (spill to shared memory) | 23.4 GB | 1.33 GB | works, impractical |
| E3b: + VAE tiling | **1,184.9 s (19.7 min)** | 1,089 s (21.8 s/step — slower run) | ~95 s | 15,970 MiB | 15,642 MiB | 15.0 GB | 8.22 GB | works, impractical |
| E3c: + FastWan DMD transformer, 3 steps, no CFG | **128.6 s (2.1 min)** | 30 s (~10 s/step) | ~97 s | 15,937 MiB | 15,650 MiB | 15.3 GB | 8.81 GB | **practical** |
| E3c, 121 frames (5.04 s) | **427.2 s (7.1 min)** | 180 s (60 s/step) | ~245 s | 15,927 MiB | 20,106 MiB | 17.2 GB | 6.92 GB | practical |
| E3c, 241 frames (10.04 s) | >900 s ×2 | 645.8 s for step 1 of 3 | — | — | — | — | — | FAIL (timeout) |

Findings:
- Precomputing embeddings removed the crash: process RSS dropped from ~23 GB to ~7.8 GB after the 11.4 GB
  text encoder was released.
- VAE tiling removed the 22-minute decode (torch reservation 29.9 GB → 15.6 GB).
- The 50-step base model stays impractical (14–22 s per step, 100 transformer passes with CFG). FastWan's
  3 passes made the difference: **9–16× faster** for the same clip.
- Run-to-run variance on the same configuration was large (14.1 vs 21.8 s/step), consistent with memory
  pressure / shared-memory spill.
- FastWan was run through Diffusers' own `FlowMatchEulerDiscreteScheduler(stochastic_sampling=True)` (its step is
  exactly the DMD x0-predict-and-re-noise update) pinned to the model card's DMD timesteps `1000,757,522`. This is
  configuration of existing components, but **it is not FastVideo's own runner**; FastVideo itself was not
  installed (it pins `torch==2.12.0`, gradio, wandb, moviepy and does not confirm Blackwell support).

## 11. E4 Character Consistency

20 keyframes + 20 clips of one character from one fixed text description (no reference conditioning, no identity
adapter, no LoRA).

| Aspect | Across shots | Inside a clip |
|---|---|---|
| Costume (lehenga, dupatta, choli, gold border) | consistent in all 20 shots | stable |
| Hairstyle (single braid with jasmine) | consistent | stable; braid follows motion |
| Jewellery (bindi, jhumkas, bangles) | consistent | stable |
| Body appearance | consistent | stable |
| Face | **same type, not the same person** — face shape and features vary shot to shot | stable within a clip, including after a 360° turn |
| Palette / visual style | consistent | stable |
| Dupatta colour | mustard-yellow rather than the prompted saffron in most shots; slight shift between shots | stable |

**CONDITIONAL**: sufficient for an ensemble/style-level music video (which matches the reference videos analysed in
the audit), **not** sufficient for a recognisable lead performer across shots. Next fix should reuse an Apache-2.0
reference-image approach (e.g. image-edit models to place the same reference face in new scenes, or I2V from
edits of one master keyframe) — not a custom identity model.

## 12. E5 Motion / Dance Quality

| Clip | Prompted action | Observed (frames) | Result |
|---|---|---|---|
| E3c 5 s spin (rooftop) | spin, lehenga flare | full continuous 360° spin, skirt and dupatta physically plausible, face consistent after turn | PASS |
| shot 1 (sway, open eyes) | gentle sway | subtle sway, hand movement | PASS |
| shot 2 (walk forward) | walk with trailing dupatta | walks toward camera, natural gait | PASS |
| shot 3 (close-up turn) | head turn + smile, close-up | turn + smile happen; framing stayed **medium**, not close-up | CONDITIONAL |
| shot 4 (classical steps, orbit) | slow steps, arm movement | arm gestures, small steps; camera orbit weak | CONDITIONAL |
| shot 5 (arms up) | raise arms | both arms rise, bangles visible | PASS |
| shot 6 (spin, low angle) | energetic spin | spin with flaring skirt | PASS |
| shot 7 (rhythmic footwork) | energetic footwork | arm choreography; footwork not visible; **unprompted crowd** appeared in background | CONDITIONAL |
| shot 8 (arms open, petals) | lean back, petals | arms open, falling petals rendered | PASS |
| shot 9 (leap) | leap and land | **no leap** — sways in place | FAIL (action) |
| shot 10 (final pose, fireworks) | spin + triumphant pose | arm-raised pose, fireworks rendered | PASS |

No broken limbs, extra fingers, melted faces or background collapse were seen in the sampled frames (first/middle/
last frame of every clip, plus full-resolution frames of shots 7 and 9). Hands are slightly soft at 704×1280.
Motion amplitude is modest; graceful/slow movements succeed, athletic actions often do not.
**CONDITIONAL** (user viewing of the montages still required).

## 13. E6 Real Tunora Song

Copied read-only from the Tunora database/storage (no production data modified):

| Item | Value |
|---|---|
| Song / Version | "I Will Rise", `ver-53c1604d-ccc4-46ac-ae2c-2b172d6dc3c1` |
| Format | MP3, 48 kHz, stereo, 128 kb/s, **60.0 s** |
| Prompt | uplifting cinematic pop ballad, female lead vocal |
| BPM | ACE-Step metadata **77**; librosa 77.05; Beat This! 76.9 (median inter-beat interval) |
| Key / meter | E♭ major, 4/4 (ACE-Step metadata) |
| Lyrics | available (Verse / Pre-Chorus / Chorus tags) |
| Timed lyrics | **available** — reused from a completed Tunora lyric MusicVideo of this Version (stable-ts): 11 lines aligned, 21 unaligned (the 60 s audio does not reach the later lyrics); first vocal 15.15 s, chorus "I will rise" 37.19 s |
| Beat analysis cost | Beat This! 1.1 s on CPU (beats from 0.90 s, downbeats every ~3.12 s); librosa 26.4 s and missed the 0–14 s intro |

## 14. E7 Shot Planning

`scripts/e7_plan.py` (lab only): deterministic, no LLM. One shot per 4/4 bar using Beat This! downbeats; section
boundary snapped to the downbeat nearest the TimedLyrics chorus start (38.30 s); verse/chorus action templates;
frames rounded up to Wan's 4k+1 rule (77 frames = 3.21 s ≥ 3.12 s bar).

| Shot | Time (s) | Section | Camera | Action |
|---|---|---|---|---|
| 01 | 22.72–25.84 | verse | slow push-in | sways, opens eyes, mudra |
| 02 | 25.84–28.96 | verse | slow tracking | walks forward, dupatta trailing |
| 03 | 28.96–32.08 | verse | static close-up | turns to camera, smiles |
| 04 | 32.08–35.20 | verse | slow orbit | slow classical steps |
| 05 | 35.20–38.30 | verse | slow tilt up | raises both arms |
| 06 | 38.30–41.42 | chorus | wide, low angle | energetic spin |
| 07 | 41.42–44.54 | chorus | handheld follow | rhythmic footwork |
| 08 | 44.54–47.66 | chorus | slow push-in | arms open, petals |
| 09 | 47.66–50.78 | chorus | wide | leap |
| 10 | 50.78–53.90 | chorus | slow pull-back crane | final pose, fireworks |

Reuse: tempo (ACE-Step metadata), beats/downbeats (Beat This!), sections and line timing (Tunora TimedLyrics). No
custom audio analysis. **PASS.**

## 15. E8 30-Second Montage (9:16) — primary gate

Pipeline: real song → plan → 10 Z-Image keyframes (704×1280) → 10 FastWan I2V clips (77 frames, 24 fps) → validation
(ffprobe frames/duration, one-pass decode, `blackdetect`, `freezedetect`) → beat-cut montage with the approved
FFmpeg (trim to bar, 30 fps, scale-to-cover to 1080×1920, OpenH264 8 Mb/s, AAC 192 kb/s 48 kHz, song window
22.72–53.90 s).

| Measure | Value |
|---|---|
| Clips planned / generated valid | 10 / **10** (0 black segments, 0 freeze segments, all 77 frames) |
| Failed attempts | **1 hang** (see below), 0 crashes, 0 invalid clips |
| Quality retries | 0 performed (shot 9's missing leap would justify one in a product) |
| Keyframes | 10 × 23.6–36.2 s = **4.4 min** (+8 s load) |
| Clip time, long-lived process (clips 1–5) | 182.1–206.2 s each (mean 187 s) |
| Clip time, one process per clip incl. load+encode (clips 6–10) | **218–223 s each** |
| Total GPU time for the 31.2 s video (excl. the hang) | **≈ 38.9 min** (keyframes 4.4 + clips 34.2 + assembly 0.16) |
| Assembly | 9.7 s |
| Peak device VRAM / torch reserved | 15,912–16,011 MiB / 17,378–17,446 MiB (above 16 GB: shared-memory spill) |
| Peak process RAM / min system available | 14.4–16.4 GB / 6.2–8.2 GB |
| Final | **1080×1920, 30 fps, 936 frames, 31.20 s, H.264 + AAC 48 kHz 31.18 s, 30.6 MB** |

**The hang:** in the first, long-lived worker process, clip 6 finished its 3 denoise steps and then never
returned — GPU 0 %, 8 W, 7.2 GB held, process 20.7 GB private / **0.37 GB resident (paged out)**, no FFmpeg child,
idle for ~2 h until killed. No exception or crash record. Root cause UNVERIFIED (memory-pressure stall in the
offload/decode path is the leading hypothesis). Operational fix verified: `run_clips.sh` runs **one process per clip
with a 900 s timeout and one retry, skipping finished clips** — it resumed at clip 6 and then produced 15/15 clips
(5 portrait + 10 landscape) without a hang. Per-process overhead ≈ 30 s/clip (~14 %).

**Gate D: CONDITIONAL** — technically complete and valid; "convincing" requires the user to watch it.

## 16. E9 16:9

Same plan, same pipeline, landscape keyframes 1280×704 (Z-Image) → FastWan 1280×704 clips → 1920×1080.

| Measure | Value |
|---|---|
| Clips valid | 10 / 10, no retries, no hangs |
| Clip wall time (per-process) | 219–226 s, total 37.0 min |
| Keyframes | 23.5–35.0 s each, 4.4 min |
| Total GPU time | **≈ 41.6 min** |
| Final | 1920×1080, 30 fps, 936 frames, 31.20 s, audio 31.18 s, 30.7 MB, assembly 8.8 s |

Composition (frame inspection): native landscape framing with the dancer centred and the environment (pool,
colonnade, field, fireworks) filling the width — no cropping artefacts; one clip ends with the dupatta crossing her
face mid-spin. Same model pipeline, only sizes differ. **PASS.**

## 17. E10 3/5-Minute Feasibility

MEASURED (E8/E9): ~3.2 s shot ≈ 3.6–3.7 min wall per clip (per-process) + 0.43 min keyframe ⇒ **≈ 4.1 min of GPU
time per shot, ≈ 77 s per second of video**; ~6 MB of intermediates per shot.

EXTRAPOLATED (same song tempo class, one shot per ~3.1 s bar, +20 % retry/regeneration allowance, ACE-Step stopped
for the whole job; not benchmarks):

| Song | Shots | GPU time (no retries) | With +20 % retries | Intermediates | Final MP4 (HD) |
|---|---|---|---|---|---|
| 30 s | 10 | **39–42 min (measured)** | — | 59 MB (measured) | 31 MB (measured) |
| 60 s | ~19 | ~1.3 h | ~1.6 h | ~115 MB | ~60 MB |
| 120 s | ~39 | ~2.7 h | ~3.2 h | ~235 MB | ~120 MB |
| 180 s | ~58 | ~4.0 h | **~4.8 h** | ~350 MB | ~175 MB |
| 300 s | ~97 | ~6.6 h | **~8.0 h** | ~580 MB | ~295 MB |

RAM: unchanged per clip (process-per-clip). VRAM: unchanged per clip. Hang risk: 1 hang in 23 short FastWan clip
attempts overall — 1 of 8 in long-lived workers, 0 of 15 in process-per-clip mode (sample too small to bound the
rate) — a 5-minute job has ~100 clips, so the watchdog is mandatory. Fewer, longer shots do not help: 5 s clips cost 7.1 min (vs 3.7 min for 3.2 s) and 10 s clips fail.

## 18. Wan-Dancer Result

**BLOCKED — not executed.** Minimal compatibility check only (code cloned at `e6c87a9`, 91 MB):
- Disk: its weights need ≥ 37 GB even in the Comfy-Org fp8 form (2 × 18.3 GB) plus umt5/CLIP/VAE; **I: had 11 GB
  free** after the primary path's models. Not downloadable without deleting the primary path.
- Code: `gen_video/gen_video_global.py:120 assert world_size == 8, "WORLD_SIZE must be 8"` — VERIFIED in the cloned
  code; running the global stage on one GPU requires modifying the script.
- First import attempt stopped at `ModuleNotFoundError: moviepy` (its output step uses moviepy/libx264, which Tunora
  would not use). Installing moviepy was aborted (see failure matrix); not retried, per the brief.
- Blocker classes: **disk (hard), multi-GPU assumption (code change needed), RAM (31.6 GB vs 14B offload), sm_120
  re-pin (documented in the audit)**.

## 19. GPU Hand-Off Result

`scripts/handoff_ace.py` starts ACE-Step with the same command as `tunora-services.ps1` (port 8001,
`ACESTEP_CONFIG_PATH2=acestep-v15-base`), forces a model load with one 10 s generation, then stops it with Tunora's
own `stop-tunora.ps1`.

| Step | Before video work | After video work |
|---|---|---|
| VRAM before start | 1,572 MiB | 816 MiB |
| ACE-Step `/health` ready | 28.0 s | 29.7 s |
| First generation (10 s audio, includes model load) | 49.9 s, succeeded | 52.6 s, succeeded |
| VRAM loaded, idle | 11,209 MiB | 10,337 MiB |
| VRAM peak while ACE-Step ran | 14,546 MiB | 13,671 MiB |
| `stop-tunora.ps1` exit / process alive after | 0 / no | 0 / no |
| Stop → VRAM released | **9.7 s** → 1,632 MiB | **8.5 s** → 760 MiB |

Between the two: every video worker process exited and VRAM returned to the desktop baseline (e.g. 810 MiB after the
timed-out 10 s test, 1,215 MiB after killing the hung worker). **The lifecycle works**: ACE-Step stop → video
workers → workers exit → ACE-Step start. Video and ACE-Step cannot coexist (ACE-Step alone holds 10.3–11.2 GB once
loaded; the video workers peak at ~16 GB).

## 20. Performance Matrix

| Experiment | Model | Resolution | Duration | VRAM peak (device) | RAM peak (process) | Time | Disk (output) | Result |
|---|---|---|---|---|---|---|---|---|
| E0 baseline | — | — | — | — | — | — | — | PASS |
| E1 refs (3) | Z-Image-Turbo bf16 | 704×1280 | image | 14,681 MiB | 20.7 GB | 24.1–29.4 s/img | 1.0–1.2 MB/img | PASS |
| E1 keyframes (20) | Z-Image-Turbo bf16 | 704×1280, 1280×704 | image | 14,877 MiB | 21.1 GB | 23.5–36.2 s/img | 21.9 MB total | PASS |
| E2 base | Wan2.2 TI2V-5B, 50 steps | 704×1280 | 2.04 s | UNVERIFIED (crash) | 23.2 GB | crash at step 0 | 0 | FAIL |
| E3a | base + embeds | 704×1280 | 2.04 s | 16,015 MiB | 23.4 GB | 2,034.6 s | 3.1 MB | works / impractical |
| E3b | base + embeds + VAE tiling | 704×1280 | 2.04 s | 15,970 MiB | 15.0 GB | 1,184.9 s | 3.0 MB | works / impractical |
| E3c | FastWan 3-step | 704×1280 | 2.04 s | 15,937 MiB | 15.3 GB | 128.6 s | 3.0 MB | PASS |
| E3c | FastWan 3-step | 704×1280 | 5.04 s | 15,927 MiB | 17.2 GB | 427.2 s | 7.5 MB | PASS |
| E2 10 s | FastWan 3-step | 704×1280 | 10.04 s | UNVERIFIED | UNVERIFIED | >900 s ×2 (step 1 = 645.8 s) | 0 | FAIL |
| E8 clips (10) | FastWan 3-step | 704×1280 | 3.21 s each | 16,011 MiB | 16.4 GB | 182–223 s/clip | 48.0 MB | PASS |
| E8 montage | FFmpeg (approved) | 1080×1920 | 31.2 s | — | — | 9.7 s (total ≈ 38.9 min) | 30.6 MB | CONDITIONAL |
| E9 clips (10) | FastWan 3-step | 1280×704 | 3.21 s each | UNVERIFIED per clip (same config) | UNVERIFIED per clip | 219–226 s/clip | 48.0 MB | PASS |
| E9 montage | FFmpeg (approved) | 1920×1080 | 31.2 s | — | — | 8.8 s (total ≈ 41.6 min) | 30.7 MB | PASS |
| Wan-Dancer | Wan-Dancer-14B | — | — | — | — | — | — | BLOCKED |
| Hand-off | ACE-Step + stop script | — | — | 14,546 MiB | — | release 8.5–9.7 s | — | PASS |

(E9 per-clip VRAM/RAM were not captured separately because the per-process driver appends to one log; the
configuration is identical to E8 clips 6–10.)

## 21. Failure Matrix

| Experiment | Failure | Root cause | Recoverable | Workaround |
|---|---|---|---|---|
| E2 base | access violation (segfault) at denoise step 0 | system RAM exhausted (0.01–0.17 GB free) while accelerate's model offload moved the 11.4 GB text encoder back to CPU | yes | precompute prompt embeddings, drop the text encoder (E3a) |
| E3a | 22-minute VAE decode | fp32 VAE decode of 49×704×1280 needed 29.9 GB → Windows shared-memory spill | yes | VAE tiling (E3b) |
| E2/E3 base | 20–34 min per 2 s clip | 50 steps × CFG (≈100 transformer passes) on a 16 GB card | yes | DMD-distilled FastWan, 3 passes (E3c) |
| E2 10 s | timeout ×2 | 241-frame attention: one step 645.8 s, heavy spill | no (on this card) | keep shots ≤ 5 s |
| E8 clip 6 | hang ~2 h after denoise, process paged out | UNVERIFIED (memory-pressure stall) | yes | one process per clip + 900 s timeout + retry (15/15 clean afterwards) |
| Song analysis | Beat This! checkpoint load error | JKU host truncated the download (34 of 81 MB); corrupt partial file in torch hub cache | yes | resumable curl download, size check, sha256 recorded |
| Download | Z-Image download interrupted (session end); HF anonymous speed ~5 MB/s | network / anonymous rate limits | yes | resumed; budget hours for first-time model setup |
| Disk | I: fell to 1.6 GB free during conversions | model repos ship fp32 (Z-Image 32.9 GB, Wan 34.2 GB) | yes | convert to bf16, delete fp32 shards |
| Wan-Dancer | not runnable | disk, 8-GPU assert, RAM | not in this phase | — |
| Lab venv | Pillow partially uninstalled | installing moviepy for the Wan-Dancer check while a worker held Pillow's DLL (uv tried to replace Pillow) | yes | reinstalled `pillow==12.3.0`; moviepy never installed. Lesson: never change a venv that a running worker uses |
| Lab driver | resume driver found no jobs | relative paths after `cd` | yes | absolute paths |
| Quality | shot 9 "leap" not performed; shot 3 close-up rendered medium; shot 7 unprompted crowd | model prompt adherence for athletic actions/framing | partly | regenerate shot with new seed / simpler action |
| Quality | face differs between shots | text-only character definition | partly | reference-image based keyframes (next phase) |

## 22. Storage Analysis

Measured (bytes on disk):

| Item | Per 30 s project (9:16) |
|---|---|
| Keyframes (10 PNG) | 11.4 MB |
| Clips (10 × 77 frames, OpenH264 12 Mb/s) | 48.0 MB |
| Failed / retry clips | 0 MB (the hung clip left no file; timeouts left no file) |
| Temporary files | none persisted (FFmpeg piping, no frame dumps) |
| Final MP4 | 30.6 MB |
| **Total** | **≈ 90 MB** (final-only 31 MB) |

Fixed costs (measured): models 29 GB (Z-Image bf16 20.5 + Wan bf16 transformer 9.4) + HF cache 23 GB (umt5 11.4,
VAE 2.8, FastWan 10.0) + venv 6.1 GB ≈ **58 GB**. First-time download: ~77 GB (fp32 repos) before conversion.

Projects (EXTRAPOLATED from the per-shot measurement): 60 s ≈ 0.18 GB, 3 min ≈ 0.53 GB, 5 min ≈ 0.88 GB with
intermediates kept; final-only 0.06 / 0.18 / 0.30 GB. Disk for models, not per-video storage, is the binding
constraint on this machine (11 GB free on I: after the lab).

## 23. Quality Review

Scores are the reviewer's frame-based judgement (1–5); the user's viewing is pending.

| Output | Identity | Motion | Anatomy | Background | Composition | Overall | Result |
|---|---|---|---|---|---|---|---|
| E1 reference images | 4 | — | 5 | 5 | 5 | 5 | PASS |
| Portrait keyframes (10) | 3 (costume 5, face 3) | — | 5 | 5 | 4 | 4 | PASS |
| Landscape keyframes (10) | 3 | — | 5 | 5 | 5 | 4 | PASS |
| E3a base 2 s spin | 4 | 4 | 5 | 5 | 5 | 4 | PASS (too slow) |
| E3c FastWan 2 s spin | 4 | 4 | 4 | 4 | 5 | 4 | PASS |
| E3c FastWan 5 s spin | 4 | 4 | 4 | 4 | 5 | 4 | PASS |
| E8 clips (10) | 3 | 3 | 4 | 4 | 4 | 3.5 | CONDITIONAL |
| E9 clips (10) | 3 | 3 | 4 | 4 | 5 | 3.5 | CONDITIONAL |
| E8 montage 9:16 | 3 | 3 | 4 | 4 | 4 | 3.5 | CONDITIONAL (user to view) |
| E9 montage 16:9 | 3 | 3 | 4 | 4 | 5 | 3.5 | CONDITIONAL (user to view) |
| E2 10 s | — | — | — | — | — | — | FAIL (not produced) |

## 24. 9:16 Assessment

Native 704×1280 generation (both Z-Image and FastWan) → `vertical_hd` 1080×1920 by scale-to-cover (0.55 → 0.5625
aspect; ~2 % crop). Full-body dancers fit well in portrait. **PASS.**

## 25. 16:9 Assessment

Native 1280×704 → `landscape_hd` 1920×1080. Same models, same plan, same scripts; only sizes change. Composition
is good and uses the width for environment. Cost identical to 9:16 (219–226 s per clip). Both orientations of the
same plan cost two full generations. **PASS.**

## 26. 3-Minute Assessment

~58 shots, ~4.0 h of exclusive GPU time without retries, ~4.8 h with a 20 % allowance (EXTRAPOLATED from measured
per-shot cost); ACE-Step must stay stopped for the whole job; ~0.5 GB disk per video. Feasible only as an
**overnight, resumable batch job** with a per-clip watchdog; not interactive. **CONDITIONAL.**

## 27. 5-Minute Assessment

~97 shots, ~6.6–8.0 h exclusive GPU time (EXTRAPOLATED), ~100 worker processes, hang rate not yet bounded
(1 of 8 in long-lived workers, 0 of 15 per-process), character drift multiplied across ~100 shots. Technically
reachable, but by the brief's own rule it is **NOT PRACTICAL** in the current form. **FAIL.**

## 28. Risks

| Risk | Probability | Impact | Evidence | Mitigation |
|---|---|---|---|---|
| Worker hang | Medium | High | 1 of 8 long-lived attempts; 0 of 15 per-process | process per clip + timeout + retry (verified) |
| RAM exhaustion | High without fixes | High | crash at 0.01 GB free; Z-Image dips to 0.6 GB | precomputed embeddings, bf16 copies, one model per process, close other apps; 64 GB would add headroom |
| VRAM spill / long clips | High above 5 s | High | 241 frames: 646 s/step | shots ≤ 5 s |
| Generation time | Certain | High | 77 s compute per video-second | overnight batch, progress UX, keep 30–60 s as the interactive tier |
| Face identity drift | High | Medium | E4 | reference-image keyframes (next phase) |
| Prompt adherence for athletic moves | High | Medium | shot 9, 7, 3 | simpler action vocabulary, per-shot regenerate |
| Disk for models | High | High | 11 GB free after lab; fp32 repos | bf16 conversion at install, delete lab after Phase 30 |
| Download time / HF rate limits | Medium | Medium | 5 MB/s anonymous | one-time setup step with resume |
| DMD sampler parity | Medium | Medium | Diffusers-configured, not FastVideo runner | compare against FastVideo once on Linux/WSL or accept as validated-by-output |
| Distilled model license | Low | High | FastWan Apache-2.0; Turbo variants unlicensed | use only FastWan; re-check on update |
| Windows compatibility | Low (for this path) | Medium | all runs native Windows, no WSL | — |
| Wan-Dancer | — | Low | blocked | keep as research item only |
| Venv fragility | Medium | Medium | Pillow incident | never modify a running worker's environment |

## 29. Lessons Learned

1. Official "minimum VRAM" text was not the binding limit — **system RAM was** (crash at 0.01 GB free).
2. Step-distilled models, not quantization or offload tricks, turned a 20–34-minute clip into a 2-minute clip.
3. VAE decode can cost more than denoising; tiling is mandatory at 704×1280.
4. Short shots are both what the reference videos use and what this GPU can produce; long single clips fail.
5. A long-lived GPU worker can stall silently; per-process isolation with timeouts is cheap (~14 %) and works.
6. Hugging Face model repos often ship fp32 weights; converting to bf16 halves disk and load time.
7. Tunora's existing TimedLyrics, ACE-Step BPM metadata and LGPL FFmpeg made planning and assembly trivial.

## 30. Reuse Decisions

| Capability | Decision | Component |
|---|---|---|
| Keyframes | REUSE | Z-Image-Turbo via Diffusers `ZImagePipeline` |
| Video clips | REUSE (ADAPT config) | FastWan2.2-TI2V-5B (Apache-2.0) + Wan2.2 TI2V-5B text encoder/VAE via Diffusers `WanImageToVideoPipeline`; DMD timesteps through Diffusers' `FlowMatchEulerDiscreteScheduler(stochastic_sampling=True)` |
| Memory | REUSE | Diffusers `enable_model_cpu_offload`, `vae.enable_tiling`, `encode_prompt` + `prompt_embeds` |
| Base Wan2.2 50-step | REJECT for this hardware | too slow |
| Turbo TI2V variants | REJECT | no license |
| FastVideo runtime | REFERENCE | heavy pins, Blackwell unconfirmed |
| Beats/downbeats | REUSE | Beat This! (MIT) |
| Tempo / sections / line timing | REUSE | ACE-Step metadata, Tunora TimedLyrics |
| Validation | REUSE | ffprobe + `blackdetect`/`freezedetect` (approved FFmpeg) |
| Montage | REUSE | approved FFmpeg (`trim`, `concat`, `scale`, OpenH264, AAC) |
| Wan-Dancer | BLOCKED / REFERENCE | — |
| ComfyUI | not needed | — |

## 31. What Tunora Should Build

Only orchestration, all small: (1) shot planner (deterministic, from existing song data); (2) a minimal
`VideoClipProvider` boundary inside an isolated worker venv (load once per process, one clip per process);
(3) clip records with resume/skip-finished, per-clip timeout and bounded retry; (4) GPU arbitration — stop
ACE-Step for the job and restart it after (scripts already prove the mechanics); (5) clip validation + FFmpeg
montage command in the existing renderer style; (6) progress UX and per-shot regenerate.

## 32. What Tunora Must NOT Build

A video model, sampler, VAE, attention kernel, quantizer or offload engine; a DMD implementation beyond
configuring Diffusers' existing scheduler; a beat detector; an identity/face model; a renderer or encoder; a
workflow engine; any queue/broker/distributed worker; any cloud dependency.

## 33. Architecture Recommendation

Confirmed by measurement: **modular monolith + isolated GPU worker processes**.

```
AIMusicVideoService (backend) ── plan shots ── persist plan + clip rows ── stop ACE-Step
   └─ for each pending clip: spawn worker process (own venv)  [timeout 900 s, 1 retry]
          worker: load bf16 models (13 s) → precomputed embeds → FastWan 3-step I2V → tiled VAE → write clip
          (exits → VRAM/RAM returned)
   └─ validate clip (ffprobe/blackdetect/freezedetect) → mark done
   └─ assemble with approved FFmpeg → VideoOutputProfile (vertical_hd / landscape_hd) → restart ACE-Step
```

Keyframe images run in the same pattern (Z-Image worker; ~26 s each). Not recommended: a long-lived in-API model
(memory, hang), ComfyUI (GPL), a resident model server (cannot share 16 GB with ACE-Step).

## 34. Decision Gates

### GATE A — Short AI video generation: **PASS**
FastWan 3-step: 2 s in 2.1 min, 3.2 s in 3.1–3.7 min, 5 s in 7.1 min; 22 short clips produced, 22/22 valid;
1 hang in 23 attempts (1 of 8 in long-lived workers, 0 of 15 in process-per-clip mode). (Base 50-step: FAIL/impractical.)

### GATE B — Character consistency: **CONDITIONAL**
Costume, hair, jewellery, palette consistent across 20 shots; face identity varies between shots.

### GATE C — Dance/motion quality: **CONDITIONAL**
Graceful motion and spins good, no anatomy failures seen; athletic actions (leap, footwork) often not performed.

### GATE D — 30-second montage: **CONDITIONAL**
Produced and valid in both formats (31.2 s, exact audio, ~39–42 min GPU); "convincing" pending the user's viewing.

### GATE E — 9:16: **PASS**

### GATE F — 16:9: **PASS**

### GATE G — RTX 5060 Ti 16 GB: **CONDITIONAL**
Works only with a distilled model, precomputed embeddings, VAE tiling, shots ≤ 5 s, ACE-Step stopped, and
per-process isolation; RAM is the tightest resource.

### GATE H — 3-minute practical feasibility: **CONDITIONAL**
~4–5 h overnight batch (EXTRAPOLATED); acceptable only as a resumable background job.

### GATE I — 5-minute practical feasibility: **FAIL**
~6.6–8 h (EXTRAPOLATED), ~100 clips; not practical in the current form.

## 35. Final Decision

The montage approach is real on this machine. The remaining blockers before production are not "can it run"
but **identity consistency of the lead performer** and **making long jobs safe** (watchdog proven at n=15,
needs a longer soak). Both can be addressed with existing OSS and lab scripts before any production code.

## 36. Recommended Next Phase

**Phase 30 — AI Video Identity Consistency & Worker Soak (lab).** Bounded: test reference-image-driven keyframes
with Apache-2.0 image-edit models for same-face consistency, run a 60-second (≈19-shot) per-process soak to measure
hang/retry rates, and get the user's quality verdict on the Phase 29 montages. Production work (Phase 31: 30-second
9:16 AI Music Video Preview) starts only if Phase 30 passes.

---

# PHASE 29 FINAL DECISION

## Short Clip Generation

    PASS

## Character Consistency

    CONDITIONAL

## Motion / Dance Quality

    CONDITIONAL

## 30-Second AI Music Video

    CONDITIONAL

## 9:16

    PASS

## 16:9

    PASS

## RTX 5060 Ti 16GB

    CONDITIONAL

## 3-Minute Video

    CONDITIONAL

## 5-Minute Video

    FAIL

## Primary Model

    Z-Image-Turbo (keyframes; 23.5–36.2 s/image, 14.9 GB VRAM peak) + FastWan2.2-TI2V-5B-FullAttn
    (Apache-2.0, DMD 3-step, on Wan2.2 TI2V-5B text encoder/VAE; 3.2 s shot in 182–226 s; 10 s clips fail).
    Wan2.2 TI2V-5B at its official 50 steps: crashed, then 19.7–33.9 min per 2 s clip — not usable here.

## Secondary Model

    Wan-Dancer — BLOCKED before execution: weights (≥37 GB fp8) do not fit the 11 GB free disk, and
    gen_video_global.py:120 asserts WORLD_SIZE == 8 (verified in code e6c87a9).

## Biggest Technical Blocker

    Memory on a 16 GB GPU + 31.6 GB RAM host: base-model crash at 0.01 GB free RAM, 29.9 GB VRAM
    reservation without VAE tiling, 646 s per step for 10 s clips, and one silent worker hang under
    memory pressure (contained by process-per-clip + timeout, 15/15 clean).

## Biggest Quality Blocker

    Face identity changes between shots (costume/style are consistent), and athletic actions such as a
    leap are often not performed.

## Biggest Hardware Constraint

    System RAM (31.6 GB) and VRAM (16 GB) jointly: every working configuration ran at 15.9–16.0 GB
    device VRAM with 6–8 GB free system RAM; ACE-Step must be stopped during video generation.

## Recommended Architecture

    Modular monolith + isolated GPU worker processes, one clip per process (load ≈13 s), per-clip
    timeout and retry, resumable clip records, ACE-Step stopped/restarted around the job (release
    8.5–9.7 s, ready ≈30 s), validation and montage with Tunora's approved LGPL FFmpeg and existing
    VideoOutputProfiles.

## Recommended Next Phase

    Phase 30 — AI Video Identity Consistency & Worker Soak

---

# NEXT PHASE MASTER PROMPT

```
TUNORA PHASE 30 — AI VIDEO IDENTITY CONSISTENCY & WORKER SOAK (LAB ONLY)

Read first: docs/PHASE-29-AI-VIDEO-FEASIBILITY-LAB.md (§11, §12, §15, §21, §33),
docs/AI-MUSIC-VIDEO-OSS-FEASIBILITY-AUDIT.md (§9), docs/validation/phase-29-ai-video/README.md, CLAUDE.md.

CONTEXT
Phase 29 proved, on the RTX 5060 Ti 16 GB / 31.6 GB RAM machine, that Z-Image-Turbo keyframes +
FastWan2.2-TI2V-5B (3-step DMD) clips + Tunora's LGPL FFmpeg montage produce a valid 31-second AI music
video in 9:16 and 16:9 (~39–42 min GPU). Two limitations block production:
  1. the performer's FACE changes between shots (costume/style are consistent);
  2. long jobs: one silent worker hang (long-lived process); process-per-clip + timeout ran 15/15 clean,
     which is too small a sample for 60–180 s jobs.
The user has not yet given a quality verdict on the Phase 29 montages.

HARD RULES
- Lab only: I:\Tunora-validation\ai-video-feasibility\ (reuse its venv, models and scripts). Do NOT modify
  Tunora production code, dependencies, schema, APIs, UI, renderer or storage.
- Never modify a venv while a worker process is running.
- Check disk before any download (I: had ~11 GB free). Prefer bf16 single copies; delete what you replace.
- Only 🟢 licenses (code AND weights). No insightface/antelopev2, FLUX-dev, InfiniteYou or unlicensed weights.
- Keep the Phase 29 configuration unchanged as the control (FastWan 3-step, precomputed embeds, VAE tiling,
  77-frame shots, one process per clip, 900 s timeout).
- Never fabricate numbers. Label MEASURED / EXTRAPOLATED / UNVERIFIED / NOT RUN / BLOCKED.

STEP 0 — USER VERDICT
Ask the user to watch outputs/final/e8_montage_9x16.mp4 and e9_montage_16x9.mp4 and score identity,
motion, anatomy, music fit and "feels like a music video" (1–5). Record verbatim. If the user rejects the
overall look, stop and report instead of continuing.

STEP 1 — IDENTITY (fresh reuse audit first, small)
Find Apache-2.0/MIT image models that place the SAME person from ONE reference image into new scenes and
poses (candidates to verify, not assume: Z-Image-Edit, Qwen-Image-Edit-2509 — check VRAM/RAM fit; 20B
models may not fit). Test at most two candidates. For the 10 Phase 29 shots, generate keyframes from one
master reference image, then FastWan clips from them.
Measure: time/VRAM/RAM per keyframe, and face consistency across the 10 shots (side-by-side face crops;
user judgement). Compare against the Phase 29 text-only keyframes.

STEP 2 — SOAK
Plan the full 60-second song (≈19 shots, one per bar) and generate all clips with the per-process
driver, twice (9:16 only). Measure per-clip time distribution, hangs, timeouts, retries, crashes,
min free RAM, and total wall time. Assemble both 60-second montages.

STEP 3 — REPORT
docs/PHASE-30-AI-VIDEO-IDENTITY-AND-SOAK.md with the user's verdict, identity comparison, soak
statistics, updated 60 s / 3 min extrapolations, and gates:
  Identity consistency, Worker reliability (≥ 38 clips, 0 unrecovered failures),
  60-second video, User quality verdict — PASS / CONDITIONAL / FAIL.
Recommend either "Phase 31 — 30-Second AI Music Video Preview (9:16, production slice)" or the specific
remaining blocker.

Commit only the report and small lab metadata (no media, no weights), one commit:
  feat(video): add AI video identity and soak lab results
Do not push.
```
