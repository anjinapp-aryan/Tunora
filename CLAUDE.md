# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo state

Planning-only repo right now. No source code, no build tooling, nothing to compile/lint/test yet. All decisions live in `docs/*.md`. Current work: Phase 2 (implementation planning / hands-on validation on real hardware — no Tunora product code written yet, validation only). Read the relevant `docs/PHASE-*.md` file before assuming what phase we're in, since it advances over time.

## What Tunora is

Free, open-source-first, self-hostable AI Music Studio. User describes a song in plain language (optionally lyrics/style/mood/language), generates via an open-source AI music model, previews in-browser, manages results in a versioned/searchable/downloadable library. Suno/Udio are UX benchmarks ONLY — no proprietary code, models, weights, datasets, or branding may be used or reverse engineered. Long-term: become for AI music generation what Stable Diffusion WebUIs became for image generation — a product layer over a swappable ecosystem of open models.

## The one rule that governs everything: Reuse-First Law

From `docs/REUSE-FIRST-LAW.md`, verbatim, applies to every phase/feature/component:

> **REUSE → ADAPT → COMPOSE → BUILD**

BUILD is permitted only when:
1. No suitable existing open-source solution exists, or
2. Existing solutions are technically unsuitable, or
3. License restrictions prevent adoption, or
4. Integration/security requirements make adoption unreasonable.

Before adding any dependency, check EACH of these separately — they can differ: source-code license, model license, model-weight license, dataset license, commercial-use restrictions, redistribution restrictions, attribution requirements, API/service restrictions. Never assume "GitHub repository = free for everything." A project can have open-source code while its model weights or training dataset carry different, more restrictive terms — this has already tripped up multiple candidates in this project (see License constraints below).

## Architecture (`docs/ARCHITECTURE-PRINCIPLES.md`)

Modular Monolith with Replaceable AI Providers — not microservices. Backend defines a `MusicGenerationProvider` interface; UI/domain layer must never depend on a specific model.

- No component the UI depends on may hardcode a specific AI model.
- No infrastructure complexity introduced without demonstrated need (no Kubernetes, no Kafka at this stage — see Non-goals).
- Zero mandatory cost for local development and self-hosting.
- Data model: `User → Project → Song → Version → Audio`. Regeneration always creates a new Version, never overwrites.

## Scope boundaries

**MVP** (`docs/MVP-SCOPE.md`, `docs/PRODUCT-SCOPE.md`): prompt/lyrics-to-song creation form; generation job lifecycle (queued/generating/processing/completed/failed); audio preview (play/pause/seek/volume, waveform if practical); song metadata + download; library (list/search/sort/play/delete/favorite); basic persistence (songs, versions, audio asset refs).

**Explicitly out of MVP**: extend/remix/repaint, Projects, stems, reference audio, melody/voice conditioning, LoRA, multi-user accounts, any infra beyond one local generation job.

**Non-goals** (`docs/NON-GOALS.md`, verbatim): "Do not clone Suno/Udio's UI, branding, or proprietary implementation." "Do not build a custom foundation music model." "Do not introduce Kubernetes at this stage." "Do not introduce Kafka at this stage." "No mandatory paid subscription/API/cloud GPU for core functionality."

## Locked-in tech decisions

Check `docs/MODEL-CANDIDATES.md`, `docs/PHASE-1-DECISIONS.md`, `docs/REUSE-MATRIX.md` before proposing alternatives — these were already audited for license/cost/technical fit.

- **Primary AI model**: ACE-Step 1.5 (MIT code, Apache-2.0 weights, self-hostable from 4GB VRAM). Not yet declared final — pending GPU validation in Phase 2.
- **Fallback models**: DiffRhythm2, YuE/YuE2 (need spikes). Reference only: HeartMuLa, Stable Audio Open. Rejected: AudioCraft/MusicGen weights (CC-BY-NC-4.0, non-commercial).
- **Application base**: adapt `fspecii/ace-step-ui` (React/TS/Express/SQLite) rather than build from scratch — covers ~6 of 9 MVP surfaces. License unresolved (README claims MIT, no LICENSE file found — treat as blocking until confirmed). Fallback base: `Sion971/ace-step-studio`.
- **Frontend**: Next.js + TypeScript, Tailwind CSS, shadcn/ui (MIT).
- **Audio playback/waveform**: WaveSurfer.js (BSD-3-Clause) — single dependency, Regions/Timeline/Spectrogram plugins as needed.
- **Backend**: Python + FastAPI.
- **Job queue**: RQ (Redis Queue, MIT) — not Celery, not Kafka.
- **GPU inference**: plain worker process using `transformers`/`diffusers` directly. No serving framework (TorchServe/Triton/BentoML/Ray Serve rejected/deferred).
- **Storage**: local filesystem for MVP. MinIO rejected (archived, AGPLv3) — re-research object storage only when actually needed.
- **Auth**: deferred for MVP (single-user/local). Fallback: fastapi-users (MIT).
- **Monitoring**: structured logging only for now; OTel/Prometheus/Grafana deferred.
- **Audio processing**: FFmpeg (LGPL-only build — do NOT enable `--enable-gpl`), soundfile (BSD-3), librosa (ISC).
- **Stem separation (V2+)**: Demucs adefossez fork — weight license ("scientific purposes only") is disputed/unverified, blocking for commercial use.
- **Transcription (V2+)**: basic-pitch (Apache-2.0 code+weights, cleanest license in the whole audit).
- **Confirmed BUILD-only** (no viable OSS reuse path found): lyrics/LRC editor UI, generation job-status UI, Projects+Versions data model/UI.

## Cost constraints (`docs/COST-AUDIT.md`)

Zero-cost policy: no mandatory paid API/subscription/cloud service for core functionality. Every MVP-stack component must be zero-cost. Watch items if scope grows: Stable Audio Open (free under $1M annual revenue, paid above), MusicGen weights (non-commercial only), MinIO (archived, vendor pushing paid "AIStor"), madmom (NC-licensed models). Hardware/electricity for self-hosting is NOT a cost-policy violation.

## License constraints (`docs/LICENSE-AUDIT.md`)

Biggest open legal risk: training-data provenance is undisclosed for every full-song vocal model audited except Stable Audio Open (which can't do vocals). Hard rejects already made: aeneas (AGPLv3), madmom pretrained models (CC BY-NC-SA 4.0), MusicGen weights (CC-BY-NC-4.0), ComfyUI/AUTOMATIC1111 code (GPL-3.0/AGPL-3.0 — reference only, cannot ship). Blocking/unresolved: `fspecii/ace-step-ui` actual license, Demucs weight license, torchaudio `forced_align`/MMS_FA API stability across versions.

## Phase 2 environment and test-plan ground rules

Real GPU validation is underway on the dev machine, not simulated (`docs/PHASE-2-ENVIRONMENT.md`, `docs/PHASE-2-TEST-PLAN.md`):

- Dev GPU: RTX 5060 Ti, 16GB VRAM. For this tier, start with the **2B DiT** variant, not XL — rule is to start smallest-practical, not largest-capable.
- Classify every test result VERIFIED / PARTIALLY VERIFIED / NOT VERIFIED / FAILED / NOT TESTED. Never invent metrics.
- Audio quality/vocals/pronunciation require human listening — Claude cannot hear audio, so report only objective facts (file exists, duration, sample rate, generation succeeded/failed) and let the user judge quality.
- No Tunora product code during this phase — validation only.
- No premature infra: do not introduce Kubernetes/Kafka/Celery/Triton/MinIO/Redis/PostgreSQL unless a validated need is demonstrated first.
- Fixed prompt set of 8 themes (English pop, instrumental, ballad, Indian-style, Hindi, Kannada, devotional, complex structure) is locked — don't alter it after seeing results.
