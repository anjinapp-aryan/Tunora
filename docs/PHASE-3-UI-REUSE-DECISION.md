# Tunora — Phase 3 UI Reuse Decision

This document answers the ten required questions from the Phase 3 master prompt directly, based on the evidence in [PHASE-3-REUSE-AUDIT.md](./PHASE-3-REUSE-AUDIT.md).

## 1. Which GitHub UI repositories were investigated?

`fspecii/ace-step-ui`, `Sion971/ace-step-studio`, `timoncool/ACE-Step-Studio`, `audiohacking/acestep-cpp-ui`, `ace-step/ACE-Step-DAW`. Also considered and ruled out on feature/architecture/license grounds without a full write-up: `gabotechs/MusicGPT`, `strnad/HeartMuse`, `cocktailpeanut/ace-step-ui.pinokio`, `Saganaki22/ACE-Step-1.5-UI_AIO`, `SAMKhadka/ace-step-ui` (authenticity could not be confirmed).

## 2. Which ones were technically suitable?

None fully, on stack-fit grounds. All five serious candidates are React+Vite+Express(+SQLite) applications; Tunora's locked stack is Next.js+TypeScript+Tailwind+shadcn/ui (frontend) and Python+FastAPI (backend, per [PHASE-1-DECISIONS.md](./PHASE-1-DECISIONS.md) and `../ACE-Step-1.5`'s own note that the parent Tunora frontend/backend are separate from the vendored model repo). Node/Express backends cannot be "adapted" into FastAPI — that's a rewrite, not a port. `timoncool/ACE-Step-Studio` additionally targets the XL (4B) model tier, not the 2B DiT tier Phase 2's test plan uses for the RTX 5060 Ti. Feature-wise (forms, lyrics, job tracking, player, library), all four ACE-Step-specific candidates (fspecii, Sion971, timoncool, audiohacking) are strong matches — the mismatch is architectural, not conceptual.

## 3. Which ones had valid licenses?

Valid (MIT, confirmed via LICENSE file + GitHub API): `Sion971/ace-step-studio`, `timoncool/ACE-Step-Studio`.
Unresolved (no LICENSE file despite README claims): `fspecii/ace-step-ui`, `audiohacking/acestep-cpp-ui`.
Blocking (confirmed AGPL-3.0): `ace-step/ACE-Step-DAW`.

## 4. Which one was selected?

None was selected for adoption as the app-shell foundation. **Decision: BUILD** the Tunora frontend (Next.js) and backend (FastAPI), **COMPOSE**d from already-locked primitives (shadcn/ui, WaveSurfer.js) plus a new `AceStepProvider` integration — informed by the UX patterns of `fspecii/ace-step-ui`, `Sion971/ace-step-studio`, and `timoncool/ACE-Step-Studio` as reference only (no code copied).

## 5. Why was it selected?

Because no candidate clears both gates simultaneously:
- The two richest, best-maintained candidates (fspecii, timoncool) fail the license or stack-fit gate outright — fspecii has no confirmed license grant at all; timoncool targets the wrong model tier and both are Node/Express, not Python/FastAPI.
- The one candidate with a clean license (Sion971) is three weeks old, has one star, one maintainer, and no track record — adopting it as a foundation means inheriting an unproven codebase for no architectural savings, since it shares the same Express/SQLite mismatch as the rest.
- Every serious candidate shares the same structural blocker: Node/Express backend vs. Tunora's locked Python/FastAPI, and Vite SPA vs. Tunora's locked Next.js. There is no candidate where "adapt the codebase" is cheaper than "write fresh code against the locked stack and reuse the already-decided component/audio primitives."

This does not violate the Reuse-First Law: the law asks whether a *suitable* existing solution exists, not whether *any* existing solution touching the same problem exists. Suitability requires clearing the license gate and the stack-fit gate together; none did.

## 6. What functionality will be reused?

- **shadcn/ui** (MIT) — dashboard/form/card/progress/badge components (Phase 1 decision, reaffirmed).
- **WaveSurfer.js** (BSD-3-Clause) — audio playback + waveform rendering (Phase 1 decision, reaffirmed).
- **ACE-Step 1.5's REST API** (`/health`, `/release_task`, `/query_result`, confirmed live in `acestep/api/http/*`) — reused as-is as the generation engine; Tunora does not modify ACE-Step.

## 7. What functionality will be adapted?

Nothing at the codebase level. UX **patterns** are adapted (not code) from the audited candidates: song-creation form field layout (title/prompt/lyrics/vocal settings/duration/model/seed — all three ACE-Step UIs converge on a similar set), job-status/queue display conventions (queued → generating → completed, progress indication), and library/history list layout.

## 8. What functionality will be composed?

The Tunora app shell itself is a composition: Next.js/shadcn/ui dashboard + WaveSurfer.js player + a new `AceStepProvider` calling the existing ACE-Step API + a Tunora-owned job/song data model and local filesystem storage. See [PHASE-3-ARCHITECTURE.md](./PHASE-3-ARCHITECTURE.md).

## 9. What functionality must be built?

Per the "Confirmed BUILD-only" list in the root `CLAUDE.md`/`PHASE-1-DECISIONS.md`, reaffirmed and scoped for Phase 3:
- Create Song form (Tunora-specific fields, Next.js + shadcn/ui)
- `MusicGenerationProvider` abstraction + `AceStepProvider` implementation (FastAPI)
- Tunora job model + lifecycle state machine (QUEUED/PROCESSING/COMPLETED/FAILED)
- Output file handling: verify ACE-Step's output, copy/move into Tunora-owned storage, expose a stable audio URL + filesystem path
- Dashboard/recent-generations list, saved-location display, download action
- SQLite persistence for jobs/songs (Phase 3 POC scope)

## 10. Why can't the remaining functionality be reused?

- **Job-status/queue UI**: Phase 1's audit already found no MIT/Apache, React-native, drop-in library for this pattern (only GPL/AGPL reference implementations — ComfyUI, AUTOMATIC1111). Nothing found in this fresh audit changes that; all viable examples are bundled inside the Node/Express candidate apps rather than being extractable independent components.
- **Provider abstraction, job model, saved-location/download flow**: these are Tunora-specific by definition — they exist to decouple Tunora from ACE-Step specifically (per `ARCHITECTURE-PRINCIPLES.md`'s "no component the UI depends on may hardcode a specific AI model" rule) and to give Tunora ownership of its own file storage rather than ACE-Step's `.cache/`. No third-party project needs this exact abstraction because none of them are trying to stay swappable across multiple generation backends.
- **The overall app shell**: blocked by the license/stack-fit combination explained in Q5, not by absence of prior art.
