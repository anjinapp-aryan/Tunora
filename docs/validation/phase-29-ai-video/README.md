# Tunora Phase 29 — AI Video Feasibility Lab

Isolated lab (not part of the Tunora application). Nothing here is imported by Tunora; no Tunora
code, dependency, database or storage was modified. Report: `docs/PHASE-29-AI-VIDEO-FEASIBILITY-LAB.md`
in the Tunora repo (branch `feature/tunor_2_video`).

## Environment

- Windows 11 Pro 10.0.26200, RTX 5060 Ti 16 GB (sm_120, driver 591.86), 31.6 GB RAM, Intel Core Ultra 7 265K.
- Python 3.12.10, `uv` 0.12.15. Venv: `.venv` (created with `uv venv --python 3.12 .venv`).
- `torch==2.7.1+cu128`, `torchvision==0.22.1+cu128`, `torchaudio==2.7.1+cu128` (index `https://download.pytorch.org/whl/cu128`).
- `diffusers==0.40.0`, `transformers==5.18.0`, `accelerate==1.15.0`, `librosa`, `soundfile`, `psutil`,
  `beat_this==1.1.0` (git `CPJKU/beat_this@b95c8ab`). Full list: `uv pip freeze --python .venv/Scripts/python.exe`.
- Video encoding: Tunora's approved LGPL FFmpeg (`I:\Tunora\backend\tools\ffmpeg\bin`, n9.0.2, `--enable-version3`,
  libopenh264, no `--enable-gpl`). `diffusers.export_to_video`/imageio/moviepy are NOT used.
- Caches kept inside the lab: `HF_HOME=./hf-home`, `TORCH_HOME=./torch-home`.

## Models (pinned revisions)

| Model | Revision | Use |
|---|---|---|
| `Tongyi-MAI/Z-Image-Turbo` | `f332072aa78be7aecdf3ee76d5c247082da564a6` | keyframes; re-saved as bf16 in `models/z-image-turbo-bf16` (the HF repo ships an fp32 transformer, 32.9 GB) |
| `Wan-AI/Wan2.2-TI2V-5B-Diffusers` | `b8fff7315c768468a5333511427288870b2e9635` | text encoder, VAE, base transformer (re-saved bf16 in `models/wan22-ti2v-5b-transformer-bf16`; fp32 shards deleted for disk) |
| `FastVideo/FastWan2.2-TI2V-5B-FullAttn-Diffusers` | `3e187042a324f6f5fb68fd22110a78725253de8f` | DMD 3-step transformer (transformer folder only) |
| Beat This! `final0` checkpoint | sha256 `8c328b45…8eb8331` | beats/downbeats |

## Scripts (`scripts/`)

| Script | Experiment |
|---|---|
| `monitor.py` | measurement helper (nvidia-smi VRAM, torch peak, process RSS, system available RAM) → `logs/measurements.jsonl` |
| `analyze_song.py` | E6: librosa + Beat This! + Tunora TimedLyrics → `song/analysis.json` |
| `e7_plan.py` | E7: deterministic shot plan (`python e7_plan.py 22.72 10 portrait|landscape`) |
| `e1_zimage.py` | E1/E4: Z-Image keyframes (`python e1_zimage.py <jobs.json> <out> [--model <dir>] [--save-bf16 <dir>]`) |
| `e2_wan.py` | E2/E3/E8: Wan2.2 TI2V-5B / FastWan clips (options: `--offload model`, `--precompute-embeds`, `--vae-tiling`, `--transformer <dir>`, `--dmd-sigmas 1.0,0.757,0.522`) |
| `run_clips.sh` | one process per clip, 900 s timeout, one retry, skips finished clips (resume) |
| `e8_montage.py` | clip validation (ffprobe, blackdetect, freezedetect) + beat-cut montage with the approved FFmpeg |
| `handoff_ace.py` | GPU hand-off test with ACE-Step (start → load → `stop-tunora.ps1` → VRAM check) |

## Reproduce (ACE-Step stopped)

```bash
cd I:/Tunora-validation/ai-video-feasibility
export HF_HOME="I:/Tunora-validation/ai-video-feasibility/hf-home" TORCH_HOME="I:/Tunora-validation/ai-video-feasibility/torch-home" PYTHONUTF8=1
.venv/Scripts/python.exe scripts/analyze_song.py
.venv/Scripts/python.exe scripts/e7_plan.py 22.72 10 portrait
.venv/Scripts/python.exe scripts/e1_zimage.py jobs/keyframes_portrait.json outputs/keyframes_portrait --model I:/Tunora-validation/ai-video-feasibility/models/z-image-turbo-bf16
bash scripts/run_clips.sh jobs/clips_portrait.json "I:/Tunora-validation/ai-video-feasibility/outputs/e8_portrait" logs/e8.log
.venv/Scripts/python.exe scripts/e8_montage.py jobs/plan_portrait.json I:/Tunora-validation/ai-video-feasibility/outputs/e8_portrait portrait outputs/final/e8_montage_9x16.mp4 portrait
```

Inputs copied read-only from Tunora: `song/source.mp3` (Version `ver-53c1604d…`, "I Will Rise"), `song/song.json`,
`song/timed_lyrics.json` (from a completed lyric MusicVideo of that Version).

Outputs (not committed anywhere): `outputs/`, `logs/`.
