# Tunora — Reuse Matrix (Phase 1)

One row per capability. Evidence-based, from live research on 2026-09-15 (see companion audit docs for full scorecards). No row is an assumption — where evidence was thin, the row says so.

| Capability | Existing OSS | Tested | License | Cost | Decision |
|---|---|---|---|---|---|
| Full song generation (primary) | ACE-Step 1.5 | NOT TESTED (no GPU) | MIT code / Apache-2.0-style weights | 🟢 Zero cost | 🟢 REUSE |
| Full song generation (secondary/fallback) | DiffRhythm2 | NOT TESTED (no GPU) | Apache-2.0 code+weights | 🟢 Zero cost | 🔵 ADAPT (needs a hands-on spike) |
| Full song generation (lyrics-heavy alt.) | YuE / YuE2 | NOT TESTED (no GPU) | Apache-2.0 code; weights mostly Apache-2.0 (per-checkpoint unresolved) | 🟢 Zero cost, but 24GB VRAM floor | 🔵 ADAPT |
| Full song generation (watchlist) | HeartMuLa | NOT TESTED (no GPU) | Apache-2.0 code+weights | 🟢 Zero cost | 🟡 REFERENCE (undisclosed training data) |
| Instrumental/SFX generation (bounded) | Stable Audio Open 1.0 | NOT TESTED (no GPU) | MIT code / Stability AI Community License weights | 🟡 Free under $1M revenue, paid above | 🟡 REFERENCE |
| Instrumental generation (melody-conditioned) | AudioCraft / MusicGen | NOT TESTED (no GPU) | MIT code / CC-BY-NC-4.0 weights | 🔴 Weights block commercial use | 🔴 REJECT (weights) / 🟡 REFERENCE (code) |
| Complete music studio application (base to adapt) | fspecii/ace-step-ui | Not run; README+structure inspected via WebFetch | MIT claimed, unconfirmed (no detected LICENSE file) | 🟢 Zero cost | 🔵 ADAPT (license verification required first) |
| Projects/workspace grouping pattern | Sion971/ace-step-studio (fork) | Not run; README inspected | MIT (confirmed via GitHub API) | 🟢 Zero cost | 🟡 REFERENCE (young/unproven, 1 star) |
| Dashboard UI component system | shadcn/ui | Verified via WebFetch (docs/repo) | MIT | 🟢 Zero cost | 🟢 REUSE |
| Audio player | WaveSurfer.js | Verified via WebFetch | BSD-3-Clause | 🟢 Zero cost | 🟢 REUSE |
| Waveform rendering | WaveSurfer.js (core + Regions/Timeline/Spectrogram plugins) | Verified via WebFetch | BSD-3-Clause | 🟢 Zero cost | 🟢 REUSE |
| Lyrics editor / LRC UI | None mature found (lyric-timer, LySy referenced only) | N/A | MIT (reference projects only) | 🟢 Zero cost | ⚪ BUILD (composed on WaveSurfer + Regions) |
| Generation job-status UI | None reusable found (ComfyUI/A1111 pattern-only, GPL/AGPL) | N/A | GPL-3.0 / AGPL-3.0 (not reusable) | 🟢 Zero cost | ⚪ BUILD (on shadcn/ui primitives) |
| Song library / history | Present inside fspecii/ace-step-ui | Not run; README inspected | Same as base app (unconfirmed) | 🟢 Zero cost | 🔵 ADAPT (comes with the base app) |
| Projects | No project has this as a first-class feature at Tunora's spec | N/A | N/A | N/A | ⚪ BUILD |
| Versioning | No project audited implements per-song version history | N/A | N/A | N/A | ⚪ BUILD |
| Stem separation | Demucs (adefossez fork) | NOT TESTED (no GPU) | MIT code; weights license disputed/unverified | 🟢 Zero cost (pending weight-license confirmation) | 🔵 ADAPT |
| General audio processing | FFmpeg + soundfile + librosa | Verified via WebFetch (license pages) | LGPL (FFmpeg, config-dependent) / BSD-3 / ISC | 🟢 Zero cost | 🟢 REUSE |
| Music transcription (audio-to-MIDI) | basic-pitch (Spotify) | NOT TESTED (no GPU) | Apache-2.0 code+weights | 🟢 Zero cost | 🟢 REUSE (V2+ scope) |
| Beat/tempo detection | librosa (built-in) | NOT TESTED | ISC | 🟢 Zero cost | 🟢 REUSE |
| Lyric alignment / LRC generation | stable-ts (archived, fork-and-maintain) / WhisperX (adapt workaround) | NOT TESTED (no GPU) | MIT / BSD-2-Clause | 🟢 Zero cost | 🔵 ADAPT |
| AI orchestration / "Song Director" | No framework adopted — deferred, avoid bloat | N/A | N/A | N/A | ⚪ BUILD (thin, minimal — evaluate LangChain/structured-output libs only if genuinely needed) |
| Job queue | RQ | Verified via WebFetch | MIT | 🟢 Zero cost | 🟢 REUSE |
| GPU worker pattern | Plain worker + HF transformers/diffusers | N/A (architectural pattern) | Apache-2.0 | 🟢 Zero cost | 🟢 REUSE |
| Storage (MVP) | Local filesystem | N/A | N/A | 🟢 Zero cost | 🟢 REUSE |
| Storage (later, object storage) | MinIO | N/A | AGPLv3 | 🟢 Zero cost but risky | 🔴 REJECT (archived April 25, 2026 — re-research when actually needed) |
| Authentication | Deferred for MVP (local/single-user); fastapi-users as fallback | N/A | MIT (fastapi-users) | 🟢 Zero cost | 🟢 REUSE (defer) / 🟡 REFERENCE (fastapi-users) |
| Monitoring | Structured logging only | N/A | MIT/BSD-family | 🟢 Zero cost | 🟢 REUSE (defer full observability stack) |
| Testing infrastructure | Standard pytest/Playwright (not deep-audited this phase) | N/A | N/A | 🟢 Zero cost | 🟡 REFERENCE (revisit in an implementation-planning phase) |
| Deployment | Docker / Docker Compose (not deep-audited this phase — no contrary evidence found) | N/A | N/A | 🟢 Zero cost | 🟢 REUSE |

See [LICENSE-AUDIT.md](./LICENSE-AUDIT.md) and [COST-AUDIT.md](./COST-AUDIT.md) for the full per-item license/cost detail behind this table, and [BUILD-VS-REUSE.md](./BUILD-VS-REUSE.md) for the reasoning behind each ⚪ BUILD row.
