# Tunora — Phase 0 Decisions

## Decisions Made

1. **Product identity**: Tunora is a free, open-source-first, self-hostable AI Music Studio. Suno/Udio are UX benchmarks only — no proprietary reuse of any kind.
2. **Core loop**: Describe a song → Generate → Listen → Save. This is the spine of every phase to follow.
3. **Architecture style**: modular monolith with a replaceable `MusicGenerationProvider` abstraction. No microservices, no Kubernetes, no Kafka at this stage.
4. **Zero-cost policy**: no mandatory paid API, subscription, or cloud service. Local development and self-hosting must always be possible.
5. **Reuse-first law**: REUSE → ADAPT → COMPOSE → BUILD is binding for every future phase, not just Phase 0.
6. **Data model direction**: User → Project → Song → Version → Audio, conceptual only. A regeneration always creates a new version; it never overwrites.
7. **Feature tiering**: MVP / V1 / V2 / Experimental defined in [MVP-SCOPE.md](./MVP-SCOPE.md) and [PRODUCT-SCOPE.md](./PRODUCT-SCOPE.md). Experimental features are not committed to until validated against real open-source model capability.
8. **AI model candidates (non-final)**: ACE-Step / ACE-Step 1.5, YuE / YuE2, HeartMuLa, AudioCraft/MusicGen, Stable Audio tools, plus any newer candidate surfaced in Phase 1. No model is selected as final in Phase 0.

## Explicit Reuse Flags for Phase 1

The following areas are flagged as "obviously reusable" and must be investigated in the Phase 1 Reuse Audit before any custom implementation is considered:

- Waveform rendering / audio player UI (candidate: WaveSurfer.js)
- Audio transcoding/processing (candidate: FFmpeg)
- Authentication (candidate: an existing mature OSS auth solution, not custom-built)
- Object storage (candidate: MinIO, only if local filesystem storage proves insufficient)
- Stem separation (candidate: existing OSS stem-separation models, e.g. Demucs family — license/fit to be verified in Phase 1)
- Music generation model itself (candidates listed above — final selection deferred to a dedicated model evaluation phase)
- Job queue technology (no default chosen; selection deferred to Phase 1 reuse audit)

## Nothing Implemented

No production code was written in Phase 0 beyond this documentation set. No technology was locked in beyond the provisional direction stated in [ARCHITECTURE-PRINCIPLES.md](./ARCHITECTURE-PRINCIPLES.md), all of which remains subject to the Phase 1 reuse audit.

## Next Phase

**Phase 1 — Open-Source Reuse Audit.** Investigate the reuse candidates listed above using the Reuse Scorecard in [REUSE-FIRST-LAW.md](./REUSE-FIRST-LAW.md), verify licenses at every layer (code, model, weights, dataset), and produce REUSE/ADAPT/COMPOSE/BUILD decisions for each major component before any implementation begins.
