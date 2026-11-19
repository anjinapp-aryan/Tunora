---
name: music-video-direction
description: Direct a Tunora AI Music Video — visual concept, style description, per-scene prompts and camera for the storyboard, performer choices and promotional cut ideas — within FastWan's limits, the GPU budget and Tunora's safety rules. Use when the user wants help with visual direction, storyboard scene descriptions, or why AI video scenes look wrong.
argument-hint: "[song id, the song's mood/lyrics, or a storyboard id]"
---

Request: `$ARGUMENTS`. Adapted (CC0) from bitwize-music-studio/claude-ai-music-skills (`album-art-director`,
`promo-director`), rewritten for Tunora's AI video pipeline (`backend/app/ai_video/`, docs
`docs/ai-music-video/`). Their Suno/Pillow promo pipeline is not used: Tunora renders with FastWan2.2-TI2V-5B
and assembles with the approved FFmpeg.

## Hard rules (enforced in code — never work around them)

- Fictional, synthetic performers only. No real people, celebrities, likenesses, face swaps or deepfakes
  (`planner.py` refuses such text). Performer default is **none**; one/two/group are gender-neutral unless the
  user chooses a presentation. Never assume a performer's gender.
- The original audio is never changed; the video is cut to it.
- No cloud upload and no external API.

## What the pipeline can and can't do

- Each scene is a ~3.2 s clip from a still keyframe, looped on whole beats for longer sections. Motion is
  gentle; no lip-sync, no choreography, no readable text, no consistent character identity across scenes.
- Scene boundaries come from Song Intelligence (sections/beats); tempo may read double or half.
- GPU cost: about 4.5–5 GPU minutes per scene (≈ 16 GB VRAM peak); one render at a time; ACE-Step must be
  stopped. Fewer scenes = faster. 2–8 scenes is the practical range.

## Writing scene prompts (scene, camera, mood — in that order)

1. **Place + light first**: "rain-soaked stone courtyard at dusk, warm lantern light". Concrete nouns,
   one location per scene.
2. **One motion**: slow push-in, gentle pan, drifting fog, flickering candles — FastWan handles slow,
   continuous motion; fast cuts or multiple actions inside a clip fail.
3. **Mood from the music**: map section energy (low/medium/high) to light and colour, e.g. low → cool,
   still, wide; high → warm, saturated, closer.
4. **Continuity**: repeat 2–3 style words in the style description (palette, film look) rather than in
   every scene; vary location and camera between adjacent scenes so cuts read.
5. Avoid: text/logos, hands doing precise tasks, crowds of faces, mirrors, brand names.

## Promotional ideas (no extra tooling)

A 15 s vertical teaser = the chorus section of the same render (9:16), trimmed by the user; YouTube metadata:
title, a 2-line description with credits ("Music and video made with Tunora, ACE-Step 1.5, FastWan2.2"),
and honest AI-generated disclosure. No auto-posting.
