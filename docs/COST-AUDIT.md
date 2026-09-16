# Tunora — Cost Audit (Phase 1)

Classification key, per [PRODUCT-VISION.md](./PRODUCT-VISION.md)'s zero-cost policy:

- 🟢 **ZERO COST** — no mandatory paid dependency.
- 🟡 **OPTIONAL COST** — free/self-hosted path exists; an optional paid cloud/API also exists.
- 🔴 **PAID DEPENDENCY** — requires a paid API/service/subscription to function.

## AI Music Generation

| Component | Classification | Note |
|---|---|---|
| ACE-Step 1.5 | 🟢 ZERO COST | Fully self-hostable, no vendor cloud dependency; acemusic.ai hosted demo is optional, not required |
| YuE / YuE2 | 🟢 ZERO COST | Self-hostable; 24GB VRAM is a hardware cost, not a software/API cost |
| HeartMuLa | 🟢 ZERO COST | Self-hostable |
| DiffRhythm2 | 🟢 ZERO COST | Self-hostable |
| Stable Audio Open 1.0 | 🟡 OPTIONAL COST | Free under $1M annual revenue; mandatory paid Stability AI commercial license above that threshold — a real constraint if Tunora ever monetizes at scale |
| AudioCraft / MusicGen | 🟢 ZERO COST (software) but 🔴 for commercial rights | Weights are CC-BY-NC-4.0 — commercial use requires either a Meta commercial license or full retraining, both outside "free reuse" |

## Application Base / Frontend

| Component | Classification | Note |
|---|---|---|
| fspecii/ace-step-ui | 🟢 ZERO COST | Self-hosted, no cloud dependency (pending license confirmation, see [LICENSE-AUDIT.md](./LICENSE-AUDIT.md)) |
| WaveSurfer.js | 🟢 ZERO COST | Client-side library, no service dependency |
| shadcn/ui | 🟢 ZERO COST | CLI + copy-in components, no runtime service; premium third-party template packs exist but are not needed |

## Audio Processing / Stem Separation / Transcription

| Component | Classification | Note |
|---|---|---|
| FFmpeg | 🟢 ZERO COST | Self-hosted binary |
| soundfile / librosa | 🟢 ZERO COST | Self-hosted libraries |
| Demucs | 🟢 ZERO COST | Self-hosted inference; no paid dependency (weight-licensing legal question is separate from cost) |
| basic-pitch | 🟢 ZERO COST | Self-hosted |
| madmom | 🟢 ZERO COST (software) but effectively 🔴 for commercial pretrained-model use | NC license requires contacting rights holder for commercial use of pretrained models |
| WhisperX / stable-ts | 🟢 ZERO COST | Self-hosted |

## Infrastructure

| Component | Classification | Note |
|---|---|---|
| RQ + Redis | 🟢 ZERO COST | Self-hosted |
| Plain GPU worker (transformers/diffusers) | 🟢 ZERO COST | Runs on user's own GPU hardware; hardware/electricity cost is explicitly out of scope per Phase 0's cost definition |
| Local filesystem storage | 🟢 ZERO COST | No dependency at all |
| MinIO | 🟡 OPTIONAL COST in theory, but currently 🔴-adjacent risk | Community edition itself has no license fee, but the project is archived and the vendor's maintained path forward ("AIStor") is commercial — do not treat this as a stable zero-cost long-term option without re-research |
| Authentication (deferred for MVP) | 🟢 ZERO COST | No auth system running at all for MVP |
| fastapi-users | 🟢 ZERO COST | Self-hosted, MIT |
| Authentik / Keycloak (deferred, future) | 🟡 OPTIONAL COST | Core self-hosted free; Authentik has a separate paid Enterprise tier (optional), Keycloak's paid layer is third-party support only |
| Structured logging | 🟢 ZERO COST | No dependency |
| Prometheus / Grafana / OpenTelemetry (deferred) | 🟡 OPTIONAL COST | Self-hosted free; Grafana Cloud is an optional paid tier, not required |

## Summary

Every component recommended for Tunora's actual MVP scope in [REUSE-MATRIX.md](./REUSE-MATRIX.md) is 🟢 ZERO COST. The only 🟡/🔴-flagged items (Stable Audio Open's revenue-gated license, MusicGen's NC weights, MinIO's uncertain future, madmom's NC models) are all items the audit already recommends REJECT or REFERENCE-only — none of them are load-bearing for the MVP path. This matches Phase 0's zero-cost policy: no mandatory paid API, subscription, or cloud service anywhere in the recommended MVP stack.

Reminder from Phase 0, reconfirmed here: hardware and electricity costs for self-hosting (a GPU-capable machine) are not counted as "software/API cost" under Tunora's definition of free — see [NON-GOALS.md](./NON-GOALS.md) and [PRODUCT-VISION.md](./PRODUCT-VISION.md).
