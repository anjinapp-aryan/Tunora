---
name: audio-quality-review
description: Measure and interpret the technical audio quality of a Tunora song version — loudness (LUFS), true peak, loudness range, clipping, silence, clicks, mono compatibility, stereo phase and tonal balance — and recommend fixes. Use when the user asks whether a song is too loud/quiet, distorted, clipped, release-ready, or how to master or improve a mix.
argument-hint: "[song id + version id, or an audio file path]"
---

Target: `$ARGUMENTS`. Adapted (CC0) from bitwize-music-studio/claude-ai-music-skills (`mastering-engineer`,
`mix-engineer`, `tools/mastering/qc_tracks.py`, `reference/mastering/*`).

## 1. Measure (never guess numbers)

- API (backend running): `GET /api/songs/{song_id}/versions/{version_id}/audio-quality`.
  On demand, about 0.4 s for a 15–30 s song, one check at a time (429 when busy), cached per Version.
- A local file: `cd backend && uv run python -c "from pathlib import Path; from app.audio_quality.measure import measure, loudness_checks; m = measure(Path(r'<file>')); print(m); print(loudness_checks(m))"`.

Loudness and true peak come from FFmpeg's EBU R128 scanner (ITU-R BS.1770), through the approved LGPL build
(`app/media/ffmpeg.py`); the other checks are numpy/scipy (`app/audio_quality/checks.py`).

## 2. Interpret

| Measure | Reference | Meaning |
|---|---|---|
| Integrated loudness | about -14 LUFS (most streaming services) | Louder than -8: heavily limited, services turn it down and the squash remains. Quieter than -20: sounds soft in a playlist. |
| True peak | ≤ -1.0 dBTP | Above -1 may distort after MP3/AAC encoding; above 0 distorts. |
| Loudness range | genre-dependent (pop 4–8 LU, acoustic/orchestral higher) | Very low LRA = flat dynamics. |
| Clipping regions | 0 | Flattened waveform; cannot be fixed by turning down afterwards. |
| Mono loss / phase | < 1 dB loss, correlation > 0.5 | Out-of-phase parts vanish on phone speakers. |
| Silence | ≤ 0.5 s start, ≤ 3 s end, no internal gaps | Long leading silence delays playback; internal gaps may be a generation glitch. |
| Spectral | not a verdict | "Dull" or "harsh" flags are prompts to listen, not facts about taste. |

Numbers cannot say whether a song sounds good — always pair them with listening.

## 3. Recommend (within what Tunora can do today)

- A clipped or glitchy generation: **Another Take** or **Repaint** the bad region — Tunora cannot repair audio.
- Too quiet/loud for release: Tunora has **no mastering step yet**. A safe, Tunora-compatible future option is
  FFmpeg `loudnorm` (two-pass, LGPL, already approved infrastructure) producing a new Version — propose it,
  don't run ad-hoc processing over stored audio (Versions are immutable).
- Rejected for Tunora: `matchering` (GPL-3.0 — the source plugin's mastering engine); per-stem mixing from the
  source plugin needs Suno stems and noisereduce, and Tunora's Extract model is the base model only.

## Honesty rules

Report measured values with units; say "not measured" when a check did not run. Never claim a song is
"release-ready" from numbers alone.
