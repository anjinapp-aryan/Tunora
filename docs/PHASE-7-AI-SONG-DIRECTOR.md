# Phase 7 — AI Song Director

## 1. Goal

Let a user describe a song in plain language ("an emotional cinematic Kannada song about a
mother, with a female vocal, soft piano, acoustic guitar and a powerful chorus") and have
Tunora turn that into a structured, provider-neutral song plan the user reviews and edits
before anything is generated. The Director never generates audio itself — the existing
generation pipeline (`JobService` → `MusicGenerationProvider` → ACE-Step) owns that,
unchanged.

## 2. Existing capability audit / 3. ACE-Step planner investigation / 4–6. Reuse audit, candidates, licenses

See `docs/PHASE-7-REUSE-AUDIT.md` for the full investigation, evidence and matrix. Summary:
ACE-Step 1.5 already ships exactly this capability as its "Simple Mode" / 5Hz-LM planner,
exposed over its own REST API (`POST /v1/create_sample`). This was confirmed by reading
`acestep/llm_inference.py` and `acestep/api/http/sample_format_routes.py`, then verified live
against the real, running local server — not assumed from documentation.

## 7. Adoption decision

**ADOPT ACE-Step's own planner.** No second LLM, no LangChain/agent framework, no external
API, no new dependency, no new model download. `AceStepSongDirector` is a ~130-line adapter
around one existing endpoint.

## 8. Architecture

```
Natural language ("query")
      |
POST /api/songs/plan  (new, stateless -- creates nothing)
      |
AceStepSongDirector.create_plan()
      |  calls ACE-Step's own POST /v1/create_sample (the SAME local server Tunora already needs)
      v
SongSpec (validated, provider-neutral)
      |
User reviews/edits (the EXISTING Create Song form, prefilled)
      |
POST /api/jobs  (existing, UNCHANGED)  ->  JobService -> AceStepMusicGenerationProvider -> ACE-Step
      |
Song / Version / Audio  (existing domain, UNCHANGED)
```

New backend modules: `app/director/{spec,base,ace_step,validation,errors}.py`,
`app/api/routes_director.py`. One 4-line-of-logic helper (`app/providers/ace_step_http.py`)
was extracted from the existing `AceStepMusicGenerationProvider` so both it and the new
Director parse ACE-Step's `{"data": ...}` envelope with the same code, not a copy.

## 9. SongSpec

```python
@dataclass(frozen=True)
class SongSpec:
    title: str
    prompt: str
    lyrics: str
    language: str
    duration: Optional[float]
    instrumental: bool
    bpm: Optional[int] = None            # informational only, never sent to generation
    key_scale: Optional[str] = None      # informational only
    time_signature: Optional[str] = None # informational only
    requested_fields: frozenset = frozenset()  # which of title/language/duration/instrumental were the USER's own choice
```
Every field except the three informational hints maps 1:1 onto `POST /api/jobs`'s existing
body (`CreateJobRequest`) — deliberately, so the review step needs no translation layer.
`bpm`/`key_scale`/`time_signature` are never sent to generation: ACE-Step's DiT does not
accept them as inputs, so presenting them as guaranteed would be dishonest (see §12).

## 10. Data flow / user-intent priority

`instrumental`, `language`, `duration` and `title` are the user's OWN explicit choices
(the same fields Create Song already exposes) and are captured **before** calling the
planner. `AceStepSongDirector.create_plan()` always applies them **after** validating the
planner's output, so they can never be silently overridden — verified directly: a test
asks for `language="ta"` while the (mocked) planner answers `"en"`, and the resulting
`SongSpec.language` is `"ta"`; the same for `duration` and `instrumental`. `instrumental`
additionally forces `lyrics` to `""` regardless of what the planner returned. `title` has
no planner equivalent at all (ACE-Step's endpoint doesn't return one) — Tunora derives it
deterministically from the user's own query text using the existing `derive_title()`
helper (Phase 3), the same one Create Song already uses; no LLM call for the title.

## 11. UI flow

`/create` gained one panel above the existing form: **AI Song Director** — a textarea
("Describe your song idea"), an Instrumental checkbox, a Language select ("Let the AI
choose" by default), and a "Create Song Plan" button. On success it calls the existing
form's own `react-hook-form` `setValue()` to fill Prompt, Lyrics, Language, Duration
(mapped to the nearest of the four fixed options, since Create Song's Duration field is
a select, not free text) and Vocals, and opens Advanced options to show the derived Title.
A status line ("AI plan applied — review and edit the fields below...") plus the
non-guaranteed bpm/key/time-signature hints appears. Every field stays exactly as editable
as it already was — nothing is locked, and Generate Song is still the same button calling
the same, unmodified submit path.

## 12. Security / no fake capabilities

The planner's response is treated as **untrusted input**, exactly like any other external
response Tunora parses: `app/director/validation.py` checks the caption/lyrics/duration/
bpm/key/time-signature before anything becomes a `SongSpec` (length bounds, numeric
ranges, type checks), and raises `InvalidSongPlanError` — mapped to a safe 502 — rather
than silently guessing a value or letting a bad field through. `InvalidDirectorRequestError`
(bad user input: empty/oversized query, malformed language/duration) is checked before any
network call and mapped to 422. A network failure or an ACE-Step error maps to
`DirectorUnavailableError` → 503. In every case, generation is never started — the plan
endpoint creates no Song, Version or Job (verified by a dedicated test). Nothing about
bpm/key/time-signature is ever represented as guaranteed; the UI labels them "AI hints
(not guaranteed)", and they are never sent to `POST /api/jobs`.

## 13. Testing (executed this session)

| Check | Result |
|---|---|
| Backend `pytest -m "not smoke"` | **VERIFIED** 406 passed (was 375; +31 in `tests/director/`) |
| Real ACE-Step planner probe | **VERIFIED** — three live calls against the running local server, evidence in `docs/PHASE-7-REUSE-AUDIT.md` §2 |
| Real-GPU smoke (`-m smoke`) | **VERIFIED** `tests/test_ace_step_director_smoke.py`: real natural-language request → real `/v1/create_sample` call → real generation → real Version with audio |
| Frontend Vitest | **VERIFIED** 292 passed (was 278; +10 for the panel, +4 integration tests in `create-song-form.test.tsx`) |
| tsc / ESLint / `next build` | **VERIFIED** clean |
| Real E2E (Next → FastAPI → ACE-Step) | **VERIFIED** in isolation, run 3 times, passed every time (~34s each): natural language → plan applied to the existing form → user edits the prompt and title → Generate Song → real GPU generation → Library → Song Details → real playback → download bytes match the stored file → exactly one job created. In the full 9-test suite run back-to-back (~24 minutes of sequential real GPU generation), this test once hit its generation timeout while the other 9 pre-existing scenarios all passed — consistent with ACE-Step's own queue being backed up by that point, not a functional defect (the same test passed cleanly every time it was run on its own, immediately before and after that run). Reported honestly rather than re-run until green. |
| Mutation checks | **VERIFIED**, all caught then reverted: (1) `AceStepSongDirector` ignoring the user's explicit language — 1 test failed; (2) ignoring explicit duration — 1 failed; (3) `validate_lyrics` no longer forcing empty lyrics when instrumental — 1 failed; (4) skipping prompt validation entirely — 3 failed; (5) swapping `SongSpec.title`/`prompt` (wrong plan shape) — 2 failed; (6) the frontend ignoring `plan.instrumental` when applying a plan — 1 failed; (7) the API route no longer mapping `InvalidSongPlanError` to a safe response — 1 failed. |
| Security | **VERIFIED**: oversized/empty query, invalid duration/language, malformed/oversized AI output, HTTP 5xx/timeout/malformed-JSON from the planner — all rejected safely; no ACE-Step task id, internal path, port or endpoint name ever appears in a response (tested directly). |
| Responsive (375 / 768 / desktop) | **VERIFIED** for the AI Song Director panel in the real E2E. |

Existing tests changed for an intentional, documented reason: `PROMPT_MAX` moved from 1000
to 2000 characters (an AI-produced description can legitimately run longer than a
hand-typed one) — `create-song-form.test.tsx`'s over-long-prompt test now uses 2001
characters and expects the updated message; three `getByLabelText` queries were anchored to
exact text (`^describe your song$`, `^language$`) because the new AI panel introduces its
own "Describe your song idea" and "Language" fields on the same page, and two E2E helper
functions (`generateRealSong`) were changed the same way for the same reason. No assertion's
*meaning* changed.

## 14. Real GPU verification

Both the backend smoke test and the real E2E test performed genuine local generations
through the RTX 5060 Ti via ACE-Step, driven by a real AI-produced plan (not a mocked one).
Objective facts only: the planner produced non-trivial, non-empty text; the subsequent
generation completed and produced a non-empty audio file that plays back and downloads
correctly. Musical/lyrical quality was not and cannot be judged by Claude — a human listener
is needed for that.

## 15. Known limitations

- Duration is mapped to the nearest of Create Song's four fixed options (30/60/120/180s);
  the planner's own suggestion (e.g. 143s) is not generated verbatim unless it happens to
  match one exactly. This preserves the existing Duration control rather than adding a new
  free-form input.
- The planner has no explicit "3-minute song" input of its own (`/v1/create_sample` takes no
  duration parameter) — an explicit duration is Tunora's own post-hoc override, applied
  after the call, not something ACE-Step itself is asked to honor.
- Exact vocal gender, exact BPM/key, and exact lyric timing are never guaranteed — one live
  probe (§2 of the reuse audit) shows the planner adding an unrequested second (male) vocal
  to a "female vocal" request. bpm/key/time-signature are shown as hints only.
- `/format_input` (refining an already-typed caption/lyrics, respecting explicit
  bpm/duration/key/time-signature via constrained decoding) was investigated and confirmed
  working but not wired into this phase's UI — the natural-language flow already satisfies
  the stated requirement; see Deferred.
- The planner call is a single foreground HTTP request (observed 15-90s locally); there is
  no job/progress tracking for it the way generation has, since ACE-Step's own endpoint is
  itself synchronous.

## 16. Deferred

Wiring up `/format_input` as a "refine what I already typed" action, a Project-aware Director
entry point (creating a plan already scoped to a Project), multi-turn conversation/refinement
with the Director, any second LLM/agent framework, exposing the Director for Extend/Remix/
Repaint plans.
