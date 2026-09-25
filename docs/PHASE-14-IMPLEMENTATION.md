# Phase 14 — Extract Model Correctness / Fail-Visible

Implementation record for Candidate K of `docs/PHASE-14-PRODUCT-CAPABILITY-GAP-AUDIT.md`:
"Extract runs on the correct base model, or fails visibly."

Note on scope: the task prompt for this phase ended after its section 10 (objective, scope, audit,
git state, ACE-Step tracing, spike, model contract, launcher, loading strategy, provider
validation). It contained no rules for tests, documentation, commit or push. The implementation
below covers sections 1-10 plus the testing and validation conventions of earlier phases; nothing
was committed or pushed.

## Findings re-verified (not trusted from the audit)

- `HEAD == origin/feature == df1545e` (Phase 13 pushed). ACE-Step submodule `ca1e85f` equals upstream HEAD.
- The launcher started ACE-Step with no `ACESTEP_CONFIG_PATH2` (no match in the launch scripts, `.env`, service doc, or the user/machine/process environment).
- Live, before the change: `/v1/model_inventory` showed `acestep-v15-base` `is_loaded: false`, and an extract request for `model=acestep-v15-base` returned `"dit_model": "acestep-v15-turbo"`.

## ACE-Step tracing (source, not guesses)

1. **How the base model is configured:** `acestep/api/lifespan_runtime.py:100-109` reads `ACESTEP_CONFIG_PATH2` (and `_PATH3`) at startup; if set, a second handler is created and `_config_path2` recorded. `docs/en/API.md:632` states slots 2/3 exist only when these variables were set before the server started.
2. **How the second model is selected:** `acestep/api/job_model_selection.py:120-215` `select_generation_handler` compares the request's `model` with the primary, then the initialized second and third handlers.
3. **Loading:** `acestep/api/startup_model_init.py:111-136` initializes handler 2 (`_initialized2`). In the tested deployment the models load on the first request (the health check alone does not load them).
4. **How `/release_task` selects a model:** the request field `model` (aliases include `dit_model`, `release_task_param_parser.py:19`) is passed to `select_generation_handler`.
5. **Why it falls back to turbo:** when no handler matches, and `ACESTEP_ON_DEMAND_MODEL_LOAD` is not enabled (default `false`, `job_model_selection.py:39`), the function only logs "Model ... not found in [...], using primary" and returns the primary handler. The request does not fail.
6. **Authoritative evidence of what ran:** `dit_model` in the result item is `selected_model_name` from that same function (`acestep/api/job_blocking_generation.py:201`, `job_result_payload.py:134`).

## Spike result and the contract

With the slot configured, the same live probe reports `"dit_model": "acestep-v15-base"`; without it, `"acestep-v15-turbo"`. So the authoritative field exists and needs no heuristic (no filename, timing, GPU memory or audio-characteristic check).

**Contract (EXTRACT):** the result is accepted only if `dit_model == "acestep-v15-base"` exactly. Turbo, any other name, an empty/null value or a missing field are all rejected. Nothing is saved for a rejected result and no Version gets audio.

## Changes

1. `tunora-services.ps1`: the ACE-Step launch command sets `$env:ACESTEP_CONFIG_PATH2 = 'acestep-v15-base'` (one line). Turbo stays the primary model; base is the second slot, exactly the mechanism documented by ACE-Step.
2. `backend/app/providers/ace_step.py` (`AceStepMusicGenerationProvider`): `generate()` records the expected model for each EXTRACT task id; `get_result()` compares the result item's `dit_model` and raises `ProviderResponseError` on mismatch. The record is removed when the result is read and the map is bounded (1000 entries). Other operations are not checked.
3. `docs/TUNORA-SERVICE-MANAGEMENT.md`: manual start command updated, new section on the second model, silent fallback and measured VRAM.
4. Tests: `backend/tests/test_ace_step_extract_model.py` (12 tests).

**How it fails visibly and safely:** the provider error goes through the existing `JobService.poll_once` path: the Job becomes FAILED, `complete_job` never runs, so no audio is stored and the Version keeps `audio = null`. The public API returns its fixed "Generation failed." (tests assert that no model name, `dit_model`, "required model" text or path appears in the job or song responses). The UI shows the existing operation-failed message.

**Restart behavior:** the expected-model map is in memory. Jobs are not resumed after a backend restart in this codebase (no recovery code in `main.py`/`service.py`), so no Extract can be polled without its expectation.

## GPU / VRAM (fresh measurements, RTX 5060 Ti 16,311 MiB, 1 Hz `nvidia-smi` sampling)

| State | Used |
|---|---|
| ACE-Step just started (nothing loaded) | ~1.5-1.8 GB |
| Turbo + 1.7B LM loaded, idle (before change) | 8,408 MiB |
| Turbo + base + LM loaded, idle (after change) | 11,633 MiB (+3.2 GB) |
| Turbo-only slot, Version-operations + Another Take + basic smoke | peak 10,203 MiB |
| Slot configured, same turbo smoke set | peak 14,864 MiB |
| Slot configured, Extract smoke only | peak 14,862 MiB |
| Slot configured, first mixed smoke set (Extract + ops) | peak 15,298 MiB |
| Slot configured, full Playwright suite | peak 15,256 MiB |

Phase 11 recorded 11.2 GB with both models; this session measured about 15.3 GB peak, i.e. roughly 1 GB of headroom. Sampling at 1-2 s can miss shorter spikes. No out-of-memory error occurred in 4+3+1 smoke runs or the full E2E suite. Trade-off: base residency costs about +3.2 GB idle and about +4.7 GB peak for the whole session. Removing the variable frees it and Extract then fails visibly by design. `ACESTEP_ON_DEMAND_MODEL_LOAD` was not adopted: it swaps the primary handler in place and requires single-worker settings, which is a larger behavioral change than this phase's scope.

## Validation

- Backend `pytest -m "not smoke"`: **566 passed** (554 before, +12).
- Real GPU, slot configured: Extract smoke, Version-operations smoke, Another Take smoke and basic ACE-Step smoke, **4 passed**; the Extract smoke passes with the model check active.
- **Negative real test:** ACE-Step restarted without the variable; the same Extract smoke test failed with the Extract job in status `FAILED` (visible failure, nothing completed); Create, Extend, Remix, Repaint and Another Take smokes passed on that same server (3 passed).
- Playwright (real stack, both models resident): 18 of 19 passed in the full run. The one failure, "Projects: create, add an existing song, …", timed out at a "Pause" button after a playback step; the test had run 2.4 h (the machine evidently stalled), and it **passed alone on rerun (27.6 s)**. Frontend code is unchanged in this phase. The Extract and Another Take E2E tests passed in the full run.
- Frontend: `tsc` clean, ESLint 0 errors (1 pre-existing warning), Vitest 365 passed.

## Mutation testing

Nine targeted mutations of the provider check, each run against the Extract test files and restored afterwards: check removed, accept-when-model-missing, prefix match, inverted comparison, expectation recorded for the wrong operation, expectation never removed, bound removed, wrong expected-model constant, error swallowed. **9 of 9 caught.**

## Known limitations

- Whether Extract audio produced by the base model is a good stem still needs a listener; this phase only guarantees which model ran. Extract Versions created before this change have unknown provenance (the model was never recorded).
- The startup change costs about +3.2 GB idle / +4.7 GB peak VRAM with ~1 GB of measured headroom.
- The check relies on ACE-Step's `dit_model` field; a future ACE-Step that drops it would make Extract fail visibly (by design), not silently succeed.
- Manual starts that omit the variable will fail Extract jobs (documented).
- `tunora-services.ps1` is the only launcher changed; other ways of starting ACE-Step must set the variable themselves.

## Deferred (not part of Phase 14)

Lossless / FLAC output, batch generation, prompt library, cover art, mastering, MIDI, chord detection, lyric alignment, new Extract track types, `lego`, `complete`.
