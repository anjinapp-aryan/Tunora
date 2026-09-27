# Phase 12: Timeline Repaint Region Selection

This is the implementation record for the capability scoped by
`docs/PHASE-12-PRODUCT-CAPABILITY-GAP-AUDIT.md` and explicitly requested by
the user. It is a UI composition phase: no Repaint, Version, AudioStorage or
JobService redesign; no ACE-Step change; no new dependency.

## 1. Objective

Replace the numeric-only Repaint Start/End workflow with a visual waveform
region selector, built entirely on the already-installed WaveSurfer.js
Regions plugin, while keeping the numeric Start/End fields as the
keyboard-accessible fallback and the backend Repaint contract (`repaint_start`
/ `repaint_end` in seconds) completely unchanged.

## 2. WaveSurfer / Regions API inspection (not assumed from memory)

- WaveSurfer.js **7.12.12** (`frontend/node_modules/wavesurfer.js/package.json`).
- Regions plugin ships at `wavesurfer.js/dist/plugins/regions.js` (+ `.cjs`,
  `.esm.js`, `.min.js`, `.d.ts`), read directly from `regions.d.ts`:
  - `RegionsPlugin.create(options?)` — static factory; `WaveSurfer.registerPlugin(plugin)` registers it.
  - `RegionsPlugin.addRegion(params)` — `{ start, end, drag?, resize?, minLength?, maxLength?, color? }`, all in **seconds**.
  - `Region` (`SingleRegion`): `.start`, `.end`, `.setOptions(partial)`, `.remove()`, events `update` / `update-end` / `remove`.
  - `EventEmitter.on(event, listener)` returns an **unsubscribe function** (confirmed in `event-emitter.d.ts`) — used for cleanup instead of `.un()`.
  - The rendered region element carries a shadow-DOM `part` attribute (`region <id>`, set in the plugin's own minified source at `setPart()`), which is what the new Playwright E2E test locates instead of inventing a data-testid inside third-party markup.
  - **No native keyboard handling** exists anywhere in the plugin (no keydown listeners found) — this is the concrete evidence behind keeping the numeric fields as the accessible path (§8).
- `enableDragSelection` (drawing a brand-new region from empty space) was
  inspected and deliberately **not used** — Repaint always has exactly one
  existing region with a default position, never an empty canvas the user
  draws from scratch.

## 3. Reuse decision

Reused unchanged: WaveSurfer.js, the Regions plugin, `AudioPlayer`'s existing
WaveSurfer instance/lifecycle, `VersionActions`'s existing Repaint form,
`repaint_start`/`repaint_end` request fields, the existing
`POST /api/songs/{id}/versions/{id}/repaint` endpoint, `REPAINT_MIN_SECONDS`
(already mirrored on the frontend since an earlier phase). Added: a `region`
prop on the existing `AudioPlayer` (§4) rather than a second player
component, and `REPAINT_MAX_SECONDS` on the frontend (`frontend/src/lib/api/songs.ts`)
to complete the existing min-only mirror of the backend's single source of
truth (`backend/app/songs/operations.py: REPAINT_MIN_SECONDS`/`REPAINT_MAX_SECONDS`).
No new npm package.

## 4. Region model and the AudioPlayer capability

`AudioPlayer` (`frontend/src/components/audio/audio-player.tsx`) gained one
optional prop:

```ts
export interface AudioPlayerRegion {
  start: number;
  end: number;
  minLength: number;
  maxLength: number;
  onChange: (start: number, end: number) => void;
}
export function AudioPlayer({ src, region }: { src: string; region?: AudioPlayerRegion })
```

When `region` is absent, `AudioPlayer` behaves exactly as before Phase 12.
When present, a `RegionsPlugin` is registered unconditionally (registering a
plugin with zero regions is free) and exactly one region is added, wired to
the Regions plugin's own `drag: true, resize: true` with `minLength`/
`maxLength` in seconds — so drag (move) and edge-resize are both native
Regions plugin behavior, not custom pointer-event code. `update`/`update-end`
report the region's current `start`/`end` back through `onChange`.

Sharing state: `AudioPlayer` (the waveform) and `VersionActions` (the
Repaint form) are **siblings** under `SongDetails`, so the single
authoritative `repaintRegion` state is lifted to their parent,
`frontend/src/components/song/song-details.tsx`, and passed down to both —
standard "lift state up," not a redesign of either component.

## 5. Region ↔ seconds conversion (`frontend/src/lib/audio/repaint-region.ts`)

A small, WaveSurfer-independent module (17 unit tests):

- `clampRepaintRegion(start, end, bounds)` — the single place that enforces
  finite/non-negative values, `start < end`, `[0, duration]`, and
  `[minLength, maxLength]`. NaN (garbage/absent input) falls back to a safe
  minimal region; `+/-Infinity` is treated as a real "as far as possible"
  value and clamps to the duration boundary like any other overflow — this
  distinction is deliberate and covered by its own tests.
- `defaultRepaintRegion(bounds)` — one quarter of the song, clamped by the
  same bounds. Documented explicitly here (and in code): previously the
  numeric fields simply started blank; a visual region needs *something* on
  screen the instant the panel opens, so this is a new, disclosed default,
  not a silent behavior change.
- `regionsApproximatelyEqual(a, b, epsilon)` — guards the two-way sync in §6
  against feedback loops from floating-point/rounding noise.

This module is the **only** place Repaint bounds logic lives on the
frontend; it mirrors the backend's `REPAINT_MIN_SECONDS`/`REPAINT_MAX_SECONDS`
as the single source of truth and never invents a second set of business
rules. The backend re-validates independently regardless (defense in depth,
not a substitute).

## 6. Synchronization design

Two React state transitions were originally attempted with (a) a ref holding
the previous `open` value compared during render — the pattern react.dev's
own docs endorse for "adjusting state when a prop changes" — and (b) plain
`useEffect`s that called `setState` synchronously. **Both attempts were
rejected by this project's ESLint configuration** (`react-hooks/refs` and
`react-hooks/set-state-in-effect`, from a stricter, React-Compiler-era
`eslint-plugin-react-hooks`), which forbids ref mutation/access during render
and synchronous `setState` inside a plain effect — stricter than react.dev's
own documented escape hatch. The final design uses only:

1. **Real event handlers.** `VersionActions.openPanel(op)` (button `onClick`)
   sets the default region the instant Repaint opens; `close()` (Cancel/Escape)
   clears it. Both are direct handler calls, never effects.
2. **React's "resetting state with a key" pattern**, not a ref/effect
   comparison: a small `RepaintRangeFields` subcomponent owns its own local
   Start/End text via lazy `useState(() => ...)` initializers, and is
   remounted via `key={repaintDragGeneration}` — a counter incremented by
   the parent (`song-details.tsx`) **only** when `AudioPlayer`'s region
   `onChange` fires from a real WaveSurfer `update`/`update-end` event
   (drag/resize), never on ordinary keystrokes. This is what lets a drag
   overwrite the text fields' buffer while normal typing is left alone,
   without an effect or a ref comparison anywhere.
3. In `AudioPlayer` itself, the one unavoidable "always-current ref for a
   stable event handler" (`regionPropRef`, so WaveSurfer's own `update`
   event handler always reads the latest `region` prop without needing it in
   a `useEffect` dependency array, which would otherwise recreate the region
   on every parent render) is written inside a plain
   `useEffect(() => { regionPropRef.current = region; })` with no
   dependency array — the standard "always latest ref" idiom, which the
   lint rule does permit because the write happens inside an effect, not
   during render.

**Numeric-field commit semantics** (`RepaintRangeFields.commit`, in
`version-actions.tsx`): typed Start/End values are pushed to the shared
`repaintRegion` **raw and unclamped** — deliberately, so a genuinely invalid
range (end before start, shorter than the minimum, past the end of the
version) survives to submit time and produces its real, specific validation
message (`validate()` in `VersionActions`), exactly as before this region
existed. Clamping is reserved for the waveform drag/resize path (the Regions
plugin's own `minLength`/`maxLength`/duration already constrain those) and
for the initial default region. An incomplete pair (either field cleared, or
mid-typing something not yet a full number) reports `null` — which hides
the waveform region and makes the fields read as blank for validation,
matching "Enter a start and an end time in seconds." exactly.

## 7. Numeric inputs: kept, not removed

The Start/End numeric fields were **not** removed. They remain visible next
to the waveform, are the fields `validate()` and submission actually read,
and are the only keyboard-operable path (§2: the installed Regions plugin
has no keyboard handling of its own). This was a design requirement, not
just a fallback bolted on afterward.

## 8. Accessibility

- Start/End retain their existing `<label>`s; both are focusable, editable,
  and sufficient on their own to select and submit a Repaint range —
  verified in the new E2E test ("stays usable from the keyboard alone")
  which never touches the waveform.
- The waveform `<div>` remains `aria-hidden="true"` (unchanged from before
  Phase 12); the visual region is a supplementary input method, not the only one.
- No keyboard behavior was added to the region itself, since the installed
  Regions plugin exposes none (§2) — adding a custom keyboard handler for
  drag/resize was out of scope for this phase and is listed under Deferred (§13).

## 9. Mobile / responsive

Verified via Playwright at 375px and 768px (`expectFitsViewport` on the
waveform + Repaint form) — no new CSS framework, reusing the existing
Tailwind layout. Touch dragging on the Regions plugin was not separately
probed beyond Playwright's pointer-event simulation (real touch-device
verification is listed under Limitations, §12); the numeric fields remain
the guaranteed-reliable path on any input device.

## 10. Tests

**Unit** (`frontend/src/lib/audio/repaint-region.test.ts`, 17 tests): passthrough,
negative clamp, NaN vs. Infinity handling, swapped/equal start-end, min/max
length enforcement, duration-boundary clamping on both ends, duration
shorter than the minimum, invalid-duration fallback, `defaultRepaintRegion`
bounds, `regionsApproximatelyEqual`.

**Component** (`version-actions.test.tsx`, `audio-player.test.tsx`, and the
mocks added to `job-tracker.test.tsx` / `version-comparison.test.tsx` /
`song-details.test.tsx` to add `registerPlugin` + a Regions plugin mock,
since every AudioPlayer instance now unconditionally registers one): pre-filled
default region on open, manual edits updating the shared region and
surviving submit, rejection with the correct message for each invalid
combination (end before start, below minimum, past the version's end,
both fields cleared), correct `repaint_start`/`repaint_end` payload.

**Full frontend suite**: 359/359 passing. **TypeScript** (`tsc --noEmit`) and
**ESLint** both clean. **Production build** (`next build`) succeeds.

**Backend regression** (unaffected — Phase 12 is frontend-only): 536/536
passing (`pytest tests -m "not smoke"`).

## 11. Mutation testing

Backed up, mutated, ran the affected test file, confirmed the mutation was
caught, restored, confirmed green again (methodology from earlier phases).

| Mutation | Result |
|---|---|
| Swap start/end in `clampRepaintRegion`'s return | Caught (13/17 tests failed) |
| Remove minimum-length enforcement branch | Caught (3/17 failed) |
| Remove maximum-length enforcement branch | Caught (2/17 failed) |
| Change `defaultRepaintRegion`'s fraction (1/4 → 1/2) | Caught (1/17 failed) |
| Swap which bound (`minLength`/`maxLength`) is clamped to duration | Caught (11/17 failed) |
| Drop the upper (duration) clamp on `start` only | **Survived** — see below |
| Swap `repaint_start`/`repaint_end` in the submitted API payload (`version-actions.tsx`) | Caught (1/22 failed) |

The one survivor (dropping `Math.min(start, duration)` while leaving the
lower `Math.max(0, ...)` clamp) is **confirmed inert, not a coverage gap**:
whenever `start > duration`, `end` is still separately clamped to
`duration`, which forces `end <= start` and triggers the existing
`e <= s` / minimum-length correction path, which always recomputes
`start = end - minLength` regardless of the mutated line. This was verified
by hand-tracing the arithmetic for the boundary case; the upper clamp on
`start` is redundant defense-in-depth with the correction logic that already
exists for a different reason, not a gap to add a test for.

## 12. Real GPU test

`backend/tests/test_version_operations_smoke.py -m smoke -k repaint` passed
against a live ACE-Step server (`models_initialized` lazily loading on first
call, as documented) — the existing Repaint contract is unaffected by a
frontend-only phase, re-verified rather than assumed.

The primary real-GPU validation for the *new* capability is the Playwright
E2E test in §13 below, which performs an actual mouse-drag gesture on the
real, live-rendered waveform, submits through the real, unmodified Repaint
API, and waits for a real ACE-Step generation.

## 13. Playwright E2E (real stack, real GPU, no mocking)

Two new tests in `frontend/e2e/create-song.spec.ts`:

1. **"Repaint: dragging the waveform region updates Start/End, and the real
   generation from that region creates a new version without touching
   Version 1"** — generates a real song, opens Repaint, reads the pre-filled
   default region, locates the actual rendered region element via its
   shadow-DOM `part~="region"` attribute (set by the Regions plugin itself —
   Playwright's CSS engine pierces open shadow roots, so no test id needed
   inside third-party plugin markup), computes a deterministic pixel target
   from the waveform's own measured width and the player's own reported
   duration (never a hardcoded pixel offset or assumed duration), performs a
   real `mouse.down` → `mouse.move` → `mouse.up` drag, and asserts the
   numeric fields actually changed and the dragged length was preserved
   (proving a move, not a resize). It then does a manual precision edit,
   confirms the region visibly shrinks on screen, captures the real
   `POST .../repaint` request body to prove the exact selected values were
   sent, waits for the real generation, and verifies the new Version's
   lineage (`Repaint · from Version 1`), that its audio is real/distinct/
   playable, and that Version 1's stored file is byte-for-byte untouched.
2. **"Repaint region selector fits mobile and tablet widths, and stays
   usable from the keyboard alone"** — responsive check at 375/768px, then a
   complete keyboard-only Repaint fill/submit-readiness path with no mouse
   interaction on the waveform at all.

**Full E2E regression** (all 18 specs in `create-song.spec.ts`, real ACE-Step,
real GPU, throwaway DB/storage on a separate backend port per the project's
own E2E convention): **18/18 passed** on a clean rerun. One test
("Extend, Remix and Repaint...", pre-existing, unrelated to this phase)
timed out on its first run in the full-suite pass (GPU contention after many
consecutive back-to-back real generations) and passed cleanly when rerun in
isolation — a real-GPU timing flake under load, not a Phase 12 regression;
recorded here per the project's "classify results honestly" testing
convention rather than silently omitted.

## 14. Performance and cleanup

No polling, no new worker/library. The Regions plugin is registered once per
`AudioPlayer` mount (keyed on `[src, safe, attempt]`, unchanged from before);
the region itself is added/removed by a separate effect keyed only on
`[phase, hasRegion]` (primitives, not the `region` object's identity), and
repositioned via `setOptions()` on the existing region object (never
recreated) when the caller's own start/end change — so ordinary typing and
drag updates never recreate WaveSurfer or the Regions plugin. Full cleanup
(`created.remove()`, both `update`/`update-end` unsubscribe functions,
`regionRef`/`regionsPluginRef` reset to `null`) runs on unmount, `src`
change, and whenever the region prop disappears.

## 15. Security

Backend validation remains authoritative and unchanged (`operations.py`'s
`REPAINT_MIN_SECONDS`/`REPAINT_MAX_SECONDS`, plus the existing duration and
start/end checks) — the frontend clamp/validate logic in §5–6 is a UX
convenience, never trusted as the only gate. NaN/Infinity/negative/swapped
values are exercised directly in the unit tests (§10); extremely large
values are handled the same way Infinity is (clamped to the duration
boundary in the drag/default path, or passed through raw to the backend's
own rejection in the manual-entry path, exactly as a manually typed
out-of-range value already was before this phase).

## 16. Limitations / deferred

- Real physical touch-device dragging (as opposed to Playwright's simulated
  pointer events) was not separately verified on hardware; the numeric
  fields are the always-reliable fallback on any device.
- The Regions plugin has no keyboard interaction of its own (§2, §8); a
  custom keyboard handler for dragging/resizing the visual region (e.g.
  arrow keys while the region is focused) was out of scope for this phase.
- No audio trim/fade/multi-region/waveform-editing capability was added or
  implied by this phase, per the master prompt's explicit hard scope.

## 17. What was NOT changed

No new API endpoint or contract change (still `repaint_start`/`repaint_end`
seconds through the existing route). No database migration (`PRAGMA
user_version` unchanged). No change to `Version`, `JobService`,
`AudioStorage`, or any ACE-Step file. No new npm dependency.
