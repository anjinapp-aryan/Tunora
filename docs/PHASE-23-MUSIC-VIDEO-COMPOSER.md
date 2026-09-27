# Phase 23 — Music Video Composer

This is the reference for how Tunora turns an audio Version into a 9:16 lyric video. It covers the architecture, the rules the code enforces, and why each choice was made. Results and measurements are in `PHASE-23-IMPLEMENTATION.md`; the research behind the renderer is in the Phase 22A/22B reports (`I:\Tunora-validation\music-video\`).

## 1. Architecture

```
Song Details (Next.js)  ── POST /api/songs/{song_id}/music-videos (background = request body)
        │                  GET  /api/songs/{song_id}/music-videos · GET /api/music-videos/{id}[/video]
        ▼
routes_music_videos ──> MusicVideoService ──> JobService.resolve_version_audio  (reused Version checks)
                               │          ──> MusicVideoRepository (SQLite, same DB, schema v6)
                               │          ──> MusicVideoStorage   (data/music-videos/<id>/…)
                               │   BackgroundTask (in-process, one render at a time)
                               ├──> LyricsAligner ── LocalForcedAligner ── align_worker process
                               │        (stable-ts + Whisper base, CPU, approved FFmpeg on PATH)
                               │        -> TimedLyrics (matched lines + unaligned_lines)
                               └──> MusicVideoRenderer ── FFmpegLibassRenderer
                                        (ASS script via libass + LGPL FFmpeg, OpenH264 + AAC)
                                        -> 1080×1920 H.264/AAC MP4
```

`main.py` remains the only place that names the concrete classes.

The renderer, the TimedLyrics validation, the ASS generation and the aligner logic are reused from the validated Phase 22B prototype. `timed_lyrics.py` and `ass_builder.py` changed only in their docstrings. `renderer.py` and `align_worker.py` are close adaptations; the changes are listed in the implementation report.

There is no LLM, no API key, no cloud service, no Remotion/Node/Chromium renderer, no GPU model, and no new queue.

## 2. MusicVideo domain

A Music Video is a **presentation artifact**, not an audio Version:

```
Song ── Versions (V1 FLAC, V2 FLAC, …)      unchanged by this phase
     └─ Music Videos (Video 1, Video 2, …)  each made from exactly one Version
```

`MusicVideo` (`app/music_videos/models.py`) has these fields:

- **Identity and source**: `id` (`mv-<uuid4>`, same convention as `song-`/`ver-`/`proj-`), `song_id`, `source_version_id`.
- **Choices**: `style` (`minimal_white` | `dreamy` | `bold`), `aspect_ratio` (`9:16` only).
- **Background**: `background_key`, `background_media_type`.
- **State and result**: `status`, `duration` (the source audio's), `output_key`, `output_size_bytes`.
- **Lyrics**: `timed_lyrics` — the document the video was rendered from, including the lines that could not be matched.
- **Error**: `error` — internal only; the API shows a fixed message.
- **Timestamps**: `created_at`, `updated_at`, `completed_at`.

Two things are enforced by the database itself, not just the code:

- The source Version belongs to the same Song (trigger `music_videos_source_same_song`).
- The source and inputs never change after creation (trigger `music_videos_source_immutable`).

A Version is only ever read. Nothing in this phase changes the Song/Version/Job tables or their behaviour.

## 3. API

| Method | Path | Result |
|---|---|---|
| POST | `/api/songs/{song_id}/music-videos?source_version_id=&style=&aspect_ratio=9:16` | 202 + MusicVideo (`PENDING`); generation is scheduled |
| GET | `/api/songs/{song_id}/music-videos` | `{items: [...]}`, newest first |
| GET | `/api/music-videos/{id}` | one Music Video (the UI polls this state through the list) |
| GET | `/api/music-videos/{id}/video` | the MP4 (`FileResponse`: Range, ETag, `nosniff`, inline) |

**Upload format.** The background is the raw request body, and `Content-Type` must be one of `image/jpeg`, `image/png`, `video/mp4`, `video/quicktime` or `video/webm`. This avoids adding a multipart-parser dependency, and it streams with an early size cap.

**Errors.** Every error message below is a fixed, user-safe sentence.

| Status | When |
|---|---|
| 404 | Unknown or malformed Song/Version, or a Version of another Song |
| 409 | The Version has no audio, or a video for this Version is already being generated |
| 413 | The upload is too large |
| 422 | Bad style, aspect ratio or background |
| 503 | No approved FFmpeg is installed |

**Response allowlist** (`schemas.MusicVideoResponse`): no storage keys, no filesystem paths, no internal error text, no timing internals. `unmatched_lines` is exposed: it is the user's own lyric text that could not be matched, so the UI can say so.

## 4. Renderer

`MusicVideoRenderer.render(audio_path, timed_lyrics, background_path, style, aspect_ratio, output_path, title=None)` is implemented by `FFmpegLibassRenderer`, which runs one FFmpeg command:

- **Image background**: covered at 112 % and slowly panned.
- **Video background**: `-stream_loop -1`, re-timed to 30 fps, cover-scaled and centre-cropped to 1080×1920.
- **Readability**: `colorlevels` + `hue` darken the background without greying it. These are LGPL filters; FFmpeg's `eq` filter is GPL-only.
- **Lyrics**: burned in by `ass=lyrics.ass:fontsdir=fonts` (libass).
- **Output**: `yuv420p` TV range, OpenH264 High profile at 8 Mb/s, AAC 192 kb/s at 48 kHz, `+faststart`, trimmed to exactly the audio duration.

**Text layout** (`ass_builder.py`):
- Each screen is one ASS event holding the active line and, dimmed below it, the next line.
- libass wraps inside 90 px side margins (`WrapStyle 0`) and stacks the wrapped rows of that single event itself, so long or consecutive long lines cannot overlap. This was the Phase 22A bug.
- A title card appears during an intro of 3 s or more.
- Words get a per-word karaoke fill (`\kf`); lines fade in and out.
- The font is Poppins (SIL OFL), bundled in `app/music_videos/fonts/` with `OFL.txt`.

## 5. TimedLyrics

The renderer consumes only **TimedLyrics** (`app/music_videos/timed_lyrics.py`), never raw lyrics:

```
{"version": 1, "duration": 60.0, "source": {"kind": "forced_alignment", ...},
 "lines": [{"text": "...", "words": [{"text": "I", "start": 15.1, "end": 15.3}, ...]}],
 "unaligned_lines": ["..."]}
```

The document is validated as untrusted input:

- Times must be finite, non-negative, ordered, and `end ≥ start`.
- Words must not end after the song.
- Size limits: at most 2 000 lines, 64 words per line, 200 characters per line, and a 5 MB file.
- Text is collapsed to printable single-line strings.

**Manual timing (deferred).** The model already supports it. A manual-correction provider would produce the same document with `source.kind = "manual"`, and the renderer would not change. The stored `timed_lyrics` of a Music Video is the natural starting point for such an editor. It is not implemented in this phase.

## 6. Alignment

`LocalForcedAligner` runs `python -m app.music_videos.align_worker` as a separate process, for three reasons:

- torch and Whisper never load into the API process.
- A stuck alignment is killed by a timeout (900 s).
- The worker prepends the approved FFmpeg to `PATH` and refuses to run if `ffmpeg` resolves anywhere else. Whisper decodes audio through `ffmpeg`, and the system `ffmpeg` on the development machine is a GPL build.

It aligns the Version's **stored lyrics**, which are never modified, using stable-ts on CPU with the Whisper `base` model.

**Detecting lines that were never sung.** Phase 22A/22B showed that ACE-Step does not always sing every stored line. Two failure signatures are detected, and those lines are reported in `unaligned_lines` rather than rendered with invented timing:
- **Pinned tail**: zero-length words stuck at the end of the audio.
- **Collapsed line**: a line squeezed to less than 0.1 s per word.

The UI tells the user how many lines were left out and lists them. If *no* line matches, the video fails with "None of this version's lyrics could be matched to its audio."

**Other rules:**
- Section tags such as `[Chorus]` and punctuation-only tokens are skipped.
- If the aligner does not return exactly one timestamp per lyric word, alignment fails rather than guessing.

**Weights.** The Whisper `base` weights (MIT) are read from the local cache (`~/.cache/whisper`, or `TUNORA_ALIGNER_MODEL_DIR`). The first run on a new machine downloads them once. That download is the only network access; alignment and rendering themselves run fully offline.

## 7. Background handling

- **Allowed types**: JPEG and PNG up to 20 MB; MP4, MOV and WebM up to 200 MB.
- **Size cap**: the upload is streamed to a temporary file and aborted as soon as it passes the cap. It is renamed into place only if complete.
- **Content checks**: the magic bytes must match the declared type, then `ffprobe` must find a video stream with an allowed codec, a positive resolution of at most 7680×4320 (a guard against decompression bombs), and a positive duration for videos.
- **Cleanup**: any failure removes the whole directory.
- **Stored at** `data/music-videos/<id>/background.<ext>`. The name and extension come from Tunora, never from the client.

## 8. FFmpeg requirements

`app/music_videos/ffmpeg.py` enforces `docs/LICENSE-AUDIT.md` ("must ship LGPL-only build").

**Where it looks**, in order: `TUNORA_FFMPEG_DIR`, then `backend/tools/ffmpeg/bin` (git-ignored, placed by the operator), then `ffmpeg` on `PATH`. Nothing is ever downloaded.

**What it checks.** It reads the binary's own `configuration:` line and requires all of these:
- no `--enable-gpl` and no `--enable-nonfree`;
- filters `ass`, `colorlevels`, `hue`, `scale`, `crop`, `setsar`, `format`;
- encoders `libopenh264` and `aac`.

**Result.** Every rejected candidate is logged. If none passes, creating a Music Video returns 503. On the development machine, the `PATH` FFmpeg (winget "full_build", `--enable-gpl --enable-libx264`) is rejected. The approved build is BtbN `n9.0` LGPL shared (`LICENSE.txt` = LGPL v3); its exact version and configuration are in the implementation report.

**Setup:** extract an LGPL build so that `backend/tools/ffmpeg/bin/ffmpeg(.exe)` exists, or set `TUNORA_FFMPEG_DIR`. Then run `uv sync --extra music-video` in `backend`.

## 9. License considerations

**New Python dependencies.** These are an optional extra (`music-video`), so the core backend stays lean:
- `stable-ts` (MIT) and `openai-whisper` (MIT; `base` weights MIT). Note: the `stable-ts` GitHub repository has been **archived (read-only) since 2026-05-30**. It installs and works, and it sits behind `LyricsAligner`, so it can be forked or replaced without touching the renderer.
- Transitive: `torch` CPU (Apache-2.0 per metadata), `torchaudio` (BSD), `numba`/`llvmlite` (BSD / Apache-2.0 with LLVM exception), `tiktoken` (MIT), `regex` (Apache-2.0 + CNRI), `tqdm` (MPL-2.0 + MIT), and other MIT/BSD packages.

**Alternatives rejected in the audit:**
- torchaudio's MMS aligner and `ctc-forced-aligner`: their weights are CC-BY-NC.
- WhisperX: needs gated pyannote models.
- aeneas: rejected in an earlier phase.

**Other components:**
- **FFmpeg**: LGPL v3 build. The libraries are separate DLLs, so they are replaceable. **FFmpeg LGPL redistribution obligations must be respected if Tunora ever ships the binary** (license text, source offer, relinkable libraries).
- **libass**: ISC. Its dependencies are FreeType (FTL), HarfBuzz (MIT), FriBidi (LGPL-2.1+) and fontconfig (MIT).
- **OpenH264**: BSD-2.
- **Poppins**: SIL OFL-1.1.
- **Adapted code**: the style values and line-grouping rules came from `dcmcand/dynamic-typography-videos` (Apache-2.0) and are attributed in the module docstrings.

**H.264 patents.** **Commercial distribution of H.264 output requires separate legal review.** Cisco's patent coverage applies only to Cisco-distributed OpenH264 binaries, and the patent question applies to any H.264 encoder. This document does not draw a legal conclusion.

## 10. Security

**Subprocesses.** Every subprocess is an argument list; `shell=True`, `os.system` and `os.popen` never appear, and a test scans the sources to check that. Large payloads such as lyrics and the ASS script go into files, never onto a command line.

**FFmpeg inputs.**
- User-influenced paths never appear inside a filtergraph: the ASS script and fonts live in a private temporary directory under fixed names.
- All inputs are opened as `file:<resolved path>` with `-protocol_whitelist file`.
- Every input is probed and checked against a codec allowlist.

**Lyric text is untrusted.** `{`, `}` and `\` are mapped to fullwidth look-alikes, and control characters are dropped. So lyrics can't become ASS drawing or font commands, FFmpeg filters, shell syntax or paths. A real render test proves this.

**Ids and paths.**
- Ids are validated against the existing id pattern.
- Storage keys reuse the audio storage's containment rules: no absolute paths, drive letters or `..`, and the resolved path must be inside the root.
- No endpoint accepts a filesystem path.

**Requests and failures.**
- A duplicate request for a Version whose video is still being generated is refused atomically, inside the insert transaction.
- Failures keep technical detail in the database and logs only.

## 11. Storage

`data/music-videos/` (setting: `TUNORA_MUSIC_VIDEO_ROOT`) is separate from `data/audio/`. The layout is:

```
data/music-videos/<id>/background.<ext>
data/music-videos/<id>/<id>.mp4
```

The MP4 is written inside a temporary directory and moved into place only on success, so a reader never sees a partial file. Deleting a Song deletes its Music Video rows (`ON DELETE CASCADE`) and then, best effort, their directories. A Music Video can never overwrite or delete audio.

## 12. Job lifecycle

```
PENDING  (accepted; waiting for the renderer)       UI: "Preparing…"
ALIGNING (local forced alignment)                   UI: "Aligning lyrics…"
RENDERING (FFmpeg + libass)                         UI: "Rendering…"
COMPLETED | FAILED
```

Generation runs as a FastAPI `BackgroundTask` in the API process, the same model as audio generation. There is no Celery, Redis or other queue. A process-wide lock renders one video at a time, because rendering is CPU-bound; extra requests wait as `PENDING`. The UI polls the list with the existing recursive-timeout and backoff discipline, and stops when every video is finished. There are no WebSockets.

## 13. Restart behavior

An alignment or render subprocess cannot resume. At startup, `MusicVideoService.recover_interrupted()` marks every non-terminal Music Video `FAILED` with "Generation was interrupted when Tunora restarted. Please generate it again." Nothing is re-run automatically, so no duplicate video can appear, and a failed video does not block a new one.

The final MP4 path only ever holds a complete file. A process killed mid-render can leave a temporary directory in the OS temp folder.

## 14. UI

Song Details has a **Music Videos** section, separate from the audio Versions list. **Create Music Video** opens a form with:

- **Version**: only finished vocal versions that have lyrics.
- **Aspect ratio**: 9:16 · 1080 × 1920, fixed.
- **Lyrics**: read-only, from the chosen Version, with a note that unmatched lines are left out and the lyrics themselves are not changed.
- **Background**: an image or video file, validated before upload.
- **Style**: Minimal, Dreamy or Bold.
- **Generate**.

Each video card shows its status (with progress), source Version, 9:16, style, duration and date. It also shows the unmatched-lyrics notice and failure message when they apply, a native `<video>` player, and **Download MP4**, which uses the same fetch → Blob → `<a download>` path as audio downloads.

The controls are native and labelled; status text uses `role="status"` and errors use `role="alert"`. The layout fits 375 px and 768 px with no horizontal overflow.

## 15. Testing

**Backend** (`tests/music_videos/`, plus `tests/test_music_video_smoke.py`):
- migration v5→v6 and idempotency, the triggers, and the repositories;
- service validation and lifecycle, unmatched lyrics, failures, restart, and song deletion;
- API contract and allowlist;
- the FFmpeg policy (fake runner, plus the real LGPL and GPL binaries);
- TimedLyrics, ASS, and aligner rules, including the Phase 22B malicious-input suite;
- **real renders** with the approved FFmpeg: image background, looping video background, black-frame and decode checks, malicious lyrics, and input rejections;
- a **real smoke test** with ACE-Step → alignment → render.

**Frontend:** Vitest tests for the API client and the section component.

**End to end:** a real Playwright run in installed Chrome (`e2e/music-video.spec.ts`) — Song Details → Version → MP4 background → Generate → real playback → download, plus an image-background run.

## 16. Known limitations

1. Stored lyrics may differ from what was actually sung.
2. Unmatched lyrics are not rendered; the UI lists them.
3. Manual lyric correction is deferred.
4. Only 9:16 at 1080×1920 and 30 fps.
5. Commercial distribution of H.264 output requires separate legal review.
6. FFmpeg LGPL redistribution obligations must be respected.
7. Rendering is CPU by default; NVENC is not used and not required.
8. No LLM is required.
9. No AI video-generation model is required, and no GPU model is loaded. Alignment runs Whisper `base` on the CPU.
10. One render at a time, and a restart fails in-flight videos; they are not resumed.
11. The first alignment on a new machine downloads the Whisper `base` weights (about 145 MB) once.
12. Music Videos are reachable from Song Details only, not from the Library.
13. The alignment engine (stable-ts) is an archived upstream project. It is a maintenance risk, isolated behind `LyricsAligner`.
14. Uploads go through the Next.js `/api` rewrite, whose request-body buffer defaults to 10 MB. `next.config.ts` raises it to 201 MB to match the backend's cap, and Next buffers the upload in memory.

## 17. Future work

These are not built in this phase:

- A manual timing and correction provider for TimedLyrics.
- Library visibility.
- More styles and aspect ratios.
- Optional NVENC with a driver-matched build.

A future, **optional** assistant could turn "make this a peaceful sunset lyric video" into a `MusicVideoSpec` (style, background choice, and so on) that the same deterministic renderer consumes. It would only choose parameters and would never render. Under Tunora's rules, it would reuse ACE-Step's own local LM first.
