# Tunora — Phase 3 Reuse Audit: Complete AI Music Studio Applications

Scope: fresh, live (2026-09-19) GitHub research for existing **complete open-source AI music generation applications/dashboards** that could serve as the app-shell foundation for Tunora's Phase 3 vertical slice (create song → track generation → play/download → saved location). This is distinct from [UI-REUSE-AUDIT.md](./UI-REUSE-AUDIT.md) (Phase 1), which evaluated generic component libraries (shadcn/ui) and audio players (WaveSurfer.js) — those conclusions stand and are not re-litigated here.

Method: live GitHub API + WebFetch checks (star counts, license files, last-commit dates), not recalled/guessed. Search terms used: "AI music generator", "AI music studio", "music generation dashboard", "AI song generator", "ACE-Step UI", "ACE-Step studio", "music generation frontend/web app", "AI music playground", "text-to-music UI", "song generation UI", "music library UI", "audio generation dashboard", "local AI music generator", "open-source Suno alternative", "open-source AI music studio", "self-hosted AI music generator".

## 1. Capability Comparison Table

| Capability | fspecii/ace-step-ui | Sion971/ace-step-studio | timoncool/ACE-Step-Studio | audiohacking/acestep-cpp-ui | ace-step/ACE-Step-DAW | Build |
|---|---|---|---|---|---|---|
| Dashboard/shell | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Create Song form | ✓ | ✓ | ✓ | ✓ | partial | ✓ |
| Lyrics input | ✓ | ✓ | ✓ | ✓ | – | ✓ |
| Prompt/style input | ✓ | ✓ | ✓ | ✓ | – | ✓ |
| Vocal settings | partial | partial | partial | partial | – | ✓ |
| ACE-Step support | ✓ (Gradio API) | ✓ (native 1.5) | ✓ (XL, native) | ✓ (GGUF/cpp) | unclear | n/a |
| Job tracking | ✓ | ✓ | ✓ | ✓ | – | ✓ |
| Progress display | ✓ | ✓ | ✓ | ✓ | – | ✓ |
| Queue | ✓ | ✓ | partial | ✓ | – | ✓ |
| Audio player | ✓ | ✓ | ✓ | ✓ | ✓ (DAW-style) | ✓ |
| Waveform | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Download | ✓ | ✓ | ✓ | ✓ | – | ✓ |
| Library/History | ✓ | ✓ | ✓ | ✓ | – | ✓ |
| Projects | – | partial (workspaces) | – | – | – | ✓ |
| Versioning | – | – | – | – | – | ✓ |

## 2. Per-Candidate Detail

### fspecii/ace-step-ui (leading known candidate — re-audited)
- **Stars**: 4,904. **Created**: 2026-02-04. **Last push**: 2026-06-27 (~3 months stale as of this audit).
- **Stack**: React 19 + TypeScript + Tailwind + Vite; Express.js server (`server/src`) with better-sqlite3 (SQLite); calls ACE-Step 1.5 via its Gradio API. Optional `@google/genai` (Gemini) dependency for AI-assisted lyrics.
- **License**: **CONFIRMED UNRESOLVED, now stronger than "unresolved"** — GitHub API `license` field is `null`, and a fresh root-directory listing shows no `LICENSE`/`LICENSE.md`/`COPYING` file anywhere. README claims MIT but there is no license grant in the repo. Directly confirms and hardens the 2026-09-15 Phase 1 finding.
- **Features**: song creation (BPM/key/time-sig/duration/style tags), lyrics editor with structure tags, instrumental mode, batch generation, waveform player, queue+progress, library/search/favorites, built-in audio editor (AudioMass), stem separation (Demucs), video generation. No Projects/Versioning.
- **Cost**: fully local/free; optional Gemini API call must remain skippable to satisfy zero-mandatory-cost policy.
- **Integration difficulty into Next.js+FastAPI**: **Medium-High**. React+Vite is not Next.js (routing/SSR conventions differ); Express+Node+SQLite backend is not FastAPI/Python — the backend would need a rewrite, not an adaptation. The license blocker makes this moot regardless.

### Sion971/ace-step-studio
- **Stars**: 1. **Created**: 2026-08-27. **Last push**: 2026-09-18 (actively worked on, day-old).
- **License**: **MIT — CONFIRMED** via GitHub API `license.key: "mit"` and an actual `LICENSE` file at repo root.
- **Stack**: React 18 + TS + Tailwind + Vite; Express.js + SQLite (same lineage/near-identical structure to fspecii's). Bundles its own copy of ACE-Step 1.5 rather than depending on a separately-run instance.
- **Features**: same superset as fspecii plus "workspaces" (closest any candidate gets to a Projects concept) and playlists, reference-audio/cover/repaint, LoRA training, MIDI conversion.
- **Maintenance**: 3 weeks old, 1 star, single-maintainer, unproven — matches the Phase 1 characterization exactly.
- **Integration difficulty**: **Medium-High**, same reasoning as fspecii, but legally usable.

### timoncool/ACE-Step-Studio (new find, not in Phase 1 audit)
- **Stars**: 343. **Created**: 2026-04-10. **Last push**: 2026-09-14 (most actively maintained of the group).
- **License**: **MIT — CONFIRMED** via API and a real `LICENSE` file at root.
- **Stack**: React+Vite frontend, Express.js backend, Python/PyTorch pipeline, Node 22, FFmpeg w/ NVENC. Stores song data client-side (`localStorage`) rather than a real DB.
- **ACE-Step integration**: targets **ACE-Step 1.5 XL (4B)**, not the 2B DiT Tunora's Phase 2 test plan uses on the RTX 5060 Ti — a real mismatch.
- **Features**: full song creation up to 8 min, Simple/Custom modes, AI-assisted lyrics/style (optional OpenRouter), cover/remix, batch generation, 10 samplers/7 schedulers, waveform repaint, LoRA, Demucs stems, GPU/VRAM monitoring, ID3/LRC export, video/visualizer generation. No Projects/Versioning.
- **Cost**: core local/free; optional OpenRouter (lyrics) and Pollinations.ai (cover art) calls — must be confirmed disable-able.
- **Integration difficulty**: **Medium-High** — richest feature set and best maintained, but same Node/Express/Vite-vs-FastAPI/Next.js mismatch, plus targets the wrong model tier.

### audiohacking/acestep-cpp-ui
- **Stars**: 103. **Created**: 2026-03-07. **Last push**: 2026-05-17 (~4 months stale).
- **License**: **UNRESOLVED — same pattern as fspecii.** API `license` field is `null`, no LICENSE file in root listing. It is an explicit fork of fspecii's UI ("UI forked from original ace-step-ui project"), which itself has no license grant — compounding the problem.
- **Stack**: identical shell to fspecii (React/TS/Tailwind/Vite + Express + better-sqlite3), but swaps the inference backend for `acestep.cpp` (GGUF-quantized, no-Python) — off Tunora's locked `transformers`/`diffusers` inference approach.
- **Integration difficulty**: **High** — license blocker plus a different (GGUF/C++) inference path.

### ace-step/ACE-Step-DAW (WIP)
- **Stars**: 82. **Created**: 2026-02-14. **Last push**: 2026-04-30 (README literally says "WIP").
- **License**: **AGPL-3.0 — CONFIRMED** via LICENSE file and API. Hard blocker per existing project policy (AGPLv3 already caused a hard-reject of `aeneas`; GPL/AGPL code is explicitly "reference only, cannot ship" per [LICENSE-AUDIT.md](./LICENSE-AUDIT.md)). AGPL's network-copyleft clause is incompatible with a self-hosted/distributed product Tunora doesn't want to force-open.
- **Stack**: Rust (`crates/`), Tauri, TypeScript — a DAW-style multitrack timeline, not a generation-request UI.
- **Verdict**: excluded — license alone disqualifies it regardless of features.

### Other candidates considered and ruled out
- **gabotechs/MusicGPT**: real, active OSS project, but a Rust **terminal/CLI** binary wrapping MusicGen (CC-BY-NC-4.0 weights — already a Tunora hard-reject). No web dashboard, no library UI.
- **strnad/HeartMuse**: genuine Gradio web UI, but built for HeartMuLa (not ACE-Step); Gradio isn't a serious foundation for a Next.js/Tailwind/shadcn product shell.
- **cocktailpeanut/ace-step-ui.pinokio** and **Saganaki22/ACE-Step-1.5-UI_AIO**: installers/launchers wrapping fspecii's UI, not independent applications — inherit its unresolved license and add nothing architecturally.
- **SAMKhadka/ace-step-ui**: file listing byte-for-byte identical to fspecii's despite `fork:false` and an internally-inconsistent `created_at: 2023-12-23` (predates ACE-Step's existence). Authenticity **could not be confirmed**; excluded.

## 3. Rough % of Phase-3 UI Requirements Covered (rough estimate, not a precise metric)

| Candidate | Rough % covered |
|---|---|
| fspecii/ace-step-ui | ~65-70% (feature-rich, but wrong backend stack + no license) |
| Sion971/ace-step-studio | ~60-65% (same features, legally usable, but 3-week-old/1-star/unproven) |
| timoncool/ACE-Step-Studio | ~65-70% (most active, richest features, but XL model + wrong backend stack) |
| audiohacking/acestep-cpp-ui | ~55-60% (feature parity with fspecii, license blocked, off-target inference engine) |
| ace-step/ACE-Step-DAW | ~20-25% (DAW-shaped, not generation-request-shaped, AGPL-blocked anyway) |

These measure feature-checklist overlap only, not how much code would actually survive a port to Tunora's locked stack.

## 4. License Findings Summary

- **UNRESOLVED (no LICENSE file, README claims unverified)**: `fspecii/ace-step-ui`, `audiohacking/acestep-cpp-ui` (fork of the former, inherits the problem).
- **BLOCKING (confirmed copyleft, hard-reject per existing policy)**: `ace-step/ACE-Step-DAW` — AGPL-3.0.
- **CONFIRMED CLEAN (MIT + real LICENSE file)**: `Sion971/ace-step-studio`, `timoncool/ACE-Step-Studio`.
- No candidate requires a mandatory paid API; `timoncool/ACE-Step-Studio` has *optional* cloud calls (OpenRouter, Pollinations.ai) that must stay skippable per Tunora's zero-mandatory-cost policy — flag for a follow-up check if it's ever reconsidered.

## 5. Recommendation carried into the decision doc

See [PHASE-3-UI-REUSE-DECISION.md](./PHASE-3-UI-REUSE-DECISION.md) for the explicit REUSE/ADAPT/COMPOSE/BUILD decision and reasoning.
