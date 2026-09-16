# Tunora — Product Scope

## Core Workflow

```
User
  ↓
Create Song
  ↓
Prompt / Lyrics
  ↓
AI Song Director
  ↓
Music Generation Model
  ↓
Generation
  ↓
Audio Processing
  ↓
Song Ready
  ↓
Preview / Play
  ↓
Save
  ↓
Library
  ↓
Open Later
```

The "AI Song Director" is the orchestration layer that turns raw user input (prompt, lyrics, style, mood, language) into a well-formed generation request for whichever music model provider is active. It does not generate audio itself — it prepares and routes the request, tracks the job, and normalizes the result.

## Feature Tiers

### MVP (must have)
- Prompt-to-song generation
- Lyrics-to-song where the underlying model supports it
- Basic style/genre and mood selection
- Generation job lifecycle (queued → generating → processing → completed/failed)
- Audio preview: play/pause/seek/volume, duration
- Waveform preview if practical with the chosen player library
- Song metadata, title, lyrics display
- Download generated audio
- Library: list, search, sort, play, open, delete
- Basic persistence: songs, versions, audio asset references
- Favorite marking, if practical without added complexity

### V1 (important, post-MVP)
- Extend, remix, repaint of existing songs
- Regenerate (creates a new version, never overwrites)
- Projects (grouping songs)
- Improved lyrics workflow (structure tags, sections)
- Improved generation controls (seed, guidance, duration control)
- Favorites as a first-class filter/view

### V2 (advanced)
- Stem separation
- Reference audio conditioning
- Melody conditioning
- Voice conditioning
- Style transfer
- LoRA-based style/voice adaptation
- Advanced multi-track editing

### Experimental (investigate only after core product works)
- AI-generated music video
- Advanced personalization
- Advanced voice cloning
- Highly specialized/niche music generation

No experimental feature is committed to until the underlying open-source technology is validated in Phase 1.

## What Tunora Owns vs. What It Reuses

Tunora owns: product experience, orchestration/glue code, the provider abstraction, UI integration, and any capability with no suitable open-source solution.

Tunora reuses/adapts: waveform/audio player, authentication, object storage, audio codec/processing (FFmpeg), stem separation, the music generation model itself, and any other component where a mature open-source solution already exists and fits the license/technical constraints. See [REUSE-FIRST-LAW.md](./REUSE-FIRST-LAW.md).
