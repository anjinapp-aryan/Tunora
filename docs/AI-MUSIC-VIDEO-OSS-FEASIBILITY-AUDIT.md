# AI Music Video — OSS Feasibility Audit

Audit + research + feasibility + architecture plan. **No implementation.** No production code, dependency, migration, API or UI was changed for this document.

- Date of research: **2026-10-03** (every "checked" date below is this date unless stated).
- Tunora code audited: branch `feature/tunor_2_video` at commit `62b87fb` ("feat(video): add multi-format video output profiles"), read-only, from the `I:\Tunora` working copy. The music-video modules referenced below (`backend/app/music_videos/*`) exist on that branch, not on `main`.
- Machine facts were measured on the development machine during this audit.

Evidence labels used throughout:

| Label | Meaning |
|---|---|
| **VERIFIED** | Measured on this machine during the audit, or read directly in source code / an official license file. |
| **OFFICIAL** | Stated by the project's own README, model card, paper or docs (not independently measured). |
| **REPORTED** | Community report (forum, model page discussion). Not reproduced. |
| **INFERRED** | Derived by arithmetic or reasoning from verified/official facts. Shown with its method. |
| **UNVERIFIED** | Unknown until measured. No number is claimed. |

---

## 1. Executive Summary

1. **The reference videos are not long single-take generations.** Measured on the three provided files: they are 5–7 minute **montages of ~55–150 short shots** (median shot **2.0–3.2 s**), 720p-class, effectively **16:9 picture** (the two "portrait" files carry a 720×404 picture letterboxed inside 720×1280), group dancers in Indian costume, constant set changes, and **cuts that are not beat-aligned** (35% of cuts within ±80 ms of a beat vs a 35% random baseline). This reframes the problem: the target product is a *music-video montage of short AI clips*, which current open models can produce clip-by-clip, not a 3–5 minute continuous dance take.
2. **Wan-Dancer is real, Apache-2.0 (code and weights), and the only open model found that does music-conditioned, minute-scale dance** — but it is a poor first fit for this product and this machine:
   - solo dancer only (multi-dancer is listed as future work), single continuous shot, 5 genres (no Indian styles), native 720×1280 portrait;
   - the official global-stage script hard-codes 8 GPUs (`assert world_size == 8`), was tested on 8× A800 80 GB, and pins `torch 2.6.0+cu124`, which has no kernels for this GPU (sm_120);
   - 14B parameters; fp8 checkpoints are 18.34 GB per stage (larger than the 16 GB card), the full bf16 set is ~86 GB (larger than any free disk on this machine), and this machine has 31.6 GB RAM while the only first-hand 16 GB-GPU reports used 64 GB.
   - Single-GPU 16 GB feasibility is **UNVERIFIED** and high-risk.
3. **The evidence-backed primary path is COMPOSE, not a single model:** existing beat/section data (Tunora already stores BPM and timed lyric sections) → a Tunora-owned shot plan → per-shot keyframe images (Apache-2.0 image model) → short image-to-video clips (Apache-2.0 Wan2.2 family) → assembly with Tunora's existing policy-checked LGPL FFmpeg pipeline and `VideoOutputProfile`s. Wan-Dancer remains a **secondary "solo dance shot" candidate**, gated by a hardware spike.
4. **Final decision: NOT YET.** 3–5 minute AI music videos on the RTX 5060 Ti 16 GB are *plausible* as an overnight batch job via the montage approach, but clip generation time, VRAM headroom with 31.6 GB RAM, and character consistency are all **UNVERIFIED** on this machine. The next phase is a measurement lab, not a feature.

---

## 2. Current Tunora Capability

Audited on `feature/tunor_2_video@62b87fb` (VERIFIED by reading the code):

| Area | What exists | File |
|---|---|---|
| Music video entity | `MusicVideo` (immutable source Version/style/profile/background; status `WAITING_FOR_AUDIO → PENDING → ALIGNING → RENDERING → COMPLETED/FAILED`) | `backend/app/music_videos/models.py` |
| Output formats | `VideoOutputProfile` table: `vertical_hd` 1080×1920, `vertical_4k` 2160×3840, `landscape_hd` 1920×1080, `landscape_4k` 3840×2160, `square_hd` 1080×1080; OpenH264 bitrates per profile | `profiles.py` |
| FFmpeg policy | Resolves one FFmpeg, refuses `--enable-gpl`/`--enable-nonfree`, requires libass, OpenH264, AAC | `ffmpeg.py` |
| Renderer | Background image/video → scale-to-cover + crop → darken → libass lyrics → H.264/AAC 30 fps; argument lists only, `file:` protocol whitelist, decode check, 7680×4320 pixel cap | `renderer.py` |
| Lyric timing | `LocalForcedAligner` runs `align_worker` (stable-ts MIT + Whisper MIT) **as a separate process** so torch never loads into the API process | `aligner.py`, `align_worker.py` |
| Storage | `MusicVideoStorage` composes `LocalAudioStorage` for key validation/containment; atomic upload; per-video directory | `storage.py` |
| Orchestration | `MusicVideoService`: FastAPI BackgroundTasks, one render at a time (`threading.Lock`), retry in place, restart → interrupted renders marked FAILED, `WAITING_FOR_AUDIO` resumed | `service.py` |
| Persistence | stdlib `sqlite3`, `PRAGMA user_version` migrations (music videos added at v6, profiles at v7) | `repository.py`, `jobs/migrations.py` |
| Song data | Version stores `bpm`, `key_scale`, `time_signature` from ACE-Step metadata; lyrics with `[Verse]`/`[Chorus]` tags | `songs/models.py:84`, `providers/ace_step.py:200` |
| Measured render cost | 60 s song: HD ≈ 7–15 s wall, 4K ≈ 48–52 s, ≤ 464 MB RAM (Phase 27 table) | `docs/PHASE-27-MULTI-FORMAT-MUSIC-VIDEO.md` |

What it is: audio + uploaded background + aligned lyrics + FFmpeg. It contains **no AI video model** and requires lyrics (instrumental Versions are rejected, `service.py`).

---

## 3. Target Product Capability

Original AI-generated music video for a Tunora song: human performers dancing, scene/costume/set changes, camera movement, coherent style, recognisable lead character across shots, visuals that follow the song's sections, delivered as 9:16 1080×1920 and 16:9 1920×1080, songs of 3–5 minutes. Generated locally, no paid API.

---

## 4. Reference Video Analysis

All numbers VERIFIED with `ffprobe`/`ffmpeg` and `librosa` (run in a scratch environment, nothing installed into Tunora). People were not identified; frames were only inspected for structure and style.

| File | Container | Active picture | FPS | Duration | Shots (scene>0.3) | Median shot | Mean shot | Max shot |
|---|---|---|---|---|---|---|---|---|
| Song-Test-1.mp4 | 720×1280 | **720×404** (16:9 letterboxed; `cropdetect`) | 30 | 6:31 | 149 | 2.0 s | 2.6 s | 10.5 s |
| Song-Test-2.mp4 | 720×1280 | **720×404** (16:9 letterboxed) | 30 | 5:10 | 99 | 2.3 s | 3.1 s | 13.8 s |
| Song 3 Test.mp4 | 1280×720 | 1280×720 | 25 | 7:20 | 55 | 3.2 s | 8.0 s | 51.7 s* |

\* the 51.7 s value may be a slow-changing passage or a detection miss (UNVERIFIED).

Beat alignment of cuts (librosa `beat_track`, ±80 ms tolerance):

| File | Tempo | Cuts on a beat | Random baseline |
|---|---|---|---|
| Song-Test-1 | 136 BPM | 0.35 | 0.35 |
| Song-Test-2 | 136 BPM | 0.36 | 0.37 |
| Song 3 | 129 BPM | 0.29 | 0.36 |

Findings:

- **Structure:** montage of short shots; 2–3 s is the typical shot, almost never above ~14 s. A 5 s generated clip covers 1–2 shots.
- **Not beat-synchronised editing.** Cuts land on beats at chance level. The "sync" viewers perceive comes from the music under energetic generic dance motion, not from frame-accurate choreography.
- **Ensembles, not soloists:** most shots show 5–12 dancers in matching costumes, plus close-up "lead singer" shots and a few overhead shots.
- **Identity is style-level, not person-level:** costumes and leads change across shots; consistency is in colour palette, set design (palace interiors, chandeliers, stage lights) and costume genre.
- **Resolution:** delivered at 720p class (the portrait files' real picture is 720×404). The production bar is lower than 1080p-native.
- **Aspect:** all three are 16:9 content; "9:16" was produced by letterboxing.
- Channel watermarks are present (third-party content). Tunora must generate original videos and must not imitate these.

**Product implication:** a credible first product is a section-aware montage of 2–5 s AI clips over the Tunora song. Long-horizon single-take continuity (what Wan-Dancer optimises) is not what the references show.

---

## 5. Fresh OSS Landscape

Checked 2026-10-03 via GitHub API, Hugging Face API and official pages.

| Project | Repo / weights | Code lic. | Weight lic. | Activity | What it is |
|---|---|---|---|---|---|
| **Wan-Dancer-14B** | [github](https://github.com/Wan-Video/Wan-Dancer) / [HF](https://huggingface.co/Wan-AI/Wan-Dancer-14B) / [paper](https://arxiv.org/abs/2607.09581) | Apache-2.0 | Apache-2.0 | created 2026-07-13, last push 2026-07-17, 437★ | Music + image → solo dance video, global keyframes + 5 s local refinement |
| Comfy-Org/Wan-Dancer (fp8) | [HF](https://huggingface.co/Comfy-Org/Wan-Dancer) | — | Apache-2.0 | 2026-09-23 | fp8-scaled repack, 18.34 GB per stage |
| realrebelai/Wan_Dancer_GGUFs | [HF](https://huggingface.co/realrebelai/Wan_Dancer_GGUFs) | — | Apache-2.0 (claimed) | community | Q3–Q6 GGUF, 9.8–15.4 GB per stage; README warns earlier uploads were corrupt |
| **Wan2.2** (T2V/I2V-A14B, **TI2V-5B**, S2V-14B, Animate-14B) | [github](https://github.com/Wan-Video/Wan2.2) / [HF](https://huggingface.co/Wan-AI) | Apache-2.0 | Apache-2.0 | push 2026-09-21, 17.7k★ | Base video family; TI2V-5B = 720p 24 fps T2V+I2V, 704×1280 and 1280×704 native |
| Wan2.1 (+ VACE) | [github](https://github.com/Wan-Video/Wan2.1), [VACE](https://github.com/ali-vilab/VACE) | Apache-2.0 | Apache-2.0 | 2026-03 / 2025-10 | 1.3B/14B; VACE = reference/pose/extension/edit control |
| SteadyDancer | [github](https://github.com/MCG-NJU/SteadyDancer) | Apache-2.0 | Apache-2.0 | 2025-12 | Pose-driven image animation (needs a driving pose video) |
| Wan2.2-Animate-14B | HF Wan-AI | Apache-2.0 | Apache-2.0 | 2025-11 | Motion transfer from a driving video |
| EchoMimicV3 | [github](https://github.com/antgroup/echomimic_v3) | Apache-2.0 | Apache-2.0 | 2026-03 | 1.3B audio-driven talking/singing, half/full body; "12G VRAM" Flash version |
| InfiniteTalk / MultiTalk | [github](https://github.com/MeiGen-AI/InfiniteTalk) | Apache-2.0 | Apache-2.0 | 2026-05 | Audio-driven long talking/singing video |
| HuMo | [github](https://github.com/Phantom-video/HuMo) | Apache-2.0 | Apache-2.0 | 2026-01 | Text+image+audio human video on Wan |
| Phantom / Stand-In / MAGREF | Phantom-video, WeChatCV, MAGREF-Video | Apache-2.0 | Apache / Apache / *unstated* | 2025–26 | Subject/identity-to-video on Wan |
| LongCat-Video 13.6B | [HF](https://huggingface.co/meituan-longcat/LongCat-Video) | MIT | MIT | 2026-05 | T2V/I2V/continuation, "minutes-long" without drift (OFFICIAL) |
| Helios 14B | [github](https://github.com/PKU-YuanGroup/Helios) | Apache-2.0 | Apache-2.0 | 2026-08 | Autoregressive minute-scale video, 640×384 examples, "~6GB" with group offload |
| LTX-2 22B | [github](https://github.com/Lightricks/LTX-2) | custom | LTX-2 Community License | 2026-10-02 | Joint audio+video; **audio-to-video pipeline** (A2VidPipelineTwoStage) |
| HunyuanVideo-1.5 | [github](https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5) | custom | Tencent Hunyuan Community | 2026-04 | 8.3B T2V/I2V |
| CogVideoX1.5-5B | [github](https://github.com/zai-org/CogVideo) | Apache-2.0 | CogVideoX License | 2025-11 | 5B, ≤10 s |
| SkyReels-V2 | [github](https://github.com/SkyworkAI/SkyReels-V2) | custom | Skywork Community | 2026-01 | Diffusion-forcing "infinite" length |
| FramePack | [github](https://github.com/lllyasviel/FramePack) | Apache-2.0 | (HunyuanVideo weights) | 2025-10 | Next-frame-section packing on HunyuanVideo |
| Music-to-motion (EDGE, Bailando, LODGE) | Stanford-TML/EDGE etc. | MIT / unstated / none | AIST++-trained | 2023–26 | Music → 3D dance motion (needs a renderer + pose-to-video) |
| Inference stacks | [DiffSynth-Studio](https://github.com/modelscope/DiffSynth-Studio), [LightX2V](https://github.com/ModelTC/LightX2V), [FastVideo](https://github.com/hao-ai-lab/FastVideo), [cache-dit](https://github.com/vipshop/cache-dit), [SageAttention](https://github.com/thu-ml/SageAttention), Diffusers | Apache-2.0 (all) | — | active 2026-09/10 | Offload, fp8, step distillation, caching, fast attention |
| UIs (reference only) | ComfyUI (GPL-3.0), [Wan2GP](https://github.com/deepbeepmeep/Wan2GP) (WanGP Community License 2.0), ComfyUI-WanVideoWrapper (Apache-2.0, ComfyUI plugin) | — | — | active | Workflow ecosystems |

Newer than the requested list and relevant: **Wan-Dancer (Jul 2026)**, **Helios (2026)**, **LongCat-Video (MIT)**, **LTX-2 A2V**, **EchoMimicV3-Flash-Pro (Jan 2026)**, **Z-Image (Apache-2.0, 6B image model)**.

---

## 6. Model Comparison

Hardware columns: OFFICIAL unless labelled.

| Model | Task fit for references | Params | Native size / FPS / clip | Music conditioning | Identity | 16 GB evidence | License | Verdict |
|---|---|---|---|---|---|---|---|---|
| **Wan2.2 TI2V-5B** | Short clips of dancers/sets from a keyframe or text | 5B | 1280×704 **and** 704×1280, 24 fps, 121 frames ≈ 5 s | none | first-frame image | OFFICIAL ≥24 GB with offload flags; ComfyUI docs: "should fit well on 8GB vram" with native offloading | 🟢 Apache-2.0 | **Primary clip model (to measure)** |
| Wan2.2 I2V-A14B (+ lightx2v distill LoRA) | Higher-quality clips | 2×14B MoE | 480p/720p, 81 frames @16 fps | none | first frame (+FLF) | OFFICIAL 80 GB single-GPU example; REPORTED: Q8 GGUF, 1024×574, 5 s ≈ 7 min on 5060 Ti 16 GB **with 64 GB RAM** + SageAttention ([HF discussion](https://huggingface.co/Wan-AI/Wan2.2-Animate-14B/discussions/4)) | 🟢 Apache-2.0 (LoRAs Apache-2.0) | Quality comparison arm |
| **Wan-Dancer-14B** | Solo continuous dance | 14B ×2 stages | 720×1280, 30 fps, 149-frame segments | **yes** (librosa onset/MFCC/chroma/beat features injected into DiT) | reference image | none; official = 8× A800 | 🟢 Apache-2.0 (training data undisclosed) | Secondary spike |
| Wan2.2-S2V-14B / EchoMimicV3 / InfiniteTalk | Lip-synced "singer" close-ups | 14B / 1.3B / 14B | 1024×704 / ≤768² / 480p+ | voice audio | reference image | EchoMimicV3: OFFICIAL "12G VRAM" (Flash) | 🟢 Apache-2.0 | Later shot type |
| VACE / SteadyDancer / Wan-Animate | Pose/motion-driven dancing | 1.3B–14B | 480p/720p | none (needs pose video) | reference image | VACE 1.3B UNVERIFIED here | 🟢 code/weights; 🟡 *driving videos* must be licensed | Later, if a licensed motion library exists |
| LTX-2 22B | Audio-conditioned clips | 22B | 1024×1536 default, 24 fps | **yes** (A2V) | keyframes | fp8 + CPU/disk offload exists; 16 GB UNVERIFIED | 🟡 free < $10M revenue, AUP, must disclose AI content | Reference / optional |
| LongCat-Video | Long continuation | 13.6B | 720p 30 fps | none | I2V | UNVERIFIED | 🟢 MIT | Reference for long takes |
| Helios | Long autoregressive | 14B | 640×384 examples | none | I2V | OFFICIAL "~6GB" with group offload | 🟢 Apache-2.0 | Reference for long takes |
| HunyuanVideo-1.5 | Clips | 8.3B | 720p | none | I2V | — | 🟡/🔴 excludes EU/UK/South Korea | Reject for default |
| CogVideoX1.5-5B | Clips | 5B | 1360×768, ≤10 s | none | I2V | — | 🟡 registration + ≤1M visits/month | Reject |
| SkyReels-V2 | Long video | 1.3B–14B | 540p/720p | none | — | — | 🟡 Skywork Community (terms not fully reviewed) | Reference |

---

## 7. Wan-Dancer Deep Audit

Sources: repo README and scripts `gen_video/gen_video_global.py`, `gen_video/gen_video_local.py` (read on 2026-10-03), HF model card and file list, arXiv 2607.09581, ComfyUI tutorial.

| Question | Finding | Evidence |
|---|---|---|
| Repository / model | `Wan-Video/Wan-Dancer`; weights `Wan-AI/Wan-Dancer-14B` | VERIFIED |
| Code license | Apache-2.0 (repo root and vendored `diffsynth/LICENSE`) | VERIFIED |
| Weight license | Apache-2.0 on HF card; not gated | VERIFIED |
| Training data | "approximately 200 hours" of proprietary dance video, five genres; no provenance or license statement | OFFICIAL (paper) — **legal open item** |
| Architecture | Wan-I2V 14B DiT fine-tuned twice: `global_model.safetensors` and `local_model.safetensors` (34.49 GB each, bf16), plus umt5-xxl (11.36 GB `.pth`), CLIP ViT-H (4.77 GB `.pth`), Wan2.1 VAE (0.51 GB `.pth`). Total ≈ 86 GB | VERIFIED (HF file list) |
| Global stage | One 149-frame generation for the *whole song*: frame rate is set to `30 / round(total_frames / 149)` and written into the prompt ("帧率是…"), so 149 frames span the song as sparse keyframes (paper: 38 latent keyframes) | VERIFIED (code) |
| Local stage | Song cut into **149-frame (4.97 s @ 30 fps) slices** — code comment `# 149 cannot be changeg` — each refined with the global keyframes that fall inside it; the **last frame of segment *i* is forced equal to the first keyframe of segment *i+1*** for continuity; sequential loop, seed = `idx*10 + seed` | VERIFIED (code) |
| Music input | Any audio file: librosa onset envelope, 20 MFCC, chroma CENS, onset peaks, beat one-hots at 30 fps → injected at DiT layers 0,4,8,…,27 | VERIFIED (code) |
| Reference image | One image, letter/pillar-boxed with grey (127) to 720×1280, then the padding is cropped from the output | VERIFIED (code) |
| Prompt | Per-genre prompt files (Chinese classical, K-pop, street, tap, Latin); Chinese negative prompt | VERIFIED |
| Styles | 5 genres; **no Indian/Bollywood genre** | OFFICIAL |
| Demonstrated duration | Paper: "exceeding one minute", up to 160 s; ModelScope post: "up to 3 minutes" | OFFICIAL (inconsistent) |
| Resolution / FPS | 720×1280 portrait, 30 fps defaults | VERIFIED (code) |
| GPU requirement | Global script: `assert world_size == 8, "WORLD_SIZE must be 8"`; README tested on 8× A800 80 GB; uses xfuser/yunchang Ulysses sequence parallelism | VERIFIED |
| Software pins | Ubuntu 22.04, Python 3.10, `torch 2.6.0+cu124` (Linux wheel URL), flash_attn 2.6.3, xfuser 0.4.0, diffusers 0.34.0 | VERIFIED |
| Runs on this GPU unmodified? | **No.** This GPU reports compute capability (12, 0) = sm_120; the working stack here is `torch 2.7.1+cu128` with sm_120 kernels. A cu124 build lacks sm_120. The stack must be re-pinned (and flash_attn replaced, e.g. SDPA/SageAttention) | VERIFIED (GPU/torch), INFERRED (re-pin works) |
| Windows | Not supported officially (Linux scripts, Linux wheel, torchrun) | VERIFIED |
| 16 GB realistic? | **UNVERIFIED, high risk.** fp8 per stage = 18.34 GB > 16 GB → block offload required; GGUF Q4_K_M = 12.55 GB (community). Per-segment token count ≈ 38×45×80 = 136,800 (Wan VAE 4×8×8, patch 1×2×2) — ~1.8× a standard 81-frame 720p Wan clip. With 31.6 GB system RAM, fp8 DiT (18.3 GB) + fp8 T5 (6.7 GB) offloaded to RAM leaves little headroom | INFERRED |
| Quantized variants legally usable? | Comfy-Org fp8 repack: Apache-2.0 card; realrebelai GGUF: Apache-2.0 card (third-party; corruption warning; pin hashes) | VERIFIED (cards) |
| Quantized quality | UNVERIFIED | — |
| ComfyUI required? | No. Native ComfyUI nodes exist (`docs.comfy.org/tutorials/video/wan/wan-dancer`; default workflow = 5 s), but the official code is a plain Python DiffSynth pipeline | VERIFIED |
| Direct Python inference | Practical in principle: `diffsynth.pipelines.wan_video_new.WanVideoPipeline` (Apache-2.0), with `enable_vram_management()` and CPU offload configs already in the scripts. Requires removing the 8-GPU assert / USP, and replacing moviepy+libx264 output (GPL encoder path) with Tunora's LGPL FFmpeg | INFERRED from code |
| 9:16 / 16:9 | 9:16 native. 16:9 = UNVERIFIED (padding code suggests landscape input becomes pillar-boxed inside portrait; training data orientation not stated) | INFERRED |
| Segment chaining / continuity | Built-in: global keyframes + shared boundary frames | VERIFIED |
| Arbitrary Tunora songs | Yes in principle (any WAV/FLAC through librosa); quality on ACE-Step songs and non-supported genres UNVERIFIED | INFERRED |
| Segments for a song | 30 s → 7; 60 s → 13; 3 min → **37**; 5 min → **61** local segments (+1 global pass) | INFERRED (⌈duration / 4.967 s⌉) |
| Stated limitations | identity consistency, semantic alignment, **multi-dancer** (future work) | OFFICIAL (paper) |
| Maintenance | One week of commits (2026-07-13…07-17), none since | VERIFIED |

**Fit vs references:** solo (refs: ensembles), single continuous scene (refs: scene changes every 2–3 s), 5 non-Indian genres, portrait-native (refs: 16:9 content). Wan-Dancer solves a *harder* problem (continuous minute-scale choreography) than the references require, on hardware this machine does not have.

---

## 8. Wan2.1 / Wan2.2 Analysis

- **Wan2.1** (Apache-2.0): T2V/I2V 1.3B/14B, FLF2V, VACE. Base of Wan-Dancer, SteadyDancer, Stand-In, EchoMimicV3, Helios.
- **Wan2.2** (Apache-2.0, last push 2026-09-21): A14B MoE (high-noise + low-noise experts), **TI2V-5B** with a 4×16×16 VAE, S2V-14B, Animate-14B. Integrated in Diffusers and ComfyUI (OFFICIAL).
- **TI2V-5B** specifics (OFFICIAL README): "the 720P resolution of the Text-Image-to-Video task is `1280*704` or `704*1280`"; single-GPU command "can run on a GPU with at least 24GB VRAM (e.g, RTX 4090)" with `--offload_model True --convert_model_dtype --t5_cpu`; "can generate a 5-second 720P video in under 9 minutes on a single consumer-grade GPU".
- **Why TI2V-5B first:** per clip it processes ≈ 31×22×40 = 27,280 tokens (704×1280×121, 4×16×16 VAE, 2×2 patch) vs ≈ 136,800 for a Wan-Dancer segment — about 5× fewer tokens with 2.8× fewer parameters (INFERRED arithmetic). Weights: fp16 DiT 10.0 GB + fp8 umt5 6.74 GB + Wan2.2 VAE 1.41 GB ≈ 18.2 GB disk (VERIFIED sizes, Comfy-Org repack).
- **Acceleration (Apache-2.0):** lightx2v step-distill LoRAs (4-step) for 14B I2V; FastVideo distilled Wan variants; cache-dit; SageAttention. Effect on 5060 Ti: UNVERIFIED.

---

## 9. Character Consistency Options

What the references need: consistent *style, palette, set and costume genre*, plus a recognisable lead in close-ups. Not frame-exact identity across 150 shots.

| Approach | Project | License | Decision | Reason |
|---|---|---|---|---|
| Shared keyframe images from one "look" (character sheet + scene prompts) → I2V | Z-Image-Turbo (6B; OFFICIAL "fits comfortably within 16G VRAM"), Qwen-Image / Qwen-Image-Edit-2509 (20B) | 🟢 Apache-2.0 | **REUSE** (Z-Image first) | Image models hold identity/costume far better than video models; I2V preserves the first frame |
| Image editing to place the same character in new sets | Qwen-Image-Edit-2509, Z-Image-Edit | 🟢 Apache-2.0 | **ADAPT** | VRAM for 20B Qwen UNVERIFIED |
| First-frame/last-frame conditioning | Wan2.2 I2V / FLF2V, Wan-Dancer keyframes | 🟢 Apache-2.0 | **REUSE** | Built into models |
| Reference-to-video (subject) | Phantom (Apache), VACE R2V (Apache), MAGREF (weights license **unstated**) | 🟢 / 🟢 / UNKNOWN | **REFERENCE** (Phantom/VACE), **DO NOT ADOPT** MAGREF | Extra 14B weights; later |
| Face-ID adapters | Stand-In, InstantID, PuLID | code Apache-2.0, **but** depend on insightface `antelopev2`, whose models are "available for non-commercial research purposes only" ([insightface README](https://github.com/deepinsight/insightface)) | 🔴 **REJECT** for commercial use | License of the face model |
| InfiniteYou | ByteDance | 🔴 CC-BY-NC-4.0 | **REJECT** | Non-commercial |
| FLUX.1-dev / Kontext-dev | BFL | 🔴 FLUX.1-dev Non-Commercial | **REJECT** | Non-commercial |
| Character LoRA training | DiffSynth-Studio / Wan LoRA training | 🟢 Apache-2.0 | **REFERENCE** (later) | Training time and 16 GB feasibility UNVERIFIED |

---

## 10. Music Synchronization Options

| Need | Existing wheel | License | Decision |
|---|---|---|---|
| Tempo | **Already stored**: Version `bpm` from ACE-Step metadata | — | **REUSE** |
| Section structure (verse/chorus) | **Already stored**: lyric section tags; **already computed**: `TimedLyrics` line/word timings from stable-ts in the lyric-video pipeline | MIT (stable-ts, Whisper) | **REUSE** |
| Beat positions / phase | librosa `beat_track` (already in Tunora's approved stack; also what Wan-Dancer uses) | ISC | **REUSE** |
| Beats + downbeats (better accuracy) | [Beat This!](https://github.com/CPJKU/beat_this) — "code and the published model weights are released under the MIT license" | 🟢 MIT | **ADAPT** if librosa is not good enough |
| Full structure (sections for instrumentals) | [All-In-One](https://github.com/mir-aidj/all-in-one) | code MIT; **weights license not stated**; needs madmom (models CC BY-NC-SA, already rejected in `LICENSE-AUDIT.md`), NATTEN (Windows: build from source), Demucs | **REFERENCE / DO NOT ADOPT** |
| Essentia | MTG/essentia | 🔴 AGPL-3.0 | **REJECT** |
| Music-conditioned motion | Wan-Dancer (in-model), LTX-2 A2V | 🟢 / 🟡 | Secondary |

The references show cuts at chance relative to beats, so the MVP sync target is: **cut on beats/downbeats and change scenes on section boundaries** (cheap, deterministic, Tunora-owned planning on top of reused analysis). In-shot motion sync is a later quality step.

---

## 11. Long-Duration Strategy

| Strategy | Example | Continuity | Cost on 16 GB | Fit |
|---|---|---|---|---|
| One-shot 3–5 min diffusion | none found | — | infeasible (tokens grow with length) | **Reject** |
| Global + local hierarchy | Wan-Dancer | best for one continuous take | 1 global + 37–61 heavy segments; UNVERIFIED | Secondary |
| Autoregressive / continuation | Helios, LongCat-Video, SkyReels-V2 DF, FramePack | good for one take | UNVERIFIED | Reference |
| Last-frame I2V chaining | Wan I2V / FLF2V | drifts over many hops | per clip | Only for 2–3 linked shots |
| **Keyframe-anchored montage** (independent shots, each from a planned keyframe image) | Wan2.2 TI2V/I2V + Z-Image | style via shared look; no drift accumulation because shots are independent | per clip, embarrassingly resumable | **Primary** (matches references) |

Segment counts:

| Song | Wan-Dancer local segments (4.97 s) | Montage shots (avg 3 s) | Montage clips (5 s clips, 1–2 shots each) |
|---|---|---|---|
| 30 s | 7 | 10 | 5–10 |
| 60 s | 13 | 20 | 10–20 |
| 2 min | 25 | 40 | 20–40 |
| 3 min | **37** | 60 | **30–60** |
| 5 min | **61** | 100 | **50–100** |

Support order: **30 s → 60 s → 2 min → 3 min → 5 min**, each gated by measured time/failure rates (Section 28). 5 minutes is not claimed achievable today.

---

## 12. 9:16 / 16:9 Strategy

Keep three sizes separate:

| Concept | 9:16 | 16:9 |
|---|---|---|
| **Model generation resolution** (TI2V-5B native) | 704×1280 | 1280×704 |
| **Intermediate** (assembly canvas) | 720×1280 (pad 8 px or scale) | 1280×720 |
| **Final delivery** (existing `VideoOutputProfile`) | `vertical_hd` 1080×1920 | `landscape_hd` 1920×1080 |

- Generate **natively per orientation** (TI2V-5B supports both; keyframe images are generated at the same orientation). Do not centre-crop 16:9 into 9:16 — it removes most of an ensemble shot.
- Upscale 720→1080 with the existing FFmpeg `scale` (LGPL; the renderer already does scale-to-cover). AI upscalers (Real-ESRGAN etc.) are later and need their own license check; 4K profiles are not meaningful from 720p sources and should be hidden for AI videos.
- Dual-format delivery = generate twice (≈2× GPU time) or, as a cheap option, the references' own trick: 16:9 letterboxed into 9:16 (the existing "cover" renderer would need a "contain/pad" mode).
- Smart reframing (MediaPipe AutoFlip, Apache-2.0): **REFERENCE** only — a C++ graph pipeline; not worth it while native generation is possible.

---

## 13. RTX 5060 Ti 16 GB Feasibility

Machine (VERIFIED 2026-10-03): RTX 5060 Ti 16,311 MiB, driver 591.86, compute capability 12.0 (sm_120); torch 2.7.1+cu128 works; Intel Core Ultra 7 265K (20 cores); **31.6 GB RAM**; free disk: I: 68.1 GB, H: 48.8, G: 40.2, F: 29.8, E: 23, D: 20.2, C: 19.1.

Constraints discovered:

1. **ACE-Step holds the GPU.** Per `docs/TUNORA-SERVICE-MANAGEMENT.md` (measured in-project): ~1.5 GB idle after start, ~11.6 GB with both models + LM resident, 14.9–15.3 GB peak. ACE-Step's API has **no model-unload endpoint** (only `/v1/lora/unload`; `ACESTEP_OFFLOAD_TO_CPU` is start-time) — VERIFIED by searching `ACE-Step-1.5/acestep/api`. → Video generation and song generation cannot share the GPU; ACE-Step must be stopped (existing `stop-tunora.ps1` logic) or started in offload mode while video runs.
2. **System RAM 31.6 GB** limits CPU offload of 14B models (the only first-hand 16 GB-GPU Wan report upgraded to 64 GB).
3. **Disk:** the full Wan-Dancer bf16 set (~86 GB) fits on no drive; the fp8 path needs ≈ 45.7 GB (2×18.34 + 6.74 + 1.26 + 0.25 + 0.74 LoRA); TI2V-5B path ≈ 18.2 GB.

| Candidate | Official | Community | This machine |
|---|---|---|---|
| Wan2.2 TI2V-5B | ≥24 GB with offload (README); 8 GB with ComfyUI offload (ComfyUI docs) | — | **UNVERIFIED** (likely: fits with offload; RAM ≈ 17 GB of weights) |
| Wan2.2 I2V-A14B | 80 GB single-GPU example | Q8 GGUF, 1024×574, 5 s ≈ 7 min on 5060 Ti 16 GB, 64 GB RAM | **UNVERIFIED**, RAM-limited |
| Wan-Dancer | 8× A800 80 GB | none found for 16 GB | **UNVERIFIED, high risk** (sm_120 re-pin, 8-GPU assert, RAM) |
| EchoMimicV3 Flash | "12G VRAM" | — | UNVERIFIED |
| Z-Image-Turbo | "fits comfortably within 16G VRAM" | — | UNVERIFIED |

---

## 14. Licensing Matrix

| Component | Code | Weights | Data | Commercial | Class |
|---|---|---|---|---|---|
| Wan2.1 / Wan2.2 (all variants), VACE | Apache-2.0 | Apache-2.0 | undisclosed | allowed | 🟢 (data provenance open) |
| Wan-Dancer | Apache-2.0 | Apache-2.0 | proprietary 200 h, undisclosed | allowed by license | 🟢/🟡 (provenance) |
| Comfy-Org fp8 repacks | — | Apache-2.0 | — | allowed | 🟢 |
| Community GGUF quants | — | Apache-2.0 (claimed) | — | allowed | 🟡 (third-party artefacts: verify hashes) |
| lightx2v distill LoRAs | Apache-2.0 | Apache-2.0 | — | allowed | 🟢 |
| DiffSynth-Studio, LightX2V, FastVideo, cache-dit, SageAttention, Diffusers | Apache-2.0 | — | — | allowed | 🟢 |
| Z-Image, Qwen-Image(-Edit), FLUX.1-schnell | Apache-2.0 | Apache-2.0 | — | allowed | 🟢 |
| EchoMimicV3, InfiniteTalk, HuMo, Phantom, Helios | Apache-2.0 | Apache-2.0 | — | allowed | 🟢 |
| LongCat-Video | MIT | MIT | — | allowed | 🟢 |
| librosa / Beat This! / stable-ts / PySceneDetect / PyAV | ISC / MIT / MIT / BSD-3 / BSD-3 | MIT (Beat This!) | mixed datasets | allowed | 🟢 |
| LTX-2 | custom | LTX-2 Community License (2026-01-05): paid licence for entities ≥ $10M revenue; must disclose machine-generated content; AUP | — | conditional | 🟡 |
| HunyuanVideo-1.5 (and FramePack's weights) | custom | "DOES NOT APPLY IN THE EUROPEAN UNION, UNITED KINGDOM AND SOUTH KOREA"; >100M MAU needs licence; outputs may not train other models | — | conditional + territorial | 🔴 for a global self-hosted default |
| CogVideoX1.5 | Apache-2.0 | CogVideoX License: registration; ≤1M visits/month | — | conditional | 🟡 → reject |
| SkyReels-V2 | custom | Skywork Community (commercial allowed, terms not fully reviewed) | — | conditional | 🟡 |
| insightface `antelopev2` (Stand-In, InstantID, PuLID) | MIT | "non-commercial research purposes only" | — | **no** | 🔴 |
| InfiniteYou | — | CC-BY-NC-4.0 | — | no | 🔴 |
| FLUX.1-dev / Kontext-dev | — | FLUX.1-dev Non-Commercial | — | no | 🔴 |
| MAGREF | Apache-2.0 | **unstated** | — | unknown | UNKNOWN / do not adopt |
| All-In-One | MIT | unstated (+ madmom NC models) | Harmonix | unknown | UNKNOWN / do not adopt |
| Essentia | AGPL-3.0 | — | — | copyleft | 🔴 |
| ComfyUI | GPL-3.0 | — | — | copyleft | 🔴 to embed (reference only, as in Phase 1) |
| Wan2GP | WanGP Community License 2.0: may not "embed it in a paid product" | — | — | restricted | 🔴 (reference only) |
| Wan-Dancer's own output step (moviepy → libx264) | MIT + GPL encoder | — | — | GPL encoder | 🔴 — replace with Tunora's LGPL FFmpeg/OpenH264 |
| AIST++ (music-to-motion training) | — | annotations CC BY 4.0; underlying AIST Dance DB video terms **not verified** | — | unknown | UNKNOWN |

Biggest licensing risk is unchanged from the music side: **undisclosed training-data provenance** of every capable open video model (Wan family included).

---

## 15. ComfyUI Assessment

- **What exists:** native ComfyUI Wan-Dancer nodes and tutorial (fp8 global/local + lightx2v LoRA, default 5 s workflow); Kijai's WanVideoWrapper (Apache-2.0 plugin, 6.7k★) with SteadyDancer and many Wan features; community GGUF Wan-Dancer workflow.
- **What to learn:** the model file set, fp8/GGUF packaging, distill-LoRA step counts, block-swap settings, which defaults produce acceptable 16 GB runs.
- **Extractable?** The underlying inference code is already available Apache-2.0 outside ComfyUI (Wan2.2 repo, DiffSynth-Studio, Diffusers). Nothing needs to be extracted from GPL ComfyUI.

| Criterion | Direct model integration (in-process) | ComfyUI as a service | Isolated worker process (own venv) |
|---|---|---|---|
| Licensing | 🟢 Apache stacks | 🔴 GPL-3.0 core (Tunora rejected it in Phase 1) | 🟢 Apache stacks |
| Complexity | high — torch/diffusers pins collide with backend | medium setup, opaque graphs | medium |
| Maintainability | poor (pins in API venv) | workflows break with node updates | good (same pattern as ACE-Step/`align_worker`) |
| Startup time | model load blocks API | always-on server | load once per video job |
| VRAM management | API process holds VRAM | server holds VRAM between jobs | process exits → VRAM freed for ACE-Step |
| Observability | good | via websocket/history API | structured progress file / stdout |
| API control | full | graph JSON | full (Tunora-defined job manifest) |
| Testing | hard | hard | fake worker, like `FakeProvider` |
| UX | — | second UI to hide | invisible |
| Model replacement | code change in API | swap workflow | swap worker implementation |

Conclusion: **do not embed or depend on ComfyUI.** Use it only as a reference for settings.

---

## 16. Existing Tunora Architecture Reuse

| Component | Decision | How |
|---|---|---|
| `VideoOutputProfile` (`profiles.py`) | **REUSE unchanged** | Final delivery sizes/bitrates; AI videos offer HD profiles only |
| FFmpeg policy (`ffmpeg.py`) | **REUSE unchanged** | All concat/scale/encode/mux; never the model repo's moviepy/libx264 |
| `probe`, `check_background` (`renderer.py`) | **REUSE** | Validate uploaded reference images and every generated segment (decode check, pixel cap) |
| `FFmpegLibassRenderer` | **REUSE as a second pass** | An assembled AI montage can be the *background video* of an existing lyric MusicVideo — lyrics overlay for free |
| `MusicVideoStorage` / `LocalAudioStorage` containment | **EXTEND** | Same root and key rules; add `<id>/segments/<n>.mp4`, `<id>/keyframes/<n>.png` |
| Migrations (`PRAGMA user_version`) | **EXTEND** | One additive step: AI video + segment tables |
| `align_worker` subprocess pattern | **REUSE pattern** | AI video worker runs as its own process in its own venv |
| `TimedLyrics`, Version `bpm`, lyric section tags | **REUSE** | Shot planning input |
| Status vocabulary incl. `WAITING_FOR_AUDIO` (Phase 26) | **REUSE pattern** | "Audio + AI Video" in one request |
| `FAILURE_MESSAGES` / `public_error` allowlist | **REUSE pattern** | No internals in responses |
| Restart recovery | **EXTEND (deliberately different)** | Lyric renders become FAILED on restart because a render cannot resume. AI segments are durable files, so an interrupted AI video resumes at the first unfinished segment |
| `JobService`, Song/Version/Job model, `MusicGenerationProvider`, ACE-Step adapter, lyric-video pipeline | **UNTOUCHED** | AI video only references a Version, like MusicVideo |
| `MusicVideo` entity | **Do not overload** | It requires lyrics, a background upload, a style allowlist and an immutable background trigger; an AI video has a plan, segments and character references. A separate `AIMusicVideo` entity that links `song_id`/`source_version_id` the same way avoids a polymorphic table |

---

## 17. Storage Analysis

Assumptions (INFERRED): segments stored as H.264 intermediates at ~10 Mb/s (≈6.3 MB per 5 s 704×1280 clip); keyframe PNG ≈ 1.5–2 MB; final HD at the existing 8 Mb/s cap (Phase 27 measured averages were lower: 2.9–4.7 Mb/s for MP4 backgrounds); 30% retry overhead.

| Item | 3-min montage | 5-min montage |
|---|---|---|
| Clips (30–60 / 50–100) | 190–380 MB | 315–630 MB |
| Retries (+30%) | 60–115 MB | 95–190 MB |
| Keyframe images | 60–120 MB | 100–200 MB |
| Final HD MP4 (≤ 8 Mb/s) | ≤ 180 MB | ≤ 300 MB |
| **Peak during job** | ≈ 0.5–0.8 GB | ≈ 0.8–1.3 GB |
| Retained, final only | ≈ 0.2 GB | ≈ 0.3 GB |

| Library | Final only (3 min / 5 min) | Keep segments (3 min / 5 min) |
|---|---|---|
| 1 video | 0.2 / 0.3 GB | 0.7 / 1.1 GB |
| 10 | 2 / 3 GB | 7 / 11 GB |
| 50 | 9 / 15 GB | 35 / 55 GB |
| 100 | 18 / 30 GB | 70 / 110 GB |

Model weights: TI2V path ≈ 18.2 GB; Z-Image-Turbo official repo 32.9 GB (single-file repacks smaller, UNVERIFIED); Wan-Dancer fp8 path ≈ 45.7 GB. With 68 GB free on the largest drive, **disk is a first-class constraint**.

Lifecycle (simplest local design): segments and keyframes are kept until the final MP4 passes validation, then deleted by default (manifest + seeds kept so any shot can be regenerated); failed jobs keep completed segments for resume until the user deletes the video; a pre-flight free-space check refuses to start below a threshold. No distributed storage.

Compute (INFERRED): GPU time dominates (Section 20); assembly CPU time ≈ the existing renderer's cost (≤ 1 min per 60 s at HD); RAM peak is the model offload footprint; disk throughput is negligible except model loading (18–46 GB read per job start → load once per job, not per segment).

---

## 18. Reliability Analysis

Design for "resume scene 17 of 42":

- **Plan first, persist first:** the shot plan (per shot: index, start/end time, prompt, keyframe key, seed, size) is written to SQLite before any GPU work — same "commit before calling the provider" rule as Song/Version/Job.
- **Segment rows** with status `PENDING/GENERATING/COMPLETED/FAILED`, `attempts`, output key, error code. A segment is COMPLETED only after its file passes validation (ffprobe duration/frames/size, one-frame decode via existing `check_background`, FFmpeg `blackdetect`/`freezedetect` heuristics — LGPL filters, availability in the approved build UNVERIFIED).
- **Deterministic seeds:** `seed = base_seed + index` (Wan-Dancer uses `idx*10 + seed`). GPU kernels are not bit-exact, so this gives *reproducible intent*, not identical pixels.
- **Crash/restart:** on startup, a `GENERATING` segment returns to `PENDING`; the video resumes from the first non-COMPLETED segment. Completed segments are never regenerated.
- **Retry:** per segment, bounded attempts with a new seed; after N failures the video is FAILED with completed segments kept for a manual retry.
- **GPU failure / OOM:** worker exits non-zero → segment FAILED with code `gpu_oom`/`worker_crashed`; the worker process boundary keeps the API alive (same reason `align_worker` is a subprocess).
- **Duration mismatch:** assembly trims/pads to the song's probed duration; the existing renderer already rejects >1 s mismatches.
- **Final assembly failure:** assembly is idempotent (re-run from validated segments).
- **Wan-Dancer exception:** its local segments depend on the global pass and on the previous segment's boundary frame — resumable in order only, and a regenerated segment can break continuity with its neighbour.

---

## 19. Security Analysis

| Risk | Control (mostly existing) |
|---|---|
| Uploaded reference images | Existing allowlist, magic bytes, size cap, ffprobe + one-frame decode, 7680×4320 pixel cap (decompression bombs) |
| Paths / filenames | Tunora-generated ids only; existing `LocalAudioStorage` containment; nothing from the client becomes a path |
| FFmpeg arguments | Existing argument-list execution, `-protocol_whitelist file`, no shell, prompts never on a command line |
| Prompts / model inputs | Passed to the worker via a JSON manifest file, never argv/shell; length limits as in `director/validation.py` |
| Model weight loading | Prefer **safetensors** (Comfy-Org repacks) over the official `.pth` files (pickle can execute code); pin SHA-256 of every downloaded weight, especially community GGUFs (one repo already shipped corrupt quants) |
| Resource exhaustion | One GPU job at a time; per-segment timeout; pre-flight disk check; cap song length per milestone |
| GPU contention | ACE-Step and the video worker never run models concurrently (Section 13) |
| Network exposure | Backend and worker bind to 127.0.0.1 only (worker needs no port at all) |
| Likeness / deepfakes | Default flow generates original characters; uploading photos of real people is a product-policy decision (open question); LTX-2's AUP and output-disclosure rule would apply if ever adopted |
| Inappropriate content | Negative prompts and a style allowlist; the HF ecosystem around dance models includes NSFW LoRAs — never auto-download LoRAs |

---

## 20. Performance Analysis

**Measured on this machine: nothing.** No model was run (audit-only phase). All figures below are OFFICIAL/REPORTED anchors or INFERRED extrapolations.

Anchors:
- OFFICIAL: TI2V-5B, 5 s 720p "under 9 minutes on a single consumer-grade GPU" (4090-class, unoptimized, with offload).
- REPORTED: Wan2.2 Q8 GGUF, 1024×574, 5 s ≈ 7 min on a 5060 Ti 16 GB (64 GB RAM, SageAttention).
- INFERRED: Wan-Dancer local segment ≈ 136,800 tokens vs ≈ 27,280 for a TI2V-5B clip; with 2.8× the parameters and 24 vs ~50 steps, a Wan-Dancer segment is roughly an order of magnitude more compute than a TI2V clip.

Scenario extrapolation for the montage path (INFERRED, **not measured**; `total = clips × minutes_per_clip × 1.3 retries`):

| Per-clip time (5 s) | 5 s | 10 s | 30 s | 60 s | 3 min (30–60 clips) | 5 min (50–100 clips) |
|---|---|---|---|---|---|---|
| Optimistic 3 min (distilled steps + fp8 + fast attention) | 3 min | 6 min | 20–40 min | 40–80 min | 2–4 h | 3.3–6.5 h |
| Central 8 min | 8 min | 16 min | 1–2 h | 1.7–3.5 h | 5–10 h | 9–17 h |
| Pessimistic 20 min (unoptimized, offload-bound) | 20 min | 40 min | 2.2–4.3 h | 4.3–8.7 h | 13–26 h | 22–43 h |

Plus keyframe images (UNVERIFIED; Z-Image-Turbo uses 8 steps) and assembly (minutes). The product is an **overnight batch job** at best; a 3-minute video in the pessimistic case is a multi-day job and would not be acceptable — Phase A decides which row is real.

---

## 21. Reuse Matrix

| Capability | Existing project | License | Evidence | Fit | VRAM | Decision |
|---|---|---|---|---|---|---|
| Short video clips (T2V/I2V) | Wan2.2 TI2V-5B | 🟢 Apache-2.0 | OFFICIAL README | high | ≥24 GB official; 8 GB ComfyUI claim | **REUSE** |
| Higher-quality clips | Wan2.2 I2V-A14B + lightx2v LoRA | 🟢 Apache-2.0 | OFFICIAL + REPORTED | high | REPORTED 16 GB w/ 64 GB RAM | **ADAPT** (comparison arm) |
| Music-conditioned solo dance | Wan-Dancer | 🟢 Apache-2.0 | VERIFIED code | medium (solo, portrait) | 8× A800 official | **ADAPT (spike only)** |
| Inference runtime / offload | DiffSynth-Studio, Diffusers | 🟢 Apache-2.0 | OFFICIAL | high | — | **REUSE** |
| Speed-ups | lightx2v, FastVideo, cache-dit, SageAttention | 🟢 Apache-2.0 | OFFICIAL | high | — | **ADAPT** (measure) |
| Keyframe / character images | Z-Image-Turbo | 🟢 Apache-2.0 | OFFICIAL "16G" | high | 16 GB official | **REUSE** |
| Same character, new set | Qwen-Image-Edit-2509 / Z-Image-Edit | 🟢 Apache-2.0 | OFFICIAL | medium | UNVERIFIED | **ADAPT** |
| Singer close-ups (lip sync) | EchoMimicV3 / Wan2.2-S2V / InfiniteTalk | 🟢 Apache-2.0 | OFFICIAL | medium | 12 GB official (EchoMimicV3 Flash) | **REFERENCE** (later) |
| Pose-driven dance | VACE / SteadyDancer / Wan-Animate | 🟢 (driving videos 🟡) | OFFICIAL | medium | UNVERIFIED | **REFERENCE** |
| Long single take | LongCat-Video / Helios | 🟢 MIT / Apache | OFFICIAL | low for refs | Helios ~6 GB official | **REFERENCE** |
| Audio-to-video | LTX-2 A2V | 🟡 community licence | OFFICIAL | medium | UNVERIFIED | **REFERENCE** |
| Tempo, sections, line timing | Version metadata, lyric tags, stable-ts TimedLyrics | 🟢 (in Tunora) | VERIFIED code | high | CPU | **REUSE** |
| Beat positions | librosa | 🟢 ISC | VERIFIED (used in audit) | high | CPU | **REUSE** |
| Beats + downbeats | Beat This! | 🟢 MIT | OFFICIAL | high | CPU/GPU | **ADAPT** (if needed) |
| Structure for instrumentals | All-In-One | UNKNOWN weights | OFFICIAL | — | — | **UNKNOWN** |
| Face-ID adapters | Stand-In / InstantID / PuLID | 🔴 (antelopev2) | VERIFIED | — | — | **REJECT** |
| Encoding, concat, scale, mux | Tunora FFmpeg policy + renderer | 🟢 LGPL build | VERIFIED code | high | CPU | **REUSE** |
| Shot-cut detection (QA/analysis) | PySceneDetect | 🟢 BSD-3 | OFFICIAL | medium | CPU | **REFERENCE** (FFmpeg `select=scene` was enough here) |
| Frame interpolation / upscale | RIFE (MIT), Real-ESRGAN | 🟢/UNVERIFIED | — | low priority | — | **REFERENCE** |
| Workflow UI | ComfyUI / Wan2GP | 🔴 GPL / 🔴 no paid embedding | VERIFIED licences | — | — | **REFERENCE** |
| Music-to-motion | EDGE / Bailando / LODGE | mixed / UNKNOWN data | — | low | — | **REFERENCE** |

REUSE/ADAPT details:

| Candidate | Repository | Exact component | What Tunora reuses | Integration complexity | Legal notes |
|---|---|---|---|---|---|
| Wan2.2 TI2V-5B | github.com/Wan-Video/Wan2.2, HF Wan-AI/Wan2.2-TI2V-5B (Diffusers variant) | `WanPipeline`/TI2V via Diffusers or DiffSynth | Clip generation inside the worker | medium (own venv, cu128 torch) | Apache-2.0; training data undisclosed |
| Wan2.2 I2V-A14B + lightx2v | HF Wan-AI/Wan2.2-I2V-A14B, lightx2v/Wan2.2-Distill-Loras | I2V + 4-step LoRA | Quality arm | high (RAM) | Apache-2.0 |
| Wan-Dancer | github.com/Wan-Video/Wan-Dancer, HF Comfy-Org/Wan-Dancer (fp8) | `diffsynth` pipeline, global/local scripts minus USP | Solo dance shot spike | high (re-pin, remove 8-GPU assert, offload) | Apache-2.0; replace moviepy/libx264 output |
| DiffSynth-Studio / Diffusers | modelscope/DiffSynth-Studio, huggingface/diffusers | VRAM management, fp8, offload | Runtime | medium | Apache-2.0 |
| Z-Image-Turbo | HF Tongyi-MAI/Z-Image-Turbo | T2I pipeline | Keyframes / character sheet | medium | Apache-2.0 |
| librosa / Beat This! | librosa/librosa, CPJKU/beat_this | `beat_track` / `File2Beats` | Beat grid | low | ISC / MIT |

---

## 22. "Do Not Reinvent" Findings — WHAT WE SHOULD NOT BUILD

| Do not build | Existing wheel | Why it is good | License | Tunora strategy |
|---|---|---|---|---|
| A video generation model / diffusion framework | Wan2.2, Wan-Dancer, LongCat, Helios | Trained on data and compute Tunora cannot match | Apache/MIT | Call through a worker |
| A sampler/scheduler, VAE, attention kernels | Diffusers, DiffSynth, SageAttention | Maintained, optimized | Apache-2.0 | Configure, don't write |
| Quantization / offloading | fp8 repacks, GGUF, DiffSynth VRAM management, Diffusers group offload | Already tuned for consumer GPUs | Apache-2.0 | Choose settings in Phase A |
| Step distillation / caching | lightx2v, FastVideo, cache-dit | Large speed-ups | Apache-2.0 | Measure, adopt if quality holds |
| Beat/tempo detection | librosa, Beat This!, ACE-Step `bpm` | Mature; already used | ISC/MIT | Reuse |
| Lyric/section timing | stable-ts TimedLyrics (already in Tunora) | Already validated in Phase 22–23 | MIT | Reuse |
| Identity/face-ID model | Image-model keyframes + I2V first frame | Works without non-commercial face models | Apache-2.0 | Reuse |
| Video encode/concat/scale/mux/subtitles | Tunora's LGPL FFmpeg + libass renderer | Already policy-checked and tested | LGPL/ISC | Reuse |
| Video validation | ffprobe + decode check (`check_background`), FFmpeg `blackdetect`/`freezedetect` (presence in the approved build to verify) | ffprobe/decode already in code | LGPL | Reuse |
| A node/workflow engine | ComfyUI (reference only) | — | GPL | Not needed: a fixed pipeline |
| Distributed queue / storage | — | Not needed for one GPU | — | SQLite + local files |

---

## 23. What Tunora Should Build

Verified as product-specific (no OSS does these *for Tunora's data model*):

1. **Song → AI video workflow** linked to an immutable source Version (same contract as `MusicVideo`).
2. **Shot planner** (deterministic first, no LLM): section tags + TimedLyrics + beat grid + a style preset → list of shots with times, prompts, seeds, orientation. (The existing Song Director wraps ACE-Step's music LM and cannot plan shots.)
3. **Minimal provider boundary** for clip generation (Section 25).
4. **Worker manifest + progress protocol** between backend and the isolated worker.
5. **Segment persistence, validation, resume, retry** (extends existing patterns).
6. **GPU arbitration with ACE-Step** (only one model owner at a time).
7. **Assembly** = a new FFmpeg command in the existing policy/renderer style (concat + cut-on-beat trims + scale + audio mux), optionally followed by the existing lyric renderer.
8. **UX:** create from Song Details, show plan/progress per shot, regenerate one shot, library integration, HD profiles only.

---

## 24. Architecture Options

| | A: Direct Wan-Dancer in the backend process | B: Isolated video worker (own venv) + minimal clip provider | C: ComfyUI execution backend | D: Long-lived model server (like ACE-Step, HTTP :8002) |
|---|---|---|---|---|
| Complexity | high (torch/diffusers/flash-attn pins inside API venv) | medium | medium setup, opaque | medium |
| License | 🟢 | 🟢 | 🔴 GPL core | 🟢 |
| Maintainability | poor | good (mirrors `align_worker`, ACE-Step submodule) | poor (node churn) | good |
| VRAM control | API holds VRAM; conflicts with ACE-Step | process exits after the job → VRAM freed | server holds VRAM | server holds VRAM → conflicts with ACE-Step resident 11.6 GB |
| Performance | load once | load once per job | load once | load once |
| Tunora integration | tight but fragile | clean: manifest in, files + progress out | graph JSON | HTTP API to design |
| Testing | hard | fake worker in unit tests | hard | fake server |
| Observability | logs | progress file + exit codes + logs | websocket | HTTP |
| Model replacement | rewrite | swap worker implementation | swap workflow | swap server |
| Matches references | no (solo, one take) | yes (montage) + can host Wan-Dancer later | yes | yes |

Constraint summary: A fails maintainability and GPU sharing; C fails licensing (already rejected for Tunora); D fails the 16 GB GPU-sharing constraint unless it can unload models on demand; **B satisfies all hard constraints.**

---

## 25. Recommended Architecture

Modular monolith + one isolated worker process. No Redis/Celery/Kafka/Kubernetes/microservices/cloud.

```
Song Details ──POST /api/songs/{id}/ai-videos──► AIMusicVideoService (backend, in-process)
   │                                              │ 1. plan shots  (TimedLyrics + bpm + librosa beats + style preset)
   │                                              │ 2. persist plan + segment rows (SQLite, one migration step)
   │                                              │ 3. acquire GPU (ACE-Step idle/stopped)
   │                                              ▼
   │                                   video_worker (separate venv/process, torch cu128)
   │                                     loads models once per job
   │                                     for each PENDING shot: keyframe image → I2V clip → write file
   │                                     reports progress (JSON lines), exits → VRAM freed
   │                                              │
   │                                   backend validates each clip (ffprobe/decode) → segment COMPLETED
   │                                              ▼
   │                                   assemble with approved LGPL FFmpeg → VideoOutputProfile (HD)
   │                                   (optional) feed result as background to existing lyric renderer
   ▼
Library / Song Details show the AI video next to lyric videos
```

Minimum provider boundary (inside the worker, model-specific code only there):

```
class VideoClipProvider:            # one implementation per model family
    def load(self) -> None
    def generate(self, shot: ShotSpec) -> Path   # prompt, keyframe path, duration, size, seed, optional audio slice
```

Wan-Dancer would be a second implementation that also needs a whole-song `prepare(audio, reference_image)` step for its global pass — add that method only when Wan-Dancer is actually adopted. No separate MusicAnalyzer/ScenePlanner/VideoAssembler/VideoValidator *services*: they are functions/modules inside `ai_music_videos/`, as `aligner.py`/`renderer.py` are today.

---

## 26. MVP Definition

**Prove the hardest risk first: can this machine generate acceptable dancer clips at a usable rate, and do montaged clips over a real Tunora song feel like a music video?**

MVP ("AI Music Video Preview"):
- One existing Tunora song Version, **30 seconds** (one section), real ACE-Step audio.
- **One orientation: 9:16** (704×1280 generation → `vertical_hd` delivery).
- One style preset (e.g. "Indian festive stage", original — no imitation of any channel), one lead "look" from one character-sheet image.
- ~8–12 shots, cuts on beats, scene change at the section boundary.
- Real AI-generated dancers via TI2V-5B (or I2V-A14B if Phase A shows it is affordable).
- Final MP4 through the existing FFmpeg pipeline; resumable per shot.
- Not in MVP: 16:9, multiple characters' identity, lip sync, Wan-Dancer, 4K, regenerating single shots from the UI, uploads of real people.

---

## 27. Experiment Matrix

All experiments run in a lab directory **outside the Tunora app** (e.g. `I:\Tunora-validation\ai-video\`), with ACE-Step stopped, nothing committed except the lab report. Each records: VRAM peak (`nvidia-smi --query-gpu=memory.used -lms 500`), system RAM peak, wall time, steps, settings, file size, ffprobe output, pass/fail.

| ID | Model / settings | Input | Output | Measure | Pass criteria |
|---|---|---|---|---|---|
| E0 | Environment | — | venv with torch cu128 (sm_120), Diffusers/DiffSynth | import + 1 tiny run | sm_120 kernels run; no CUDA arch error |
| E1 | TI2V-5B fp16, offload, default steps | text prompt "group of dancers in festive costumes on a palace stage", 704×1280, 121 f | 5 s MP4 | time, VRAM, RAM | completes; VRAM ≤ 15 GB; RAM ≤ 28 GB |
| E2 | E1 as I2V | keyframe image (E5) | 5 s MP4 | same + first-frame similarity | completes; first frame matches keyframe visually |
| E3 | E2 at 1280×704 | landscape keyframe | 5 s MP4 | same | completes; composition intact |
| E4 | E2 + speed-ups (fp8 / distilled steps / SageAttention / cache-dit), one at a time | same | 5 s MP4 | time vs quality vs E2 | ≥2× faster with no obvious quality loss (human judged) |
| E5 | Z-Image-Turbo | character sheet + 10 scene prompts | 704×1280 PNGs | time, VRAM | ≤ 1 min/image; same costume/look across 10 images (human judged) |
| E6 | I2V-A14B GGUF Q8/Q4 + lightx2v 4-step, block swap | E5 keyframe | 5 s MP4 | time, VRAM, RAM | runs with 31.6 GB RAM without swapping to disk |
| E7 | Wan-Dancer local stage, 1 segment, fp8 or GGUF, offload, sm_120 re-pin, USP removed | reference image + 5 s of a Tunora song | 4.97 s MP4 | time, VRAM, RAM, does it run | runs at all; record time; human-judged dance quality |
| E8 | Wan-Dancer global stage, single GPU | same + full 30 s song | 149-frame keyframe video | same | runs at all without 8 GPUs |
| E9 | Stability | best of E2/E4/E6 | 20 clips back-to-back | failure rate, time variance, thermals | ≥ 95% success; no VRAM growth across runs |
| E10 | Montage | 10 clips + 30 s Tunora song | 30 s 9:16 MP4 via lab FFmpeg script (LGPL build) | cut-on-beat accuracy, A/V duration | duration = song ±0.05 s; plays in Chrome; human review "feels like a music video" |

Human judgement is required for anatomy, hands, faces, dance motion and "music-video feel". Score each 1–5 on: anatomy, hands, faces, motion smoothness, background stability, costume consistency, identity consistency, beat feel. "Good enough" for MVP = median ≥ 3 on every axis, no shot below 2 on anatomy, ≥ 70% of generated clips usable without retry.

---

## 28. Implementation Roadmap

**Phase 29 — AI Video Feasibility Lab** (next)
- Goal: replace every UNVERIFIED hardware/time number with a measurement.
- Why: all go/no-go decisions depend on per-clip time, VRAM/RAM and quality on this machine.
- OSS reused: Wan2.2 TI2V-5B, I2V-A14B + lightx2v, Z-Image-Turbo, Wan-Dancer, Diffusers/DiffSynth, librosa.
- New Tunora code: none (lab scripts outside the app).
- Hardware: this machine, ACE-Step stopped.
- Tests: E0–E10.
- Acceptance: report with measured table, chosen model + settings, per-clip time, failure rate.
- Risks: sm_120 compatibility, RAM limit, disk space.
- Exit: per-clip time ≤ 10 min at acceptable quality → proceed; otherwise stop or revisit (RAM upgrade, lower resolution).

**Phase 30 — 30 s AI Music Video Preview (MVP, 9:16)**
- Goal: Section 26 inside Tunora.
- OSS reused: Phase 29 winners; existing FFmpeg policy, profiles, storage, migrations, TimedLyrics.
- New code: `ai_music_videos/` (service, repository, planner functions, assembly command), worker venv + `VideoClipProvider`, one migration step, minimal API + Song Details card.
- Hardware: same.
- Tests: unit (fake worker, planner, resume), integration (real FFmpeg assembly over fake clips), smoke (real worker, marked like ACE-Step smoke), Playwright (one real run).
- Acceptance: a 30 s video from a real Tunora Version; restart mid-job resumes at the next shot; no internals in responses.
- Risks: GPU arbitration with ACE-Step; worker env fragility.
- Exit: 3 consecutive successful runs; human review passes.

**Phase 31 — 60 s and section-aware planning**
- Goal: whole-verse/chorus coverage, beat-cut assembly, character sheet → per-section keyframes, per-shot regenerate.
- New code: planner presets, shot regeneration endpoint.
- Acceptance: 60 s video ≤ the time budget measured in Phase 29 × 2; ≤ 10% shots need regeneration.

**Phase 32 — 16:9 and dual delivery**
- Goal: landscape native generation; optional letterbox 16:9→9:16 output mode in the renderer.
- Acceptance: both orientations from one plan; no centre-crop.

**Phase 33 — 2–3 minute overnight jobs**
- Goal: full songs as batch jobs; storage lifecycle (intermediate cleanup, pre-flight disk check); progress/ETA UX.
- Acceptance: 3 min video completes unattended within the measured budget; resume after forced restart; disk returns to final-only size.

**Phase 34 — Optional shot types (each its own spike)**
- Wan-Dancer solo dance shots (only if E7/E8 passed), singer lip-sync close-ups (EchoMimicV3/S2V), lyrics overlay on AI video via the existing renderer.

**Phase 35 — 5-minute reliability**
- Only after Phase 33 metrics: failure rate, time variance, thermal stability over 50–100 clips.

---

## 29. Risk Register

| Risk | Probability | Impact | Evidence | Mitigation |
|---|---|---|---|---|
| VRAM: 14B models don't fit 16 GB | High | High | fp8 = 18.34 GB/stage; official 80 GB examples | Start with TI2V-5B; offload; GGUF only with hash pinning |
| System RAM 31.6 GB too small for offload | High (14B) / Medium (5B) | High | VERIFIED RAM; REPORTED 64 GB in the only 16 GB report | Measure in E6/E7; 64 GB upgrade is a known fix |
| Generation time makes 3–5 min impractical | Medium–High | High | Section 20 range 2 h – 43 h | Phase 29 gates; distilled steps; 30 s → 60 s ladder |
| ACE-Step and video both need the GPU | Certain | Medium | VERIFIED: ~11.6 GB resident, no unload API | Exclusive GPU ownership; stop/offload ACE-Step during video jobs |
| sm_120 incompatibility of model stacks | Medium | High | VERIFIED: Wan-Dancer pins cu124 | Use cu128 stacks; E0 first |
| Model quality (anatomy, hands, group dance) | High | High | no local evidence; group dance hardest | Shot length ≤ 5 s, more wide/medium shots, human review gates |
| Character drift across shots | Medium | Medium | references tolerate costume changes | Keyframes from one character sheet; style-level consistency target |
| Dance drift / long-take continuity | Low (montage) / High (Wan-Dancer) | Medium | references are 2–3 s shots | Montage first |
| Audio sync | Low | Medium | references cut at chance | Beat-cut assembly; exact duration mux |
| Storage | Medium | Medium | 68 GB max free; 0.7–1.3 GB peak/video; 18–46 GB models | Delete intermediates; pre-flight check |
| Windows compatibility | Medium | High | Wan-Dancer Linux-only; flash_attn | Diffusers/DiffSynth on Windows; WSL2 as fallback (adds complexity) |
| Licensing — training data provenance | High (unknown) | High | undisclosed for Wan family and Wan-Dancer | Record in LICENSE-AUDIT; product-level disclosure |
| Licensing — accidental NC component | Medium | High | antelopev2, FLUX-dev, InfiniteYou found | Rejection list in this doc; review per dependency |
| Model availability | Low | Medium | Apache weights mirrored on HF/ModelScope | Pin hashes; keep local copies |
| Maintenance (Wan-Dancer inactive since 2026-07-17) | Medium | Medium | VERIFIED | Wan-Dancer secondary only |
| Dependency risk (torch/diffusers pins) | Medium | Medium | — | Separate worker venv, like ACE-Step |
| Security (pickle weights, uploads) | Low | High | official `.pth` files | safetensors only; existing upload checks |
| UX: multi-hour jobs | High | Medium | Section 20 | Overnight mode, per-shot progress, preview of first shots |

---

## 30. Open Questions

1. Is a RAM upgrade (31.6 → 64 GB) acceptable if Phase 29 shows it is the limiting factor?
2. May the video job stop ACE-Step automatically, or must the user switch modes explicitly?
3. Product policy for uploading photos of real people as the lead character.
4. Is 720p-generated / 1080p-delivered acceptable (the references themselves are 720p)?
5. Should AI videos keep segments for later re-editing (≈3–4× storage) or only the final MP4?
6. Instrumental songs: allowed for AI video (unlike lyric videos)? Section structure then needs Beat This!/structure analysis.
7. Is a disclosure label ("AI-generated video") wanted in the product regardless of license?
8. Does the user want Wan-Dancer-style *continuous solo dance* at all, given the references are montages?

---

## 31. Final Decision

**Can Tunora realistically support 3–5 minute AI music videos locally on an RTX 5060 Ti 16 GB? → NOT YET.**

Evidence: the montage structure that matches the references needs 30–60 (3 min) or 50–100 (5 min) short clips; Apache-2.0 models exist for every step; but per-clip time, VRAM/RAM fit (31.6 GB RAM, ACE-Step co-residency) and quality are UNVERIFIED on this machine, and the extrapolated range (2 h to 43 h for 3–5 min) spans "overnight job" to "impractical". It becomes "YES, WITH CONDITIONS" if Phase 29 measures ≤ ~10 min per acceptable 5 s clip.

| Question | Answer |
|---|---|
| Can 9:16 be supported? | Yes — native 704×1280 (TI2V-5B) / 720×1280 (Wan-Dancer) → `vertical_hd`. |
| Can 16:9 be supported? | Yes — native 1280×704 for TI2V-5B; Wan-Dancer landscape UNVERIFIED. |
| Same architecture for both? | Yes — orientation is a plan parameter; generation and delivery profiles differ only in size. |
| Smallest viable first milestone | 30 s, one section, 9:16, one style, TI2V-5B clips cut on beats over a real Tunora song. |
| Biggest technical risk | Per-clip generation time on 16 GB VRAM + 31.6 GB RAM. |
| Biggest quality risk | Anatomy/hands in multi-dancer shots. |
| Biggest licensing risk | Undisclosed training-data provenance of all capable video models; plus avoiding NC face/identity components. |
| Biggest hardware risk | RAM-bound offloading and GPU co-residency with ACE-Step. |

---

## Evidence Index (checked 2026-10-03)

Primary sources:
- Wan-Dancer: https://github.com/Wan-Video/Wan-Dancer (README, `gen_video/gen_video_global.py`, `gen_video/gen_video_local.py`, LICENSE) · https://huggingface.co/Wan-AI/Wan-Dancer-14B · https://arxiv.org/abs/2607.09581 · https://humanaigc.github.io/wan-dancer-project/ · https://docs.comfy.org/tutorials/video/wan/wan-dancer · https://huggingface.co/Comfy-Org/Wan-Dancer · https://huggingface.co/realrebelai/Wan_Dancer_GGUFs (community)
- Wan2.2 README (VRAM/size statements): https://github.com/Wan-Video/Wan2.2 · ComfyUI Wan2.2 docs: https://docs.comfy.org/tutorials/video/wan/wan2_2 · Comfy-Org repacks: https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged, https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged
- Licenses: LTX-2 https://huggingface.co/Lightricks/LTX-2/blob/main/LICENSE · HunyuanVideo-1.5 https://huggingface.co/tencent/HunyuanVideo-1.5/blob/main/LICENSE · CogVideoX1.5 https://huggingface.co/zai-org/CogVideoX1.5-5B-I2V/blob/main/LICENSE · SkyReels-V2 https://huggingface.co/Skywork/SkyReels-V2-DF-1.3B-540P/blob/main/LICENSE · insightface https://github.com/deepinsight/insightface · Wan2GP https://github.com/deepbeepmeep/Wan2GP (LICENSE.txt)
- Other models: https://github.com/PKU-YuanGroup/Helios · https://huggingface.co/meituan-longcat/LongCat-Video · https://github.com/Lightricks/LTX-2 · https://github.com/antgroup/echomimic_v3 · https://humanaigc.github.io/wan-s2v-webpage/ · https://github.com/WeChatCV/Stand-In · https://huggingface.co/Tongyi-MAI/Z-Image-Turbo
- Music analysis: https://github.com/CPJKU/beat_this · https://github.com/mir-aidj/all-in-one · https://github.com/librosa/librosa · AIST++ terms https://google.github.io/aistplusplus_dataset/factsfigures.html
- License/metadata for all other repos/models: GitHub REST API (`/repos/{owner}/{repo}`) and Hugging Face API (`/api/models/{id}`), queried 2026-10-03.

Community sources (labelled REPORTED): https://huggingface.co/Wan-AI/Wan2.2-Animate-14B/discussions/4 (5060 Ti 16 GB, Q8 GGUF, ~7 min/5 s, 64 GB RAM). Search-result blog claims of "2–4 min per 720p clip on a 5060 Ti" were found but not used because no first-hand measurement was given.

Local measurements: `ffprobe`/`cropdetect`/`select=scene` on the three reference files; librosa beat tracking (latest PyPI release at run time, ephemeral `uv run --with librosa`, scratch directory); `nvidia-smi`; ACE-Step venv torch build; `Win32_ComputerSystem` RAM; drive free space; grep of `ACE-Step-1.5/acestep/api`.

---

## FINAL ARCHITECTURAL DECISION

1. **Should Tunora pursue AI Music Video generation?** Yes — as a staged, evidence-gated capability starting with a 30 s montage preview. Not as a committed 3–5 minute feature yet.
2. **Should Wan-Dancer be investigated as the primary candidate?** No. Investigate it as a **secondary spike** (E7/E8). It is solo-only, single-take, 8-GPU-reference, sm_120-incompatible as pinned, and does not match the references' ensemble montage style. The primary candidate is the Wan2.2 family (TI2V-5B first) with keyframe images.
3. **Is RTX 5060 Ti 16 GB sufficient?** **Currently unverified.** Plausibly conditionally sufficient for TI2V-5B clips; high risk for 14B models with 31.6 GB RAM.
4. **Should generation be segmented?** Yes — always. As independent, keyframe-anchored shots (montage), each persisted and resumable.
5. **Can 9:16 and 16:9 share one architecture?** Yes; orientation is a plan parameter with native generation per orientation and existing HD delivery profiles.
6. **What should be reused?** Wan2.2 models, Diffusers/DiffSynth runtimes and speed-ups, Z-Image for keyframes, librosa (+ Beat This! if needed), Tunora's TimedLyrics/BPM/section tags, FFmpeg policy, renderer, `VideoOutputProfile`, storage, migrations, worker-subprocess pattern, failure-message allowlist.
7. **What should NOT be built?** Video/image models, diffusion runtimes, quantization/offload, beat detection, identity models, encoders, a workflow engine, any distributed queue or storage.
8. **What should Tunora own?** Song→video workflow, shot planner, minimal clip-provider boundary, worker manifest/progress protocol, segment persistence/validation/resume, GPU arbitration with ACE-Step, assembly command, UX.
9. **Smallest next experiment?** E0–E2 + E10: generate one 5 s 704×1280 TI2V-5B clip from a Z-Image keyframe on this machine with ACE-Step stopped, recording time/VRAM/RAM; then montage 10 such clips over a 30 s Tunora song.
10. **Name of the next phase:** **Phase 29 — AI Video Feasibility Lab.**

---

## NEXT PHASE MASTER PROMPT

```
You are acting as the Tunora engineer for Phase 29 — AI Video Feasibility Lab.

Read first: docs/AI-MUSIC-VIDEO-OSS-FEASIBILITY-AUDIT.md (especially §13, §20, §27), CLAUDE.md,
docs/TUNORA-SERVICE-MANAGEMENT.md, docs/LICENSE-AUDIT.md.

GOAL
Replace the audit's UNVERIFIED hardware/time/quality numbers with measurements on this machine
(RTX 5060 Ti 16 GB, 31.6 GB RAM, Windows 11). This is a LAB phase.

HARD RULES
- Do NOT modify Tunora application code, dependencies, migrations, APIs or UI.
- Work only in a lab directory outside the app (e.g. I:\Tunora-validation\ai-video\) with its own venv
  (torch built for CUDA 12.8 / sm_120). Nothing from the lab is added to Tunora's venvs.
- Stop ACE-Step before GPU runs (stop-tunora.ps1 or stop port 8001 only) and record that you did.
- Use only components classified 🟢 in the audit. Prefer safetensors; record SHA-256 of every
  downloaded weight. Check free disk space before every download.
- Assembly experiments use the approved LGPL FFmpeg build (backend/tools/ffmpeg or TUNORA_FFMPEG_DIR),
  never moviepy/libx264.
- Never fabricate numbers. Every result is VERIFIED (measured), FAILED, or NOT TESTED.
  Quality (anatomy, hands, faces, motion, "feels like a music video") is judged by the user;
  you report objective facts only.

EXPERIMENTS (in order; stop and report if E0 or E1 fails)
E0 environment: torch cu128 imports, sm_120 kernel runs.
E1 Wan2.2 TI2V-5B T2V, 704x1280, 121 frames, offload settings from the official README / Diffusers.
E2 same as I2V from a Z-Image-Turbo keyframe (E5 can run first to produce it).
E3 1280x704 landscape.
E4 speed-ups one at a time (fp8, distilled steps, SageAttention, cache-dit), same seed/prompt.
E5 Z-Image-Turbo: one character sheet + 10 scene keyframes, same look.
E6 Wan2.2 I2V-A14B (GGUF or fp8) + lightx2v 4-step LoRA — only if disk/RAM allow; record RAM swap.
E7/E8 Wan-Dancer local (1 segment) and global stage on one GPU — time-boxed spike; report "does not run"
      honestly if the 8-GPU/USP/sm_120 issues block it.
E9 stability: 20 clips back-to-back with the best configuration.
E10 30 s montage over a real Tunora song (one section), cuts on librosa beats, exact audio duration,
    9:16 1080x1920 output.

For every run record: model, quantization, resolution, frames, steps, attention backend, offload mode,
wall time, peak VRAM (nvidia-smi -lms 500), peak system RAM, output file ffprobe, success/failure, error.

DELIVERABLE
docs/PHASE-29-AI-VIDEO-FEASIBILITY-LAB.md with: environment, per-experiment tables, chosen model +
settings, measured per-clip time, failure rate, disk used, the recomputed 30 s / 60 s / 3 min / 5 min
estimates (labelled extrapolation), user quality scores (placeholders for the user to fill), and a
GO / NO-GO recommendation for Phase 30 (30 s AI Music Video Preview, 9:16).
GO requires: an acceptable 5 s clip in ≤ 10 min, ≥ 95% success over E9, RAM without disk swapping.

Commit only the lab report (one commit). Do not push unless asked.
```
