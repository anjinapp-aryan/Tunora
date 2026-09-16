# Tunora — Phase 2 Test Environment (Verified)

Captured live from the actual test machine on 2026-09-15/16. Every value below was read directly from the machine via `nvidia-smi`, `python --version`, `git --version`, `df -h`, etc. — none is assumed or copied from documentation.

## Hardware

| Item | Verified value |
|---|---|
| GPU | NVIDIA GeForce RTX 5060 Ti |
| VRAM | 16311 MiB total (~16GB), 1350 MiB in use by desktop/background apps at idle, 0% GPU utilization at idle |
| Driver | 591.86 |
| CUDA (driver-reported) | 13.1 |
| OS | Windows 11 Pro, build 10.0.26200 |
| Platform | win32 |

## Software (baseline, before ACE-Step install)

| Item | Verified value |
|---|---|
| Python (Windows, `python`) | 3.12.10 |
| pip | 26.1.1 |
| git | 2.53.0.windows.2 |
| node | v24.14.1 |
| nvcc (CUDA toolkit compiler) | NOT INSTALLED (not required — PyTorch ships its own CUDA runtime in the wheel) |
| torch (pre-install check) | NOT INSTALLED (`ModuleNotFoundError`) |
| uv (package manager) | NOT INSTALLED initially; installed this session, version 0.12.15 |

## Disk Space (checked before choosing an install location)

| Drive | Total | Used | Free |
|---|---|---|---|
| C: (Git-mounted root) | 385G | 350G | 35G |
| D: | 98G | 76G | **23G** |
| E: | 98G | 71G | 27G |
| F: | 98G | 56G | 43G |
| G: | 98G | 58G | 41G |
| H: | 57G | 8.0G | 49G |
| I: | 98G | 13G | **86G** |

**Decision (user-approved):** install ACE-Step 1.5 to `I:\AI\ACE-Step-1.5` — D: had only 23GB free, too tight for PyTorch/CUDA wheels + model weights.

## ACE-Step 1.5 — Repository Facts

| Item | Verified value |
|---|---|
| Repository | https://github.com/ace-step/ACE-Step-1.5 |
| Clone location | `I:\AI\ACE-Step-1.5` |
| Code license | MIT — confirmed by reading the LICENSE file directly at `I:\AI\ACE-Step-1.5\LICENSE` (Copyright (c) 2026 ACEStep) |
| Stated requirements (README/INSTALL.md) | Python 3.11-3.12; CUDA GPU recommended (also MPS/ROCm/Intel XPU/CPU); ≥4GB VRAM for DiT-only mode, ≥6GB for LLM+DiT; ~10GB disk for core models |
| Install method used | Official `uv sync` path (README Quick Start / INSTALL.md), not a manual pip/conda install |

## GPU Tier Recommendation (from ACE-Step's own README table, for a 16GB card)

Per `I:\AI\ACE-Step-1.5\README.md`, the 16-20GB VRAM tier recommends:
- DiT: **2B sft or XL turbo**
- LM: `acestep-5Hz-lm-1.7B`
- Backend: `vllm`
- Note: "XL requires CPU offload below 20GB"

Per Phase 2's own rule ("start with the smallest practical configuration, do NOT immediately attempt the largest model"), the first test run will use the **2B** DiT tier, not XL, regardless of the 16GB card technically qualifying for XL-with-offload.

## Status of this document

This file will be updated as installation proceeds (actual `uv sync` duration, actual disk consumed, actual model download sizes) — see [PHASE-2-RESULTS.md](./PHASE-2-RESULTS.md) for live results once generation testing begins.
