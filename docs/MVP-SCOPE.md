# Tunora — MVP Scope

The smallest useful version of Tunora. Goal: prove the full loop end to end — describe a song, generate it, listen to it, save it, find it again.

## Create
- Prompt text field
- Optional lyrics field
- Basic style/genre selector
- Basic mood selector
- Language selector, where the model supports it
- Generate button

## Generation
- Job creation on submit
- Generation status (queued / generating / processing / completed / failed)
- Progress indicator where the provider exposes progress
- Error handling with a user-readable failure message and retry option

## Preview
- Audio playback: play/pause, seek, duration display, volume control
- Waveform display if practical with the chosen player library
- Instant preview once generation completes

## Song
- Generated title
- Metadata (prompt, style, mood, language, model/provider used, created date)
- Lyrics display where available
- Download (audio file)

## Library
- List of previously generated songs
- Search by title/prompt
- Sort (date, title)
- Playback from library
- Open song detail
- Delete
- Favorite marking, if practical without added complexity

## Basic Persistence
- Songs
- Versions (even if MVP only ever creates one version per song, the schema must support many — see [SONG-VERSION-MODEL note in PHASE-0-DECISIONS.md](./PHASE-0-DECISIONS.md))
- Generated audio asset references (path/URL, not raw blobs duplicated in the DB)

## Explicitly Out of Scope for MVP
- Extend / remix / repaint
- Projects
- Stems, reference audio, melody/voice conditioning, LoRA
- Multi-user accounts/teams (single local user is enough to prove the loop; auth can be a stub or a reused OSS solution, not custom-built)
- Any infrastructure beyond what is needed to run one generation job locally (no Kubernetes, no distributed queue, no cloud dependency)
