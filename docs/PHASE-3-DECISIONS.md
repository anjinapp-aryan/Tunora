# Tunora — Phase 3 Decisions

## Decisions Made

1. **UI/app-shell reuse decision: BUILD** (with UX patterns COMPOSEd from reference, no code reuse). No existing complete AI-music-studio application clears both the license gate and the Next.js+TypeScript+Tailwind+FastAPI stack-fit gate at once — see [PHASE-3-UI-REUSE-DECISION.md](./PHASE-3-UI-REUSE-DECISION.md) for the full evidence-based reasoning.
2. **`fspecii/ace-step-ui`'s license status is now CONFIRMED UNRESOLVED**, not merely unconfirmed — a fresh repo listing found no LICENSE file at all despite the README's MIT claim. This closes the "pending direct confirmation" hedge from [PHASE-1-DECISIONS.md](./PHASE-1-DECISIONS.md) decision #1 (which had tentatively named it as an ADAPT candidate) — it is no longer a viable adaptation base.
3. **Two new MIT-licensed candidates surfaced** in this fresh audit that Phase 1 didn't have: `Sion971/ace-step-studio` (already known but now license-confirmed) and `timoncool/ACE-Step-Studio` (new find, most actively maintained of the group). Both are reference-only for UX patterns, not adoption candidates, per the stack-fit reasoning in the decision doc.
4. **Provider abstraction confirmed as Tunora-owned, BUILD-only**: `MusicGenerationProvider` interface + `AceStepProvider` implementation against ACE-Step's confirmed-live REST endpoints (`/health`, `/release_task`, `/query_result`), per [PHASE-3-ARCHITECTURE.md](./PHASE-3-ARCHITECTURE.md).
5. **Job identity is Tunora-owned**: `TunoraJob.id` is primary; ACE-Step's task id is stored only as `providerTaskId`, never the primary key — required so switching or adding providers later doesn't break job history.
6. **No fabricated progress percentages** — if ACE-Step's `/query_result` doesn't expose true completion percentage, the UI shows truthful coarse state (queue position / phase name) instead, consistent with the Phase 2 "never invent metrics" rule extended into Phase 3 UI copy.
7. **Tunora owns final audio storage** — generated output is copied out of ACE-Step's own working directory (`.cache/`) into Tunora-owned local storage (e.g. `I:\Tunora\data\audio\`) before being exposed to the user; ACE-Step's cache is treated as ephemeral/internal to ACE-Step, not a Tunora storage location.
8. **No new infra introduced**: SQLite for the Phase 3 job/song store, local filesystem for audio, polling (not SSE/WebSocket) for status — reaffirms Phase 1/2's zero-premature-infra stance for this scope.

## What Changed From Phase 1

- Phase 1 tentatively named `fspecii/ace-step-ui` as an ADAPT candidate pending license confirmation. This phase's direct, fresh repo inspection confirms no LICENSE file exists — the tentative plan is superseded by decision #1 above. `ARCHITECTURE-PRINCIPLES.md`'s implied "adapt an existing app" starting point from Phase 1 should be read as superseded by this phase's BUILD decision for the app shell (component-level REUSE of shadcn/ui and WaveSurfer.js from Phase 1 is unaffected and still stands).
- Phase 1 did not evaluate `timoncool/ACE-Step-Studio` (did not yet exist prominently) or re-verify `Sion971/ace-step-studio`'s license with a direct file check; both are now confirmed MIT but still ruled out as adoption candidates for stack-fit reasons.

## Stop Gate (per Phase 3 spec §24)

Per the Phase 3 master prompt's explicit instruction, implementation does **not** proceed automatically past this point. This decision (BUILD the app shell, REUSE shadcn/ui + WaveSurfer.js + the live ACE-Step API, COMPOSE the rest) is presented for confirmation before Steps 11+ (backend/provider integration, job lifecycle, storage, UI implementation) begin.

## Next Phase

Pending go-ahead: implement Steps 11-19 of the Phase 3 spec (provider integration → job lifecycle → storage → UI → playback → saved-location display → end-to-end tests → dependency/license audit of anything newly added) against the architecture in [PHASE-3-ARCHITECTURE.md](./PHASE-3-ARCHITECTURE.md). `docs/PHASE-3-TEST-RESULTS.md` will be created once there is something real to test.
