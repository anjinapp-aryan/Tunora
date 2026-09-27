# Phase 17 — Lossless / Native FLAC Audio Pipeline

Implementation of the decision in `docs/PHASE-17-PRODUCT-CAPABILITY-GAP-AUDIT.md`: **16-bit FLAC is the canonical
audio format for new Versions.**

## Objective and motivation

Tunora generated 128 kbps MP3 (ACE-Step's REST default) and re-uploaded that MP3 as the source of every
Extend, Remix, Repaint and Extract, so each derived Version was encoded through lossy MP3 again. The audit
measured, in a Repaint's untouched region, 24.1 dB SNR against the lossless original for the MP3 source and
22.9 dB after three chained Repaints, versus a bit-exact copy through a FLAC chain.

**What FLAC does and does not do:** FLAC prevents additional lossy codec compression between derived Versions.
It does not improve what the model generates (ACE-Step's own processing is unchanged), and no listening test
was done, so no perceptual improvement is claimed.

## Architecture

- **One source of truth:** `AceStepMusicGenerationProvider.DEFAULT_AUDIO_FORMAT = "flac"`. The provider adds
  `audio_format` to every `/release_task` payload (`_build_release_task_payload`), so Create (including AI
  Director plan and refinement, which only fill the Create form), Another Take, Extend, Remix, Repaint and Extract
  all request it without per-operation logic. `SongSpec`/`GenerationRequest` are unchanged.
- **Rollback lever, not a user setting:** the backend reads `TUNORA_AUDIO_FORMAT` (`flac` default, `mp3`
  allowed). Only formats verified to produce a file are accepted; anything else raises at startup (opus/aac
  report success without writing a file in this ACE-Step deployment; `wav` is float32 and 24x MP3 size). No UI,
  no per-Version format.
- **Derived sources keep their identity:** the multipart upload is named from the stored file
  (`source.flac` / `source.mp3` / `source.wav`, unknown extension falls back to `source.mp3`) with the matching
  media type instead of the hard-coded `source.mp3` / `audio/mpeg`. (ACE-Step decodes by content, so this is about
  not mislabelling.)
- **MIME normalization:** `guess_media_type` rewrites only `audio/x-flac` (what Python's `mimetypes` returns for
  `.flac` on this Windows machine) to `audio/flac`; MP3/WAV and everything else are untouched. Stored media type,
  API responses, `Content-Type` and the frontend "Download FLAC" label all follow.
- **Storage, API, player unchanged:** `LocalAudioStorage` already stores `<job-id>.flac`; the audio route,
  Range, ETag, `VersionAudio` fields and WaveSurfer are format-agnostic (audit). No migration (the stored
  filename/media type already record the format), no new dependency, no FFmpeg, no export/conversion.
- **ACE-Step:** unchanged.

## Why FLAC, not WAV or MP3

MP3 128k is the lossy chain being removed. WAV from ACE-Step is 32-bit float at 24x MP3 size with unverified
float-WAV support outside Chromium, and there is no mastering stage that would use the headroom. 16-bit FLAC is
about 5x MP3, verified in Chromium and Firefox (below), and needs no library. Known trade-off: ACE-Step's FLAC is
16-bit, so the model's float output is quantized. FFmpeg is not needed because Tunora stores the file ACE-Step
returns; a FLAC output path also removes ACE-Step's own need for `ffmpeg` to write MP3.

## Compatibility

- **Existing MP3 Versions:** untouched (never converted, renamed or regenerated). Mixed libraries work: MP3 V1 ->
  FLAC V2 -> FLAC V3 and FLAC -> FLAC chains are covered by tests and were run for real.
- **Phase 14:** the Extract `dit_model` check is independent of format; tests with FLAC results: base COMPLETED,
  turbo FAILED, missing FAILED.
- **Phase 16:** recovery restores the provider expectation from the persisted operation and takes the stored type
  from the ACE-Step result path, so nothing about the format is persisted or needed; tested (one submission, one
  Version, two recoveries) and run for real.

## Tests

- Backend `tests/test_flac_pipeline.py` (32): format sent on Create/Another Take (JSON) and Extend/Remix/Repaint/
  Extract (multipart); configurable format and validation; source upload name and type for flac/FLAC/mp3/wav/
  unknown; MIME normalization and no broad rewriting; public filename allowlist; FLAC stored/served/Range/ETag/
  no path leak; old MP3 unchanged; mixed lineages including a FLAC source and an MP3 source; Extract model checks
  with FLAC; FLAC recovery without a second submission; source untouched; app wiring of the setting.
- Frontend: Download button offers and saves a `.flac` file under "Download FLAC"; a Song with an MP3 and a FLAC
  Version shows the right label and player URL for each. `AudioPlayer` only takes a URL (format-agnostic), so no
  player unit test was added: it would prove nothing; playback is covered by the real-browser runs.
- E2E: the MP3-specific assertions of the shared download helper (`.mp3`, `audio/mpeg`, "Download MP3") were
  changed on purpose to the FLAC contract (`E2E_AUDIO_FORMAT=mp3` restores the old expectation for rollback runs).

## Mutation testing

11 mutations, each run and restored: format omitted, format sent as mp3, default changed to mp3, wrong source
extension, wrong source MIME, MP3 fallback broken, FLAC normalization removed, MP3 media type broken by
normalization, storage extension forced to mp3, Extract model check bypassed, configured format not wired.
**11 of 11 caught.**

## Real GPU validation (real ACE-Step, throwaway backend and DB; 10 s clips)

All outputs: FLAC, 16-bit, 48 kHz, stereo, served as `audio/flac`, Range 206.

| Operation | Version | File (ext) | Bytes | Duration | SHA-256 (first 16) |
|---|---|---|---|---|---|
| Create | 1 | .flac | 940,719 | 10.000 s | eb5369e99b019d9d |
| Another Take | 2 | .flac | 1,064,304 | 10.000 s | 0a84f8a921db4e43 |
| Extend +10 s | 3 | .flac | 1,693,428 | 20.000 s | 4b82d4a4d9bd0c97 |
| Remix | 4 | .flac | 871,936 | 10.000 s | 7c6800c9674fada3 |
| Repaint 3-7 s | 5 | .flac | 724,540 | 10.000 s | 22fdda6fb4bf7bb0 |
| Extract vocals (base model) | 6 | .flac | 896,443 | 10.000 s | e0f8deb6b8a5baa7 |
| Repaint from a FLAC Version | 7 | .flac | 1,049,858 | 10.000 s | 73a07d97b852f00f |
| Old MP3 Version (created with `TUNORA_AUDIO_FORMAT=mp3`) | 1 | .mp3 / audio/mpeg | 160,940 | 10.000 s | 2c815381945ea8e7 |
| Another Take from the MP3 Version | 2 | .flac | 643,567 | 10.000 s | 6e502967beb620ea |
| Repaint from the MP3 Version | 3 | .flac | 625,908 | 10.000 s | 391a49ff03dd2ca9 |
| Create recovered after a backend kill/restart | 1 | .flac | 991,043 | 10.000 s | 832cf97ac43e047a |

Source Version 1 and the old MP3 Version were byte-identical after their derivations; lineage
(`ANOTHER_TAKE/EXTEND/REMIX/REPAINT/EXTRACT` from Version 1) correct; the recovered generation submitted exactly one
ACE-Step job and produced one Version. SHA-256 values differ between runs and are not evidence of anything (fixed
seeds are not byte-deterministic in this stack).

## Browser validation

Real Tunora UI, FLAC and MP3 Versions of the same Song (play, seek, waveform painted, download filename):

| Browser | Result |
|---|---|
| Chromium 153 | PASS: FLAC and MP3 play, seek, waveform, download `.flac`/`.mp3` |
| Firefox (Playwright build `firefox-1543`) | PASS: same checks |
| Safari | **NOT VALIDATED.** No Safari exists for this Windows machine. The nearest engine, Playwright's WebKit build on Windows (`webkit-2359`), fails to load **any** audio, MP3 and FLAC alike ("This audio can't be played right now", MediaError, although `canPlayType` says "probably"), so it says nothing about Safari or FLAC. |

Both extra browsers were installed for this run with `npx playwright install` (outside the repository; no repo file
or dependency changed). A manual check in real Safari (macOS/iOS) is still required before relying on Safari.

## Security and performance

Nothing new is accepted from clients. Paths still come from trusted job records; the filename allowlist covers
`.flac`; the provider's upload extension is limited to the same allowlist; absolute paths and provider ids stay
out of responses (tested). There is still no content validation of stored audio (unchanged; files come only from
ACE-Step). Latency did not change in the audit (mp3 13.1 s, flac 12.7 s); storage grows about 5x per new Version
(about 10 MB per 120 s song, ESTIMATE); no quota exists.

## Known limitations

- Safari (and any WebKit) not validated; Firefox validated only in Playwright's build.
- New Versions are about 5x larger; no quota; old MP3 Versions are not converted.
- ACE-Step's FLAC is 16-bit (quantized from the model's float output).
- The perceptual value is unmeasured (no listening test).
- Existing pre-change Versions that were derived from MP3 keep the loss they already have.
- No MP3/WAV export yet (next candidate); opus/aac unsupported.

## Regression results (final code)

- Backend `pytest -m "not smoke"`: **630 passed** (598 before, +32).
- Real-GPU smoke `pytest -m smoke`: **13 passed**. Three assertions in the existing smoke tests
  (`test_audio_endpoint_smoke.py`, `test_job_lifecycle_smoke.py`, `test_song_version_smoke.py`) expected MP3
  (`audio/mpeg`, `<job>.mp3`); they failed on the first run and were updated on purpose to the FLAC contract
  (`audio/flac`, `<job>.flac`), not weakened.
- Frontend: `tsc` clean, ESLint 0 errors (1 pre-existing warning), Vitest **367 passed** (365 before, +2), `next build` passes.
- Full Playwright suite (real stack and GPU, FLAC default): **19 passed**, including byte-for-byte downloads, Range
  requests, Extend/Remix/Repaint/Extract/Another Take, Compare, Projects, Director and song management.

## Files changed

`backend/app/providers/ace_step.py`, `backend/app/storage/media_types.py`, `backend/app/main.py`,
`backend/tests/test_flac_pipeline.py`, `frontend/src/components/audio/download-button.test.tsx`,
`frontend/src/components/song/version-actions.test.tsx`, `frontend/e2e/create-song.spec.ts`, three smoke tests (assertions moved to FLAC), `docs/TUNORA-SERVICE-MANAGEMENT.md`,
`docs/PHASE-17-PRODUCT-CAPABILITY-GAP-AUDIT.md` (still untracked, included), this document.
Dependencies: none. Database: no migration. ACE-Step: unchanged.

## Not part of Phase 17

MP3/WAV export or conversion, FFmpeg, a format selector or any UI, converting existing Versions, batch generation,
prompt library, cover art, mastering, MIDI, chords, lyric alignment, audio editing, new Extract tracks.
