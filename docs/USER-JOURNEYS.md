# Tunora — User Journeys

## First-Time User Journey (MVP)

```
Open Tunora
    ↓
Dashboard
    ↓
Create Song
    ↓
Enter prompt (+ optional lyrics/style/mood/language)
    ↓
Generate
    ↓
Generation screen (queued → generating → processing)
    ↓
Song ready
    ↓
Automatic/instant preview
    ↓
Play
    ↓
Save (implicit — song is persisted once generation completes)
    ↓
Library
    ↓
Play again later
```

## Key Interactions

1. **Prompt entry** — user types a natural-language description of the song they want. Lyrics, style, mood, language are optional refinements, not required fields.
2. **Generate trigger** — single primary action; no multi-step wizard for MVP.
3. **Generation feedback** — user must always see current job state (queued/generating/processing/failed) and never be left wondering if anything is happening.
4. **Failure recovery** — on failed generation, user sees why (as far as the provider reports) and can retry without re-entering all fields.
5. **Instant preview** — the moment a song completes, it is playable without extra navigation.
6. **Implicit save** — a completed generation is a song in the library by default; there is no separate "save" step that risks losing a generation the user paid compute time for.
7. **Return visit** — user reopens Tunora, lands on dashboard or library, finds prior songs via recent list or search, and can play immediately.
8. **Version awareness (post-MVP)** — when a user regenerates or extends a song, they should always understand a new version was created, not that their old one was overwritten.

## Secondary Journeys (V1+)

- **Regenerate**: user opens an existing song, adjusts prompt/style, regenerates → new version appended to the same song.
- **Extend/remix/repaint**: user selects a song section or the whole song and applies a transformation → new version.
- **Organize into projects**: user groups related songs (e.g., an album/EP in progress) into a project.
- **Favorite**: user marks a song as favorite for quick access from a filtered library view.

Every journey in Tunora ultimately returns to the same base loop: describe/adjust → generate → preview → land in library.
