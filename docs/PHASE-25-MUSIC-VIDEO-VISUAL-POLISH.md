# Phase 25 — Music Video Visual Polish

## 1. Objective

Make the automatically generated 9:16 music videos look more polished and ready for social media, with no editor, timeline or manual work. The Phase 23 renderer and the Phase 24 workflow were to stay as they are; this phase adds only visual styling.

## 2. Phase 23/24 baseline

The baseline is the real "I Will Rise" Version with the Minimal style (`phase25/baseline.mp4`). Frames at 0, 5, 15, 30, 45 and 55 s and at the end show:

- **Blank first and last frames.** The title card only appears at 0.5 s, and the video ends on an empty background.
- **A small, sentence-case title** at about 100 px.
- **Lyrics in a thin band mid-frame** with harsh dark outlines. The next line is 60 px and small on a phone.
- **A flat, washed-out background** with no depth, and motion only from the source clip.
- **A subtle karaoke fill** that is hard to see.

The baseline works and is readable, but it isn't engaging.

## 3. Fresh OSS audit

The audit was run live against GitHub on 2026-09-28. The search terms were:

- ASS karaoke effects, KFX, libass animation, animated subtitles with FFmpeg;
- lyric video with FFmpeg, Ken Burns with FFmpeg, audio visualizer with FFmpeg;
- shorts/reels subtitle generators.

Source code was read, not just READMEs. Hugging Face was not searched: no AI model is needed for deterministic visual composition.

**Finding.** Every serious project that makes polished "CapCut-style" animated lyrics or captions does it the way Tunora already does: an ASS script rendered by libass, plus FFmpeg filters. None of them brings a capability that would justify a new engine or dependency. The value is in *techniques* expressed as ASS tags, which fits Tunora's existing renderer.

## 4. Candidate projects

**Primary candidates**

| Candidate | License (verified) | Activity | What it offers | Decision |
|---|---|---|---|---|
| `sebetancurch/auto-caption` | MIT | pushed 2026-07-17, 7★ | ASS "pop" captions (active word recoloured and scaled with `\t`) and karaoke sweep; data-driven `StylePreset` | **ADAPT (technique)** — per-word pop, adapted with attribution |
| `nicolaigaina/ai-video-captions` | MIT | 63★, 2026-03-27 | JSON-configured caption styles (size 105–120, thick outlines, highlight colour, animation type) rendered as ASS | **REFERENCE** — confirms the style-as-data design and phone-scale sizing |
| `CoffeeStraw/PyonFX` | LGPL-3.0 | 187★, 2025-08-31 | Advanced per-glyph KFX generation for ASS | **REFERENCE** — needs `pywin32` (Win32 font metrics) plus `VideoTimestamps`. Its strength, per-glyph effects, isn't needed for word-level pop and fades |

**Adjacent tools and Phase 22 re-checks**

| Candidate | License (verified) | Activity | What it offers | Decision |
|---|---|---|---|---|
| `glenwrhodes/KillerSubtitles`, `muneebkhan08/Capite` | MIT | small | Whisper and animated captions for existing videos | **REFERENCE** — same ASS/FFmpeg approach; Tunora already has its own alignment |
| `Trekky12/kburns-slideshow` | MIT | 75★ | Ken Burns slideshows with FFmpeg `zoompan` | **REFERENCE** — Tunora's crop-based pan is cheaper and already built |
| `Picorims/wav2bar` / `wav2bar-reborn` | GPL-3.0 / MPL-2.0 | active | Audio-visualization video export | **REJECT** (GPL) / **REFERENCE** (P7 deferred) |
| `dcmcand/dynamic-typography-videos` (re-checked) | Apache-2.0 | — | Style presets (reused in Phase 22B) | Unchanged: its Remotion renderer is still rejected |
| Remotion (re-checked) | "Remotion License", source-available with a company-size gate | — | Browser renderer | **REJECT** — unchanged; not OSI open source |
| FFmpeg filters in the **approved LGPL build** | LGPL v3 | — | `vignette`, `zoompan`, `fade`, `xfade`, `curves`, `gblur`, `noise`, `showwaves`, `showfreqs` (`eq` is correctly absent: GPL-only) | **REUSE** — `vignette` |

## 5. License analysis

- **No new licensed component in the product.** The new visuals are ASS tags rendered by libass (ISC), already in use, and the FFmpeg `vignette` filter, which is present in the approved LGPL v3 build and rejected by nothing in the ffmpeg policy.
- **Fonts.** One more weight of the already-bundled font was added: `Poppins-ExtraBold.ttf`, SIL OFL-1.1, covered by the existing `OFL.txt`.
- **Code adaptation.** The per-word "pop" technique is adapted from `sebetancurch/auto-caption` (MIT, `autocaption/ass_builder.py`) and credited in the module docstring. The implementation is Tunora's own; it scales vertically only, see §11.
- **Not adopted:** PyonFX is LGPL-3.0 and would have been acceptable as a library, but it wasn't needed. Remotion and wav2bar (GPL) were rejected.

## 6. Dependency analysis

Phase 25 adds **no new dependencies**: no Python package, no npm package, no binary, no model, no GPU runtime. FFmpeg is the same approved build and passes the same policy checks.

## 7. Decision matrix

| Candidate | License | Mature | Windows | Offline | GPL risk | Reuse level | Fit | Decision |
|---|---|---|---|---|---|---|---|---|
| libass ASS tags (already in Tunora) | ISC | yes | yes | yes | none | full | exact | **REUSE** |
| FFmpeg `vignette` (approved build) | LGPL v3 | yes | yes | yes | none | full | background depth | **REUSE** |
| auto-caption pop technique | MIT | small but clear | yes | yes | none | technique | active-word emphasis | **ADAPT** |
| ai-video-captions style config | MIT | small | yes | yes | none | design | style as data | **REFERENCE** |
| PyonFX | LGPL-3.0 | moderate | needs pywin32 | yes | none (LGPL) | library | overkill | **REFERENCE** |
| kburns-slideshow / zoompan | MIT / LGPL | yes | yes | yes | none | technique | already covered | **REFERENCE** |
| wav2bar | GPL-3.0 | yes | yes | yes | **GPL** | — | audio-reactive | **REJECT** |
| Remotion | source-available | yes | yes | yes | commercial gate | — | — | **REJECT** |

## 8. Final decision

**ADAPT.** The capability already exists in Tunora's approved stack (libass and LGPL FFmpeg). What was missing was using it well. Phase 25 adapts proven OSS techniques into the existing ASS builder as **composable style data**, and adds a style-driven background treatment. It adds no new renderer, engine or dependency.

## 9. Prototype results

The prototype is in `I:\Tunora-validation\music-video\phase25\proto\`, outside the repository. It uses:
- the real "I Will Rise" Version and its real audio;
- the **same stored TimedLyrics** as the baseline video (identical timing, no re-alignment);
- the same looping sunset MP4 background.

| Style | Render (60 s video) | Output size | FFmpeg peak RAM | GPU |
|---|---|---|---|---|
| minimal_white (baseline) | 11.3 s | 18.2 MB | 232 MB | none |
| **cinematic** | **12.4 s** | 16.3 MB | 318 MB | none |
| **karaoke** | **12.7 s** | 14.2 MB | 308 MB | none |

GPU memory stayed at the idle desktop level (about 1.2 GB) in all three runs.

**Findings that changed the design:**

- **Vignette cost.** The first version rendered in **21 s**. Profiling individual filters found `vignette` was the entire extra cost (+11 s), because it ran on RGB frames after `colorlevels` with per-pixel dithering. Moving it before `colorlevels`, on YUV, with `dither=0`, costs about 0.6 s. A corner-crop comparison showed no new banding; the background clip's own compression blocks are identical in the baseline. libass itself (glow, animated title, per-word events) measured about 7.3 s in every variant, so it is not the cost.
- **First frame.** The title card first faded in from invisible, leaving frame 0 empty, which is a bad thumbnail. It is now fully visible on frame 0.
- **Lead-in readability.** Words not yet sung were too transparent at first; this was corrected.

## 10. Architecture

Unchanged:

```
Song → Version → (Audio | Music Video) ; MusicVideoService → TimedLyrics → MusicVideoRenderer → libass + LGPL FFmpeg → MP4
```

A style is a `Style` record (`app/music_videos/ass_builder.py`) that composes primitives:

| Primitive | Effect |
|---|---|
| `caps` | Capitals |
| `word_mode` | `"fill"` = karaoke sweep; `"pop"` = active word recoloured with a vertical-only pop |
| `highlight` | Colour of the active word |
| `glow` | `\blur` on the border: a soft halo |
| `rise` | Lines rise into place as they fade in |
| `spacing` | Letter spacing |
| `title_card` | `"cinematic"`: title on frame 0 with a slow grow, plus an end card |
| `vignette` | Renderer background treatment |
| `drift` | Renderer background treatment: slow pan also on video backgrounds |

There is no per-style branching code: `cinematic` and `karaoke` are two data rows.

## 11. Implementation

**`ass_builder.py`**

- The new primitives were added to `Style`, and two styles were added:
  - **Cinematic:** capitals; the sung word pops in warm gold; soft glow; lines rise in; title card and end card.
  - **Karaoke:** capitals; a bright gold sweep; strong outline; title card and end card.
- A style that uses no primitive (the three Phase 23 styles) follows the **unchanged** Phase 23 code path.
- The "pop" uses **vertical-only scaling** (`\fscy`), so a popped word can never make a line wider and re-wrap it. A test enforces this.

**Other files**

- **`renderer.py`:** drift on video backgrounds, and a vignette on YUV with no dithering placed before the RGB colour steps. Both come from the style.
- **`models.py`, the API `Literal`, the frontend style list:** accept `cinematic` and `karaoke`.
- **Frontend default:** the form now defaults to **Cinematic**, so new videos look polished without an extra choice. The API's own default (`minimal_white`) is unchanged, so no existing API contract changes.
- **Font:** `Poppins-ExtraBold.ttf` added (OFL, same family).

## 12. Tests

**Backend: 763 passed** (751 + 12 new in `tests/music_videos/test_visual_styles.py`):

- The domain, API and builder expose exactly the same style set.
- **Golden files:** the three Phase 23 styles produce **byte-identical ASS** to the committed Phase 23/24 builder. The golden files were generated from `git show HEAD:…ass_builder.py`, not from the new code.
- Cinematic: the title is visible on frame 0; the end card runs to the end; there is one event per sung word with exactly one popped word; no horizontal scale anywhere; the entry motion runs only on a line's first event.
- Karaoke uses the sweep, in capitals.
- The new styles keep malicious lyric text inert (`{\p1}`, `{\fn…}`, `\N`).
- The renderer's graph is unchanged for Phase 23 styles; for Cinematic it applies drift, and the vignette comes before `colorlevels` with `dither=0` (the performance guard).
- The API accepts the new styles and rejects unknown ones.
- A **real render** of Cinematic over a looping video background: 1080×1920, correct duration, no black frames.

**Mutation checks: 6/6 caught.** Each of these was introduced deliberately and each made a test fail:

- routing old styles through the new path;
- a title fade-in (blank first frame);
- a pop that scales width;
- dropping the vignette;
- no drift on video;
- capitals skipping escaping.

**Frontend: 410 passed.** The style selector lists Cinematic first and defaults to it, and generating without choosing a style sends `style=cinematic`. One existing assertion (default "Minimal") was intentionally updated. Typecheck is clean.

**E2E against the real stack, in Chrome: 4/4.**

- The **default style (Cinematic)** from the finished-song link, then real playback and a byte-identical download.
- The **new Karaoke style** on an image background.
- The audio-only flow.
- The failure → retry flow.

The existing `create-song` suite was not re-run in this phase: Phase 25 changes only the Music Video form's style options, not the Song Details layout. It passed 21/21 in Phase 24.

## 13. Real GPU validation

The real Phase 23/24 Version "I Will Rise" was rendered in the Cinematic style through the full stack (Next → backend → renderer):

- COMPLETED in 19 s end to end, including alignment; 11 lines matched.
- Output: H.264 High, 1080×1920, 30 fps, `yuv420p`, AAC LC 48 kHz, 60.000 s, 17.0 MB.
- 0 black segments and 0 decode errors.
- The **source audio SHA-256 is unchanged** (`10e1e4cc…`), and the Song's Version list is byte-identical before and after.

## 14. Visual validation

`phase25/compare-sheet.png` puts baseline and Cinematic side by side at 0/5/15/30/45/55 s and the end. Human viewing is still needed for taste, but objectively:

| Aspect | Baseline | Phase 25 Cinematic |
|---|---|---|
| First frame (thumbnail) | empty background | title visible |
| Last frame | empty background | end card |
| Typography | SemiBold 92 px, mixed case, harsh dark outline | ExtraBold 104 px capitals, soft glow halo, letter spacing |
| Active word | faint karaoke fill | sung word pops in warm gold |
| Lyric motion | fade | fade + 28 px rise on entry, word pop |
| Background | flat, washed-out | vignette depth, drift also on video |
| Mobile readability | readable, small next line | larger, higher-contrast text; next line 62 px |

The following were inspected and **none were found**: clipping, overlap (long lines wrap as one event), black frames, unexpected text, malformed subtitles or broken transitions. Each line still starts at the same time (same TimedLyrics and windows).

**Human viewing is still required** for aesthetic preference, how the timing and pop feel, and how distracting the background is. Tests can't judge taste.

## 15. Performance

A 60 s video takes **11.3 s → 12.4 s** for Cinematic and **12.7 s** for Karaoke, on CPU, with no GPU use. FFmpeg peak RAM goes from about 232 MB to about 318 MB. Output is smaller (18.2 → 16.3 MB). The RTX 5060 Ti's VRAM isn't used for rendering at all.

## 16. Security

All existing guarantees are unchanged:
- lyric text is escaped before any tag is added, and capitals are applied before escaping (tested);
- style names come from a fixed allowlist, enforced in the domain, the API `Literal` and the builder;
- there is no path input, no shell, and the protocol whitelist still applies;
- the Phase 24 background decode check (about 40 ms rejection of corrupt images) is untouched and still runs before rendering.

## 17. Backward compatibility

**PASS.**
- Phase 23 styles produce byte-identical ASS (golden tests), and a full real render of `minimal_white` had **MD5-identical video frames** to the Phase 23 baseline.
- Existing records keep their style name and still render identically on retry.
- There is no migration and no schema change.
- The API default is unchanged. Only the form's default for *new* videos is now Cinematic.

## 18. Known limitations

- Two new presets only (Cinematic, Karaoke). Nature, Emotional and Energetic were not added, because they would be palette variants without a demonstrated benefit.
- There is no per-video customisation of fonts or colours; that is by design.
- The vignette is fixed-strength, and drift is a simple sinusoidal pan rather than a true zoom (`zoompan` would cost more).
- All Phase 23/24 limitations remain: 9:16 only, unmatched lyric lines are omitted, stable-ts is archived upstream, and the H.264 and LGPL notes apply.

## 19. Deferred work

- **Audio-reactive visuals (P7), investigated only.**
  - What is possible: the approved LGPL build has `showwaves`, `showfreqs` and `astats`, so an energy-driven element could be done with no new dependency.
  - Why deferred: it adds a moving element that competes with the lyrics, and it needs design and human testing.
  - Rejected option: wav2bar is GPL.
- More presets, cross-fade scene changes (`xfade`), a true Ken Burns zoom, colour grading (`curves`), and user-selectable fonts.

## 20. Final decision

**ADAPT.** The polish is delivered by **reusing** libass and the approved LGPL FFmpeg `vignette`, and **adapting** one MIT technique (the per-word pop). It is expressed as composable style data in the existing renderer. There is no new dependency or engine, and the Phase 23 styles are byte-identical.
