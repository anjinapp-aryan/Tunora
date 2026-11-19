---
name: ace-step-prompting
description: Write or improve ACE-Step 1.5 song descriptions (captions), lyrics tags and generation settings for Tunora, and choose how to regenerate (Another Take, Revise, Remix, Repaint, Extend). Use when the user asks for a better prompt, a genre/mood/instrument description, generation settings, or why a generation didn't match what they wanted.
argument-hint: "[what the song should be, or a song/version id to improve]"
---

Request: `$ARGUMENTS`. Knowledge adapted from ACE-Step's own guide (`ACE-Step-1.5/docs/en/Tutorial.md`,
"Guiding the Elephant") and, as reference only, the CC0 `suno-engineer` skill of
bitwize-music-studio/claude-ai-music-skills (its Suno model names, sliders and v-tags do **not** apply to
ACE-Step). Never add Suno-specific runtime code or dependencies.

## What Tunora actually sends (backend/app/providers/ace_step.py)

`prompt` (the caption), `lyrics` (empty when instrumental), `vocal_language`, `audio_duration` (Create offers
30/60/120/180 s), `seed` (or random). BPM, key and time signature are only suggested by the AI Song Director
(ACE-Step's own 5Hz LM, `app/director`). There are no guidance/steps/model controls in the UI.

## Caption (the most important input)

One or two sentences, concrete and ordered: **genre + era/subgenre → mood → lead instruments → vocal
description → production/space → tempo feel**. Example: "Warm acoustic folk ballad, nostalgic and hopeful,
fingerpicked guitar and soft cello, intimate breathy lead vocal, close-miked, slow tempo." (Vocal gender
only when the user asked for it — never assume one.)
- Name instruments, not adjectives about quality ("amazing", "professional" add nothing).
- No artist names or song titles (copyright and imitation risk); describe the sound instead.
- Contradictions (e.g. "minimal" + "huge orchestra") produce mush; pick one.
- Indian styles: name the tradition and instruments (Carnatic violin, mridangam, tabla, nadaswaram,
  dhol, harmonium, bansuri) plus the modern production if any; language goes in the Language field,
  not the caption.

## Lyrics tags

Structure tags on their own lines (`[Verse]`, `[Chorus]`, `[Bridge]`...), at most one modifier per tag. Run
the `lyrics-review` skill / `POST /api/lyrics/check` before generating.

## Regenerating (choose the cheapest operation that fixes the problem)

| Problem | Use |
|---|---|
| Good idea, unlucky result | **Another Take** (same inputs, new seed) |
| Wrong genre/mood/lyrics | **Revise** (new Version from edited inputs) |
| Keep the melody, change the style | **Remix** (cover strength: lower = closer to the source) |
| One section is bad | **Repaint** that region |
| Song is too short | **Extend** |
| Want stems | **Extract** (needs the base model slot; see CLAUDE.md) |
Imported songs (Phase 32) cannot use Extend/Remix/Repaint/Extract/Another Take yet (O-11).

## Honesty rules

Generation quality, vocals and pronunciation need human listening; report only objective facts. Kannada is
not in ACE-Step's trained-language list. A seed reproduces a result only with the same model and inputs.
