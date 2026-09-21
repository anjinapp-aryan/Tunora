# Phase 7 — AI Song Director: Reuse Audit

Per the Tunora reuse law, ACE-Step 1.5 (already a hard dependency, already running locally,
already the reason Tunora needs a GPU) was investigated FIRST, before any external search,
by reading its source and probing the real running server. That investigation answered the
requirement completely — see §"Adoption decision" below.

## 1. ACE-Step 1.5 source investigation (evidence, not README wording)

| File | What it shows |
|---|---|
| `acestep/llm_inference.py` (`LLMHandler`, 4253 lines) | A "5Hz LM" planner already loaded alongside the DiT model. `create_sample_from_query()` (docstring: *"This is the 'Simple Mode' / 'Inspiration Mode' feature"*) turns one natural-language `query` into caption + lyrics + metadata. `format_sample_from_input()` does the same starting from a caption/lyrics the user already typed, honoring a `user_metadata` dict via **constrained decoding** (an FSM that forces the LM's output to match given values, not just hint at them). |
| `acestep/api/http/sample_format_routes.py` | Three HTTP routes exposing this: `POST /v1/create_sample` (docstring: *"the API equivalent of the Gradio UI's Simple Mode 'Create Sample' button"*), `POST /format_input`, `POST /create_random_sample`. All local, all use the already-downloaded LM model, no external call. |
| `acestep/constants.py` | `DEFAULT_LM_INSPIRED_INSTRUCTION = "Expand the user's input into a more detailed and specific musical description:"` — the LM's own designed purpose is exactly "natural language → detailed song description", i.e. an AI Song Director. |
| `docs/en/API.md` §4–7 | Documents `/v1/create_sample`'s request (`query`, `instrumental`, `vocal_language`, `temperature`) and response (`caption`, `lyrics`, `bpm`, `keyscale`, `duration`, `timesignature`, `vocal_language`) fields. |

## 2. Live probes against the real, running ACE-Step server (not inference from docs)

All three run locally on the RTX 5060 Ti, zero external network calls, using the already-loaded `acestep-5Hz-lm-1.7B` model.

**`POST /v1/create_sample`**, `query="an emotional cinematic Kannada song about a mother, with a female vocal, soft piano, acoustic guitar and a powerful chorus", vocal_language="kn"`:
```json
{"caption": "An emotional and cinematic ballad...", "lyrics": "[Intro: Female Vocal & Piano]\n...", "bpm": 167, "keyscale": "D minor", "duration": 143.0, "timesignature": "6", "vocal_language": "kn"}
```
Real, non-trivial, Kannada-script lyrics were produced; `vocal_language` came back exactly `"kn"` as requested.

**`POST /v1/create_sample`, `instrumental=true`**: `lyrics` came back as the literal `"[Instrumental]"` and `vocal_language: "unknown"` — the explicit flag was honored, no lyrics were invented.

**`POST /format_input`, `param_obj={"duration": 45, "language": "en"}`**: response `duration: 45.0`, `vocal_language: "en"` — **exactly** the values given, not an AI approximation of them. This is the constrained-decoding behavior the docstring promises, confirmed live.

## 3. Reuse matrix

| Capability | Existing Project | URL | License | Local/Offline | GPU | % Covered | Decision | Why |
|---|---|---|---|---|---|---|---|---|
| Planner (NL → structured song blueprint) | ACE-Step 1.5's 5Hz LM (`acestep-5Hz-lm-1.7B`/`0.6B`) | already vendored at `ACE-Step-1.5/` (upstream: github.com/ace-step/ACE-Step) | MIT code, Apache-2.0 weights (per Tunora's existing `docs/MODEL-CANDIDATES.md`) | Yes | Yes (already required) | 100% | **ADOPT** | Already running, already GPU-provisioned, already license-cleared; confirmed live to do exactly this job. |
| Natural language parsing | same (`/v1/create_sample`) | same | same | Yes | Yes | 100% | **ADOPT** | Same endpoint. |
| Structured output | ACE-Step's constrained (FSM) decoding, normalized into Tunora's `SongSpec` (a plain `dataclass`, same pattern as `GenerationRequest`) | n/a (internal) | n/a | Yes | Yes | ~90% | **ADOPT** ACE-Step's decoding + **BUILD** the thin `SongSpec` dataclass/validation (no existing OSS project defines Tunora's own provider-neutral shape) | Pydantic (already a project dependency) validates the API boundary; the domain dataclass mirrors the existing `GenerationRequest` convention. No schema-validation library (e.g. `instructor`, `outlines`) was needed since ACE-Step's own FSM already constrains the model. |
| Lyrics generation | ACE-Step 5Hz LM | same | same | Yes | Yes | 100% | **ADOPT** | Same endpoint; lyrics are part of the same response. |
| Music metadata (bpm/key/time signature) | ACE-Step 5Hz LM | same | same | Yes | Yes | 100% (as informational hints; see §"No fake capabilities" in the main doc) | **ADOPT**, exposed as non-guaranteed hints | ACE-Step itself doesn't accept these as DiT generation inputs, so Tunora doesn't pretend they are guaranteed either. |
| Prompt rewriting | ACE-Step 5Hz LM (`format_sample_from_input`) | same | same | Yes | Yes | 100% (not wired up this phase) | **REFERENCE** | The natural-language flow (`/v1/create_sample`) already satisfies the Phase 7 requirement end to end; `/format_input` (refine an already-typed prompt) is a natural Phase 8+ addition, not required now (see Deferred). |
| Local LLM runtime | vLLM / llama.cpp / Ollama, already inside ACE-Step's own stack (`acestep/llm_backend_compat.py` supports `vllm`/`pt`/`mlx` backends) | n/a | n/a | Yes | Yes | 100% | **REJECT introducing a second one** | ACE-Step already manages its own LM runtime; a second local-LLM stack (Ollama, llama.cpp) would duplicate a GPU-resident model Tunora already loads, doubling VRAM use for no gain. |
| Song/plan review UI | Tunora's own existing Create Song form (`components/create-song/create-song-form.tsx`) | n/a (Tunora) | n/a | n/a | n/a | ~90% | **ADOPT/REUSE Tunora's own component** | The exact fields a SongSpec carries (prompt, lyrics, language, duration, instrumental, title) are already editable, validated fields on that form; only a small panel that fills them was needed (`BUILD`, ~150 lines). |
| Request/response validation | Pydantic (already a Tunora dependency, used by every other endpoint in `app/api/schemas.py`) | n/a | BSD-licensed, already installed | n/a | n/a | 100% at the API boundary | **ADOPT** | No new library. |
| Agent/orchestration framework | LangChain, LangGraph, AutoGPT-style agents | — | — | — | — | 0% needed | **REJECT** | The requirement is one call, one response, no tools, no multi-step reasoning, no autonomy — an agent framework would be pure unjustified complexity (see the "No agent framework" rule below). |

## 4. Adoption decision

**Option A (ACE-Step already sufficient) — ADOPTED.** No second LLM, no external API, no new model download, no new GPU allocation. The only code written was:
- `app/director/spec.py` — the `SongSpec` dataclass (provider-neutral, mirrors `GenerationRequest`'s own pattern).
- `app/director/validation.py` — bounds-checking the LM's output as untrusted input (same spirit as every other Tunora input boundary).
- `app/director/ace_step.py` — a ~130-line adapter calling ACE-Step's own `/v1/create_sample` and normalizing the result; reuses `app/providers/ace_step_http.py` (a 4-line-of-logic envelope parser extracted from the existing `AceStepMusicGenerationProvider`, so the same parsing code is not duplicated).
- One new API route (`POST /api/songs/plan`) and one new UI panel (`SongDirectorPanel`, ~140 lines) that feeds the existing Create Song form.

Nothing about the existing generation pipeline (`JobService`, `MusicGenerationProvider`, `AceStepMusicGenerationProvider`, the Song/Version domain) was changed to make this work — the Director's output is literally the same field set `POST /api/jobs` already accepted.

## 5. Dependency discipline

**No new dependency was added**, front or back end. `httpx`, `pydantic` and `dataclasses` (all already used identically elsewhere in the codebase) are the entire toolkit. This was verified before writing any code, not assumed.
