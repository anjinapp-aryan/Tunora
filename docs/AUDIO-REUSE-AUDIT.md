# Tunora — Phase 1 Reuse Audit: Audio Player, Waveform & Lyrics UI

Scope: frontend UI layer for playing back and visualizing generated songs, and for editing/displaying synchronized (LRC-style) lyrics. Follows the Reuse Scorecard in [REUSE-FIRST-LAW.md](./REUSE-FIRST-LAW.md).

Verification key:
- ✅ verified this session via WebFetch/WebSearch against the live repo/npm page
- ⚠️ not independently verified this session (recalled/inferred, or search results were incomplete) — re-check before locking a decision

---

## 1. Audio Player

### Candidate: WaveSurfer.js

```
Repository: katspaugh/wavesurfer.js
URL: https://github.com/katspaugh/wavesurfer.js
Capability: Full audio playback engine (play/pause/seek/volume/duration) built on Web Audio + Canvas/WebAudio, PLUS waveform rendering in one package. Streams/loads arbitrary audio URLs, supports seeking on generated/streamed files.
License: BSD-3-Clause ✅ (verified on repo page)
Maintenance (last commit/release): Active. Latest tag observed was 8.0.0-beta.5 (~Sept 2026); prior stable 7.12.6 (~Apr 2026) ✅ (verified via GitHub releases search). Exact last-commit date not pulled from a live commit log this session ⚠️.
Stars/community: ~10.4k stars ✅ (verified via WebFetch of repo page)
Documentation: Strong — dedicated docs site, TypeScript types, official plugin examples. ⚠️ (docs site itself not fetched this session, based on repo README summary)
Integration complexity (into Next.js/TS): Low-medium. Pure client-side JS/TS library, no server dependency; needs a client component wrapper in Next.js (it touches `window`/Canvas, so must be dynamically imported / `"use client"`). Official React usage patterns exist in the community (e.g. `@wavesurfer/react` wrapper) but core lib itself is framework-agnostic.
Mandatory paid dependency: None.
Tunora fit: Excellent — this is the one library that covers BOTH the audio player transport controls (via its own play/pause/seek/volume API) AND the waveform visualization Tunora needs for a generated-song player, in a single MIT/BSD dependency. Matches the candidate already flagged in PHASE-0-DECISIONS.md.
Decision: 🟢 REUSE (as the primary playback + waveform engine; wrap in a thin Tunora React component for the actual player chrome/buttons)
```

### Candidate: react-h5-audio-player

```
Repository: lhz516/react-h5-audio-player
URL: https://github.com/lhz516/react-h5-audio-player
Capability: Pre-built React `<AudioPlayer>` UI component — play/pause, rewind/forward, progress bar with download/filled progress, volume, duration/current-time display, loop, mute, keyboard shortcuts, i18n/aria labels. Supports MSE/EME for advanced streaming.
License: MIT ✅ (verified via WebFetch)
Maintenance (last commit/release): Repo shows recent commit activity ("updated 3 weeks ago" per npm/GitHub metadata), but latest published release (v3.10.1) is ~10 months old per npm ⚠️ (search-derived, not a direct commit-log fetch — worth re-checking before committing to it, since "recent commits, stale release" can mean an unreleased major rewrite in progress, referenced in repo as v4.0.0-rc.1).
Stars/community: ~691 stars ✅ (verified via WebFetch) — a real but modest community, much smaller than WaveSurfer.
Documentation: Good README with props table and CSS customization guide. ⚠️ not deeply audited this session.
Integration complexity: Low — drop-in React component, TypeScript-native, Flexbox/SVG based so themeable with Tailwind overrides.
Mandatory paid dependency: None.
Tunora fit: Gives ready-made *player chrome* (buttons, progress bar, time labels) but has NO waveform rendering — it draws a plain progress bar, not a waveform. Redundant with WaveSurfer's own controls for the core transport, since WaveSurfer already exposes play/pause/seek/volume APIs Tunora can wire to custom Tailwind buttons.
Decision: 🟡 REFERENCE (useful as a UX/accessibility reference — e.g. its keyboard-shortcut and aria-label conventions — but not needed as a hard dependency once WaveSurfer is the playback engine)
```

### Candidate: react-player (cookpete/react-player)

```
Repository: cookpete/react-player
URL: https://github.com/cookpete/react-player
Capability: Unified React player for many URL types — file paths, HLS/DASH, YouTube, Vimeo, SoundCloud, Mux, etc. Version 3 is a rewritten architecture (not backwards-compatible with v2).
License: MIT ⚠️ (widely known as MIT; not independently re-confirmed via WebFetch this session — treat as needing a quick license-file check before use)
Maintenance (last commit/release): Actively maintained — maintenance was formally taken over by Mux, with an explicit statement of "higher rate of fixes and releases over time" ✅ (verified via WebSearch of official messaging).
Stars/community: Historically one of the most-starred React media libraries (tens of thousands) ⚠️ (exact current count not fetched this session).
Documentation: Extensive, actively updated for v3 migration.
Integration complexity: Low-medium — designed for React generally, works in Next.js client components; heavier than needed since Tunora only needs local/generated audio files, not YouTube/Vimeo/Twitch style multi-provider playback.
Mandatory paid dependency: None for open-source use; Mux's own hosted product is a separate paid upsell but not required to use the OSS player.
Tunora fit: Overkill for Tunora's need (single-source generated audio files, no third-party video platforms), and it does not provide waveform rendering. Its multi-provider abstraction is unnecessary surface area/complexity for a music-generation app.
Decision: 🔴 REJECT (for the primary player) — WaveSurfer.js already covers Tunora's actual requirement (local/streamed generated audio + waveform) more directly with less unused surface area.
```

**Audio Player summary:** WaveSurfer.js REUSE as the single playback+waveform engine. No second dependency needed for basic transport controls — building a thin custom control bar (Tailwind + WaveSurfer's own JS API for play/pause/seek/volume/duration) is less integration overhead than pulling in a second full player library and reconciling two audio elements/state sources.

---

## 2. Waveform Rendering

### Candidate: WaveSurfer.js plugin ecosystem

```
Repository: katspaugh/wavesurfer.js (plugins ship from the same monorepo)
URL: https://github.com/katspaugh/wavesurfer.js
Capability: Official first-party plugins confirmed via repo page ✅: Regions (visual overlays/markers over time ranges — useful for marking song sections, lyric lines, or generation "takes"), Timeline (time-axis labels under the waveform), Spectrogram (frequency-spectrum visualization), plus Minimap, Envelope, Record, and Hover plugins.
License: Same BSD-3-Clause as core, distributed from the same repo. ✅
Maintenance: Same as core — active, part of the same release cadence. ✅
Stars/community: Same repo/community as core (~10.4k). ✅
Documentation: Plugin-specific examples exist in the official docs site (per repo README links). ⚠️ not independently fetched.
Integration complexity: Low — plugins are added via `wavesurfer.registerPlugin()` calls, same client-side integration pattern as core.
Mandatory paid dependency: None.
Tunora fit: The Regions plugin is a strong candidate for marking synced-lyric-line boundaries or song sections directly on the waveform; Timeline gives free time-axis UI; Spectrogram is a nice-to-have visualization for a "studio" feel.
Decision: 🟢 REUSE (Regions + Timeline as near-term; Spectrogram as a V1/V2 nice-to-have)
```

### Competing waveform libraries

No mature, actively-maintained, framework-agnostic competitor with WaveSurfer's combination of (a) waveform rendering, (b) playback engine, and (c) a plugin ecosystem was found with independent verification this session. Options like `peaks.js` (BBC) exist in this space ⚠️ (recalled, not verified this session — flagged for a follow-up check if WaveSurfer turns out to be unsuitable) but were not fetched/confirmed here, since WaveSurfer already clears the bar and a second waveform library would just duplicate REUSE's job.

```
Decision: ⚪ BUILD not needed — no further waveform library search required unless WaveSurfer proves unsuitable in prototyping.
```

---

## 3. Lyrics Editor / Synchronized Lyrics (LRC) UI

Searched specifically for mature, web-based, timestamped/karaoke-style lyric editors. Findings below are honestly reported: **nothing at WaveSurfer/shadcn maturity level exists in this niche.** All candidates found are small, low-star, hobbyist-maintained projects.

```
Repository: abesmon/lyric-timer
URL: https://github.com/abesmon/lyric-timer
Capability: Per-word lyric timing — upload audio + lyrics, tap spacebar to stamp timestamps per word, drag-and-drop reposition, exports JSON/LRC/SRT. Uses WaveSurfer.js v7 internally for the waveform. ✅ (verified via WebFetch)
License: MIT ✅ (verified via WebFetch)
Maintenance: Small project — 23 commits total on main, 0 stars ✅ (verified via WebFetch). Effectively a solo/early-stage hobby project, not a maintained "library."
Stars/community: 0 stars ✅ (verified) — no real community.
Documentation: README only.
Integration complexity: High if reused directly — it's a full Vue + Tauri application, not a packaged component/library. Would need to be forked and gutted for its lyric-timing UI logic rather than installed as a dependency.
Mandatory paid dependency: None.
Tunora fit: The *interaction pattern* (play audio, tap key/click to stamp timestamp per line/word, drag to adjust, export LRC) is exactly the UX Tunora needs for a lyrics editor. But the codebase itself is not a reusable package.
Decision: 🟡 REFERENCE (borrow the interaction pattern and export format; do not adopt the codebase as a dependency)
```

```
Repository: pxeemo/LySy
URL: https://github.com/pxeemo/LySy
Capability: Browser-based LRC creation tool — paste lyrics, play song, stamp line-level timestamps, download .lrc. ✅ (verified via WebFetch)
License: MIT ✅ (verified via WebFetch)
Maintenance: ~23 stars ✅ (verified via WebFetch), small but slightly more traction than lyric-timer. Built with Vite. Last-commit date not independently confirmed ⚠️.
Documentation: README only.
Integration complexity: Similar to lyric-timer — a standalone web app, not a component library; would require extracting logic rather than installing.
Mandatory paid dependency: None.
Tunora fit: Same class as lyric-timer — good reference for line-level (not word-level) LRC stamping, which is likely the right MVP scope for Tunora (word-level karaoke sync can be a V2 stretch).
Decision: 🟡 REFERENCE
```

```
Repository: gyunaev/karlyriceditor
URL: https://github.com/gyunaev/karlyriceditor
Capability: Lyrics editor + CDG/video exporter for karaoke.
License: ⚠️ not independently verified this session (commonly GPL-family for this class of desktop karaoke tool — must confirm before any code reuse).
Maintenance: ⚠️ not verified this session.
Tunora fit: Desktop Qt application, not a web component — wrong platform for a Next.js frontend regardless of license.
Decision: 🔴 REJECT (wrong platform: desktop Qt, not web)
```

**Lyrics Editor conclusion:** Confirms the honest finding requested — **no mature, actively-maintained, installable open-source library exists for web-based synchronized-lyrics/LRC editing.** Every candidate found is a small (0–23 star) solo project shipped as a full app, not a package. Tunora's Reuse-First Law route here is legitimately **⚪ BUILD**, but informed by real prior art:
- Reuse WaveSurfer.js (already a REUSE decision above) as the underlying waveform/playback surface for the lyrics editor.
- Reuse WaveSurfer's **Regions plugin** to represent lyric-line time ranges visually (avoids building custom region-drawing code).
- Reference lyric-timer's and LySy's tap-to-stamp / drag-to-adjust interaction pattern and their JSON/LRC/SRT export shape.
- Build only the thin layer Tunora actually needs: a line list bound to Regions, a "stamp current line at playhead" action, and an LRC/JSON exporter.

```
Decision: ⚪ BUILD (thin custom lyrics UI, composed on top of WaveSurfer.js + Regions plugin — per REUSE-FIRST-LAW.md's BUILD criteria: no suitable existing packaged solution exists)
```

---

## 4. General Audio Processing (backend)

*Research date 2026-09-15, verified via WebSearch/WebFetch against official repos/LICENSE files unless flagged ⚠️.*

```
Repository: FFmpeg
URL: https://github.com/FFmpeg/FFmpeg
Capability: Format conversion, resampling, transcoding, loudness normalization (loudnorm filter), metadata read/write, container muxing (MP3/WAV/FLAC).
License: LGPL v2.1+ by default; --enable-gpl (x264 etc.) makes the WHOLE build GPL. This is configure-time, not fixed.
Maintenance: Very active.
Documentation: Extensive.
Integration complexity: Low (CLI/subprocess, or ffmpeg-python).
Mandatory paid dependency: None.
GPU requirements: None for Tunora's needs.
Tunora fit: Excellent for final packaging — MUST build/ship the LGPL-only configuration (no --enable-gpl, no libx264/libx265), dynamically link, ship LGPL notices.
Decision: 🟢 REUSE (LGPL build only — flag license-config choice explicitly in build docs)
```

```
Repository: jiaaro/pydub
URL: https://github.com/jiaaro/pydub
Capability: High-level slicing/concatenating/exporting, wraps ffmpeg.
License: MIT.
Maintenance: Stagnant — last commit Dec 2022, breaking on Python 3.13 (audioop removed from stdlib).
Tunora fit: Fine for prototyping only, maintenance liability for production.
Decision: 🟡 REFERENCE
```

```
Repository: librosa/librosa
URL: https://github.com/librosa/librosa
Capability: Audio analysis — loading, resampling, feature extraction, beat/tempo/onset detection, spectrograms.
License: ISC (permissive).
Maintenance: Active, latest stable 0.11.0 (Numpy 2.0 support, March 2025).
Tunora fit: Strong for analysis-side needs (beat/tempo, later phases); secondary role vs ffmpeg for bulk transcode.
Decision: 🟢 REUSE
```

```
Repository: pytorch/audio (torchaudio)
URL: https://github.com/pytorch/audio
Capability: PyTorch-native audio I/O, transforms, (historically) forced-alignment utilities.
License: BSD.
Maintenance: Entered "maintenance phase" as of 2.10 (Jan 2026); scope trimmed, decode/encode consolidating into TorchCodec.
Tunora fit: Only worth it if PyTorch already required (it is, via Demucs/basic-pitch) — don't add solely for I/O.
Decision: 🔵 ADAPT (side-effect dependency only, not primary I/O library)
```

```
Repository: bastibe/python-soundfile (PyPI: soundfile)
URL: https://github.com/bastibe/python-soundfile
Capability: Read/write WAV/FLAC/OGG as numpy arrays via libsndfile. No native MP3.
License: BSD-3-Clause.
Maintenance: Active; use current package name `soundfile`, not deprecated `pysoundfile`.
Tunora fit: Best-in-class for precise WAV/FLAC I/O; pair with FFmpeg for MP3 export and mutagen for tagging.
Decision: 🟢 REUSE
```

**Recommended combination:** FFmpeg (LGPL build) for conversion/normalization/muxing, soundfile for precise WAV/FLAC I/O, librosa for analysis, mutagen (flagged, not deep-audited) for ID3/Vorbis tagging. Avoid pydub as a long-term dependency.

---

## 5. Stem Separation

```
Repository: facebookresearch/demucs (original)
URL: https://github.com/facebookresearch/demucs
Capability: Hybrid Transformer source separation — vocals/drums/bass/other, instrumental via subtraction.
License: MIT (code).
Model/weights license: DISPUTED/UNVERIFIED — secondary sources claim maintainer stated pretrained weights are "for scientific purposes" only, distinct from the MIT code license; some HF mirrors mislabel weights "MIT". NOT independently confirmed this session — hard blocker requiring direct confirmation before any commercial weight bundling.
Maintenance: Archived by owner Jan 1, 2025 (read-only); author no longer at Meta.
GPU requirements: ~3GB VRAM min, ~7GB recommended. NOT TESTED, no GPU access.
Tunora fit: Best-in-class reputation, but archived + weight-license ambiguity.
Decision: 🟡 REFERENCE (redirect to maintained fork below; weight licensing unresolved)
```

```
Repository: adefossez/demucs (community-maintained fork, same original author)
URL: https://github.com/adefossez/demucs
Capability: Same as above, continued independently.
License: MIT (code, inherited); weight-license status same unresolved issue as upstream.
Maintenance: De facto "official" continuation but explicitly slow — bug-fixes only, no new features, "expect slow replies."
Tunora fit: Pragmatic default if Demucs-quality separation is needed now, accepting low-maintenance mode. Budget for eventually forking/self-maintaining; get legal sign-off on weight licensing before commercial redistribution; consider own-licensed retraining as a longer-term hedge.
Decision: 🔵 ADAPT
```

```
Repository: Anjok07/ultimatevocalremovergui (UVR/UVR5)
URL: https://github.com/Anjok07/ultimatevocalremovergui
Capability: GUI + model zoo (MDX-Net, VR Arch, Demucs) — widely regarded as best practical vocal-isolation quality via ensembling.
License: MIT (GUI code); model zoo licenses mixed/unverified per-model.
Maintenance: Appears active.
Integration complexity: Higher — PyQt desktop GUI, not a clean library/API.
Tunora fit: Good reference for model/ensemble choices; not a good backend-integration fit as-is.
Decision: 🟡 REFERENCE
```

```
Repository: deezer/spleeter
URL: https://github.com/deezer/spleeter
Capability: TensorFlow-based separation (2/4/5-stem), first popular OSS separator, superseded in quality by Demucs/MDX-Net.
License: MIT (code + models per repo, not independently re-verified this session).
Maintenance: Ambiguous — likely maintenance mode.
Tunora fit: Lower quality reputation + adds a second ML framework (TensorFlow) alongside a PyTorch stack.
Decision: 🔴 REJECT (primary) / 🟡 REFERENCE (lightweight CPU fallback only)
```

**Recommendation:** Demucs (adefossez fork) as primary stem-separation engine, running as a server-side inference service (lower legal risk than redistributing weight files) with the weight-license question flagged for direct legal confirmation before any commercial bundling.

---

## 6. Music Transcription / Melody / Beat / Tempo Detection

*V2+ scope per Phase 0 tiering — not MVP.*

```
Repository: librosa/librosa (beat/tempo/onset — built-in, classical DSP)
License: ISC. No model weights (no ML licensing concern).
Tunora fit: Good enough for basic tempo/beat-grid features without a full ML transcription stack.
Decision: 🟢 REUSE (when this scope is prioritized)
```

```
Repository: spotify/basic-pitch
URL: https://github.com/spotify/basic-pitch
Capability: Lightweight neural audio-to-MIDI with pitch-bend detection.
License: Apache 2.0 (code AND shipped model — same permissive grant for both, a real advantage over Demucs).
Maintenance: Active (2026 PRs seen).
GPU requirements: Marketed as lightweight/CPU-usable. NOT TESTED, no GPU access.
Tunora fit: Best-licensed, best-maintained candidate for future audio-to-MIDI/melody-extraction features.
Decision: 🟢 REUSE (V2+)
```

```
Repository: CPJKU/madmom
URL: https://github.com/CPJKU/madmom
Capability: RNN-based beat/downbeat tracking — historically strongest open-source accuracy.
License: Code BSD; models/data CC BY-NC-SA 4.0 (CONFIRMED directly from repo README/LICENSE — commercial use requires contacting the university).
Maintenance: Classified "Inactive" (Snyk, Jan 2026 snapshot).
Tunora fit: NC model license disqualifies for a project aiming at freely-usable/monetizable output.
Decision: 🔴 REJECT (pretrained models are NC-licensed, confirmed)
```

---

## 7. Lyric Alignment / LRC Generation

*Tunora's actual need: align KNOWN lyrics text (already generated/entered) to KNOWN generated audio — i.e., forced alignment, not transcription.*

```
Repository: m-bain/whisperX
URL: https://github.com/m-bain/whisperX
Capability: Batched Whisper transcription + word-level alignment (wav2vec2 phoneme models) + diarization.
License: BSD-2-Clause (code); alignment model licenses vary per-language, mostly permissive but not exhaustively verified.
Maintenance: Active, ~24k stars.
Important caveat: designed to refine timestamps for Whisper's OWN transcription, not to force-align a separately-supplied fixed lyrics transcript — community issues discuss workarounds; needs a proof-of-concept, not assumed turnkey.
Decision: 🔵 ADAPT (usable for Tunora's need only via a workaround feeding lyrics as if they were the transcript)
```

```
Repository: pytorch/audio — torchaudio.functional.forced_align / MMS_FA pipeline
Capability: General CTC forced alignment of arbitrary known text to audio — conceptually the exact match for Tunora's need; MMS_FA covers 1000+ languages.
License: BSD (code); MMS weights possibly CC-BY-NC 4.0 for some MMS assets — NOT verified for this specific checkpoint.
Maintenance: CONTRADICTORY signals found — one source says forced_align was removed in torchaudio 2.9 (migrate to TorchCodec, no 1:1 replacement), another says it was explicitly preserved through 2.10. UNRESOLVED — must verify against the exact pinned torchaudio version before building on it.
Decision: 🟡 REFERENCE pending re-verification
```

```
Repository: readbeyond/aeneas
URL: https://github.com/readbeyond/aeneas
Capability: Classical (non-neural) forced alignment, built for audiobook sync, many languages via espeak.
License: AGPL v3 (CONFIRMED from repo LICENSE) — as a network service, AGPL would require releasing the entire combined service's source.
Maintenance: Effectively unmaintained since 2017.
Decision: 🔴 REJECT (AGPL copyleft poor fit; stale)
```

```
Repository: lowerquality/gentle
URL: https://github.com/lowerquality/gentle
Capability: Kaldi-based forced aligner, ships local web GUI + REST API — conceptually right tool.
License: NOT independently verified this session (commonly cited as MIT elsewhere — unconfirmed).
Maintenance: Low/stale; built on aging Kaldi toolkit.
Decision: 🔴 REJECT for now (stale toolkit, unverified license, heavier integration than Whisper-based alternatives)
```

```
Repository: jianfch/stable-ts
URL: https://github.com/jianfch/stable-ts
Capability: Wraps Whisper for stable timestamps + explicit forced-alignment mode against a GIVEN transcript — closest functional match to Tunora's actual need.
License: MIT (code); relies on Whisper weights (permissive, OpenAI).
Maintenance: Recently ARCHIVED (~1 month before this audit) — ~2.3k stars/236 forks of prior traction, now frozen.
Decision: 🔵 ADAPT (fork/vendor rather than depend on live upstream, given archived status)
```

**Recommendation, in order:** (1) fork/vendor `stable-ts` (MIT, closest functional fit); (2) or adapt WhisperX's alignment stage to accept externally supplied lyrics (needs a proof-of-concept); (3) re-check torchaudio's MMS_FA API against the exact pinned version as a cleaner long-term option. Reject aeneas (AGPL) and Gentle (stale/unverified license) outright. This whole category is V1/V2 scope, not MVP-blocking.

## Flags requiring follow-up before finalizing architecture
1. Demucs pretrained-weight licensing ("scientific use only" claim) — not confirmed via a primary maintainer statement this session; get a definitive answer before any weight redistribution/commercial bundling decision.
2. torchaudio forced_align/MMS_FA API stability — contradictory information found; verify against the exact pinned torchaudio version before committing to it.
3. UVR and MMS model-zoo per-model licenses — not exhaustively audited.
4. Gentle's actual license — unconfirmed, needs a direct LICENSE-file read.
5. All GPU/runtime performance and quality-reputation claims in this document are unverified by direct testing (no GPU access) — reputation-based signal only, confirm via real benchmarking before committing to a single stem-separation or transcription engine.
