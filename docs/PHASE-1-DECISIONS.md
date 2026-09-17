# Tunora — Phase 1 Decisions

## Decisions Made

1. **Architecture pivot**: Tunora will ADAPT an existing complete application (`fspecii/ace-step-ui`, license pending direct confirmation) as its foundation, rather than composing a new frontend/backend from scratch as Phase 0's provisional architecture assumed. This is a direct, evidence-based update to [ARCHITECTURE-PRINCIPLES.md](./ARCHITECTURE-PRINCIPLES.md).
2. **Primary AI model**: ACE-Step 1.5 is the leading candidate for Tunora's `MusicGenerationProvider` (🟢 REUSE) — MIT code, Apache-2.0-style weights, self-hostable from 4GB VRAM. Not declared final; a dedicated model-evaluation phase (with actual GPU testing) is still required before shipping.
3. **Secondary/fallback model candidates**: DiffRhythm2 and YuE2 (🔵 ADAPT) — worth hands-on spikes, not commitments.
4. **Frontend component system**: shadcn/ui (🟢 REUSE) for dashboard components; WaveSurfer.js (🟢 REUSE) for audio playback and waveform, replacing the "prefer WaveSurfer.js where suitable" hedge in Phase 0 with a confirmed decision.
5. **Job queue**: RQ (🟢 REUSE), not Celery/Kafka — confirms and finalizes Phase 0's "select only after a reuse audit" placeholder.
6. **GPU inference pattern**: a plain worker process (RQ worker + `transformers`/`diffusers`), not a serving framework (TorchServe/Triton/BentoML/Ray Serve all rejected or deferred for MVP scale).
7. **Storage correction**: MinIO is REJECTED as a settled "Phase 2" default — Phase 0's architecture doc named it without checking current status; it is now confirmed archived (April 25, 2026) and AGPLv3-licensed. Local filesystem remains the MVP choice; object storage needs fresh research when actually required.
8. **Authentication deferred**: no auth system is built for MVP (single-user/local self-hosted); fastapi-users is the fallback if/when multi-user need becomes real.
9. **Monitoring deferred**: structured logging only for MVP; full OpenTelemetry/Prometheus/Grafana stack is out of scope until real production load exists.
10. **Confirmed BUILD list** (the only components with no viable OSS reuse path): lyrics/LRC editor UI, generation job-status UI component, and the Projects + Song Version data model/UI. All three are scoped thin and composed on top of already-REUSEd primitives (WaveSurfer.js+Regions, shadcn/ui, the adapted application's existing SQLite schema).
11. **Audio processing stack**: FFmpeg (LGPL-only build), soundfile, librosa — confirmed, with an explicit build-configuration requirement (no `--enable-gpl`) flagged for the eventual build/deployment docs.
12. **Stem separation and transcription** (V2+ scope, not MVP): Demucs (adefossez fork, pending weight-license confirmation) for separation; basic-pitch (cleanest license in the whole audit — Apache-2.0 code AND weights) for future transcription/melody-extraction features.

## Blocking Items for Phase 2 / Implementation Planning

These must be resolved with a direct primary-source check before the relevant component is built upon:

1. **`fspecii/ace-step-ui`'s actual code license** — README claims MIT, GitHub API detects no LICENSE file. Open the repo directly and confirm before any adaptation work begins.
2. **Demucs pretrained-weight licensing** — "scientific purposes only" claim is from secondary sources, not a confirmed primary maintainer statement. Get a definitive answer before any commercial weight bundling (self-hosted server-side inference is lower-risk and can likely proceed in parallel).
3. **torchaudio's forced_align/MMS_FA API stability** — contradictory reports on whether it survived the 2.9→2.10 transition. Verify against whichever torchaudio version Tunora eventually pins.
4. **Training-data provenance for ACE-Step, YuE, HeartMuLa, DiffRhythm2** — none of the four disclose training sources for their song-generation checkpoints. This is a standing legal/ethical risk to flag to users (per each model's own ethics guidance) rather than something Tunora can resolve unilaterally; track for re-evaluation as these projects mature or publish clarifications.

## What Changed From Phase 0

- Phase 0's architecture diagram listed MinIO as a "later" storage option without a license/maintenance check — this audit found it archived and AGPLv3, and downgrades it accordingly. [ARCHITECTURE-PRINCIPLES.md](./ARCHITECTURE-PRINCIPLES.md) should be updated to reflect this before Phase 2 treats it as settled.
- Phase 0 assumed Tunora's UI/backend would be assembled from scratch or composed from separate libraries; this audit found a viable complete-application ADAPT candidate, which changes the recommended starting point substantially (see [REUSE-AUDIT.md](./REUSE-AUDIT.md)).
- Phase 0 listed AudioCraft/MusicGen as a model candidate without flagging its NC weight license; this audit confirms that license is a hard blocker for commercial use and downgrades the model to reference-only.

## Next Phase

**Phase 2 — Implementation Planning**, gated on resolving the four blocking items above (especially #1, the application-base license) before any adaptation work begins. Phase 2 should also include the actual hands-on GPU testing that this phase could not perform (no GPU access), to validate ACE-Step 1.5's real output quality before committing to it as the primary `MusicGenerationProvider`.
