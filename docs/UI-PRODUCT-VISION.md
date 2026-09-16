# Tunora — UI Product Vision

This defines product structure, not pixel-level design. Visual design happens in a later phase, and even then, per the Reuse-First Law, existing open-source UI components (dashboards, players, waveform, lyrics editors) must be evaluated before anything is designed from scratch.

## Navigation

```
┌───────────────────────┐
│ 🎵 TUNORA             │
├───────────────────────┤
│ 🏠 Home               │
│ ➕ Create Song        │
│ 🎵 Library            │
│ 📁 Projects           │
│ ❤️ Favorites          │
│ ⚙ Settings            │
└───────────────────────┘
```

## Dashboard (Home)
- Primary "Create Song" entry point
- Recent songs
- Recent projects (once projects exist)
- Recent activity, where useful (e.g., a generation that just completed)

## Create Song
- Prompt input
- Lyrics input (optional)
- Style/genre selector
- Mood selector
- Language selector
- Generation controls (Generate button; advanced controls deferred past MVP)

## Generation Screen
- Job status: queued / generating / processing / completed / failed
- Progress indicator where the provider supports it
- Clear failure state with retry

## Song Preview
- Audio player
- Waveform
- Title
- Metadata
- Lyrics
- Download action
- Slots reserved for future editing actions (extend/remix/repaint) — not built at MVP, but the layout should not need to be redesigned to add them

## Library
- Song list
- Search
- Filtering
- Sorting
- Favorites view
- Inline playback

## Song Details
- Audio player
- Waveform
- Lyrics
- Metadata
- Version list/history
- Actions (download, delete, favorite, regenerate, and later extend/remix/repaint)

## Design Principle

The UI must never assume a specific music generation model. Any model-specific parameter (e.g., a control unique to one provider) is rendered conditionally based on what the active `MusicGenerationProvider` reports it supports — the UI reads capabilities, it does not hardcode them.
