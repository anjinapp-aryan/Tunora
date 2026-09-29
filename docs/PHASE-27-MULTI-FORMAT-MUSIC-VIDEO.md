# Phase 27 — Multi-Format Music Video Output (9:16 / 16:9 / 1:1, HD / 4K)

## 1. Problem

Until Phase 26 every music video was 9:16 at 1080×1920. The values `ASPECTS = {"9:16": (1080, 1920)}` and `MUSIC_VIDEO_DIMENSIONS` were hard-coded in the renderer and the API schema. The lyric layout was written for that one canvas.

Users need to choose among three formats:

- landscape, for YouTube and desktop;
- square, for feeds;
- 4K, for high-resolution output.

The same single rendering pipeline must serve all three, and the old default must stay unchanged.

## 2. Existing architecture (Phases 23–26)

`MusicVideoService` passes a Version's FLAC audio, TimedLyrics, the background and the style to `FFmpegLibassRenderer`. The renderer does the following:

1. Builds an ASS script with `ass_builder`, whose PlayRes equals the frame.
2. Runs one policy-checked LGPL FFmpeg command, with no shell and `file:` inputs only. The background filter graph is:
   - `scale=W:H:force_original_aspect_ratio=increase,crop=W:H`, which is already scale-to-cover;
   - a slow pan or drift;
   - darkening;
   - `ass=` for the lyrics;
   - OpenH264 and AAC.

The 9:16 frame was stored per video in `music_videos.aspect_ratio`, which a trigger keeps immutable.

## 3. OSS reuse audit (live, 2026-09-29)

The audit ran GitHub searches for:

- ffmpeg aspect-ratio crop/scale and reframing;
- subtitle safe areas;
- lyric-video generators;
- shorts/reels makers;
- Python video bindings;
- Remotion.

Hugging Face was not searched: the phase needs no model.

**Finding.** Every relevant project does multi-format output the way Tunora already does: FFmpeg scale-to-cover plus crop for the background, and an ASS/libass script, or a canvas framework, for text. The one reusable *capability* that matters is libass itself. It scales a script from its `PlayResX/Y` to the frame it renders onto, drawing vector glyphs at full output resolution. As a result:

- a single layout serves a profile's HD and 4K sizes;
- 4K needs no new code path;
- no dependency is needed.

## 4. Candidates evaluated

| Candidate | License | Activity | Relevant functionality | Decision |
|---|---|---|---|---|
| `libass/libass` (already in FFmpeg) | ISC | pushed 2026-09-17 | PlayRes→frame scaling; vector text at any output size | **REUSE.** 4K profiles reuse their HD layout canvas. |
| FFmpeg `scale` `force_original_aspect_ratio=increase` + `crop` (already used) | LGPL build | — | Scale-to-cover without stretching, then crop | **REUSE.** The existing graph already does this. It is now driven by the profile's size. |
| `Zulko/moviepy` | MIT | 14.9k★, 2026-08-26 | Python compositing and resize | **REJECT.** It processes frames in Python (numpy) and would be far slower at 4K than FFmpeg filters. It also duplicates the renderer. |
| `FujiwaraChoki/MoneyPrinter` | MIT | 14.0k★ | Shorts maker (MoviePy) | **REFERENCE.** Portrait only, built on MoviePy. Nothing to reuse. |
| `mifi/editly` | MIT | 5.5k★, 2025-05-12 | Declarative Node video editing with `cover`/`contain` resize modes | **REFERENCE.** It confirms that "cover" means scale plus crop. It is a Node runtime and a second renderer, so it was rejected as a dependency. |
| `kkroening/ffmpeg-python` / `lucemia/typed-ffmpeg` | Apache-2.0 / MIT | 11.0k★ (last push 2024-08) / 1.2k★ | Python builders for filter graphs | **REJECT.** Tunora builds a short, reviewed argument list. A builder adds a dependency and no capability. |
| `PyAV-Org/PyAV` | BSD-3-Clause | 3.3k★ | libav bindings | **REJECT.** It would mean a Python frame loop; FFmpeg's own filters are faster. |
| `KazKozDev/auto-vertical-reframe`, `fralapo/clippyme` | MIT | 21★ / 47★ | Content-aware 16:9→9:16 reframing (face/scene tracking) | **REFERENCE.** They solve a different problem: smart crops of footage. Tunora's backgrounds are decorative, and a centred cover crop is the expected behaviour. |
| `remotion-dev/remotion` | Remotion License (NOASSERTION) | 61k★ | React video with any composition size | **REJECT.** Already rejected in Phase 22A (license, Node runtime). |
| `Cizzurp215/lyric-video-generator`, `ethanstoner/lyric-generator` | MIT | 0★ | Small lyric-video apps (Pillow/FFmpeg) | **REFERENCE.** Fixed sizes, no multi-format layout. |

No model, weights or dataset is involved, so there are no model-licensing restrictions.

## 5. Decisions

- **REUSE:** libass PlayRes scaling; FFmpeg scale-to-cover and crop (already in use); the Phase 23–26 service, retry, delete and storage; the Phase 26 Create workflow.
- **ADAPT:** the renderer, the ASS builder, the service, the API route and schema, the repository, and the Create and Song Details forms. All of them now read one profile.
- **BUILD (small):**
  - `app/music_videos/profiles.py`: the canonical table;
  - `ass_builder.Layout`: the aspect-aware layout;
  - migration v7;
  - `VideoFormatPicker` (native radio groups);
  - tests.
- **No new dependency**, backend or frontend. No GPU encoding, queue or infrastructure.

## 6. VideoOutputProfile design

`backend/app/music_videos/profiles.py` is the **only** place that maps a profile id to sizes. Each profile holds:

- `id`, `orientation`, `aspect_ratio`, `width`, `height`, `resolution_class`, `display_name`;
- `canvas_width` × `canvas_height`: the ASS layout canvas. It equals the HD size, so a 4K profile reuses its HD layout and libass scales it;
- `video_bitrate`, `max_bitrate`, `buffer_size`: OpenH264 settings. HD keeps the Phase 23 8/10/16 Mb/s; 4K uses 32/40/64 Mb/s.

`get_profile(id)` is the allowlist; anything else raises `InvalidMusicVideoRequestError`. `renderer_profile()` also accepts the legacy renderer value `"9:16"`, which means `vertical_hd`.

The frontend mirrors the ids and sizes (`VIDEO_OUTPUT_PROFILES` in `lib/api/music-videos.ts`) **only to label the choices**. It sends only the id, and every returned video carries the backend's own `width`/`height`/`resolution`. This is the same mirror pattern already used for styles and background limits, and a unit test pins the mirror to the backend table's values.

## 7. Supported profiles

| Profile | Orientation | Ratio | Output | Layout canvas | Bitrate |
|---|---|---|---|---|---|
| `vertical_hd` (default) | portrait | 9:16 | 1080×1920 | 1080×1920 | 8 Mb/s |
| `vertical_4k` | portrait | 9:16 | 2160×3840 | 1080×1920 | 32 Mb/s |
| `landscape_hd` | landscape | 16:9 | 1920×1080 | 1920×1080 | 8 Mb/s |
| `landscape_4k` | landscape | 16:9 | 3840×2160 | 1920×1080 | 32 Mb/s |
| `square_hd` | square | 1:1 | 1080×1080 | 1080×1080 | 8 Mb/s |

There is deliberately no 1:1 4K: mainstream platforms deliver square video at 1080×1080 at most.

## 8. API contract

`POST /api/songs/{song_id}/music-videos` now accepts these parameters:

- `output_profile`: a FastAPI `Literal` of the five ids. The default is `vertical_hd`, so every Phase 23–26 request behaves exactly as before.
- `aspect_ratio`: optional, for old clients. It must agree with the profile, so `aspect_ratio=9:16` alone still means `vertical_hd`. `16:9` together with `vertical_hd` returns a 422.
- There are no `width`/`height` parameters. If a client sends them anyway, they are ignored (a test asserts that `width=99999` still produces 1080×1920).

Unknown, empty or wrongly cased profiles, and `square_4k`, return 422. Ownership checks are unchanged: a Version from another song returns 404.

`MusicVideoResponse` gains `output_profile` and `resolution`, and `width`/`height`/`aspect_ratio` now come from the profile.

## 9. UI flow

`VideoFormatPicker` (`components/song/video-format-picker.tsx`) is shared by the Create page (Audio + Video and Lyrics Video) and by Song Details → Create Music Video. It has two native radio groups:

1. **Aspect ratio:** 9:16 Vertical, 16:9 Landscape or 1:1 Square.
2. **Resolution:** only the choices the ratio supports, with the size as supporting text. 9:16 offers HD 1080 × 1920 and 4K 2160 × 3840; 16:9 offers HD 1920 × 1080 and 4K 3840 × 2160; 1:1 offers HD 1080 × 1080 only.

Details:

- Switching the ratio keeps 4K where the new ratio offers it, and falls back to HD otherwise.
- Choosing 4K shows a note that it renders more slowly and makes larger files.
- There are no dimension inputs. Audio Only shows no format choice.
- Video cards show the ratio, style and size, for example "From Version 1 · 16:9 · Cinematic · 3840 × 2160 4K · 01:00".
- The player keeps the video's own shape: 9:16, 16:9 or 1:1.

## 10. Renderer architecture

```
UI (VideoFormatPicker) -> output_profile id
  -> POST /api/songs/{id}/music-videos?output_profile=…   (FastAPI Literal allowlist)
  -> MusicVideoService.create: get_profile(); stores output_profile (+ derived aspect_ratio)
  -> generate(): renderer.render(..., video.output_profile, ...)
  -> FFmpegLibassRenderer: profile = renderer_profile(id)
       ASS script on (canvas_width x canvas_height)       [layout]
       FFmpeg graph on (width x height), encoder_args(profile), timeout x pixel_factor
  -> MP4 (H.264 High yuv420p 30 fps + AAC 48 kHz), exact profile size
```

It is still one renderer and one filter graph. Only the numbers come from the profile.

## 11. Aspect-aware lyric layout

`ass_builder.layout_for(width, height, style)` returns a `Layout`:

- **Side safe margin:** `width × style.margin_x/1080`, which is 1/12 of the width (90 px at 1080 wide, the original value; 160 px at 1920).
- **Vertical safe margin:** 8 % of the height, the original value.
- **Centre:** `\pos` and `\move` for lyrics and for the title and end cards.
- **Text scale by orientation:** portrait 1.0, landscape 0.9, square 0.85. It applies to the Active, Next and Title font sizes and the rise distance.

Landscape and square canvases are only 1080 px tall. The scale was chosen so that a worst-case lyric still fits inside the vertical safe margins. The test lyric is 130 characters and wraps to 5 rows; together with its 2-row next line it fits inside the margins on square (see §19).

The title and end cards use the same centre and margins. They are shown only before the first and after the last lyric window, so they can never overlap lyrics.

The **portrait layout is byte-identical to Phase 25**, confirmed by the existing Phase 23 golden ASS files and the Phase 25 style tests, which pass unchanged. Every existing style (Minimal, Dreamy, Bold, Cinematic, Karaoke) works on every canvas (tested: 5 styles × 4 non-default profiles).

## 12. Background scaling

The graph was already scale-to-cover, and now uses the profile's frame:

- **Images:** cover at 112 %, then a slow pan, then crop to the frame.
- **Videos:** cover (at 108 % plus drift for Cinematic and Karaoke), looped with `-stream_loop -1` and trimmed with `-t`.

The aspect ratio is always preserved and only the overflow is cropped, so nothing is ever stretched and there are no bars. Real-render tests use backgrounds of the *opposite* shape (portrait art in landscape frames and vice versa) and check two things:

- ffprobe reports exactly the profile's size;
- every outer row and column of a decoded frame contains picture, not bar black.

The LGPL build has no GPL-only `cropdetect`, so that check reads raw luma instead.

## 13. 4K support

4K is real: `vertical_4k` renders 2160×3840 and `landscape_4k` renders 3840×2160, verified by ffprobe and played in Chrome at native size. The renderer handled it without architectural change:

- Text is rasterised by libass at 4K; a native-resolution crop shows sharp glyph edges, not upscaled ones.
- Filters run inside FFmpeg with no Python frame processing and no intermediate files.
- The FFmpeg timeout scales with the pixel count (`pixel_factor`, 4× for 4K).
- The bitrate is 32 Mb/s, against 8 Mb/s for HD.
- No NVENC or GPU encoding was introduced. The render stays CPU-only with the policy-approved LGPL FFmpeg and OpenH264.

## 14. Performance measurements

Every row is a real render of the same real Tunora Version: "Lyrics Video E2E", a 60.0 s FLAC from ACE-Step with 5 aligned lyric lines. The measurements used the production renderer, with the FFmpeg process instrumented through Windows `GetProcessMemoryInfo`/`GetProcessTimes`. The machine had an RTX 5060 Ti 16 GB. GPU memory was 2,271 MiB before and 2,285 MiB after the batch, so the render uses no GPU.

| Profile | Style / background | Output | Render (wall) | Peak RAM (FFmpeg) | CPU (avg cores) | File size | Avg bitrate |
|---|---|---|---|---|---|---|---|
| vertical_hd | Cinematic / MP4 | 1080×1920 | 11.9 s | 215 MB | 4.3 | 21.0 MB | 2.9 Mb/s |
| vertical_4k | Cinematic / MP4 | 2160×3840 | 50.9 s | 464 MB | 5.3 | 53.2 MB | 7.4 Mb/s |
| landscape_hd | Cinematic / MP4 | 1920×1080 | 12.5 s | 200 MB | 4.3 | 33.3 MB | 4.7 Mb/s |
| landscape_4k | Cinematic / MP4 | 3840×2160 | 49.7 s | 438 MB | 4.7 | 87.5 MB | 12.2 Mb/s |
| square_hd | Cinematic / MP4 | 1080×1080 | 6.7 s | 163 MB | 3.8 | 17.9 MB | 2.5 Mb/s |
| vertical_hd | Karaoke / JPG | 1080×1920 | 15.3 s | 197 MB | 4.0 | 4.5 MB | 0.6 Mb/s |
| vertical_4k | Karaoke / JPG | 2160×3840 | 52.0 s | 446 MB | 5.1 | 9.0 MB | 1.3 Mb/s |
| landscape_hd | Karaoke / JPG | 1920×1080 | 11.1 s | 183 MB | 4.4 | 4.7 MB | 0.7 Mb/s |
| landscape_4k | Karaoke / JPG | 3840×2160 | 47.6 s | 398 MB | 4.5 | 10.2 MB | 1.4 Mb/s |
| square_hd | Karaoke / JPG | 1080×1080 | 7.9 s | 155 MB | 4.0 | 3.8 MB | 0.5 Mb/s |

- **4K cost:** about 4× the HD render time (roughly 50 s for a 60 s song, still faster than real time on this CPU), about 2.2× the peak RAM, and 2.5–4× the file size. These costs are documented, not hidden; the UI warns when 4K is chosen.
- **Why the image renders are small:** a slow-panning still compresses far better than moving footage.

## 15. Security

- **`output_profile`** is checked against an allowlist twice: FastAPI `Literal` at the route, then `get_profile` in the service. The renderer re-resolves it and rejects anything else.
- **No dimensions, filter expressions, codec arguments or paths** are accepted from the client. Width, height, bitrate and filter numbers come only from the profile table. FFmpeg still runs as an argument list with no shell, and inputs still use `file:` with `-protocol_whitelist file`.
- **Legacy `aspect_ratio`** is itself a `Literal` and must agree with the profile.
- **Unchanged:** the style allowlist, background type and magic bytes, the decode check, the decompression-bomb pixel cap, lyric escaping, the same-song trigger and ownership checks, and no internals in any response.
- **The profile is immutable** after creation, enforced by the new DB trigger `music_videos_profile_immutable`.

## 16. Backward compatibility

- **Migration v7 (additive).** `music_videos.output_profile TEXT NOT NULL DEFAULT 'vertical_hd'` plus the immutability trigger. No row is rewritten and no file is touched. All pre-Phase-27 videos were 1080×1920 9:16, which is exactly `vertical_hd`.
- **Verified on the real E2E database** that holds Phase 26 videos: `user_version` went 6 → 7, and an old COMPLETED video reads as `vertical_hd` 9:16 1080×1920 HD and is still served (200, `video/mp4`, 22.8 MB).
- **Requests without `output_profile`** are 9:16 1080×1920, as before. The Phase 23 golden ASS output for 9:16 is byte-identical.
- **Retry keeps the stored profile**; deleting a video still keeps the audio; each Version can still have several videos, now in different formats.

## 17. Tests

- **Backend:** new file `tests/music_videos/test_output_profiles.py` with 50 tests:
  - the canonical table: exact sizes, no square 4K, even dimensions, HD canvas reused for 4K, bitrates;
  - invalid ids: empty, wrong case, `square_4k`, `1080x1920`, path-like, `None`, int;
  - legacy mapping;
  - each profile stored and reaching the renderer;
  - default and legacy `aspect_ratio`;
  - a conflicting ratio stores nothing;
  - cross-song rejection;
  - several formats per Version, with retry keeping the profile;
  - v6→v7 migration and the immutability trigger;
  - API dimensions per profile, 422s, client width/height ignored;
  - layout values;
  - 5 styles × 4 canvases, centred inside the safe margins;
  - a 4K scale-to-cover graph;
  - real renders at landscape HD, square HD, vertical 4K and landscape 4K with opposite-shape backgrounds, checking exact size, codecs, duration, no decode errors, no black segments and no edge bars;
  - rejection of unknown profiles.
- **Contract updates** (intentional, as the contract changed):
  - migration test `LATEST_VERSION` 6 → 7;
  - `FakeRenderer` now receives the profile id, so its assertion `"9:16"` became `"vertical_hd"`.
- **Frontend:**
  - new `video-format-picker.test.tsx` (4 tests): the mirror table, 9:16/16:9/1:1 options, 4K kept across ratios, no dimension inputs;
  - `creation-intent.test.tsx` (+1): the chosen format is sent as `output_profile=landscape_4k` with no width, height or aspect ratio; Audio Only shows no picker; Lyrics Video defaults to `vertical_hd`;
  - existing tests updated for the new query string (`output_profile=vertical_hd` instead of `aspect_ratio=9%3A16`), the new response fields, the card text with dimensions, and the radio-based picker in Song Details.

Results:

| Suite | Result |
|---|---|
| Backend unit/integration (`-m "not smoke"`) | **825 passed** (50 of them new) |
| Backend real-GPU music video smoke | 1 passed |
| Frontend Vitest | **430 passed**, 25 files |
| Typecheck | clean |
| ESLint | 0 errors (1 pre-existing warning in `e2e/create-song.spec.ts`, which this phase did not touch) |
| `next build` | succeeded |

## 18. E2E results

`frontend/e2e/multi-format.spec.ts` runs on the real stack: ACE-Step, a throwaway backend on :8010, Next on :3100, and real Chrome. Each case goes through the Create page UI, the intent card, the aspect ratio and resolution radios, a real song and a real video. Each case then checks:

- the job completed and the Music Video record carries the exact profile, width, height and `source_version_id`;
- the job page card shows the size;
- the video plays in Chrome with `videoWidth`/`videoHeight` equal to the profile;
- the downloaded file is served as `video/mp4`;
- ffprobe reports H.264 yuv420p at the exact size and AAC at 48 kHz, with a duration of 60 ± 1.5 s;
- a full decode reports no errors.

The cases are:

1. Audio + Video, 9:16 HD, 1080×1920 (this case also checks no overflow at 375 and 768 px).
2. Audio + Video, 16:9 HD, 1920×1080.
3. Lyrics Video, 1:1 HD, 1080×1080.
4. Audio + Video, 16:9 4K, 3840×2160.
5. Lyrics Video, 9:16 4K, 2160×3840.

**All 35 E2E tests passed in 19.9 min in one run**: the 5 new multi-format cases plus the full `creation-workflow`, `music-video` and `create-song` regression suites.

The regression suites confirm that Phase 23–26 behaviour is unchanged:
- Audio Only, Audio + Video and Lyrics Video;
- video failure → Retry, and Delete keeps the audio;
- Song Details Create Music Video (whose form now uses the picker, with 9:16 HD checked by default, and has no overflow at 375 and 768 px);
- the waveform, versions, Library and downloads.

Backend render times for the E2E videos: HD 9.8–15.6 s, 4K 51.2 s and 59.1 s (60 s songs).

## 19. Real render results and visual inspection

The renders in §14 are real renders of a real Tunora Version. Frames were extracted at the title (0.5 s), the first lyric, the middle and the end for all ten renders and inspected. A worst-case long-line render was also made for square, landscape and portrait with the Cinematic and Bold styles. What was checked:

- **Lyric position:** centred horizontally and vertically on every format. The next line is dimmed below and stays inside the safe margins.
- **Title and end card:** centred and fully readable on 9:16, 16:9 and 1:1 at HD and 4K. They never overlap lyrics.
- **Background:** scale-to-cover everywhere. There is no stretching (the gradient and footage keep their proportions) and no black bars; the edge check in the tests passes.
- **Long lyrics:** a 130-character line wraps to 5 rows plus a 2-row next line and stays inside the square frame's safe area. In landscape it wraps to 3 rows plus 1.
- **4K sharpness:** a native-resolution 1000×420 crop of `landscape_4k` shows crisp glyph edges, so libass draws at 4K and nothing is upscaled.

## 20. Known limitations

- **4K takes about 4× longer to render** than HD: about 50 s for a 60 s song on this machine, CPU-only. Files are 2.5–4× larger. The UI says so.
- **Landscape lyrics are relatively small.** They are centred and sized for the worst case, so short lines occupy only the middle half of a 16:9 frame. Lines longer than about 130 characters could exceed the square frame's vertical safe area. Real sung lines are far shorter.
- **Safe zones are generic.** They are proportional margins (1/12 of the width at the sides, 8 % of the height top and bottom), not per-platform overlays. Lyrics are centred, which clears the usual bottom and right UI areas of the 9:16 apps; the 9:16 layout itself was deliberately left unchanged.
- **Backgrounds are cropped to the centre.** A background whose subject is off-centre can have it cropped away. There is no content-aware reframing.
- **The frontend keeps a copy of the profile table for labels.** The backend stays authoritative, and a test pins the copy.

## 21. Deferred work

- Square 4K, or any other size, if a real platform need appears.
- Per-platform safe-zone presets (for example TikTok or Shorts overlays).
- Content-aware background reframing.
- GPU (NVENC) encoding. It is not needed: 4K renders in less time than the song lasts.
- Custom FPS or bitrate, HDR, HEVC/AV1 and publishing integrations are out of scope for this phase.
