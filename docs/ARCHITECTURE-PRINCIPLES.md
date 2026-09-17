# Tunora — Architecture Principles

## Style: Modular Monolith with Replaceable AI Providers

Tunora starts as a modular monolith, not microservices. Boundaries between domain, jobs, and the music provider are enforced in code (module/package boundaries), not by network calls between services. Microservices, Kubernetes, and Kafka are explicitly deferred until a later phase demonstrates actual need — see [NON-GOALS.md](./NON-GOALS.md).

## Provisional High-Level Architecture

```
                  TUNORA
                     │
              Next.js Web App
                     │
                 REST/SSE
                     │
                  FastAPI
                     │
        ┌────────────┼────────────┐
        │            │            │
      Domain       Jobs       Music Provider
        │            │            │
        │            ▼            │
        │        GPU Worker       │
        │            │            │
        │       ┌────┼────┐       │
        │       ▼    ▼    ▼       │
        │     ACE  YuE  HeartMuLa │
        │                         │
        └──────────┬──────────────┘
                   ▼
              Audio Pipeline
                   │
                 FFmpeg
                   │
                Storage
```

This is a starting point only. Every major component in this diagram must pass a reuse audit (Phase 1) before it is implemented from scratch.

## AI Provider Abstraction

The backend defines a `MusicGenerationProvider` interface. The UI and domain layer depend only on this interface — never on a specific model. Providers implement it:

```
MusicGenerationProvider
    ├── ACE-Step provider
    ├── YuE provider
    ├── HeartMuLa provider
    └── Future model provider
```

A provider declares its own capabilities (lyrics support, style conditioning, max duration, languages supported, progress reporting) so the UI can adapt without code changes when a provider is swapped.

## Provisional Technology Direction

- **Frontend**: Next.js + TypeScript
- **UI**: Tailwind CSS + mature open-source component libraries where suitable
- **Audio UI**: prefer existing mature waveform/player solutions (e.g., WaveSurfer.js) over custom-built audio UI
- **Backend**: Python + FastAPI
- **AI**: PyTorch + Hugging Face ecosystem + selected open-source music model(s)
- **Audio processing**: FFmpeg + mature Python audio libraries
- **Database**: PostgreSQL, once persistence needs justify it
- **Cache / job state**: Redis, only if required
- **Queue**: selected only after a reuse audit — do not default to a specific queue technology prematurely
- **Storage**: local filesystem initially; MinIO if/when object-storage semantics are actually needed
- **Deployment**: Docker / Docker Compose

None of these are final. Each is subject to the reuse audit in Phase 1 and can change if a better-fitting open-source option is found.

## Data Model Direction (Conceptual)

```
User
  │
  └── Project
        │
        └── Song
              │
              ├── Version 1 → Audio
              ├── Version 2 → Audio
              └── Version 3 → Audio
```

Core rule: a regeneration creates a new Version, it never overwrites an existing one. Concepts to define in the eventual schema: Project, Song, Song Version, Audio Asset, Lyrics, Generation Request, Generation Job, Metadata. The database itself is not designed in Phase 0 — this is conceptual scaffolding only.

## Principles Carried Forward

- Reuse → Adapt → Compose → Build, in that order, for every component.
- Zero mandatory cost for local development and self-hosting.
- No component the UI depends on may hardcode a specific AI model.
- No infrastructure complexity introduced without demonstrated need.
