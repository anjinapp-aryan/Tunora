# Phase 5B — Extend / Remix / Repaint

Each operation is applied to one existing **Version** and creates a **new Version** of the same Song. The source version is never modified. Only what ACE-Step demonstrably does is exposed; nothing is simulated.

```
Song Details (active Version N, has audio)
   | Actions: Extend | Remix | Repaint  (inline form)
   v
POST /api/songs/{song}/versions/{version}/{extend|remix|repaint}
   v
JobService.create_version_from_operation  -> new Version N+1 (source_version_id = version, operation, params)
   v                                          + new Job, same lifecycle as any generation
provider.generate(GenerationRequest{operation, source_audio_path, ...})
   v  ACE-Step /release_task (multipart src_audio, task_type repaint | cover)
new audio stored under the NEW job (AudioStorage) -> Version N+1 attached atomically
```

## 1. Reuse audit

| Need | Decision |
|---|---|
| Job lifecycle, polling, atomic completion | **REUSE unchanged** (`create_and_submit`, `poll_once`, `complete_job`). |
| Storage | **REUSE** `AudioStorage`; the new audio gets its own key; source file only read. |
| Player / download / job polling in UI | **REUSE** `AudioPlayer`, `DownloadButton`, `useJobStatus`. |
| Forms / dialogs | **REUSE** the platform (`<form>`, native `<select>`, radios) plus existing `Button`, `Input`, `Textarea`. No dialog, form or timeline library added (a repaint timeline editor was rejected: not required to make the operation work). |
| Audio editing (cut/crossfade/stitch) | **NOT USED.** The model produces the result; Tunora does not edit audio. |
| Operations themselves | **REUSE ACE-Step** (`repaint`, `cover` task types). |
| Lineage columns, validation, endpoint | **BUILD** (thin, domain-specific; no library exists for this domain model). |

No dependency was added.

## 2. ACE-Step capability audit

Verified by real probes against the running local ACE-Step turbo model, not from documentation alone (docs, `release_task_models.py`, `constants.py` and `release_task_audio_paths.py` were read first). Turbo task types: `text2music`, `repaint`, `cover`, `cover-nofsq`. Source audio must be uploaded as multipart `src_audio`; the API refuses absolute server paths. For `cover`/`repaint` results the reported duration is `"N/A"`.

## 3. Capability matrix

| Operation | Status | Basis |
|---|---|---|
| Extend | **SUPPORTED** (verified locally, objective checks only) | `repaint` past the source end with a longer `audio_duration`; real run: 10 s source + 10 s -> 20.0 s file (ffprobe). |
| Remix | **SUPPORTED** (verified locally, objective checks only) | `cover` with `audio_cover_strength`; real run keeps 10.0 s. |
| Repaint | **SUPPORTED** (verified locally, objective checks only) | `repaint` with an explicit time mask; real run 3–7 s of a 10 s source keeps 10.0 s. |

Human listening has **not** been done: nothing here claims the results sound good, or that the new content matches the description.

## 4. Supported / unsupported

Supported: the three above, on any version that has stored audio, with the ACE-Step provider. **NOT SUPPORTED / NOT IMPLEMENTED:** Extend backwards (before the start), multiple repaint regions, reference-audio/voice conditioning, stems, lego/complete tasks, operations on a version without audio, and any provider that does not declare the operation (`supported_operations`; others get a clear 422).

## 5. Semantics

- **Extend:** length 5–90 s (UI presets 10/20/30/60). New duration = source + extension. Description optional (inherits the source prompt).
- **Remix:** description required; strength 0–1 (UI: Subtle 0.85, Balanced 0.7, Bold 0.5; default 0.7). Keeps source length.
- **Repaint:** start/end seconds, region ≥ 3 s and ≤ 90 s, inside the source duration; description required; lyrics optional. Keeps source length.
- Lyrics, language, instrumental flag and seed are inherited from the source unless the operation supplies new ones.

## 6. Lineage

`versions.source_version_id` points at the exact version used. Branching is allowed (several versions may share a source) and chaining too (an operation version can be a source). The source must belong to the **same song** (service check plus DB trigger). "Extend · from Version 2" is shown from the source's number; ids are never displayed.

## 7. Operation metadata

`operation` (ORIGINAL/EXTEND/REMIX/REPAINT) and `operation_params` (JSON: `extend_seconds` / `remix_strength` / `repaint_start`,`repaint_end`). The version snapshot (`spec`) never stores the source file path.

## 8. Database changes

Migration 2 -> 3 (one `BEGIN IMMEDIATE` transaction, additive, repeat-safe, existing rows become `ORIGINAL`): columns `operation`, `source_version_id`, `operation_params`; triggers `versions_lineage_immutable` (lineage never updated) and `versions_source_same_song` (no cross-song source on INSERT). Numbering still comes from `UNIQUE(song_id, version_number)` inside the existing write lock; no transaction is held across ACE-Step.

## 9. API

`POST /api/songs/{song_id}/versions/{version_id}/{extend|remix|repaint}` with `{prompt?, lyrics?, extend_seconds?, repaint_start?, repaint_end?, remix_strength?}` (NaN/Infinity rejected, prompt ≤ 1000, lyrics ≤ 5000). Returns the new job (same shape as `POST /api/jobs`). 404 unknown song/version (including a version of another song), 409 source audio unavailable, 422 invalid ids/parameters/unsupported operation. `GET /api/songs/{id}` versions gained `operation` and `source_version_number`. **Contract change:** `is_latest` is now the newest version *with audio*, so a generating or failed version is never Latest (two Phase 5A assertions updated for this).

## 10. UI

Song Details: an "Actions" section on the active version, shown only when it has audio and no operation is pending. Extend/Remix/Repaint open an inline form (`aria-expanded`/`aria-controls`, Escape/Cancel close, double submit blocked). While the job runs: "Creating Version N…" (existing `useJobStatus`); the new version is listed (operation label, "Audio unavailable", not Latest, not selected). On COMPLETED the details reload and the new version is selected and Latest; on FAILED a fixed message appears and the previous selection stays. The version list and active panel show "Original" or "Extend · from Version N". Library unchanged (one row per song).

## 11. Audio handling

The backend reads the source bytes from trusted storage and uploads them to ACE-Step; the path exists only inside the provider call and is stripped before the Job/Version are stored. The result is saved as a new file under the new job id; the source file is only read.

## 12. Security

Ids validated at route and service; injection strings, traversal, backslash/drive-letter/overlong ids, cross-song versions and fake ids are refused with nothing created. API responses were scanned for storage paths, provider ids, `/v1/audio`, `source_audio_path`, provider names. The UI shows fixed error messages, never server text.

## 13. Testing (executed this session)

| Check | Result |
|---|---|
| Backend `pytest -m "not smoke"` | **VERIFIED** 333 passed (was 283; +50 in `tests/songs/test_operations.py`: request building, validation matrix, lineage/branching, numbering + concurrency, DB trigger/immutability, missing source, unsupported provider, failure paths, migration 2->3, API, respx provider mapping incl. multipart upload) |
| Frontend Vitest | **VERIFIED** 256 passed (was 231) |
| tsc / ESLint / `next build` | **VERIFIED** clean |
| Real E2E (Next -> FastAPI -> ACE-Step) | **VERIFIED** 8/8, including the new scenario |
| Mutation checks (backend) | **VERIFIED** caught then reverted: Extend ignoring the source position (1 failure), Remix ignoring the chosen strength (2), wrong/absent `source_version_id` (6). "Overwrite the source" is covered by immutability tests but was not mutated. No UI-level mutation was run |
| Responsive (375 / 768 / desktop) | **VERIFIED** in the E2E for the Song page with four versions |

## 14. Real GPU evidence

Smoke test `tests/test_version_operations_smoke.py` (real ACE-Step turbo on the RTX 5060 Ti): one 10 s source, then real Extend, Remix and Repaint through the Tunora API. Objective results: every job COMPLETED; each new version has its own audio key and bytes, different from the source; durations (Tunora / ffprobe) Extend 20.0 / 20.0, Remix 10.0 / 10.0, Repaint 10.0 / 10.0; source hash, size and record unchanged after each; lineage rows correct; four jobs, one song. The UI E2E repeated all three operations from the browser: "Creating Version N…" shown, new version selected and Latest, plays (waveform, play/pause/seek) and downloads bytes equal to its stored file, Library shows one song with 4 versions, labels "Repaint/Remix/Extend · from Version 1" and "Original", Version 1 hash and size unchanged.

## 15. Known limitations

Turbo model only. Remix/Repaint/Extend quality and faithfulness to the description are **not judged** (needs a listener). Seed is inherited, so identical parameters may produce similar output. Remix/Repaint durations are assumed equal to the source when ACE-Step reports `N/A`; the E2E/smoke ffprobe check confirmed this for the tested cases only. No timeline UI for Repaint (numeric seconds). One operation at a time per open Song page (another tab can still start one; the backend serializes numbering). A navigation away while a job runs is not resumed in the UI (the job still completes; the version appears on reload).

## 16. Deferred

Projects, AI Song Director, multi-provider UI, stems, advanced audio editing, music video, sharing/auth, rename/delete versions.
