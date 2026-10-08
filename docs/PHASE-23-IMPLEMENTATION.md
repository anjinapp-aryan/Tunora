# PHASE 23 — MUSIC VIDEO COMPOSER

Implementation report. The design reference is `PHASE-23-MUSIC-VIDEO-COMPOSER.md`. Research and prototype: `I:\Tunora-validation\music-video\PHASE-22A-ADOPTION-REPORT.md` and `PHASE-22B-IMPLEMENTATION-REPORT.md`.

## 1. Executive Summary

Tunora can now turn any finished vocal Version of a Song into a **9:16, 1080×1920, 30 fps H.264/AAC lyric video**, directly from Song Details. The user picks a Version, confirms its lyrics, uploads an image or MP4 background, picks a style, and generates. The result can be played in the page and downloaded.

The pipeline is the Phase 22B prototype, moved into Tunora:

- local forced alignment of the Version's stored lyrics (stable-ts on CPU);
- a **TimedLyrics** boundary between lyrics and rendering;
- a libass + LGPL FFmpeg renderer.

It needs no LLM, no API key, no cloud service, no new AI video model, and no Remotion. No GPU model is loaded for it.

A Music Video is a new, separate domain object. It references exactly one source Version, which is never modified.

**Real generation.** The Phase 22A "I Will Rise" Version produced a real Music Video in 17.9 s end-to-end: 11 matched lines, and 21 unmatched lines that were omitted, not invented.

**Tests.**

| Suite | Result |
|---|---|
| Backend | 740 passed (656 pre-existing + 84 new) |
| Real-GPU smoke | passed |
| Frontend | 399 passed |
| Music Video E2E (real stack, Chrome) | 2/2 passed |

**Regressions found and fixed during the phase:**

- The Next.js proxy limited uploads to 10 MB.
- Two existing E2E tests broke because Song Details is now taller.
- An existing Vitest race failed more often (see §20).

## 2. Scope

**Built:** the MusicVideo domain, SQLite schema v6, the API, the TimedLyrics boundary, local alignment, the libass/FFmpeg renderer, the FFmpeg LGPL policy, secure background upload and storage, the in-process job lifecycle with restart handling, the Song Details UI (create, progress, play, download), tests, and docs.

**Not built, as the phase required:** AI video or image generation, avatars or lip sync, a timeline or subtitle editor, trimming, transitions, 16:9 and 1:1 output, publishing integrations, cloud rendering, GPU video models, an LLM creative director, stock-media search, and manual lyric timing (deferred; see §25).

## 3. Phase 22 Reuse Decision

| Phase 22B piece | Phase 23 | Classification |
|---|---|---|
| `timed_lyrics.py` | `app/music_videos/timed_lyrics.py` | **REUSE** — only docstrings changed |
| `ass_builder.py` (styles, layout, escaping, karaoke) | `app/music_videos/ass_builder.py` | **REUSE** — only docstrings and imports changed |
| `render.py` | `renderer.py` | **ADAPT** — FFmpeg injected from the policy; 9:16 + OpenH264 only; a timeout; `probe` / `check_background` helpers. The filter graph, encoder arguments and safety rules are unchanged. |
| `align.py` | `align_worker.py` + `aligner.py` | **ADAPT** — runs as a worker process; exit codes; drops punctuation-only tokens; model cache location configurable. The pinned-tail and collapsed-line detection is unchanged. |
| Security suite | `tests/music_videos/test_timed_lyrics_and_ass.py`, `test_renderer_real.py` | **REUSE** (ported) |
| Poppins OFL fonts | `app/music_videos/fonts/` | **REUSE** |
| Song, Version, AudioStorage, JobService, polling, download | used as they are | **COMPOSE** |

No external application or CLI was embedded: not dynamic-typography-videos, not Remotion, not ACE-Step-Studio.

## 4. Architecture

```
Song Details UI -> Next /api rewrite -> routes_music_videos -> MusicVideoService
   MusicVideoService -> JobService.resolve_version_audio (reused source checks)
                     -> MusicVideoRepository (SQLite v6) / MusicVideoStorage (data/music-videos)
                     -> BackgroundTask: LocalForcedAligner (worker process) -> TimedLyrics
                                        -> FFmpegLibassRenderer (LGPL FFmpeg + libass) -> MP4
```

The full description is in `PHASE-23-MUSIC-VIDEO-COMPOSER.md` §1.

## 5. MusicVideo Domain

`MusicVideo` has these fields:

- `id` (`mv-<uuid4>`), `song_id`, `source_version_id`
- `status`: PENDING → ALIGNING → RENDERING → COMPLETED | FAILED
- `style`, `aspect_ratio`
- `background_key`, `background_media_type`
- `duration`, `output_key`, `output_size_bytes`
- `timed_lyrics` (matched and unaligned lines)
- `error` (internal only)
- `created_at`, `updated_at`, `completed_at`

There is no timeline, scene graph, effects database, prompt history, social or publishing metadata, or analytics.

## 6. Database Migration

Migration **5 → 6** (`app/jobs/migrations.py`) uses the existing `PRAGMA user_version` framework. It is one `BEGIN IMMEDIATE` step, additive only, and uses `IF NOT EXISTS` throughout.

**New table and indexes.** It adds the `music_videos` table, with `ON DELETE CASCADE` on both `song_id` and `source_version_id`, plus indexes on `song_id` and `status`.

**Integrity triggers:**

- `music_videos_source_same_song` rejects a source Version that belongs to another Song.
- `music_videos_source_immutable` rejects changes to the source, the style/aspect choices, or the background.

**Verification:**

- A test upgrades a v5 database with existing rows and confirms that every Song and Version row is byte-identical afterwards, and that re-running the migration is a no-op.
- The real development database migrated at startup to schema 6, keeping all 13 Versions.

## 7. TimedLyrics

The renderer consumes only validated TimedLyrics, never raw lyrics. Validation rejects:

- NaN, Infinity or negative times, or `end` before `start`;
- words that end after the song, or are out of order;
- more than 2 000 lines, more than 64 words per line, lines over 200 characters, or a file over 5 MB.

The document carries `unaligned_lines`. A future manual-correction provider would plug into the same boundary, using `source.kind = "manual"`.

## 8. Alignment

The aligner (`LocalForcedAligner` → `python -m app.music_videos.align_worker`) runs stable-ts 2.19.1 with Whisper `base` on the CPU, in a separate process with a timeout. The approved FFmpeg is pinned on that process's `PATH`; the worker exits with code 6 if `ffmpeg` resolves anywhere else.

**Stored lyrics are never altered.** Lines the audio doesn't contain are detected as pinned tails or collapsed lines, then omitted from the video and listed to the user.

**Verified on real audio:**

- From Tunora's own venv, the aligner reproduces Phase 22B exactly on the 22B FLAC: 13 matched / 19 unmatched, in 4.9 s including model load.
- One fresh 30 s ACE-Step generation came back effectively **without vocals**; an independent Whisper-small pass heard no speech at all. Tunora correctly failed that video with "None of this version's lyrics could be matched to its audio." The smoke and E2E tests now use the prompt that produced clear vocals in 22A/22B. This is a provider limitation, not a Tunora bug, and no timing was fabricated.

## 9. Renderer

`FFmpegLibassRenderer` produces H.264 High (OpenH264, 8 Mb/s), `yuv420p` limited range, 30 fps, AAC 192 kb/s at 48 kHz, with `+faststart`, trimmed exactly to the audio length.

- Readability comes from `colorlevels` + `hue`, because `eq` is GPL-only.
- Lyrics are burned in by libass with the bundled Poppins (OFL).
- The output is written in a private temporary directory and moved into place only on success.

## 10. Background Video

Supported backgrounds are JPEG/PNG (image with a slow pan) and MP4/MOV/WebM (looped with `-stream_loop -1`, re-timed to 30 fps, cover-scaled and centre-cropped to 1080×1920).

Verified by real tests:

- A 2 s 16:9 clip under a 7 s song loops to the full length with 0 black segments and 0 decode errors.
- The real "I Will Rise" render, using the 12 s sunset clip under 60 s of audio, has 0 black segments and 0 decode errors.
- A real 68 MB background went through the whole stack and rendered correctly.

## 11. 9:16 Rendering

9:16 at 1080×1920 is the only production path. The UI shows the aspect ratio but it cannot be changed; the API accepts only `9:16`.

Layout is the Phase 22B libass approach: one event holds the active line plus the dimmed next line, wrapped inside 90 px safe margins. Real render tests cover a 94-character line, consecutive long lines, and malicious text. Frames of the real "I Will Rise" video were inspected: title card, per-word fill, next-line preview, and no overlap or clipping.

## 12. FFmpeg Validation

The approved build is **BtbN `ffmpeg n9.0.2-10-g51c4a23d74-20260926`**, `win64-lgpl-shared`, installed by the operator in `backend/tools/ffmpeg/` (git-ignored; copied from the Phase 22B workspace, not re-downloaded).

- Its `LICENSE.txt` is **LGPL v3**.
- The configuration includes `--enable-version3 --enable-libass --enable-libfreetype --enable-libharfbuzz --enable-libfribidi --enable-fontconfig --enable-libopenh264 --enable-ffnvcodec --enable-amf --enable-libvpl`.
- There is **no** `--enable-gpl` and **no** `--enable-nonfree`.

**Relevant codecs and filters:** encoders `libopenh264` and `aac`; filters `ass`, `colorlevels`, `hue`, `scale`, `crop`, `setsar`, `format`.

**Policy** (`app/music_videos/ffmpeg.py`):

- It looks in `TUNORA_FFMPEG_DIR`, then `backend/tools/ffmpeg/bin`, then `PATH`.
- It reads each candidate's own configuration, rejects GPL or non-free builds, and requires the features above.
- It logs every rejection, never downloads anything, and returns 503 when no build is approved.

**Verified against real binaries:** the LGPL build is accepted. The machine's `PATH` FFmpeg (winget "full_build" 9.0.1) is **rejected**: `--enable-gpl`.

## 13. License Analysis

The new Python dependencies are an **optional extra**: `uv sync --extra music-video`.

| Package | Version | License | Why it's needed |
|---|---|---|---|
| stable-ts | 2.19.1 | MIT | Forced alignment of given lyrics. The core backend has nothing that aligns text to audio. |
| openai-whisper | 20250625 | MIT (weights MIT) | Alignment model. |
| torch (CPU) / torchaudio | 2.14.0 / 2.11.0 | Apache-2.0 (per package metadata) / BSD | Pulled in by the two above. |
| numba/llvmlite, tiktoken, regex, tqdm, networkx, sympy, … | — | BSD, MIT, Apache-2.0 + CNRI, MPL-2.0 + MIT | Transitive. |

**Alternatives rejected in the fresh audit:**

- torchaudio's MMS aligner and ctc-forced-aligner: their weights are CC-BY-NC.
- WhisperX: needs gated pyannote models.
- aeneas: AGPL.
- `python-multipart`: not added. Uploads use the raw request body instead.

**Other components:**

- FFmpeg: LGPL v3 build. The libraries are separate DLLs, so they can be replaced.
- libass (ISC) and its dependencies: FreeType (FTL), HarfBuzz (MIT), FriBidi (LGPL-2.1+), fontconfig (MIT).
- OpenH264: BSD-2.
- Poppins: OFL-1.1.
- `docs/LICENSE-AUDIT.md` has a new Phase 23 section.

**Findings recorded, not hidden:**

- **The stable-ts GitHub repository has been archived (read-only) since 2026-05-30.** It still installs and works, and it sits behind `LyricsAligner`, so it can be replaced or forked. This is a maintenance risk.
- **Commercial distribution of H.264 output requires separate legal review.** No legal conclusion is drawn here.
- **FFmpeg's LGPL redistribution obligations must be respected** if Tunora ever ships the binary.

## 14. Security

**Tested:**

- Path traversal and arbitrary paths: `..\..\Windows`, `C:\Windows\win.ini`, `notepad.exe`, `concat:` and URLs.
- Invalid, cross-Song and malformed source Versions; missing or deleted audio.
- Missing background, wrong type (SVG, EXE), magic bytes that don't match the declared type, oversized uploads (a streaming cap plus `Content-Length` → 413), decompression-bomb resolution, and an audio-only "video".
- Malformed or huge TimedLyrics; NaN, Infinity or negative timestamps; `end < start`.
- Malicious ASS syntax (`{\p1}` drawing, `{\fn…}`), FFmpeg filter syntax, shell syntax and control characters. These were rendered for real and appear as plain text.
- A GPL FFmpeg (rejected), unsupported encoders, duplicate generation requests (409, enforced atomically), and a restart during rendering.

**Structural guarantees:**

- A source scan finds no `shell=True`, `os.system` or `os.popen`.
- Every FFmpeg input is `file:` with `-protocol_whitelist file`; a test checks the actual argument list.
- No caller path ever appears in the filtergraph.
- Public responses never contain keys, paths or internal errors (tested).

**Mutation checks:** 9 mutations to the key protections, 9 caught. Two initially survived; both exposed real test gaps (a pinned-tail-only line, and the protocol pinning), and tests were added.

## 15. API

- `POST /api/songs/{song_id}/music-videos?source_version_id=&style=&aspect_ratio=9:16`. The background is the raw body with its `Content-Type`. Returns 202.
- `GET /api/songs/{song_id}/music-videos`
- `GET /api/music-videos/{id}`
- `GET /api/music-videos/{id}/video` (Range, ETag, `nosniff`).

Errors: 404, 409, 413, 422 and 503, each with a fixed safe message.

**Configuration change:** `next.config.ts` sets `experimental.proxyClientMaxBodySize: "201mb"`. Next's `/api` rewrite buffers request bodies up to 10 MB by default and failed larger uploads with a plain 500. This was found by a real test, not assumed. After the fix, a 68 MB background uploaded through Next was stored byte-identical.

## 16. UI

Song Details has a separate **Music Videos** section: a create form (Version, fixed 9:16, read-only lyrics, background, style, Generate), progress text ("Preparing / Aligning lyrics / Rendering / Completed"), an unmatched-lyrics notice, a safe failure message, a native `<video>` player, and **Download MP4** (the same fetch → Blob → `<a download>` path as audio).

The controls are labelled native elements, with `role="status"` / `role="alert"` and visible focus. E2E confirms no horizontal overflow at 375 px and 768 px. The Library is unchanged; Music Videos are reached from Song Details only.

## 17. Job Lifecycle

Generation runs as a FastAPI `BackgroundTask` in the API process, the same model as audio generation. There is no Celery, Redis or other queue.

- A process lock allows one render at a time; others wait as PENDING.
- The UI polls with the existing recursive-timeout, backoff and abort discipline, only while something is unfinished. There are no WebSockets.
- A duplicate request for a Version whose video is still in progress is refused atomically, inside the insert transaction.

## 18. Restart Behavior

At startup, `recover_interrupted()` marks every non-terminal Music Video FAILED with "Generation was interrupted when Tunora restarted. Please generate it again." Nothing is re-run and nothing is duplicated, and the failed video doesn't block a new one.

The final MP4 path only ever holds a complete file. A process killed mid-render may leave a temporary directory in the OS temp folder.

## 19. Storage

Music Videos have their own root, `data/music-videos/<id>/` (setting: `TUNORA_MUSIC_VIDEO_ROOT`), which holds `background.<ext>` and `<id>.mp4`. Keys are resolved with the audio storage's own containment rules; nothing is ever written under `data/audio`.

Deleting a Song cascades its rows and then removes the files (tested through the API and in E2E). A Song deleted *while* its video renders leaves no files (tested).

## 20. Testing

**Backend: 740 passed** (656 pre-existing, unchanged, plus 84 new). The new tests cover:

- migration and repository (8);
- service (28);
- API (8);
- FFmpeg policy (12, including the real LGPL accepted and the real GPL rejected);
- TimedLyrics, ASS and aligner rules (21);
- real FFmpeg renders (7).

**Real-GPU smoke:** `tests/test_music_video_smoke.py` passed. A real ACE-Step 60 s vocal Version → alignment → render took 15.9 s, 12.5 MB, 6/6 lines matched. The pre-existing 16 real-GPU smoke tests were **not** re-run in this phase. Phase 23 changes only a shared helper that the creative-operation smoke tests use; the equivalent real E2E creative-operation tests passed (below).

**Frontend: 399 passed.** New: the API client (15) and the section component (9). Typecheck is clean, ESLint shows only the pre-existing Phase 12 warning, and `next build` passes.

**E2E, full suite against the real stack:** 20 passed and 3 failed on the first run. Each failure was investigated:

1. *Extend, Remix and Repaint*: the Repaint job completed on the backend in 9 s, but the page stalled while I was running CPU-heavy backend and mutation tests in parallel. **Passed when re-run alone.** This was contention, not code.
2. and 3. *Extract* and *Repaint drag*: a **real regression caused by Phase 23**. Confirmed by removing only the new section: they passed without it and failed with it. A Playwright trace showed the waveform click landing at y = −29. The taller Song Details page left the waveform just above the viewport, and the test helper clicked raw coordinates without scrolling. Fix: the helper now calls `scrollIntoViewIfNeeded()` before measuring. The assertion is unchanged. **Both passed on re-run.**

The **Music Video E2E** (2 tests) passed in the full run and separately. It uses installed Chrome, because Playwright's Chromium has no H.264 decoder. It covers a real vocal song → Song Details → Version → MP4 background → Generate → progress → real playback (1080×1920, time advancing) → download byte-identical to the served file; plus the image background, an SVG refused before upload, and Song deletion removing the video.

**Changes to existing tests.** Each is intentional:

- `song-details.test.tsx`: the page now also issues one read-only `GET .../music-videos`.
- `version-actions.test.tsx`: the known Phase 19 real-timer race became more frequent with the new section's extra fetch. The baseline passed 4/4; with Phase 23 it failed 2/4. The test now *waits* for the "— Latest" title instead of checking it instantly; the assertion is the same. After the change: 6/6.
- The test mock gained a route for the new endpoint.
- `create-song.spec.ts`: the waveform scroll fix above.

## 21. Real Generation

These used the real development database and stack: ACE-Step on :8001, the backend on :8000, Next on :3000.

- **"I Will Rise" (the Phase 22A Version, `ver-53c1604d…`, real ACE-Step MP3)** with the 12 s looping sunset MP4 and the Minimal style:
  - COMPLETED in **17.9 s** end-to-end: upload, about 5 s of alignment, about 12 s of rendering.
  - H.264 High 1080×1920 30 fps, `yuv420p`; AAC LC 48 kHz stereo; 60.000 s; 19,078,854 bytes.
  - 0 black segments, 0 decode errors; the served bytes equal the stored file.
  - 11 matched lines, 21 unmatched (reported, not rendered).
  - The source MP3's SHA-256 is unchanged (`10e1e4cc…`).
- **Same Version, 68 MB background uploaded through Next:** COMPLETED, 61,745,908 bytes, 11 lines matched.
- **Smoke test:** a fresh 60 s ACE-Step vocal Version → 6/6 lines matched → 15.9 s.

A copy of the first video is kept outside the repository at `I:\Tunora-validation\music-video\phase23\real-i-will-rise.mp4`.

## 22. Performance

| Step | Measured |
|---|---|
| Alignment, 60 s song (CPU, Whisper `base`, worker process incl. model load) | about 4.9–5 s |
| Rendering, 60 s at 1080×1920 (CPU, OpenH264) | about 11–12 s |
| Total, 60 s real Version, via the API | 15.9–17.9 s |
| Output size, 60 s | 12.5–19 MB (depends on the background) |

This is the same order of magnitude as Phase 22B's 11.8 s CPU render. No GPU model is loaded; ACE-Step is only used to create the audio Version itself. No optimization was attempted.

## 23. Human Validation Status

Frames of the real "I Will Rise" video were inspected automatically: title card, per-word fill, next-line preview, no overlap or clipping, correct 9:16 crop.

**Human viewing is still required** for visual aesthetics, how the lyric timing *feels*, typography preference, and how distracting the background is. Tests do not validate subjective quality. The uploaded reference videos were not available in this session.

## 24. Known Limitations

1. Stored lyrics may differ from what was sung; ACE-Step can skip or merge lines, or return an almost instrumental take.
2. Unmatched lyrics are not rendered; the UI lists them.
3. Manual lyric correction is deferred.
4. Only 9:16 is available in this first version.
5. Commercial distribution of H.264 output requires separate legal review.
6. FFmpeg's LGPL redistribution obligations must be respected.
7. Rendering uses the CPU by default.
8. NVENC is not required and not used.
9. No LLM is required.
10. No AI video-generation model is required, and no GPU model is loaded.
11. One render at a time; a restart fails in-flight videos, which are not resumed.
12. stable-ts upstream is archived.
13. The first alignment on a new machine downloads the Whisper `base` weights (about 145 MB) once.
14. Uploads through Next are buffered in memory, up to the 201 MB limit.
15. Music Videos are not shown in the Library.

## 25. Deferred Work

- A manual timing and correction provider for TimedLyrics.
- Library visibility.
- More styles and aspect ratios.
- Optional NVENC with a driver-matched build.
- Replacing or forking the archived aligner if needed.
- An **optional** future assistant that fills a `MusicVideoSpec` for the same deterministic renderer. It would never render, and under Tunora's rules it would reuse ACE-Step's own local LM first. Documented only; not built.

## 26. Git Commit

Exactly one commit on `feature/tunor_2_video`: **"Add Music Video Composer"**.

**Excluded, deliberately:**

- the pre-existing, unrelated `CLAUDE.md` diff;
- the `ACE-Step-1.5` submodule marker;
- the untracked Phase 20 audit doc;
- git-ignored files: `backend/tools/ffmpeg`, `data/`, `*.db`;
- the E2E build output and the `tsconfig.json` change that `next typegen` made automatically for it (reverted).

## 27. Git Push

The commit is pushed with `git push -u origin feature/tunor_2_video`, and `git rev-parse HEAD` is verified to equal `git rev-parse origin/feature/tunor_2_video`. The commit hash is reported in the final summary.
