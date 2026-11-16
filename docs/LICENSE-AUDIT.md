# Tunora — License Audit (Phase 1)

Per [REUSE-FIRST-LAW.md](./REUSE-FIRST-LAW.md): code license, model license, weight license, and dataset restrictions are tracked SEPARATELY for every dependency. "GitHub repo = free for everything" is never assumed. All entries below reflect live verification on 2026-09-15 unless flagged.

## AI Music Generation Models

| Project | Source license | Model license | Weights license | Dataset disclosed? | Commercial use | Verified? |
|---|---|---|---|---|---|---|
| ACE-Step 1.5 | MIT | Apache-2.0-style | Apache 2.0 | ❌ Not disclosed | Allowed (code+weights), training-data risk unquantified | ✅ code+HF card |
| YuE / YuE2 | Apache 2.0 | Apache 2.0 (per-checkpoint unresolved) | Apache 2.0 (conflicting secondary reports of CC-BY-NC for some checkpoints) | ❌ Not disclosed | Explicitly encouraged by model card | ✅ LICENSE file + HF card; ⚠️ per-checkpoint conflict unresolved |
| HeartMuLa | Apache 2.0 | Apache 2.0 | Apache 2.0 | ❌ "Internal dataset," no source/clearance statement (confirmed via arXiv paper) | Technically permitted; real unquantified risk | ✅ repo + paper |
| Stable Audio Open 1.0 | MIT (code) | Stability AI Community License | Stability AI Community License | ✅ Cleanest of all — CC0/CC-BY/CC-Sampling+ only, screened for copyrighted content, full attribution published | Free under $1M revenue, paid above | ✅ model card + attribution page |
| AudioCraft / MusicGen | MIT (code) | CC-BY-NC 4.0 | CC-BY-NC 4.0 | Not fully disclosed | Weights: NO (non-commercial only) | ✅ LICENSE + LICENSE_weights files |
| DiffRhythm2 | Apache 2.0 | Apache 2.0 | Apache 2.0 | ❌ Not documented | Permitted, subject to training-data caveat | ✅ repo + HF card |

**Cross-cutting risk:** training-data provenance is undisclosed for every full-song vocal-generation model audited except Stable Audio Open (which can't do vocals/full songs). This is the single biggest legal open item for Tunora's core feature.

## Complete Application Base

| Project | Claimed license | Actually detected | Status |
|---|---|---|---|
| fspecii/ace-step-ui | MIT (per README) | GitHub API reports `license: null` — no machine-detected LICENSE file at repo root | ⚠️ BLOCKING — must open the repo and manually confirm before any adaptation work begins |
| Sion971/ace-step-studio (fork) | MIT | Confirmed via GitHub API license field | ✅ verified |
| rustyorb/heartmula-studio | MIT | Confirmed | ✅ verified, but project is dormant (~7 months no activity) |

## Frontend / UI

| Component | License | Verified? |
|---|---|---|
| WaveSurfer.js (core + plugins) | BSD-3-Clause | ✅ verified via repo page |
| shadcn/ui | MIT | ✅ verified via WebFetch |
| Mantine (fallback only) | MIT (widely reported) | ⚠️ not independently re-fetched from LICENSE file |
| react-h5-audio-player (reference only) | MIT | ✅ verified |
| react-player (rejected) | MIT | ⚠️ widely known, not independently re-confirmed |
| lyric-timer / LySy (reference only, not adopted as dependency) | MIT | ✅ verified via WebFetch |
| karlyriceditor (rejected — wrong platform) | Unknown | ❌ not verified — rejected on platform grounds before license check |
| ComfyUI_frontend (pattern reference only, no code reuse) | GPL-3.0 | ✅ verified — license itself is why code cannot be copied |
| AUTOMATIC1111/stable-diffusion-webui (pattern reference only, no code reuse) | AGPL-3.0 | ✅ verified via LICENSE.txt |

## Audio Processing / Stem Separation / Transcription / Alignment

| Component | Source license | Model/weights license | Verified? |
|---|---|---|---|
| FFmpeg | LGPL v2.1+ default; GPL if `--enable-gpl` used | N/A | ✅ — build-configuration dependent, must ship LGPL-only build |
| soundfile | BSD-3-Clause | N/A | ✅ |
| librosa | ISC | N/A | ✅ |
| torchaudio | BSD | N/A (transforms); MMS weights possibly CC-BY-NC for some assets | ⚠️ MMS weight license not verified for the specific alignment checkpoint |
| pydub (reference only) | MIT | N/A | ✅ (but stagnant/breaking on Python 3.13) |
| Demucs (both original and adefossez fork) | MIT (code) | ⚠️ DISPUTED — secondary sources claim "scientific purposes only" for pretrained weights, distinct from MIT code; not confirmed via a primary maintainer statement this session | ⚠️ BLOCKING before any commercial weight bundling |
| UVR (Ultimate Vocal Remover) | MIT (GUI) | Mixed/unverified per bundled model | ⚠️ not exhaustively audited |
| Spleeter | MIT (code + models per repo) | Same | ⚠️ not independently re-verified this session |
| basic-pitch | Apache 2.0 (code) | Apache 2.0 (weights) — same permissive grant for both | ✅ — cleanest ML-component license found in this whole audit |
| madmom | BSD (code) | **CC BY-NC-SA 4.0 (CONFIRMED)** — commercial use requires contacting the rights holder | ✅ confirmed directly from repo README/LICENSE |
| WhisperX | BSD-2-Clause | Alignment models mostly permissive, not exhaustively verified per-language | ⚠️ partial |
| torchaudio forced_align/MMS_FA | BSD (code) | Unresolved — MMS weights possibly CC-BY-NC for some assets | ⚠️ BLOCKING before commercial use |
| aeneas (rejected) | AGPL v3 | N/A | ✅ confirmed from repo LICENSE |
| Gentle (rejected) | Unverified | Unverified (Kaldi-based) | ❌ not confirmed |
| stable-ts | MIT (code) | Whisper weights (permissive, OpenAI) | ✅ — but repo itself now archived |

## Infrastructure

| Component | License | Verified? |
|---|---|---|
| RQ | MIT | ✅ |
| Dramatiq (reference only) | Dual LGPL-3.0/GPL-3.0 | ✅ confirmed via COPYING files — copyleft, not adopted as primary |
| ARQ (rejected) | MIT | ✅ (rejected on maintenance grounds, not license) |
| Celery (rejected for MVP) | BSD (New BSD) | ✅ |
| transformers / diffusers | Apache-2.0 | ✅ |
| TorchServe (rejected) | Apache-2.0 | ✅ (rejected — archived project, not license) |
| Triton Inference Server (reference only) | BSD-3-Clause | ✅ |
| BentoML (reference only) | Apache-2.0 | ✅ |
| Ray (rejected for MVP) | Apache-2.0 | ✅ |
| MinIO | **AGPLv3 (confirmed)** | ✅ — plus confirmed archived April 25, 2026; downgraded to reject-pending-re-research |
| fastapi-users (reference) | MIT | ✅ |
| Authentik (reference) | Core reported MIT; separate paid Enterprise license | ⚠️ not independently fetched from authentik's own license page |
| Keycloak (rejected for MVP) | Apache-2.0 | ✅ |
| OpenTelemetry / Prometheus | Apache-2.0 | ✅ |
| Grafana (reference, deferred) | AGPLv3 per 2021 relicensing (reported) | ⚠️ not re-verified this session |

## Music Video Composer (Phase 23) — adopted components

Verified 2026-09-27 against each project's LICENSE / package metadata / the binary's own build
configuration (details: `PHASE-23-MUSIC-VIDEO-COMPOSER.md` §9, `PHASE-23-IMPLEMENTATION.md` §13).

| Component | Source license | Model/weights license | Verified? |
|---|---|---|---|
| FFmpeg (BtbN `n9.0` **lgpl-shared** build, operator-installed in `backend/tools/ffmpeg`) | **LGPL v3** (`--enable-version3`, no `--enable-gpl`, no `--enable-nonfree`; bundled `LICENSE.txt`) | N/A | ✅ — enforced at runtime by `app/music_videos/ffmpeg.py`, which rejects GPL/non-free builds (the winget "full_build" on PATH is rejected) |
| libass (inside the FFmpeg build) + FreeType / HarfBuzz / FriBidi / fontconfig | ISC; FTL; MIT; LGPL-2.1+; MIT | N/A | ✅ |
| OpenH264 encoder (inside the FFmpeg build) | BSD-2-Clause | N/A | ✅ copyright. ⚠️ **H.264 patents: commercial distribution of H.264 output requires separate legal review** (Cisco's patent coverage applies only to Cisco-distributed binaries) |
| stable-ts 2.19.1 (optional `music-video` extra) | MIT | — | ✅ license. ⚠️ **repository archived (read-only) since 2026-05-30** — works as installed; isolated behind `LyricsAligner`, replaceable/forkable |
| openai-whisper 20250625 (+ `base` weights) | MIT | MIT | ✅ |
| torch 2.14.0 (CPU) / torchaudio 2.11.0 | Apache-2.0 (per package metadata) / BSD | N/A (torchaudio MMS weights NOT used) | ✅ |
| numba/llvmlite, tiktoken, regex, tqdm, networkx, sympy, … (transitive) | BSD / BSD-2 + Apache-2.0-with-LLVM-exception, MIT, Apache-2.0 + CNRI-Python, MPL-2.0 + MIT, BSD-3, BSD | N/A | ✅ from installed package metadata |
| Poppins font | SIL OFL-1.1 | N/A | ✅ (`OFL.txt` bundled with the font) |
| Remotion (rejected, Phase 22B) | Source-available "Remotion License" (company-size gated) | N/A | ✅ — rejected |

## Standing Policy

Every entry above marked ⚠️ or ❌ is a blocking or follow-up item before that component can move from "candidate" to "adopted" in an implementation phase. No component with an unresolved commercial-use-relevant license question (Demucs weights, torchaudio MMS weights, `fspecii/ace-step-ui`'s actual LICENSE file) should be built upon without first resolving the flag directly — reading the primary source (LICENSE file, model card, or a direct statement from the maintainer), not a secondary summary.
