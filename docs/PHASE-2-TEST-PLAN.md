# Tunora — Phase 2 Test Plan

Real hands-on validation of ACE-Step 1.5 + fspecii/ace-step-ui on the actual dev machine (RTX 5060 Ti 16GB). No claim in the resulting docs is made without either a command output, a file on disk, or an explicit note that it needs the user's own listening judgment.

## Ground Rules (from the Phase 2 master prompt)

- Classify every result: VERIFIED / PARTIALLY VERIFIED / NOT VERIFIED / FAILED / NOT TESTED.
- Never invent generation time, VRAM usage, audio quality, or success rate.
- **Audio quality, vocals, pronunciation, and lyric accuracy require human listening** — I (the assistant) cannot hear. For every quality test I will generate the file, report objective facts I can check (duration, sample rate, file size, clipping/silence via a script), and hand the file + a specific question to the user. I will not write a 1-5 quality score myself.
- No Tunora product code in this phase — validation only.
- No paid APIs, no premature infra (Kubernetes/Kafka/Celery/Triton/MinIO/Redis/PostgreSQL) unless this phase proves a need.

## Stage 1 — Environment Setup (in progress)

1. ✅ Verify GPU/driver/CUDA via `nvidia-smi` — see [PHASE-2-ENVIRONMENT.md](./PHASE-2-ENVIRONMENT.md)
2. ✅ Verify disk space, choose install drive (I:\AI)
3. ✅ Clone `ace-step/ACE-Step-1.5`, confirm LICENSE file directly (MIT, confirmed)
4. ✅ Install `uv` package manager
5. ⏳ Run `uv sync` (creates venv, installs PyTorch+CUDA build and all deps) — running
6. Launch `start_gradio_ui.bat` with the smallest practical config (2B DiT tier)
7. Confirm the UI loads at `http://localhost:7860` and models auto-download

## Stage 2 — Basic Generation Test

Per Phase 2 §4: one simple instrumental, one simple vocal song, short duration, before the full benchmark. Record prompt, settings, duration, output format, generation time, peak VRAM, success/failure.

## Stage 3 — Standardized Quality Benchmark (fixed prompt set, same settings every time)

| Test | Prompt theme | What I can verify myself | What needs your ears |
|---|---|---|---|
| A — English Pop | Modern emotional pop song, chasing dreams | File exists, duration, sample rate, generation time, VRAM | Vocals, lyrics, melody, structure, pronunciation, artifacts |
| B — Instrumental | Cinematic instrumental | Same objective checks | Instrumentation, arrangement, dynamics, atmosphere |
| C — Emotional Song | Slow emotional ballad | Same | Vocal expression, melody, emotional consistency |
| D — Indian Style | Indian-inspired instrumentation | Same | Instrumentation/rhythm — I will NOT claim cultural authenticity myself |
| E — Hindi | Hindi lyrics | Same | Pronunciation, lyric accuracy, vocal clarity — you'll need to read the Devanagari/romanized lyrics against the audio |
| F — Kannada | Kannada lyrics | Same, plus honest note if the model has no Kannada training signal | Pronunciation, lyric accuracy |
| G — Devotional | Devotional-style song | Same | Vocal quality, style adherence, pronunciation |
| H — Complex structure | Intro/Verse/Pre-Chorus/Chorus/Verse/Chorus/Bridge/Final Chorus/Outro | Duration matches expected section count/timing (roughly, via waveform/silence analysis) | Whether the structure actually sounds distinct section-to-section |

Exact prompts will be fixed BEFORE the first run in this set and not altered after seeing results, per Phase 2 §5.

## Stage 4 — Model Comparison (only if Stage 1-3 succeed and time/VRAM allow)

Candidates already scored on paper in [MODEL-CANDIDATES.md](./MODEL-CANDIDATES.md): YuE2 (24GB VRAM min — may not fit this 16GB card, will note as RED if so), DiffRhythm2. Only installed if ACE-Step's results leave open questions a second model would answer, per Phase 2 §6 ("do not spend excessive time installing every model").

## Stage 5 — fspecii/ace-step-ui End-to-End Test

Re-verify the license (Phase 1 flagged it as unresolved — README claims MIT, GitHub API showed no detected LICENSE file). If still unresolved after directly opening the repo: **do not adopt**, fall back to `Sion971/ace-step-studio` per the master prompt's Rule 2.

Full workflow test: open app → create song → prompt → lyrics → generate → progress → audio → waveform → save → library → repaint/edit → stems (if exposed).

## Stage 6 — Stability Test

1, 3, then 5 sequential generations. Watch for CUDA OOM, memory leak, stale processes, corrupted output.

## Stage 7 — Documentation

Populate the remaining Phase 2 docs (MODEL-BENCHMARK.md, MODEL-COMPARISON.md, ACE-STEP-VALIDATION.md, ACE-STEP-UI-VALIDATION.md, PERFORMANCE-RESULTS.md, QUALITY-EVALUATION.md, LICENSE-VALIDATION.md, MVP-CAPABILITY-MATRIX.md, BUILD-VS-ADAPT-DECISION.md, PHASE-2-DECISIONS.md) as each stage actually completes — not written in advance of the evidence.

## Current Status

Stage 1, step 5 (`uv sync`) is running in the background. Next update lands once that completes or fails.
