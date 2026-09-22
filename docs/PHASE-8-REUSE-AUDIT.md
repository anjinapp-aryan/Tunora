# Phase 8 — AI Song Director Refinement: Reuse Audit

Per the Tunora reuse law, ACE-Step 1.5's `/format_input` was investigated FIRST — by
reading its source and probing the real running server — before considering any external
project. That investigation was decisive; see §3 below.

## 1. ACE-Step 1.5 `/format_input` source investigation

| File | What it shows |
|---|---|
| `acestep/api/http/sample_format_routes.py::format_input_endpoint` | Reads `prompt` (caption), `lyrics`, `temperature`, `param_obj` (a dict or JSON string of `duration`/`bpm`/`key`/`key_scale`/`time_signature`/`language`). Calls `format_sample_from_input(...)`. Returns `caption, lyrics, bpm, key_scale, time_signature, duration, vocal_language`. |
| `acestep/llm_inference.py::LLMHandler.format_sample_from_input` (docstring) | *"Formats user-provided caption and lyrics into structured music metadata... This is the 'Format' feature."* It reformats/expands the caption and lyrics **it is given** — there is no separate "instruction" or "change request" parameter anywhere in its signature. |
| Same method, body | Builds `constrained_metadata` from `user_metadata` (bpm/duration/keyscale/timesignature/language) and passes it into `generate_from_formatted_prompt(... "user_metadata": constrained_metadata ...)`, which uses **constrained (FSM) decoding** — the same mechanism Phase 7 already relies on for `duration`/`language`. There is **no** `instrumental`/vocal-state parameter anywhere in this endpoint. |

**Conclusion from source alone**: ACE-Step has no built-in "take a plan and a free-text
change request, apply the change, keep everything else" operation. `/format_input` only
reformats whatever caption/lyrics it receives, with metadata **preservation** available via
`param_obj`, but no field for describing *what to change*.

## 2. Real probes against the running local server

Three refinement probes were run against the real, already-loaded `acestep-5Hz-lm-1.7B`
model (base caption/lyrics for a pop ballad, no mocking):

**Probe 1 — "Make the chorus more powerful and anthemic."**, sent as
`"<existing caption> Additional direction: Make the chorus more powerful and anthemic."`:
the returned caption explicitly described *"swells into a powerful chorus where layered
vocals soar... climactic final choruses"* — the instruction was genuinely incorporated.
`duration` came back exactly `60.0` (as constrained), `vocal_language` exactly `"en"`.

**Probe 2 — same instruction placed as a prefix instead** (`"Refine this song: ... <caption>"`):
produced an unrelated arrangement (drums/tom-toms) with no trace of the requested change —
**word order/placement matters**; appending after the caption worked, prefixing did not.

**Probe 3 — "Add acoustic guitar and softer percussion."`** (appended): the caption
correctly gained *"a warm acoustic guitar enters... a light, steady drum pattern"* — but
the response's lyrics silently collapsed to `"[Instrumental]"` even though the source had
real lyrics and nothing asked for that. **This is a real, reproducible provider
limitation**, not a one-off artifact: it also occurred once in the later real-GPU smoke
test (§13 of the main doc) — the run was correctly rejected there rather than silently
accepted.

**Conclusion**: appending the instruction to the existing caption as
`"<caption> Additional direction: <instruction>"` is a working, adopted technique — this
is prompt construction at the adapter layer using ACE-Step's own model, not a second LLM.

## 3. Reuse matrix

| Capability | Existing Project | License | Fit | Decision |
|---|---|---|---|---|
| Plan refinement (apply a change to an existing plan) | ACE-Step 1.5's `/format_input` (+ Tunora's own prompt composition: appending the instruction to the caption) | MIT code / Apache-2.0 weights, already vendored | ~85% (verified: incorporates the instruction; no native "instruction" field, no instrumental control) | **ADAPT** (reuse the endpoint, compose the input) |
| Prompt rewriting | Same | Same | 100% for the caption side | **ADOPT** |
| Lyrics refinement | Same | Same | ~80% (reformats real lyrics; occasionally collapses them to "[Instrumental]" unprompted — a documented provider limitation, guarded against, not solved) | **ADOPT + VALIDATE** (reject the degenerate case rather than accept it) |
| Structured output | Pydantic (`SongSpecPayload`), reusing the exact same `SongSpec` dataclass and `app/director/validation.py` functions Phase 7 already built | Already a dependency | 100% | **REUSE Tunora's own Phase 7 code**, not a new library |
| Validation | `app/director/validation.py` (Phase 7) | n/a | 100% | **REUSE verbatim** — every `validate_*` function Phase 7 wrote for AI *output* is reused unchanged for refinement's output too |
| UI refinement | Existing `SongDirectorPanel`/Create Song form (Phase 7) | n/a | ~90% | **REUSE the form; BUILD one small panel** (`SongRefinePanel`, ~90 lines) that feeds it, mirroring `SongDirectorPanel`'s own shape |
| A second LLM / local runtime for refinement | Ollama, llama.cpp, an external API | — | 0% needed | **REJECT** — ACE-Step's own LM, already loaded, already does the job |
| Agent/orchestration framework for "refine, then maybe refine again" | LangChain, LangGraph | — | 0% needed | **REJECT** — one call, one response; no multi-step planning or tool use exists in this requirement |

## 4. Adoption decision

**ADAPT ACE-Step's `/format_input`.** No second LLM, no external API, no new dependency.
The gap between what `/format_input` natively offers (reformat what it's given, preserve
metadata via constraints) and what Phase 8 needs (apply a *described change*) is closed
entirely by how the adapter **constructs its request** — not by any new model or framework.
The genuinely missing pieces, all small and all Tunora's own:
- Appending the instruction to the existing prompt in the one format verified to work.
- Enforcing `title`/`language`/`duration`/`instrumental` unchanged afterward, since
  `/format_input` has no field for any of them except `duration`/`language` (which it
  already respects via constraints) — mirrors exactly how Phase 7 already had to enforce
  `duration`/`title` post-hoc for `/v1/create_sample`.
- Detecting and rejecting the observed "lyrics silently became [Instrumental]" failure
  mode as invalid output, rather than passing it through.

No new dependency was added, front or back end.
