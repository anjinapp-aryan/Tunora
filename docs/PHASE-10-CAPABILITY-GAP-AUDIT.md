# PHASE 10 — AUDIO INTELLIGENCE & VERSION COMPARISON
# CAPABILITY GAP + OSS REUSE AUDIT

Status: **AUDIT ONLY**. No application code, dependency, schema, API, or UI was
changed to produce this document. See §36/§37 for the git-state proof.

Research date: 2026-09-23. Verification key: ✅ verified this session via
WebFetch/WebSearch against the live repo/license/npm/docs page; ⚠️ recalled or
inferred, not independently re-verified this session.

---

## 1. Executive Summary

Tunora currently does **zero local audio analysis**. Every numeric fact about
a generation (duration, bpm, genres, key/scale, time signature) is either (a)
copied verbatim from ACE-Step's own generation result, or (b) a filesystem
fact Tunora records at save time (media type, byte size). Tunora has **no**
audio-processing Python dependency at all — `backend/pyproject.toml` lists
only `fastapi`, `uvicorn`, `httpx`. The richer metadata ACE-Step already
returns (bpm, genres, key/scale, time signature) is captured on the **Job**
response but is **not surfaced** on the Song/Version API that the Library,
Song Details, and Version History UI actually use — this is a real,
zero-new-dependency gap, and it is the single highest-value, lowest-cost item
this audit found.

Beyond that, the honest finding is: **the smallest useful Phase 10 needs no
new backend dependency at all.** WaveSurfer.js (already a dependency) fully
covers waveform rendering, and a Version Comparison UI can be composed from
two existing `AudioPlayer` instances plus the existing Song/Version/lineage
data model, unmodified. Everything past that (RMS/peak, LUFS, BPM/key
*re-computed* rather than reused, spectrograms, audio similarity/diff,
embeddings) is real, well-understood OSS territory, but each one adds cost
(new dependency, CPU time, storage, complexity) against a use case (comparing
two AI-generated variants of the same prompt) where the product value is
speculative until a user actually asks for it.

**Recommended Phase 10 MVP:** surface Version Comparison (A vs B: metadata +
independent waveform playback, both already-existing capabilities, newly
composed) and plumb through the bpm/genre/key/time-signature Tunora already
has but doesn't show. **Zero new dependencies. No DB migration** (the
existing `jobs.result_json` column already holds the data; see §14). RMS,
peak, LUFS, spectrogram, audio similarity, and embeddings are all real,
licensable capabilities with viable OSS candidates — documented in full below
— but are recommended as **DEFER**, not because they're bad ideas, but
because none of them are needed to ship a genuinely useful, fully-reused
Version Comparison feature, and REUSE-FIRST law says not to add a dependency
before the gap is proven.

---

## 2. Current Tunora Audio Capabilities

Verified by reading the actual code (not assumed from prior planning docs):

| Capability | Exists? | Where | Source of truth |
|---|---|---|---|
| Duration | ✅ | `VersionAudio.duration` (`app/songs/models.py`) | ACE-Step's `GenerationResult.duration` |
| Media type | ✅ | `VersionAudio.media_type` | ACE-Step's declared content type |
| File size (bytes) | ✅ | `VersionAudio.size_bytes` | Measured by Tunora at save time (`app/storage/local.py`) |
| Filename | ✅ | `VersionAudio.filename` | Sanitized (`app/storage/filenames.py`) |
| BPM / genres / key-scale / time-signature | ⚠️ partial | `Job.result["metadata"]`, exposed only via `JobResponse` (`app/api/schemas.py:_PUBLIC_METADATA_FIELDS`) | ACE-Step's own LM planner output — **not guaranteed accurate** (documented limitation, `CLAUDE.md`) |
| Sample rate, channels, codec, bitrate | ❌ | not captured anywhere | — |
| RMS, peak, LUFS, dynamic range | ❌ | not captured anywhere | — |
| Waveform | ✅ (client-side only) | `AudioPlayer` decodes the downloaded file in-browser via WaveSurfer.js; nothing persisted server-side | WaveSurfer.js |
| Spectrogram | ❌ | not used anywhere (plugin exists in the already-installed package but is not imported) | — |
| A/B or version comparison UI | ❌ | Song Details shows one "active version" at a time, selected by radio button (`song-details.tsx`) | — |
| Audio similarity / diff / fingerprinting / embeddings | ❌ | not present | — |

**Backend dependencies (`backend/pyproject.toml`), verified directly:**
`fastapi`, `uvicorn[standard]`, `httpx` (+ dev: `pytest`, `pytest-asyncio`,
`respx`). No `numpy`, `scipy`, `soundfile`, `librosa`, `mutagen`, `ffmpeg-python`,
or any audio library.

**Frontend dependencies (`frontend/package.json`), verified directly:**
`wavesurfer.js@^7.12.12` is the only audio-related package. No spectrogram,
regions, or multitrack plugin is imported anywhere in `frontend/src`
(verified by grep — only the base `WaveSurferClass.create()` call in
`audio-player.tsx`).

**ACE-Step's own dependencies** (`ACE-Step-1.5/pyproject.toml`), which Tunora
does **not** inherit (ACE-Step is a separate process, spoken to only over
HTTP, per `CLAUDE.md`'s "must never leave `app/providers/ace_step.py`"
rule): `scipy`, `soundfile`, `torch`/`torchaudio`. No `librosa`, no
`mutagen`, no `pyloudnorm`, no `essentia`, no `aubio`. ACE-Step does have an
internal `full_analysis_only` mode (`acestep/api/job_analysis_runtime.py`)
that re-runs its **LM** (not classical DSP) over an existing audio file to
re-derive bpm/key/genre/lyrics — this is GPU-bound, non-deterministic, and
requires the LM to be loaded; it is a real capability but not a lightweight
metadata call, and re-deriving what a version's own Job already recorded at
generation time would be redundant. Noted in §11 as a rejected approach for
Phase 10, not adopted.

**FFmpeg**: referenced in `CLAUDE.md` as a locked-in constraint ("LGPL-only
build") for ACE-Step's own MP3 encoding. It is **not** verified to be on the
Tunora backend process's `PATH` — ACE-Step and the Tunora backend run in
separate `uv` virtual environments/processes (`backend/.venv` vs
`ACE-Step-1.5/.venv`), and nothing in `backend/` shells out to `ffmpeg`
today. Any Phase 10 recommendation that assumes `ffmpeg` is callable from the
Tunora backend must treat that as **unverified** until confirmed on the
actual dev machine, not assumed from ACE-Step's requirement.

---

## 3. Current Version / Lineage Capabilities

`app/songs/models.py` (`Version`) and `app/songs/operations.py` already carry
everything a comparison feature needs, unmodified:

- `version_number` (1, 2, 3… per Song), `created_at`, `provider`.
- `operation`: `ORIGINAL | EXTEND | REMIX | REPAINT` (`app/songs/operations.py`).
- `source_version_id`: which version (of the *same* Song — enforced by a DB
  trigger) this one was made from; `null` for `ORIGINAL`.
- `operation_params`: the operation's own parameters (extend seconds, repaint
  range, remix strength).
- `spec`: the full provider-neutral `GenerationRequest` for that version
  (prompt, lyrics, language, duration, seed, instrumental).
- `audio`: the immutable `VersionAudio` reference (write-once).

`JobService.song_details()` / `list_version_entries()` already return every
Version of a Song, newest first, each paired with its Job id/status — this is
already the exact data a "Song → V1/V2/V3/V4/V5 → Compare" tree view needs.
**No Version model change is required** to render lineage or to pick any two
versions of the same Song for comparison. This confirms §12's instruction:
the existing lineage is sufficient; there is no genuine architectural gap
here.

---

## 4. Capability Gap

| Target UX item | Gap type | Severity |
|---|---|---|
| BPM/Key/Genre/Time-signature shown on Song Details / Library | **Plumbing gap only** — data already exists on the Job, just not copied to the Song/Version response | Real, cheap to close |
| Waveform comparison (two versions) | **UI composition gap** — WaveSurfer already renders one; nothing renders two side by side | Real, cheap to close (no new dependency) |
| A/B playback (switch or sync) | **UI gap** — no such control exists | Real, small new code, no new dependency for "switch"; a little more for "sync" |
| Sample rate / channels / codec / bitrate | **True gap** — never captured | Real but low value (see §10) |
| RMS / Peak | **True gap** — never computed | Real, low-medium value, needs a new (small) dependency |
| LUFS / loudness normalization info | **True gap** | Real, speculative value for MVP |
| Spectrogram | **True gap**, but the fix is a plugin already inside an installed package | Real, no new dependency, low urgency |
| Audio similarity / diff score | **True gap** | Speculative value; see §13 |
| Audio fingerprinting / embeddings | **True gap** | No evidence Tunora's product needs this yet |

---

## 5. OSS Reuse Audit

### 5.1 Metadata extraction (duration/sample-rate/channels/codec/bitrate)

- **FFmpeg / ffprobe** — Extensive, industry-standard, already a locked-in
  constraint for ACE-Step (LGPL-only build). Would give every metadata field
  in one subprocess call (`ffprobe -show_streams -of json`). ✅ Verified
  active/maintained (it's FFmpeg). **Caveat**: availability on the Tunora
  backend's own `PATH` is unverified (§2). 🟢 REUSE **if and only if**
  confirmed reachable from the backend process; otherwise this whole
  category is not free.
- **mutagen** — Pure-Python, zero non-stdlib dependencies, reads/writes tags
  and basic stream info (duration, bitrate, sample rate) for MP3/FLAC/OGG/etc.
  License: **GPLv2+** ✅ (verified via WebFetch of `quodlibet/mutagen`'s own
  docs) — this contradicts this repo's earlier planning-era assumption; it
  was never re-verified before. GPL is a copyleft license; Tunora's own
  established policy (`CLAUDE.md`: "no `--enable-gpl`" for FFmpeg) shows a
  deliberate GPL-avoidance stance. Using mutagen as an unmodified,
  dynamically-imported Python dependency (not modifying/embedding its source)
  is common practice and does not require Tunora's own code to be GPL, but it
  is a **stricter license than everything else in Tunora's stack** and should
  get an explicit legal sign-off before adoption, consistent with how this
  project already treats GPL/AGPL as hard-review triggers (Essentia, aubio —
  see below; MinIO/AGPL already hard-rejected in `docs/REUSE-MATRIX.md`).
  🔵 ADAPT (usable, but flag the GPL license explicitly before adopting;
  do not silently treat it as equivalent to the BSD/MIT stack).
- **soundfile** (`python-soundfile`, wraps `libsndfile`) — BSD-3-Clause ✅
  (already pre-cleared in `docs/LICENSE-AUDIT.md`). **New finding this
  session**: `libsndfile` gained MP3 **read** support in 1.1.0 (March 2022),
  and `soundfile` 0.14.0 (June 2026) ships with it ✅ (verified via
  WebSearch). This matters specifically for Tunora because **every stored
  Version's audio is MP3** (`<job_id>/<job_id>.mp3`) — so `soundfile` alone
  (no `ffmpeg`, no `librosa`) can decode Tunora's actual files to a NumPy
  array for RMS/peak computation. Pure C extension + `cffi`, no compiled
  Python-native build step (prebuilt wheels for Windows exist). 🟢 REUSE
  candidate **if** RMS/peak/LUFS is ever prioritized (see §21 — this still
  requires adding `numpy`, which Tunora does not currently have).
- **pymediainfo** — wraps the MediaInfo C library; needs the native
  `MediaInfo` shared library installed/bundled separately on the target
  machine (not a pure pip install on Windows without also shipping the DLL).
  Higher integration friction than `soundfile`/`ffprobe` for the same
  information. 🟡 REFERENCE (not recommended; redundant with FFmpeg/soundfile
  and adds a native-library packaging burden this project's Windows-first
  constraint (§16) argues against).
- **audioread** — a fallback decode-only backend (used internally by
  `librosa` when `soundfile` can't handle a format); not useful standalone
  now that `soundfile` reads MP3 directly. 🟡 REFERENCE only.

### 5.2 Music analysis (BPM / key / loudness)

- **librosa** — ISC license ✅ (pre-cleared). Actively maintained. Provides
  `librosa.beat.beat_track` (tempo/BPM) and chroma features, but **has no
  built-in "key" function** — musical key estimation would still have to be
  hand-built on top of librosa's chroma output (Krumhansl-Schmuckler
  template matching), which is a genuine BUILD, not a REUSE, for key
  specifically. Pulls in `numba`/`llvmlite` as transitive dependencies
  (JIT compiler infrastructure) — real dependency weight for a single BPM
  number Tunora may already have from ACE-Step. 🔵 ADAPT (only for BPM,
  only if ACE-Step's self-reported BPM is judged insufficient — see §11 for
  why that hasn't been demonstrated).
- **Essentia** — **AGPLv3** ✅ (verified via WebSearch of the official
  `MTG/essentia` repo). Has the most complete built-in key/BPM/loudness
  descriptor set of any candidate here, but AGPL is Tunora's strictest
  hard-reject category (already the exact reasoning used to reject MinIO in
  `docs/REUSE-MATRIX.md`). 🔴 REJECT — consistent with existing project
  precedent, no exception warranted.
- **aubio** — **GPLv3** ✅ (verified via WebSearch of the official
  `aubio/aubio` repo/site). Good tempo/beat/onset tracking, no key
  detection. Same GPL caution as mutagen, and no unique capability aubio
  offers that librosa (ISC) doesn't already cover for BPM. 🔴 REJECT (no
  reason to accept a GPL dependency when an ISC one does the same job).
- **madmom** — already hard-rejected in this repo's own prior audit
  (`docs/AUDIO-REUSE-AUDIT.md`): pretrained models are CC-BY-NC-SA
  (non-commercial), and the project is classified inactive. 🔴 REJECT
  (standing decision, re-confirmed, not re-litigated).
- **pyloudnorm** — **MIT** ✅ (verified via WebFetch of the repo). 783
  stars, pure `numpy`+`scipy`, implements the ITU-R BS.1770-4 standard (the
  actual LUFS algorithm used by streaming platforms for loudness
  normalization). No GPU, no heavy transitive dependencies beyond
  numpy/scipy. This is the cleanest candidate in the entire audit if LUFS is
  ever wanted. 🟢 REUSE candidate (deferred — see §13, no proven need yet).
- **FFmpeg's own `loudnorm`/`volumedetect` filters** — already covered under
  FFmpeg's REUSE status (§5.1); would give peak/RMS/loudness via a filter
  pass without adding any Python dependency at all, **if** ffmpeg is
  confirmed reachable from the backend. This is a genuine alternative to
  adding `soundfile`+`numpy`+`pyloudnorm` as three new Python packages —
  worth re-evaluating once ffmpeg-on-backend-PATH is confirmed.

### 5.3 Waveform / spectrogram

Covered in full in §12. Conclusion: **REUSE WaveSurfer's existing,
already-installed capabilities**; no new dependency for either.

### 5.4 Version comparison / A-B playback

- **`wavesurfer-multitrack`** (katspaugh, same GitHub org as WaveSurfer core)
  — an official "super-plugin" for stacking multiple synced audio tracks.
  ✅ Verified to exist and be maintained. **However**: its actual purpose is
  multi-track *editing* (drag tracks to reposition, simultaneous mixed
  playback of several layers) — a different problem from "let me A/B two
  full-length alternate takes of the same song." Multiple open GitHub
  discussions/issues (`#2868`, `#3944`) report tracks drifting out of sync
  during use ✅ (verified via WebSearch) — a real, documented maturity risk
  for the one thing Tunora would actually need (drift-free switching). 🟡
  REFERENCE (useful prior art for a *future* stretch feature — true
  simultaneous mixed playback — but not the right tool for a simple A/B
  switch, which is better served by composing two already-proven,
  independent `AudioPlayer` instances — see §11).
- **No dedicated "audio A/B comparison" OSS package** was found with any
  meaningful maturity signal (stars, recent commits, real usage) distinct
  from either a DAW feature or the multitrack plugin above. This confirms
  the target UX's A/B comparison is best served by **composing existing,
  already-adopted components** (two `AudioPlayer`s + a small selection/sync
  controller), not by adding a library.

### 5.5 Audio similarity / diff / fingerprinting / embeddings

No specific "AudioCompare"/"audiodiff" project was found with real
maturity. The realistic OSS building blocks for a similarity *score* would
be: librosa's MFCC/chroma feature vectors + a distance metric (cosine/
Euclidean) — a **BUILD**, using an already-audited library, not a turnkey
REUSE; or an audio embedding model (CLAP-family, on Hugging Face) — a real
ML dependency with GPU/CPU inference cost. See §13 for why neither is
recommended for Phase 10.

---

## 6. GitHub Candidates

| Repository | URL | Stars (approx, this session) | Activity | License | Capability | Recommendation |
|---|---|---|---|---|---|---|
| csteinmetz1/pyloudnorm | github.com/csteinmetz1/pyloudnorm | 783 ✅ | Established, low-churn (a finished algorithm, not a churn signal of neglect) | MIT ✅ | LUFS loudness | 🟢 REUSE (deferred) |
| quodlibet/mutagen | github.com/quodlibet/mutagen | large, long-standing project ⚠️ (exact count not pulled) | Active ✅ | GPLv2+ ✅ | Tag/metadata read | 🔵 ADAPT (flag license) |
| bastibe/python-soundfile | github.com/bastibe/python-soundfile | established ⚠️ | Active, 0.14.0 shipped June 2026 ✅ | BSD-3-Clause ✅ | PCM/MP3 decode to NumPy | 🟢 REUSE (deferred) |
| librosa/librosa | github.com/librosa/librosa | large, established ⚠️ | Active ✅ | ISC ✅ | BPM/tempo, chroma | 🔵 ADAPT (BPM only, deferred) |
| MTG/essentia | github.com/MTG/essentia | large ⚠️ | Active ✅ | AGPLv3 ✅ | Full MIR descriptor set | 🔴 REJECT |
| aubio/aubio | github.com/aubio/aubio | established ⚠️ | Maintained ✅ | GPLv3 ✅ | Tempo/beat | 🔴 REJECT |
| CPJKU/madmom | github.com/CPJKU/madmom | established ⚠️ | Inactive (per prior audit) | Code BSD / models CC-BY-NC-SA | Beat tracking | 🔴 REJECT (standing decision) |
| katspaugh/wavesurfer.js | github.com/katspaugh/wavesurfer.js | ~10.4k ⚠️ (prior session figure) | Active ✅ | BSD-3-Clause ✅ | Waveform/spectrogram/regions (already installed) | 🟢 REUSE |
| katspaugh/wavesurfer-multitrack | github.com/katspaugh/wavesurfer-multitrack | modest ⚠️ | Active, but documented sync-drift issues ✅ | BSD-3-Clause ✅ (same org/license family) | Multi-track sync | 🟡 REFERENCE |

---

## 7. Hugging Face Candidates

Per §20's instruction, only investigated because "audio similarity/
embeddings" is one of the requested investigation areas — **not** because a
concrete product need was established. The realistic family here is
CLAP-style audio-text/audio-audio embedding models (e.g. LAION-CLAP,
Microsoft CLAP). These were **not deep-audited** (no per-checkpoint license/
weight review performed) because §20 explicitly says not to introduce an ML
model when conventional DSP is sufficient, and §13's analysis concludes
conventional metadata + waveform is sufficient for the MVP comparison use
case. Recorded here as 🟡 REFERENCE only: if a future phase's audit
establishes real product demand for a numeric "these two versions sound
alike" score, CLAP-family models are the right starting search, with a full
license/weight/inference-cost audit at that time — not now.

---

## 8. License Analysis

| Project | License | Verified | Classification |
|---|---|---|---|
| FFmpeg (LGPL build) | LGPL v2.1+ (build-config dependent) | ✅ (existing Tunora policy) | 🟢 REUSE, config-gated |
| soundfile | BSD-3-Clause | ✅ | 🟢 REUSE |
| pyloudnorm | MIT | ✅ | 🟢 REUSE |
| librosa | ISC | ✅ (pre-cleared, re-confirmed) | 🟢 REUSE (BPM only) |
| mutagen | GPLv2+ | ✅ (new finding — was previously unverified) | 🔵 ADAPT, legal flag |
| Essentia | AGPLv3 | ✅ | 🔴 REJECT |
| aubio | GPLv3 | ✅ | 🔴 REJECT |
| madmom (models) | CC-BY-NC-SA 4.0 | ✅ (standing, prior session) | 🔴 REJECT |
| WaveSurfer.js (+ official plugins) | BSD-3-Clause | ✅ | 🟢 REUSE |
| wavesurfer-multitrack | BSD-3-Clause (same org) | ✅ | 🟡 REFERENCE |
| pymediainfo (Python wrapper) | MIT (wrapper) — native `MediaInfo` lib license not verified this session | ⚠️ | 🟡 REFERENCE |
| CLAP-family embedding models | Varies by checkpoint, not audited | ⚠️ unresolved | 🟡 REFERENCE only, no adoption |

No candidate here was recommended for direct adoption with an unresolved
("no license" / unknown) status — where a native dependency's license wasn't
independently confirmed this session (pymediainfo's underlying `MediaInfo`
library), it is marked REFERENCE, not REUSE, per §18's rule.

---

## 9. Reuse Matrix

| Capability | Existing Tunora | OSS Candidate | License | Decision | Reason |
|---|---|---|---|---|---|
| Duration | ✅ `VersionAudio.duration` | — | — | REUSE (already have it) | No gap |
| Media type / filename / size | ✅ `VersionAudio` | — | — | REUSE | No gap |
| BPM / genres / key-scale / time-sig | ⚠️ on Job only | (none needed — data already exists) | — | **ADAPT** | Plumb existing `jobs.result_json` through to Version/Song responses; zero new dependency |
| Sample rate / channels / codec / bitrate | ❌ | soundfile / ffprobe | BSD / LGPL | DEFER | Low product value (§10); would need a new dependency for a fact users haven't asked for |
| RMS / Peak | ❌ | soundfile + numpy | BSD | DEFER | Real candidate, but no proven need vs. the waveform Tunora already renders |
| LUFS | ❌ | pyloudnorm (+ soundfile/numpy) | MIT/BSD | DEFER | Same — real, clean candidate, not yet justified |
| Waveform | ✅ client-side (WaveSurfer) | — | — | REUSE | Already solved |
| Spectrogram | ❌ (plugin present, unused) | WaveSurfer Spectrogram plugin | BSD-3-Clause | DEFER | Zero-cost to add later; no evidence it helps compare two AI generations |
| A/B playback (switch) | ❌ | Compose 2x existing `AudioPlayer` | — | **COMPOSE** | Simplest, most reliable option; no library fits better |
| Synchronized playback | ❌ | wavesurfer-multitrack | BSD-3-Clause | REFERENCE / DEFER | Documented sync-drift bugs; not needed for MVP "switch" UX |
| Version comparison (metadata+waveform) | Data exists, UI doesn't | Compose existing Song/Version API + UI | — | **COMPOSE / BUILD (thin UI)** | This *is* Phase 10's MVP |
| Audio similarity score | ❌ | librosa features + distance, or CLAP embeddings | ISC / varies | DEFER | Unproven need; adds real complexity either way |
| Audio diff (structural) | ❌ | (none needed for MVP) | — | DEFER — simple metadata delta is enough if ever wanted | See §13 |
| Audio fingerprinting | ❌ | (not investigated further) | — | DEFER | No stated use case (e.g. duplicate detection) exists yet |
| Audio embeddings | ❌ | CLAP-family (HF) | Unresolved per-checkpoint | REJECT for now | Contradicts "no ML model unless DSP is insufficient"; DSP hasn't been tried and found insufficient |

---

## 10. Audio Analysis Options

Given the existing data (§2) and the target UX (§0's diagram), the realistic
tiers are:

1. **Tier 0 (already have it, just not shown):** duration, size, media type,
   and — critically — bpm/genres/key-scale/time-signature, all already
   computed by ACE-Step and stored in `jobs.result_json`. Zero cost. This is
   the actual Phase 10 "audio metadata" deliverable.
2. **Tier 1 (small, clean, deferred):** RMS/peak/LUFS via `soundfile` +
   `numpy` (+ `pyloudnorm` for LUFS specifically). All MIT/BSD, all
   Windows-wheel-friendly, all CPU-only. Real candidates *if* a future
   product decision says "users want to compare loudness/dynamics
   numerically," which nothing in the current UI or user request has
   established yet — the waveform already gives a visual proxy for this.
3. **Tier 2 (heavier, not recommended without stronger justification):**
   librosa-based BPM re-computation (if ACE-Step's self-reported bpm proves
   unreliable in practice — not yet demonstrated) and/or spectrogram
   rendering (zero-cost to add, since the plugin ships in the already
   installed npm package, but no demonstrated product need).
4. **Tier 3 (rejected/deferred, real complexity):** key detection beyond
   what ACE-Step already reports (would require BUILDing Krumhansl-Schmuckler
   scoring on librosa chroma — no mature OSS "key detector" library exists
   with a compatible license), audio similarity, embeddings, fingerprinting.

Sample rate/channels/codec/bitrate are explicitly **not** recommended even at
Tier 1: every Version's audio is Tunora's own MP3 output from a single
provider pipeline (ACE-Step → LocalAudioStorage), so these values are
effectively constant across the whole library today; capturing them adds
columns/computation for information that doesn't yet vary or matter, and
becomes relevant primarily once a *second* provider or *uploaded* audio
exists (§14) — at which point it should be captured, not before.

---

## 11. Version Comparison Options

**Recommended approach: COMPOSE, not adopt a new player.** Song Details
already renders exactly one `AudioPlayer` (WaveSurfer-backed) for the
"active" version, selected from a radio list of all versions
(`song-details.tsx`). A comparison view needs only:

- Two version selectors (reusing the existing version list/radio pattern,
  doubled) instead of one.
- Two `AudioPlayer` instances rendered side by side (the component already
  supports being mounted multiple times — it's keyed per version id and
  fully self-contained per `audio-player.tsx`).
- A metadata table reading the same `VersionResponse` fields (duration,
  bpm/genres/key-scale if §9's ADAPT is done, operation/lineage label via
  the already-existing `operationLabel()` helper).

This deliberately rejects `wavesurfer-multitrack` (§5.4): that plugin solves
simultaneous mixed playback of stacked layers with documented drift issues,
not "play A, stop, play B" or "keep position when switching," which two
independent, already-proven `AudioPlayer` instances handle for free.
**Synchronized playback** (play both at once, aligned) is the one piece that
would need small new code (subscribe to one player's `timeupdate`, call
`setTime` on the other) — this is a handful of lines against an already-owned
component, not a new dependency, and should only be built if the MVP's
simple switch-based A/B proves insufficient in practice (see §21, MVP scope).

---

## 12. Waveform / Spectrogram Analysis

**Waveform:** fully solved today. WaveSurfer decodes the downloaded audio
client-side and paints the canvas; nothing is computed or stored server-side,
and nothing needs to be. For comparison, rendering two `AudioPlayer`
instances is the entire "waveform comparison" feature — no backend work, no
new dependency, no persisted waveform peaks. Persisting server-generated
waveform peaks (a common pattern for e.g. long podcasts to avoid a full
download before rendering) is **not** justified here: Tunora's songs are
short (seconds to a few minutes), already fully downloaded for playback (per
`AudioPlayer`'s own docstring — "downloads and decodes the whole file once"),
so there is no separate "peaks-before-full-download" problem to solve.

**Spectrogram:** the WaveSurfer package Tunora already depends on ships an
official `Spectrogram` plugin (BSD-3-Clause, same license, verified this
session) that is simply not imported yet. Adding it is literally a new
`import` line and a `registerPlugin()` call — no new dependency, no backend
work. Recommended as **DEFER**, not REJECT: it is genuinely free to add, but
nothing in the current product surface or this audit's investigation
establishes that a spectrogram materially helps a user judge "is Version B
better than Version A" for an AI music generation — it's a visualization
looking for a use case, not a use case looking for a visualization. Should
be revisited if user feedback specifically asks for it.

---

## 13. Similarity / Diff Analysis

**Do we need an "audio similarity score"? No, not for Phase 10.**

The product surface this audit investigated (comparing two versions of the
same Song, made via Extend/Remix/Repaint/regeneration) already gives the
user everything needed to judge similarity/difference *themselves*: they can
see the lineage (`operationLabel`, e.g. "Extend · from Version 2"), see the
metadata side by side, and listen to both. A numeric similarity score would
answer a question ("how similar are these, 0–100%") the user isn't shown
evidence of asking, and computing one honestly (beyond a superficial
metadata diff) requires either hand-built DSP feature-distance code (a BUILD,
using already-vetted librosa, but real new code and real ongoing tuning) or
an ML embedding model (real GPU/CPU cost, an unaudited license/weights
question, and a category of "AI judging AI" quality claim `CLAUDE.md`
explicitly says Tunora must not overstate — "audio quality, vocals and
pronunciation need human listening; report only objective facts").

**A simple, deterministic metadata diff** — duration delta, size delta, and
(once §9's ADAPT ships) bpm/key delta where both versions have them — is
sufficient "diff" for the MVP and requires no new capability at all: it's
arithmetic over data the comparison view already has.

**Audio fingerprinting / embeddings**: no concrete use case for these was
identified (e.g. de-duplication across a large library was never requested,
and version identity is already tracked structurally via the DB, not
acoustically). REJECT for now — revisit only if a specific, stated need
(e.g. "warn me if I'm about to generate a near-duplicate") is prioritized in
a future audit.

---

## 14. Storage Strategy

**Recommendation: extend the read path, not the write path.** The Job's
`result_json` column already durably stores bpm/genres/key-scale/
time-signature, keyed 1:1 to the Version it produced (`jobs.version_id`,
`Version` is immutable, `Job` rows are never deleted except by whole-Song
deletion — Phase 9). `JobRepository.list_version_entries()`'s existing SQL
can be extended to also select `j.result_json` (or the specific JSON path)
alongside what it already selects, parse the small `_PUBLIC_METADATA_FIELDS`
subset in Python (mirroring `app/api/schemas.py:_public_result`'s existing
allowlist pattern), and attach it to `VersionEntry`/`VersionResponse`. **This
needs zero migration, zero new column, and zero new dependency** — it is a
pure read-path/response-shape change.

If Tier 1 (§10) is ever adopted (RMS/peak/LUFS), the correct storage
strategy — following the audit's own reasoning about Version immutability —
is: **compute once, cache beside the immutable audio artifact, keyed to the
Version's audio reference, on first request or right after generation
completes** (not on every API call), stored as a small additive
`VersionAudio` field/JSON blob (mirroring how `bpm`/`genres`/etc. already
live inside a JSON blob on `Job`) rather than new normalized SQLite columns —
this avoids a migration for a fast-moving, still-speculative feature and
matches the existing project convention of storing generation-result-shaped
data as JSON rather than over-normalizing it prematurely. This mirrors
Tunora's own established precedent (`Job.result` is JSON, not columns) and
should only be implemented when Tier 1 is actually greenlit, not now.

**Explicitly rejected:** a separate "analysis" microservice, queue, or
database (Redis/Celery/Kafka/vector DB — see §31). Analysis, if ever added,
is a synchronous or background-task computation over a local file already on
disk, exactly like every other Tunora operation today — no new
infrastructure category is justified by anything in this audit.

---

## 15. API Proposal

**Minimum surface, and only if the MVP (§21) is accepted:**

- **No new endpoint is strictly required for the metadata gap.** Extending
  `GET /api/songs/{id}` (`SongDetailsResponse.versions[].metadata`, or flat
  fields on `VersionResponse`) to include bpm/genres/key-scale/time-signature
  is the entire "audio metadata" API change — it's an *extension* of an
  existing response, not a new route.
- **Version comparison itself does not need a dedicated backend endpoint
  either.** The frontend already has both versions' full data from the one
  existing `GET /api/songs/{id}` call (it returns every version). A
  "Compare" view can be built entirely as a frontend composition of data
  Tunora's API already returns in full. This directly answers §26's
  question: **the minimum API surface for Phase 10's MVP is zero new
  endpoints.**
- **If Tier 1 (RMS/peak/LUFS) is ever built**, a new
  `GET /api/versions/{id}/analysis` (or nested under the existing Song
  details response) would become justified, since that computation is
  non-trivial and worth caching server-side rather than shipping raw audio
  bytes to the browser for client-side computation. Not proposed for the
  MVP.

---

## 16. UI Proposal

Minimum UX for the MVP, composed entirely from existing primitives
(`song-details.tsx`'s existing version-list/radio pattern, `AudioPlayer`,
`formatDate`/`formatTime`, `operationLabel`):

```
Song Details
    │
    ├── existing single-version view (unchanged)
    │
    └── "Compare Versions" (new, small control — e.g. a toggle/link)
             │
             ▼
        Select Version A   Select Version B   (reuse the existing
        (existing radio-     (a second,        version list/labels;
         style list)          identical list)   no new selection UI
             │                    │              pattern to invent)
             ▼                    ▼
        ┌─────────────────────────────────┐
        │  Version A         │  Version B  │
        │  AudioPlayer (existing component)│  ← two mounts, not one
        │  duration / bpm / key / genre    │  ← from the extended
        │  (from the extended response)    │    VersionResponse
        │  operationLabel() (existing)     │
        └─────────────────────────────────┘
             │
             ▼
        Independent play/pause per side (reuses AudioPlayer's own
        controls; no new transport UI). Synchronized playback: DEFER,
        small future addition if requested (§11).
```

No spectrogram, no similarity score, no new player chrome, no modal
framework — all explicitly deferred/rejected above.

---

## 17. Security Analysis

Applies to the MVP's read-only, purely-derived-from-existing-data scope:

- **No new attack surface for path traversal or arbitrary-file access**: the
  comparison view reads two `version_id`s the caller already has permission
  to see (they come from the same Song's own `GET /api/songs/{id}` response)
  — the same `is_valid_id()`/ownership checks Song Details already uses
  apply unchanged. No new "give me any two version ids" endpoint is proposed
  that would need cross-Song isolation checks beyond what already exists.
- **Cross-Song comparison**: if a future iteration allowed comparing
  versions from *different* Songs, that would need an explicit ownership/
  existence check on both ids (mirroring Phase 9's cross-song audio
  isolation tests) — not needed for the MVP, which compares two versions of
  the *same* Song, already loaded together.
- **If Tier 1 analysis is ever added**: the same `AudioStorage`/`get_path()`
  traversal guards already protecting playback/download apply unchanged to
  any analysis read (analysis would read the same already-validated audio
  key, never a client-supplied path). Malformed/oversized/corrupt audio
  files should fail the same way audio playback failures already do today
  (a safe, generic error — never raw decoder exception text) — this is an
  extension of Tunora's existing `AudioIntegrityError`/`resolve_audio()`
  pattern (`app/jobs/service.py`), not a new security model.
- **Resource exhaustion**: any future server-side analysis must cap file
  size/duration before decoding (the same bound ACE-Step already applies to
  generation duration is a reasonable ceiling) to avoid a "decompression
  bomb"-style DoS from an oversized or malformed audio file; not a concern
  for the MVP since it does no new decoding.

---

## 18. Performance Analysis

- **MVP (metadata + two `AudioPlayer`s):** no new server-side computation at
  all — it's a slightly larger JSON response (a few extra small fields) and
  a second client-side WaveSurfer decode, exactly as expensive as opening
  Song Details twice today. Negligible.
- **If Tier 1 is ever added:** RMS/peak is O(samples) and fast (well under a
  second for a multi-minute MP3 on any modern CPU); LUFS (ITU-R BS.1770) is
  similarly cheap. Both are one-time-per-Version costs if cached (§14), not
  per-request costs. Recommended timing, if built: compute as a background
  step right after `JobService.complete_job` attaches audio (mirroring how
  audio itself is attached once, immutably), not synchronously in the
  request path and not lazily on first UI view (which would make the first
  viewer of a Version pay an unpredictable latency spike).
- **BPM/key re-computation (librosa), if ever needed:** meaningfully more
  expensive (multi-second, CPU-bound, scales with duration) — a real reason
  to keep relying on ACE-Step's already-computed bpm/key rather than
  redundantly recomputing it, absent evidence the existing value is wrong
  often enough to matter.

---

## 19. Failure Modes

| Scenario | Recommended behavior |
|---|---|
| One of the two compared versions has no audio (failed/still generating) | Show the existing "Audio is temporarily unavailable" state for that side only; the other side still plays (mirrors the existing per-version audio-availability handling in `song-details.tsx`) |
| A version was deleted mid-comparison (Phase 9 delete race) | The existing `SongNotFoundError`/404 handling already covers "the Song/Version I was looking at is gone"; the comparison view should show the same safe not-found state, not a partial/stale view |
| Missing bpm/key/genre on one or both versions (ACE-Step didn't report it, or it's an older Version from before this field was surfaced) | Show "—" / omit the row; never fabricate a value, per `CLAUDE.md`'s "no fake capabilities" rule |
| Corrupted/unsupported audio during any future server-side analysis | Fail that one Version's analysis only, log the error, return a safe generic message — exactly the pattern `resolve_audio()`/`AudioIntegrityError` already establish; never surface a raw decoder exception |
| Analysis timeout (future Tier 1) | Treat like any other bounded background step: a reasonable timeout, mark analysis as unavailable rather than blocking the request indefinitely |
| Concurrent/duplicate analysis requests for the same Version (future Tier 1) | Idempotent by construction if cached by Version id (§14) — a second request either finds the cached result or redoes cheap, side-effect-free work; no locking infrastructure needed at this scale |

---

## 20. REUSE / ADAPT / COMPOSE / BUILD Decisions

- **REUSE**: WaveSurfer.js (already installed) for all waveform needs,
  including comparison (two instances) and spectrogram (unused plugin,
  deferred). Existing Song/Version/lineage domain model, unmodified.
- **ADAPT**: the existing `jobs.result_json` → surface bpm/genres/key-scale/
  time-signature through the Song/Version API (currently Job-only). No new
  dependency; a response-shape and query extension only.
- **COMPOSE**: the Version Comparison feature itself, from two existing
  `AudioPlayer` components + the existing version-list UI pattern + the
  (adapted) metadata fields. This is the actual Phase 10 deliverable.
- **BUILD (thin, only if requested later)**: synchronized dual playback (a
  small `timeupdate`→`setTime` bridge between two existing player instances)
  — deferred out of the MVP.
- **REFERENCE**: `wavesurfer-multitrack` (documented sync issues; wrong
  problem shape), CLAP-family embeddings (no proven need), pymediainfo
  (native-library packaging friction), mutagen (usable but GPL-flagged).
- **REJECT**: Essentia (AGPL), aubio (GPL, redundant with ISC librosa for the
  one thing it'd be used for), madmom (NC-licensed models, standing
  decision).
- **DEFER**: RMS/peak/LUFS (soundfile+numpy+pyloudnorm — clean candidates,
  no proven need yet), spectrogram UI (zero-cost to add, no proven need),
  sample-rate/channels/codec/bitrate capture, audio similarity/diff scoring,
  audio fingerprinting.

---

## 21. Recommended Phase 10 MVP

**In scope:**
1. Surface ACE-Step's already-computed bpm/genres/key-scale/time-signature on
   the Song/Version API (extend `VersionResponse`, extend
   `list_version_entries()`'s query to read `jobs.result_json`) — zero new
   dependency, zero migration.
2. A "Compare Versions" view on Song Details: pick any two versions of the
   same Song, see both rendered with the existing `AudioPlayer` side by side,
   plus a metadata table (duration, operation/lineage label, and the newly
   surfaced bpm/key/genre where available).
3. A simple deterministic metadata diff (duration delta, size delta,
   bpm/key delta where both sides have a value) shown in the comparison view
   — arithmetic over existing data, not a new capability.

**Out of scope for this MVP** (all explicitly deferred, not rejected as
ideas — see §9/§20 for why each is deferred rather than built now):
RMS/peak, LUFS, spectrogram, synchronized dual playback, sample-rate/
channels/codec/bitrate capture, audio similarity/diff scoring, audio
fingerprinting, audio embeddings, any new backend dependency.

**Phase 10A/10B/10C breakdown**: not recommended as a multi-part rollout.
The MVP above is small enough (one response-shape extension + one composed
UI view, zero new dependencies) to ship as a single focused phase, matching
the size and shape of Phase 9. A further breakdown would be
premature/artificial scope-splitting for work this contained.

---

## 22. Out of Scope

Per §32/§9: sample-rate/channels/codec/bitrate capture, RMS/peak, LUFS,
spectrogram rendering, synchronized playback, audio similarity/diff scoring,
audio fingerprinting, audio embeddings/ML models, any new analysis
microservice or queue infrastructure, mutagen/librosa/soundfile/pyloudnorm as
new dependencies (all deferred pending proven need, not adopted now).

## 23. Deferred Capabilities

Same list as §22, explicitly carried forward as candidates for a *future*
audit once a concrete product signal (a user request, an observed limitation
of ACE-Step's self-reported bpm/key, a specific "I want to compare loudness"
ask) justifies revisiting them — each already has a vetted, licensed OSS
path recorded above (§5–§9) so a future phase does not need to re-research
from scratch.

## 24. Implementation Plan

Not applicable — this is an audit-only document per the governing prompt
(§3, §36). If the MVP in §21 is accepted, its implementation should follow
the same phase discipline as Phase 9 (a dedicated implementation prompt,
its own audit-acceptance step, reuse-first law, full test suite, one focused
commit) — not started here.

## 25. Risks

- **ACE-Step's self-reported bpm/key/genre may be inaccurate or absent**
  (already a documented limitation, `CLAUDE.md`) — the MVP must display it
  as "reported," never as a verified fact, and must handle its absence
  gracefully (§19), not assume every Version has it.
- **mutagen's GPL license** could be miscategorized as equivalent to the
  rest of Tunora's permissive stack if not explicitly flagged at adoption
  time — this audit flags it now specifically so a future implementer
  doesn't silently treat it as MIT/BSD-equivalent.
- **wavesurfer-multitrack's sync-drift issues** are a real risk if a future
  phase reaches for it instead of the simpler two-independent-players
  composition recommended here — worth re-verifying against the
  then-current plugin version before ever adopting it.
- **Scope creep risk**: the target UX diagram in the governing prompt (§0)
  lists BPM/Key/Loudness/RMS/Peak/LUFS/spectrogram/similarity all together;
  the single biggest risk to this phase is building all of it because it
  was drawn together, rather than shipping the zero-dependency MVP and
  letting real usage justify anything further.

## 26. Final Recommendation

See the decision block below.

---

================================================
PHASE 10 AUDIT — FINAL DECISION
================================================

RECOMMENDED PHASE 10:

    Version Comparison MVP: surface ACE-Step's already-computed bpm/genres/
    key-scale/time-signature on the Song/Version API (currently Job-only),
    and build a "Compare Versions" view on Song Details composed from two
    existing AudioPlayer instances, the existing version-list UI pattern,
    and a simple deterministic metadata diff. No new backend dependency,
    no database migration, no new API endpoint.

REUSE:

    WaveSurfer.js (waveform, and its unused-but-installed Spectrogram
    plugin if ever wanted later); the existing Song/Version/lineage domain
    model unmodified; the existing jobs.result_json data ACE-Step already
    computes.

ADAPT:

    jobs.result_json -> Song/Version API response shape (bpm/genres/
    key-scale/time-signature surfaced where currently Job-only). If ever
    prioritized later: mutagen (GPL, flagged), librosa (BPM only, ISC).

COMPOSE:

    The Version Comparison UI itself, from two existing AudioPlayer
    components + existing version-selection UI + the adapted metadata.

BUILD:

    Nothing new for the MVP beyond the thin comparison UI composition
    above. (Deferred, only if requested later: a small timeupdate/setTime
    bridge for synchronized dual playback.)

REFERENCE:

    wavesurfer-multitrack (documented sync-drift issues; wrong problem
    shape for this use case); pymediainfo (native-library packaging
    friction); CLAP-family audio embeddings (no proven need); mutagen
    (usable, but its GPL license must be explicitly flagged, not treated
    as equivalent to the rest of the permissive stack).

REJECT:

    Essentia (AGPLv3), aubio (GPLv3, redundant with ISC librosa for the
    one relevant capability), madmom (CC-BY-NC-SA model weights, standing
    decision, inactive project).

DEFER:

    RMS/peak/LUFS (soundfile + numpy + pyloudnorm — clean, permissively
    licensed candidates, but no proven product need yet), spectrogram UI
    (zero-cost to add later, no proven need), sample-rate/channels/codec/
    bitrate capture, synchronized dual playback, audio similarity/diff
    scoring, audio fingerprinting, audio embeddings, any dedicated analysis
    microservice/queue/vector-database infrastructure.

NEW DEPENDENCIES EXPECTED:

    Zero, for the recommended MVP. (soundfile, numpy, pyloudnorm are
    pre-vetted and ready if Tier 1 is ever greenlit in a future phase.)

DATABASE CHANGES EXPECTED:

    None. The MVP reads jobs.result_json, which already exists.

API CHANGES EXPECTED:

    An extension of the existing GET /api/songs/{id} response shape
    (VersionResponse gains bpm/genres/key_scale/time_signature fields,
    following the same allowlist pattern _PUBLIC_METADATA_FIELDS already
    uses for JobResponse). No new endpoint.

UI CHANGES EXPECTED:

    A new "Compare Versions" view on the Song Details page, composed from
    existing components (AudioPlayer x2, the existing version list/label
    helpers) plus a small new metadata-diff table.

MAJOR RISKS:

    ACE-Step's self-reported bpm/key/genre accuracy is unverified and must
    be presented honestly as provider-reported, not ground truth; scope
    creep toward building every item in the target UX diagram at once
    rather than shipping the zero-dependency MVP first.

IMPLEMENTATION COMPLEXITY:

    LOW

RECOMMENDATION:

    Approve the MVP as scoped in §21. Do not approve RMS/peak/LUFS/
    spectrogram/similarity/embeddings for this phase; revisit each only if
    real usage of the MVP surfaces a concrete need, per REUSE-FIRST-LAW.

AUDIT STATUS:

    READY FOR USER REVIEW
