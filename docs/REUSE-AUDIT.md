# Tunora — Phase 1 Reuse Audit (Overview)

This is the top-level summary of Phase 1's open-source discovery work. Detailed scorecards live in the companion documents:

- [MODEL-CANDIDATES.md](./MODEL-CANDIDATES.md) — AI music generation models
- [UI-REUSE-AUDIT.md](./UI-REUSE-AUDIT.md) — dashboard components, generation-progress UI
- [AUDIO-REUSE-AUDIT.md](./AUDIO-REUSE-AUDIT.md) — audio player, waveform, lyrics UI, audio processing, stem separation, transcription, lyric alignment
- [INFRA-REUSE-AUDIT.md](./INFRA-REUSE-AUDIT.md) — job queue, GPU serving, storage, auth, monitoring
- [LICENSE-AUDIT.md](./LICENSE-AUDIT.md) — license findings across every layer
- [COST-AUDIT.md](./COST-AUDIT.md) — zero-cost / optional-cost / paid classification
- [REUSE-MATRIX.md](./REUSE-MATRIX.md) — one-row-per-capability final matrix
- [BUILD-VS-REUSE.md](./BUILD-VS-REUSE.md) — explicit reasoning per capability
- [PHASE-1-DECISIONS.md](./PHASE-1-DECISIONS.md) — decisions carried forward

All research was conducted live (WebSearch/WebFetch) on 2026-09-15 against GitHub, Hugging Face, and official vendor/license pages — not recalled from training memory alone, since project status, maintenance, and licensing change over time. No production code was written in this phase. No model was executed (no GPU access) — every capability claim about actual generation quality is marked NOT TESTED.

## Most Important Finding: A Complete-Application ADAPT Candidate Exists

Unlike Phase 0's assumption that Tunora would be assembled from separate frontend/backend/UI pieces, the audit found a real, actively-maintained, mostly-complete open-source application:

**`fspecii/ace-step-ui`** — a full-stack React/TypeScript/Express/SQLite web application built specifically on top of ACE-Step 1.5, explicitly positioned as an open-source Suno alternative. It already covers: dashboard, prompt/lyrics/style/mood creation form, generation job with real-time progress, waveform player, searchable library, likes/playlists, and repaint/cover-style editing — roughly 6 of Tunora's 9 planned MVP surfaces. A more actively-diverging fork, `Sion971/ace-step-studio`, adds an explicit "Workspaces/Playlists" grouping concept closest to Tunora's planned "Projects" feature, and confirms MIT licensing (the parent repo's license is unresolved — see [LICENSE-AUDIT.md](./LICENSE-AUDIT.md)).

This changes Tunora's Phase 1 recommendation from "compose from separate parts" to "**ADAPT an existing application, backfill the gaps**" — specifically Projects, Versions, confirmed Download, and true Extend/Remix, which no project in the ecosystem currently implements as first-class features.

## Second Most Important Finding: A Recommended Infra Default Was Just Discontinued

MinIO — listed provisionally in Phase 0's architecture doc as a later object-storage option — was found to be **archived by its maintainer on April 25, 2026**, with a "NO LONGER MAINTAINED" banner on its own GitHub page, and the vendor now steering users to a commercial replacement ("AIStor"). Combined with its AGPLv3 license, MinIO is downgraded from a soft default to 🔴 REJECT pending re-research. This is exactly the kind of assumption the Reuse-First Law's license/maintenance verification step exists to catch — Phase 0 named it without checking current status.

## What Tunora Can Reuse

- **AI music generation**: ACE-Step 1.5 (MIT code, Apache-2.0-style weights, self-hostable, 4GB+ VRAM) — see [MODEL-CANDIDATES.md](./MODEL-CANDIDATES.md).
- **Application base**: `fspecii/ace-step-ui` (license pending direct verification) as an adaptation starting point.
- **Audio player + waveform**: WaveSurfer.js (BSD-3-Clause) — covers both in one dependency.
- **Dashboard components**: shadcn/ui (MIT) — matches Tunora's Next.js/TS/Tailwind stack exactly.
- **Job queue**: RQ (MIT) — simple, Redis-backed, sufficient for single-node MVP.
- **GPU inference pattern**: plain worker process using `transformers`/`diffusers` directly — no serving framework needed at MVP scale.
- **Storage (MVP)**: local filesystem.
- **General audio processing**: FFmpeg (LGPL build), soundfile (BSD-3), librosa (ISC).
- **Stem separation** (V2+): Demucs, adefossez fork — pending a legal check on weight licensing.
- **Transcription** (V2+): basic-pitch (Apache-2.0, cleanest license of any ML component audited).

## What Tunora Must Build

- **Lyrics/LRC editor UI** — no mature packaged library exists anywhere in the ecosystem searched. Build a thin custom UI composed on WaveSurfer.js + its Regions plugin.
- **Generation job-status UI component** — no MIT/Apache React component library found for this pattern; the only real-world references (ComfyUI, AUTOMATIC1111) are GPL/AGPL and cannot be copied. Build a small state-driven component on shadcn/ui primitives.
- **Projects and Versions data model + UI** — no project in the ecosystem implements Tunora's exact Project→Song→Version hierarchy; this is a genuine gap across every candidate audited and becomes Tunora's core structural addition on top of an adapted application base.

## What Remains Unresolved (flagged for direct follow-up before implementation)

- `fspecii/ace-step-ui`'s actual code license (README says MIT, GitHub API detects no LICENSE file).
- Demucs pretrained-weight licensing ("scientific use only" claim, not confirmed via a primary maintainer statement).
- torchaudio's forced_align/MMS_FA API survival across versions (contradictory sources).
- Training-data provenance for ACE-Step, YuE, HeartMuLa, and DiffRhythm2 — none disclose training sources for their song-generation checkpoints.

See [BUILD-VS-REUSE.md](./BUILD-VS-REUSE.md) for the full capability-by-capability reasoning and [PHASE-1-DECISIONS.md](./PHASE-1-DECISIONS.md) for what is carried forward into Phase 2.
