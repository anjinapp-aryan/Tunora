# Tunora — Phase 3, Step 14: Create Song UI

## 1. UI Reuse Audit

Scope: reusable primitives and patterns only. No existing ACE-Step application (fspecii/ace-step-ui, Sion971/ace-step-studio, timoncool/ACE-Step-Studio) was adopted or copied, consistent with [PHASE-3-UI-REUSE-DECISION.md](./PHASE-3-UI-REUSE-DECISION.md). Licenses below were read from each installed package's own `package.json` (`license` field) on 2026-09-19, not recalled.

| Candidate | License (verified) | Relevant piece | Cost / fit | Decision |
|---|---|---|---|---|
| **shadcn/ui** (`shadcn` CLI, registry) | MIT | Copy-in `Field`, `Input`, `Textarea`, `Label`, `Switch`, `NativeSelect`, `Button`, `Alert` | Native to Next.js + TS + Tailwind; components are owned in-repo, no runtime lock-in | **REUSE** |
| **@base-ui/react** 1.8.0 | MIT | Headless primitives (Button, Switch) underneath the current shadcn "base-nova" style | Pulled in automatically by the shadcn CLI's default style; accessible | **REUSE** (transitive, not chosen separately) |
| **Radix UI** | MIT (not installed) | Same role as Base UI in older shadcn styles | Not needed: the shadcn CLI default in this project resolved to Base UI | **REFERENCE** (equivalent alternative, unused) |
| **react-hook-form** 7.88.0 | MIT | Form state, submit lifecycle (`isSubmitting`) | Mature, small, works with uncontrolled inputs; no existing form code in the project to conflict with | **REUSE** |
| **zod** 4.6.5 | MIT | Schema validation + inferred TS types | Single source for form rules and types | **REUSE** |
| **@hookform/resolvers** 5.9.1 | MIT | RHF ↔ zod bridge | Standard glue, no alternative needed | **REUSE** |
| **lucide-react** 1.47.0 | ISC | Icons (button, spinner) | Default shadcn icon set | **REUSE** |
| **class-variance-authority** 0.7.1 / **cn** 0.3.0 | Apache-2.0 / MIT | Class merging/variants used by shadcn components (`cn` is the official `shadcn-ui/cn` package, verified from its `package.json` repository field) | Transitive requirement of shadcn output | **REUSE** (transitive) |
| **Base UI `Select`** (shadcn `select`) | MIT | Custom select | Generated but **not used**: a native `<select>` is more robust on mobile, needs no portal/focus machinery, and is trivially testable | **REJECT** for this form |
| **Formik / other form libs** | not evaluated in depth | — | No reason to add a second form library once RHF fit | **REJECT** (not audited further; RHF already satisfies every requirement) |
| **Existing ACE-Step UIs** (fspecii, Sion971, timoncool) | see Phase 3 audit | Form layout and field-set conventions | Licenses/stack blockers already documented | **REFERENCE** (UX ideas only; no code copied) |
| **Vitest** 5.0.1, **@testing-library/react** 16.3.3, **user-event** 14.6.7, **jsdom** 29.1.1 | MIT | Unit/component tests | Standard, Vite-based, no Next.js-specific runner needed | **REUSE** |
| **Playwright** 1.63.0 | Apache-2.0 | E2E | Not previously present in the repo; audited and chosen as the minimum appropriate real-browser tool (it can also verify layout overflow, which jsdom cannot) | **REUSE** |

Build-only code written for Tunora: the Create Song page composition, the schema (field list, limits), the typed API client, and the job-started page. Nothing else here reimplements an existing library.

## 2. Frontend Inspection

No frontend existed (`I:\Tunora` contained only `ACE-Step-1.5/`, `backend/`, `docs/`), so the minimum correct structure was created with `create-next-app`, not layered on top of prior work. Nothing was overwritten.

- Next.js **16.3.5**, React 19.2.8, **App Router**, `src/` layout, Tailwind CSS **v4**, TypeScript strict, `@/*` alias.
- Next 16 ships its own docs at `node_modules/next/dist/docs/` (the generated `AGENTS.md` says its APIs differ from older versions); `rewrites` and typed route props (`PageProps<'/jobs/[jobId]'>`, requires `next typegen`) were checked/used per that guidance.
- shadcn initialised with defaults (`base-nova`, neutral, CSS variables, lucide).
- Two shadcn-generated issues were fixed: `--font-sans` in `globals.css` was self-referential (`var(--font-sans)`), which silently fell back to a serif font — repointed to `var(--font-geist-sans)`; found by looking at a real screenshot, not by tests.
- Frontend/backend layout: `frontend/` (Next.js), `backend/` (FastAPI). The browser only talks to Next.js; `next.config.ts` rewrites `/api/*` to `TUNORA_API_URL` (default `http://127.0.0.1:8000`), so no CORS change was needed on the backend and the backend origin stays out of client code.

## 3. Page Architecture

```
/                    → redirect to /create
/create              → CreateSongPage (server) → CreateSongForm (client)
/jobs/[jobId]        → JobPage (server): "Generation started" + job id + link back
src/lib/api/jobs.ts            typed Tunora API client (createJob, ApiError)
src/lib/create-song-schema.ts  zod schema, option lists, limits
src/components/create-song/    form + tests
src/components/ui/             shadcn primitives (owned in-repo)
```

Layout is a dark, single-column studio surface (header wordmark "TUNORA · AI Music Studio", constrained to `max-w-3xl`), not an admin dashboard. No animation beyond the button spinner. No new design system was introduced. `/jobs/[jobId]` deliberately does not fetch or poll — status tracking is Step 15.

## 4. Form Fields

Derived from the real code, not the sketch: `backend/app/api/schemas.py::CreateJobRequest` and `backend/app/providers/base.py::GenerationRequest` support `prompt, lyrics, language, duration, seed, instrumental, batch_size`.

| Field | UI | Sent as |
|---|---|---|
| Describe your song | textarea, required, counter | `prompt` |
| Lyrics (optional) | textarea; disabled when Instrumental is on | `lyrics` (`""` when instrumental) |
| Language | native select (11 codes) | `language` |
| Duration | native select (30 s, 1, 2, 3 min) | `duration` (number, seconds) |
| Instrumental | switch | `instrumental` |
| Seed (optional) | numeric text | `seed` (int or `null`) |

**`batch_size` is intentionally not exposed.** The backend accepts it, but `JobService` persists and exposes only the first generated file, so a batch UI would promise outputs nothing downstream can show (Library/Versions are later steps). Covered by a test.

## 5. API Contract

`POST /api/jobs` with `CreateJobRequest`: `{ prompt: string, lyrics: string, language: string, duration: number|null, seed: number|null, instrumental: boolean, batch_size?: number|null }`. Response: `JobResponse` `{ id, provider, status, created_at, submitted_at, started_at, completed_at, error, result }`. Typed on the frontend in `src/lib/api/jobs.ts`; contents were read from `backend/app/api/schemas.py` and `routes_jobs.py`, not guessed.

Important backend behavior the UI accounts for: provider submission failures come back as **HTTP 200 with `status: "FAILED"`** (by Step 12 design), so the form treats `FAILED` as a submission failure instead of navigating. The frontend never references ACE-Step, `/release_task`, `/query_result` or `/v1/audio`; no ACE-Step types exist in TypeScript. No OpenAPI codegen was introduced.

## 6. Validation

zod (client convenience only; backend remains authoritative): prompt trimmed, required, ≤ 1000 chars; lyrics ≤ 5000 chars; language and duration must be one of the offered values; seed empty or 1–9 digits. The 1000/5000 limits are frontend choices — the backend currently has no limits, so these are conservative UI guards, not mirrored business rules. Impossible combination handled: Instrumental disables lyrics and sends empty lyrics.

## 7. Error Handling

`createJob` maps every failure to a user-safe `ApiError` (`validation` for 400/422, `server` for other statuses or unreadable bodies, `network` for fetch failure); server response bodies and exception text are only ever `console.error`-logged as status codes, never displayed. Messages: "Some details look invalid…", "Unable to start the song generation. Please try again.", "Can't reach the Tunora service…". Tests inject bodies containing a traceback, `/query_result`, a Windows path and an exception name, and assert none appear in the rendered alert.

## 8. Accessibility

Real `<label htmlFor>` for every control; the switch has `aria-labelledby`; helper text linked with `aria-describedby`; `aria-invalid` on invalid fields; errors render with `role="alert"`; native selects; form has an accessible name; semantic `<form>`/`<main>`/`<header>`; visible focus rings from the shadcn primitives; loading button uses `aria-busy` and is disabled. Verified through Testing Library role/label queries. Not verified: screen-reader behavior in a real assistive technology, and automated axe scanning (not run).

## 9. Responsive Behavior

Single column; language/duration and instrumental/seed pairs collapse from two columns to one below the `sm` breakpoint. Verified visually (desktop 1280 and 375 px screenshots reviewed) and by a Playwright assertion of no horizontal overflow at 375 px. jsdom does no layout, so the vitest "mobile" test only proves the form remains functional with a narrow `innerWidth`, not that it looks right; the Playwright check is the real one. Tablet width was not separately tested (layout is the same single column between the breakpoints).

## 10. Tests

**Frontend: 19/19 vitest tests pass** (`npm test`): page fields and labels; batch size not exposed; required prompt; non-numeric seed rejected; over-long prompt rejected; instrumental disables lyrics; exact request body sent to `/api/jobs` (language/duration/seed/lyrics mapped) and navigation to `/jobs/<id>`; instrumental payload (empty lyrics, `null` seed); loading state and duplicate-submission prevention (`dblClick` produces exactly one `fetch`); HTTP 400/422/500 safe messages; network failure; 200-with-`FAILED`; mobile-width functional check; plus 4 API-client tests. `tsc --noEmit`, `eslint` and `next build` all clean. All use a mocked `fetch`; no GPU.

Duplicate-submission note: the guard relies on react-hook-form's `isSubmitting` disabling the button. An earlier `useRef` guard was removed because the React Compiler lint rule rejects passing a ref-reading handler to `handleSubmit`; the double-click test confirms one request either way. This is not an idempotency mechanism — two separate deliberate submissions still create two jobs.

## 11. E2E Result

`npm run test:e2e` (Playwright, Chromium) against the **real stack**: Next.js dev server → FastAPI (port 8000, temp DB/storage) → real ACE-Step. **2/2 passed.** Test 1: open Create Song, enter a prompt, toggle Instrumental, click Generate Song, receive `200` from `POST /api/jobs` with a `tunora-…` id, land on `/jobs/<id>`, see "Generation started" and the same id, and confirm `GET /api/jobs/<id>` is not `FAILED`. Test 2: no horizontal overflow at 375 px. The test does not wait for audio; the job it started did complete in the background (`COMPLETED` observed afterwards), which is incidental, not asserted.

Finding during E2E: the first run timed out because Next 16's dev server blocks cross-origin dev resources, so the page loaded via `127.0.0.1` never hydrated and the click did nothing. Fixed with `allowedDevOrigins: ["127.0.0.1"]` in `next.config.ts` (dev-only).

To reproduce, start ACE-Step (`uv run acestep-api` in `ACE-Step-1.5`), the backend (`uv run uvicorn app.main:app --port 8000` in `backend`), then `npm run test:e2e` in `frontend` (it starts Next.js itself).

## 12. Backend Regression

`uv run pytest tests -m "not smoke"` → 95 passed (unchanged from Step 13). No backend file or test was modified in this step. The real-GPU smoke tests were not re-run separately; the E2E above exercised the same real path once.

## 13. Known Limitations

- No live progress or status polling: the job page shows only the id and a static "started" message. Step 15.
- No cancel, no way to return to a job from the UI later (no Library); the job id on screen is the only handle.
- Client limits (1000/5000 chars, duration list, language list) are UI choices; the backend does not enforce them, and the language codes beyond `en`/`kn` were not individually verified against ACE-Step in this step.
- The rendered hard-coded error text for `FAILED` on submission is generic by design; the reason stays in `Job.error` (backend) and is not surfaced.
- Duplicate protection is per form instance only.
- Accessibility verified with Testing Library and code review only (no axe run, no screen reader).
- Tablet width not separately checked; dark theme only.
- Dev-only `allowedDevOrigins` and the `TUNORA_API_URL` env var need real deployment config later.
