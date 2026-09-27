# Phase 9 Capability Gap Audit

**Audit only — no implementation.** This document inspects the actual Phase 1–8 codebase (not just its docs), maps what genuinely exists against Tunora's own product scope, performs a fresh open-source search for every serious gap candidate, and recommends one capability for Phase 9. Nothing in `backend/`, `frontend/`, `ACE-Step-1.5/`, migrations, schemas, or dependencies was touched to produce this report.

## 1. Executive Summary

Tunora's generation, versioning, creative-operation (Extend/Remix/Repaint), Projects and AI Song Director capabilities are real, tested against a running local ACE-Step server, and match their own phase docs. However, cross-checking the implementation against Tunora's **own governing scope document** (`docs/PRODUCT-SCOPE.md`, `docs/MVP-SCOPE.md`) surfaces a gap that predates all of Phases 1–8: **Library management (delete, favorite) was explicitly scoped as MVP-must-have and has never been built.** `AudioStorage.delete()` doesn't exist (deliberately deferred in Phase 3, "nothing requires it yet" — it now does). There is no way to remove an unwanted or failed Song from a library that only ever grows, and no way to mark or filter favorites, despite both being called out by name in the MVP scope. This is not a new feature idea; it is a documented, unmet commitment. Recommendation: Phase 9 = **Song delete and favorites**, built entirely from existing Tunora primitives (no new dependency), closing the ORGANIZE stage of the product's own north-star workflow.

## 2. Current Tunora Capability Map

Verified against source (`backend/app/`, `frontend/src/`) and the passing test suites (429 backend, 309 frontend, 11 real E2E scenarios), not against documentation claims alone.

| Area | Capability | Status | Evidence | Gap |
|---|---|---|---|---|
| Generation | Prompt/lyrics/language/duration/instrumental/seed → job | Complete | `CreateJobRequest`, `JobService.create_and_submit`, real smoke tests | none |
| Generation | Job lifecycle (queued/submitted/running/completed/failed) | Complete | `app/jobs/state_machine.py`, `JobStatus`, polling hook | none |
| AI Planning | Natural language → SongSpec via ACE-Step's own LM | Complete | `app/director/ace_step.py::create_plan`, real GPU smoke test, real E2E | none |
| AI Refinement | Natural-language edit of an existing plan | Complete | `app/director/ace_step.py::refine`, real smoke test (incl. a documented provider failure case) | Known: no instrumental control in `/format_input`; occasional lyrics-collapse (documented, guarded, not solved) |
| Song Editing | Extend / Remix / Repaint an existing Version | Complete | `app/songs/operations.py`, real GPU smoke tests for all three | Turbo model only; no timeline UI for Repaint region (numeric seconds) |
| Audio | Playback, waveform, seek, volume | Complete | `components/audio/audio-player.tsx` (WaveSurfer), Playwright real-audio assertions | Player downloads the whole file (no streaming) — accepted trade-off, documented |
| Audio | Download | Complete | `GET /api/jobs/{id}/audio`, `DownloadButton` | Single-file only; no batch/zip export |
| Versions | Immutable snapshots, lineage, numbering | Complete | SQLite triggers (`versions_snapshot_immutable`, `versions_lineage_immutable`), concurrency tests | none |
| Projects | Create/list/rename/delete a Project, add/remove Songs | Complete | `app/projects/`, `routes_projects.py`, real E2E | No Project-level bulk actions (e.g. "generate a plan already scoped to this Project" — explicitly deferred in Phase 7/8 docs) |
| Library | List, search (title+prompt), sort (newest/oldest/title), Project filter | Complete | `library-list.tsx`, `list_song_summaries` | **No delete. No favorite. No rename a Song's title after creation.** |
| Search | Case-insensitive substring, SQL-injection-safe | Complete | `ESCAPE '!'` pattern, tested with injection strings | Not full-text/fuzzy; acceptable at local-single-user scale (documented) |
| Metadata | Prompt, lyrics, language, duration, bpm/key/time-signature hints | Complete (as hints, not guarantees) | `SongPlanResponse`, `_PUBLIC_METADATA_FIELDS` | none beyond documented "not guaranteed" caveats |
| Export | Single MP3 download | Partial | `DownloadButton` | No packaging of multiple versions/a whole Project; no metadata-embedded export |
| Organization | Projects, Library sort/filter | Complete for what exists | — | **No favorites-as-a-filter (explicitly a V1 scope item)**, no tags |
| UX | Review-first plan editing, inline panels (no dialog library) | Complete | Phase 7/8 UI | Delete has no confirmation pattern yet to reuse-consistent-with (Projects' own delete confirm exists and is the right template) |
| Accessibility | Native controls, labelled forms/radio groups, keyboard nav checked at each phase | Partial | Per-phase "accessibility" sections; **no axe/screen-reader run in any phase** (stated explicitly every time) | Known, accepted, unverified beyond manual/native-semantics checks |
| Security | Id validation, SQLi tests, no path/provider leakage, untrusted-AI-output validation | Complete for implemented surface | Extensive per-phase security test sections | A delete endpoint doesn't exist yet to audit |
| Performance | Grouped queries (no N+1) for Library/Projects | Complete | Phase 5A/6 "performance" sections, tested with query counting | none observed |
| Storage | Local filesystem, key-based, path-traversal guarded | Complete | `LocalAudioStorage`, `AudioStorage` interface | **`AudioStorage.delete()` was deliberately never implemented** (Phase 3: "nothing requires it yet") |
| Import | Reference audio / upload | Not implemented | Explicitly out of MVP/V1 (`docs/MVP-SCOPE.md`) | Deferred by design, not a gap |
| Provider architecture | `MusicGenerationProvider`, `supported_operations` | Complete | `app/providers/base.py`, one real implementation | Single provider (ACE-Step) in practice; abstraction exists and is exercised by fakes in tests |
| Model management | DiT/LM model selection | Delegated to ACE-Step's own `.env`/model-tier config | `ACESTEP_CONFIG_PATH`, `gpu_config.py` (vendored) | Tunora has no UI for switching model tier; not previously scoped |
| Deployment | Local scripts (`start/stop/restart-tunora.ps1`) | Complete for local-first goal | `docs/TUNORA-SERVICE-MANAGEMENT.md`, tested | No packaging/installer; explicitly out of scope (self-hosted, not distributed) |
| Observability | `loguru`-style structured logging inside ACE-Step; plain logging in Tunora | Minimal, as scoped | `docs/COST-AUDIT.md` — OTel/Prometheus deferred | Matches stated non-goals; not a current gap |
| Testing | Unit, integration, respx-mocked provider/director, real GPU smoke, real Playwright E2E, mutation testing every phase | Extensive | 429 backend + 309 frontend + 11 E2E, per-phase mutation sections | One known, documented Vitest timing flake under parallel load (not a Phase 9 blocker) |
| Extensibility | Provider/Director abstractions used consistently | Complete | Same interfaces reused across Phases 3–8 without redesign | none |

## 3. Product Workflow Analysis

```
IDEA → PLAN → REFINE → GENERATE → LISTEN → SAVE → ORGANIZE → EDIT/EXTEND/REMIX → VERSION → EXPORT/USE
 ✅     ✅       ✅        ✅         ✅       ✅      ⚠️              ✅               ✅         ⚠️
```

- IDEA → PLAN → REFINE → GENERATE → LISTEN → SAVE: solid, tested end to end with real audio (Phases 3, 7, 8).
- EDIT/EXTEND/REMIX → VERSION: solid (Phase 5B, 4).
- **ORGANIZE**: Library and Projects exist, but a Library that can only grow, with no delete and no favorite/filter, is a structurally incomplete "organize" stage for exactly the reason `docs/MVP-SCOPE.md` called both out by name — once a user has generated a few dozen songs (trivial after 8 phases of real-GPU testing alone), there is no way to remove the ones they don't want or to surface the ones they do. This is the clearest break in the workflow: not a missing nice-to-have, but a documented product requirement that silently never shipped.
- **EXPORT/USE**: single-file download exists; multi-version/whole-project export does not. This is a real but smaller gap — V1 scope never explicitly promised it, unlike delete/favorite which MVP scope did.

## 4. Current Gaps

Ranked by how directly they map to a documented, unmet product requirement (not by implementation difficulty):

1. **Song delete** (`docs/MVP-SCOPE.md`: "Library: ... delete" — MVP must-have, never built).
2. **Favorites** (`docs/MVP-SCOPE.md`: "Favorite marking, if practical" — MVP should-have; `docs/PRODUCT-SCOPE.md` V1: "Favorites as a first-class filter/view" — still never built).
3. Song rename after creation (not explicitly scoped, but a natural companion to delete/favorite for Library hygiene — see §16).
4. Export/package multiple versions or a whole Project (not explicitly MVP-scoped; V1/V2 territory at most).
5. Stem separation (`docs/PRODUCT-SCOPE.md` V2, `docs/AUDIO-REUSE-AUDIT.md` — explicitly deferred until core product works; see §8 for why ACE-Step's own native "extract" capability doesn't change that timing).
6. Audio mastering/loudness normalization (never scoped anywhere in `docs/`).
7. Version diff / comparison UI (never scoped).

## 5. Technical Debt Relevant to V1

- **`AudioStorage.delete()` does not exist.** Not a design flaw — Phase 3 explicitly deferred it as speculative — but it is now a real blocker for the #1 gap above, not a hypothetical one.
- **No `PATCH /api/songs/{id}`.** A Song's title is set once at creation (`derive_title`) and never editable. Minor, but any delete/favorite UI naturally invites "and let me fix the title too" — worth deciding in scope, not by accident.
- **Migration is at `user_version = 4`.** Adding `is_favorite`/handling delete is a clean, additive `4 → 5` step in the same proven pattern — no risk identified.
- **One known Vitest flake** (`version-actions.test.tsx`, a real-timer poll race under heavy parallel load) — cosmetic, already documented, does not block anything.
- Nothing else rises to "materially affects reliability, security or extensibility" — the codebase is consistent in its patterns (provider abstraction, migration style, allowlisted API responses, inline-panel UI, mutation-tested behavior) across all eight phases, which is itself evidence against broad refactoring being needed right now.

## 6. Fresh Open-Source Audit

Searches run this session (GitHub, Hugging Face, official docs); URLs and dates below.

- **Demucs weight license** — Tunora's own `docs/AUDIO-REUSE-AUDIT.md` flagged this as "disputed/unverified." Re-checked 2026-09-22: [adefossez/demucs](https://github.com/adefossez/demucs) and its `LICENSE` file ([fetched directly](https://github.com/adefossez/demucs/blob/main/LICENSE), 2026-09-22) is **MIT**, applied to the repository as a whole with no separate weights clause and no commercial restriction. This **updates** the prior audit's "disputed" status — worth a note in `docs/AUDIO-REUSE-AUDIT.md` whenever stem separation is actually scheduled, but stem separation is not this phase's recommendation (see §8), so no doc change is made here.
- **ACE-Step 1.5 native stem/track capability** — [ace-step/ACE-Step-1.5 README](https://github.com/ace-step/ACE-Step-1.5/blob/main/README.md) (fetched 2026-09-22) advertises "Track Separation — Separate audio into individual stems" and "Multi-Track Generation." Confirmed in the **vendored source** (`ACE-Step-1.5/acestep/constants.py`): `extract`/`lego`/`complete` task types exist, but only under `TASK_TYPES_BASE`/`GENERATION_MODES_BASE` — the **base** model tier, not the `turbo` tier Tunora currently runs. This is a real, previously-undocumented-in-Tunora capability, but adopting it means a model-tier change (larger download, more VRAM), which is exactly the kind of decision Tunora's own process requires a dedicated Phase to validate — not something to fold into an unrelated Phase 9. Recorded here as an **alternative candidate**, not silently adopted.
- **Loudness normalization** — [csteinmetz1/pyloudnorm](https://github.com/csteinmetz1/pyloudnorm) (checked 2026-09-22): MIT license, implements ITU-R BS.1770-4, pure Python + numpy, no GPU. Would be the correct REUSE candidate *if* mastering were the Phase 9 pick — it is not (see §9, §14).
- **Audio diff/comparison** — [`audiodiff`](https://pypi.org/project/audiodiff/) (byte/tag-level, not musically meaningful) and [AudioCompare](https://github.com/charlesconnell/AudioCompare) (fingerprint similarity) exist but solve a different problem (detecting whether two files are related) than "show a user what changed between two Versions" (a UI/waveform-visual problem, for which WaveSurfer — already a Tunora dependency — is the correct tool, not a new library).
- **Song delete / favorite / rename**: no external search applies — these are CRUD operations on Tunora's own schema. Confirmed (2026-09-22, reading the actual code) that no OSS "song library management" package exists that could plug into a bespoke `Song`/`Version` domain like Tunora's; this is squarely product-owned logic per `docs/PRODUCT-SCOPE.md`'s own "What Tunora Owns vs. What It Reuses" section.

## 7. Reuse Matrix

| Capability | Repository | License | Maturity | Fit | Local | Decision |
|---|---|---|---|---|---|---|
| Song delete (DB rows + audio files) | — (Tunora's own `SongRepository`/`AudioStorage`) | n/a | n/a | Exact fit — extends an interface designed for this | Yes | **BUILD** (compose existing `AudioStorage`, `SongRepository`, migration pattern) |
| Favorites (flag + filter) | — (Tunora's own `Song` model, Library query) | n/a | n/a | Exact fit — same shape as the Phase 6 Project filter already shipped | Yes | **BUILD** (compose the exact pattern already used for the Project filter) |
| Confirmation UI pattern | Tunora's own `ProjectDetailsView` delete-confirm block (Phase 6) | n/a | Already shipped, tested | Exact fit | Yes | **REUSE verbatim pattern** |
| Loudness normalization (if mastering were chosen) | [csteinmetz1/pyloudnorm](https://github.com/csteinmetz1/pyloudnorm) | MIT | Active, citable (has a preprint), stable API | High, if needed | Yes, CPU-only | REFERENCE (not needed this phase) |
| Stem separation via ACE-Step base tier | vendored `ACE-Step-1.5` (`extract`/`lego` task types) | MIT code / Apache-2.0 weights (per Tunora's existing model-license audit) | Native to an already-vendored dependency | High capability, but requires a model-tier change | Yes | REFERENCE (deserves its own future phase, not Phase 9) |
| Stem separation via Demucs (fallback if ACE-Step base tier is rejected) | [adefossez/demucs](https://github.com/adefossez/demucs) | MIT (code and weights; re-verified 2026-09-22) | Mature, widely used | High | Yes, GPU or CPU | REFERENCE (not needed this phase) |
| Audio diff/comparison | audiodiff, AudioCompare (see §6) | MIT-family | Small, narrow | Low — solves a different problem than a Version-comparison UI | Yes | REJECT (WaveSurfer, already adopted, is the right tool if this is ever built) |
| Export/zip packaging | Python stdlib `zipfile` | stdlib | n/a | Exact fit for "bundle a few files" | Yes | REFERENCE (stdlib, no dependency decision needed; not this phase) |

## 8. Candidate Capabilities

Every candidate from the prompt's suggested list was considered against the evidence above; only the ones with real signal are discussed here (the rest — auth, collaboration, sharing, mobile UX redesign, playlists — have no basis in Tunora's own scope docs and were not investigated further, consistent with "do not overbuild").

- **Song delete + favorites** — directly, explicitly scoped in MVP; genuinely missing; zero new dependencies; additive migration; reuses four already-proven Tunora patterns (migration step, `AudioStorage` interface, Library filter, inline confirm UI).
- **Song rename** — not explicitly scoped, but trivial to add alongside delete/favorite (same `PATCH` surface) and closes an obvious adjacent hole (a Song's name is currently frozen at creation). Considered as an in-scope companion, not a separate phase.
- **Stem separation** — real native capability was just discovered in the vendored ACE-Step base tier, license-clean either via that or via Demucs, but requires a model-tier/VRAM decision Tunora's own process says deserves a dedicated validation phase (per `docs/PHASE-2-*` methodology), not a rider on a Library-management phase.
- **Export/zip packaging** — no dependency needed (stdlib `zipfile`), but not scoped by any product doc and has no urgent user-pain evidence the way delete/favorites do.
- **Audio mastering (loudness normalization)** — a clean OSS candidate exists (pyloudnorm) but was never part of Tunora's scope at any tier (MVP/V1/V2) and there is no evidence users are blocked by unmastered output today.
- **Version diff/comparison** — no suitable OSS wheel found that solves the actual problem (visual/semantic comparison of two generations); would be a non-trivial BUILD with no scope backing.

## 9. Phase 9 Recommendation

```
PHASE 9 RECOMMENDATION

Capability:
    Song management: delete a Song (and its audio), mark/unmark a Song as
    a favorite, and filter the Library by favorites. (Song rename included
    as a directly adjacent, same-surface companion — see Scope Boundary.)

User problem:
    A Library that only ever grows, with no way to remove a failed/unwanted
    Song or surface the ones worth keeping, becomes unusable after normal use
    (each Phase's own real-GPU testing already generates dozens of Songs).

Current Tunora behavior:
    Songs can be created, edited via Extend/Remix/Repaint, and grouped into
    Projects, but never deleted, favorited, or renamed. `AudioStorage.delete()`
    does not exist. `docs/MVP-SCOPE.md` and `docs/PRODUCT-SCOPE.md` both list
    delete and favorites as MVP/V1 requirements.

Missing capability:
    DELETE /api/songs/{id} (removes the Song, its Versions, and their audio
    files); a favorite flag on Song with a Library filter; PATCH for title
    and favorite state.

Existing OSS solution:
    None applicable — this is Tunora's own domain data (see §6). No adoption
    decision needed for the core capability.

Adoption decision:
    BUILD (composed entirely from existing Tunora interfaces/patterns).

Why:
    No OSS project can delete rows in Tunora's own schema or files in its own
    storage layout; the existing Reuse-First Law explicitly names this kind
    of product-owned glue as something Tunora is expected to build (see
    docs/PRODUCT-SCOPE.md, "What Tunora Owns vs. What It Reuses").

Reuse evidence:
    `AudioStorage` interface was designed with `delete()` as an anticipated,
    deferred addition (Phase 3 docstring: "delete() ... not included --
    nothing in Phase 3 requires them yet"). The Library's Project filter
    (Phase 6) is the exact pattern a favorites filter would reuse. The
    Project delete confirmation UI (Phase 6, `ProjectDetailsView`) is the
    exact pattern a Song delete confirmation would reuse. The migration
    mechanism (`PRAGMA user_version`, additive steps) is unchanged.

New code required:
    `AudioStorage.delete(key)` (+ `LocalAudioStorage` implementation);
    `SongRepository`/`JobRepository` delete-cascade query (Song + its
    Versions + their Job rows); migration 4→5 (`songs.is_favorite`,
    `songs.title` already exists and just needs a PATCH path); 
    `DELETE /api/songs/{id}`, `PATCH /api/songs/{id}`; Library UI: a
    delete button + confirm block (Phase 6's own pattern), a favorite
    toggle, and a favorites filter (Phase 6's own Project-filter pattern).

Existing Tunora code reused:
    `AudioStorage` interface (extended, not replaced), `SongRepository`,
    the migration framework, the Library's search/sort/filter UI shape,
    the Project delete-confirmation component pattern, existing id
    validation (`app/songs/ids.py`), existing allowlisted-response pattern.

New dependencies:
    None.

Dependencies avoided:
    Any "library management" package (none exists for a bespoke schema);
    a dialog/modal library (the existing inline-confirm pattern is reused).

Architecture impact:
    Additive only. `AudioStorage` gains one method (implemented, not
    redesigned). No change to `MusicGenerationProvider`, `SongDirector`,
    `SongSpec`, `JobService`'s generation path, or the Project domain.

Database impact:
    One additive migration (5): `songs.is_favorite BOOLEAN NOT NULL DEFAULT 0`.
    Deleting a Song's rows (Versions, Jobs) needs an explicit transactional
    delete — unlike Project deletion, Version/Job rows should NOT survive a
    Song delete (they have no meaning without their Song), so this is a real
    cascading delete, not a `SET NULL`; needs its own careful design and
    tests (see Security Impact) rather than copying the Project pattern
    verbatim.

API impact:
    Additive: `DELETE /api/songs/{id}`, `PATCH /api/songs/{id}` (title,
    is_favorite), `GET /api/songs?favorite=true` filter param (same shape
    as the existing `?project=` filter). No existing endpoint's behavior
    changes.

UI impact:
    Library gains a favorite toggle per row, a "Favorites only" filter
    (reusing the Project-filter select pattern), and a delete action with
    the existing inline confirmation block. Song Details gains the same
    delete/favorite/rename controls on its header. No new pages.

Testing impact:
    New: delete-cascade tests (Song, Versions, Jobs, audio files all
    actually gone; a Song in a Project is correctly unassigned from it
    first or the FK behavior is decided explicitly); favorite-flag tests
    (toggle, filter, persists across reload); rename validation tests
    (length bounds, same as existing title handling); security tests
    (malformed/cross-song ids, no path leakage on delete errors); a real
    E2E (create → favorite → filter → delete → confirm gone from Library
    and from disk); mutation tests (e.g. delete not actually removing the
    audio file, favorite filter ignoring the flag).

Security impact:
    A delete endpoint is a genuinely new destructive surface: must validate
    the Song id the same way every other route does, require the same kind
    of explicit confirmation Projects already use, and must be proven (by
    test) to never delete another Song's data, never leave orphaned audio
    files, and never leave orphaned DB rows on a partial failure (the
    existing `BEGIN IMMEDIATE` transactional pattern applies directly).

Known limitations:
    Delete is permanent (no trash/undo) unless explicitly scoped in;
    deleting a Song currently assigned to a Project needs an explicit,
    documented decision (most consistent option: it is simply removed from
    the Project's song list, mirroring how a Project's own deletion already
    unassigns Songs rather than cascading).
```

## 10. Alternative Candidates

- **Capability:** Stem separation via ACE-Step's native base-tier `extract`/`lego` task types (or Demucs as a fallback).
  **Why it matters:** V2-scoped, and a real, previously-undocumented-in-Tunora native capability was found this session.
  **Existing OSS:** Native to the vendored `ACE-Step-1.5` base tier (MIT/Apache-2.0, already audited); Demucs (MIT, re-verified 2026-09-22) as a fallback.
  **Reuse decision:** REFERENCE — worth its own future phase.
  **Why not selected:** Requires a model-tier/VRAM change that Tunora's own process (Phase 2-style hardware validation) says needs dedicated evaluation, not a rider on an unrelated phase; V2-scoped, not MVP; no unmet-MVP-commitment evidence the way delete/favorites has.

- **Capability:** Export/package multiple Versions or a whole Project as a zip.
  **Why it matters:** A natural EXPORT/USE-stage improvement once a Library holds many Versions.
  **Existing OSS:** Python stdlib `zipfile` — no dependency decision needed.
  **Reuse decision:** REFERENCE.
  **Why not selected:** Not scoped in any product doc at any tier; no evidence of current user pain (single-file download already works); smaller, cleanly separable follow-on once Library management (this phase's pick) exists to select *which* Versions to export.

- **Capability:** Audio mastering / loudness normalization.
  **Why it matters:** Could make generated output sound more consistent/professional.
  **Existing OSS:** [pyloudnorm](https://github.com/csteinmetz1/pyloudnorm) (MIT, ITU-R BS.1770-4).
  **Reuse decision:** REFERENCE.
  **Why not selected:** Never scoped anywhere in Tunora's product docs; no evidence of a real gap versus a hypothetical improvement; would touch the audio pipeline (a higher-risk area) for a benefit nobody has asked for yet.

- **Capability:** Version diff/comparison (semantic or visual "what changed between v1 and v2").
  **Why it matters:** Could help users understand Extend/Remix/Repaint results.
  **Existing OSS:** No suitable wheel found (audiodiff/AudioCompare solve a different problem; WaveSurfer, already adopted, would be the actual tool if built).
  **Reuse decision:** BUILD, if ever done.
  **Why not selected:** No scope backing, nontrivial UX design question (what does "diff" even mean for two AI-generated songs), and no evidence of current user need.

- **Capability:** Song rename after creation.
  **Why it matters:** An obvious companion to delete/favorite Library hygiene.
  **Existing OSS:** n/a (Tunora's own field).
  **Reuse decision:** BUILD.
  **Why not selected as its own phase:** Not rejected — folded into the Phase 9 recommendation itself as a same-surface companion (see §9's Scope Boundary), because it shares the same `PATCH /api/songs/{id}` endpoint and the same Library-row UI real estate as favorites.

## 11. Architecture Impact

| Component | Affected? | How |
|---|---|---|
| Database | Yes | Additive migration 4→5 (`songs.is_favorite`); a new cascading delete path for Song/Version/Job rows |
| API | Yes (additive) | New `DELETE`/`PATCH /api/songs/{id}`, new `?favorite=` Library filter param |
| Backend | Yes | `SongRepository`, `AudioStorage` gain methods; `JobService` gains delete/rename orchestration |
| Frontend | Yes | Library and Song Details gain controls; no new pages/routes |
| Song | Yes | Gains `is_favorite`; title becomes mutable post-creation |
| Version | Indirectly | Deleted as part of a Song delete (cascade), never independently |
| Project | Indirectly | Must decide/implement what happens to a Project's song list when a member Song is deleted |
| Job | Indirectly | Deleted as part of a Song delete (cascade) |
| AudioStorage | Yes | Gains `delete(key)` |
| MusicGenerationProvider | No | Unaffected |
| SongDirector | No | Unaffected |
| SongSpec | No | Unaffected |

All changes are additive to existing interfaces; nothing requires redesigning an abstraction that already exists.

## 12. Testing Impact

Gaps the current suite does not cover (because the capability doesn't exist yet): destructive-operation tests (delete-cascade correctness, orphan-file/orphan-row prevention), favorite-flag persistence/filter tests, rename validation tests, a real E2E covering create→favorite→filter→delete→verify-gone-from-disk, and mutation tests specific to a delete path (e.g., "delete doesn't actually remove the file" or "delete removes the wrong Song"). No new *type* of testing infrastructure is needed — the same pytest/respx/Vitest/Playwright/mutation-testing approach used in every prior phase applies directly.

## 13. Security Impact

A delete endpoint is Tunora's first genuinely destructive user-facing API surface (Project delete already exists but is non-destructive to Songs by design). It must reuse the existing id-validation and allowlisted-response patterns, must be provably atomic (no partial deletes leaving orphaned files or rows), and must be tested against cross-song id confusion the same way every other Song/Version endpoint already is. No new class of security concern is introduced beyond "deletion must be complete, authorized-by-being-local-only, and irreversible-with-clear-confirmation" — consistent with how Project deletion was already handled.

## 14. Scope Boundary

```
IN SCOPE
    - DELETE /api/songs/{id}: deletes the Song, all its Versions, their Jobs,
      and their audio files; removes it from any Project's song list.
    - PATCH /api/songs/{id}: title (rename) and is_favorite (toggle).
    - GET /api/songs?favorite=true filter (same shape as the existing
      ?project= filter).
    - Library UI: favorite toggle per row, "Favorites only" filter, delete
      action with an inline confirmation (reusing the Project delete-confirm
      pattern).
    - Song Details UI: the same delete/favorite/rename controls.
    - Migration 4->5 (songs.is_favorite).
    - AudioStorage.delete(key).

OUT OF SCOPE
    - Trash/undo/soft-delete.
    - Bulk/multi-select delete.
    - Export/zip packaging.
    - Stem separation (any tier).
    - Audio mastering/loudness normalization.
    - Version-level delete (only whole-Song delete; a single Version cannot
      be deleted independently -- consistent with Versions being immutable
      history).
    - Tags/labels beyond a single favorite boolean.
    - Any change to generation, Extend/Remix/Repaint, Projects' own CRUD,
      or the AI Song Director.

MUST NOT BUILD
    - A generic "soft delete" framework.
    - A new UI dialog/modal library (reuse the existing inline-confirm
      pattern).
    - A new database (SQLite migration only).
    - Any new external dependency.

REUSE
    - SongRepository, AudioStorage interface, migration framework,
      app/songs/ids.py validation, existing allowlisted-response builders.

ADAPT
    - The Phase 6 Project delete-confirmation UI pattern, adapted for a Song.
    - The Phase 6 Library Project-filter pattern, adapted for a favorite
      filter.

COMPOSE
    - Song delete = compose AudioStorage.delete() (new) with a new
      transactional repository method that removes Version/Job rows before
      the Song row, inside one BEGIN IMMEDIATE transaction.

BUILD
    - AudioStorage.delete(key) implementation.
    - The cascading delete repository method.
    - PATCH /api/songs/{id} and its schema/validation.
    - The is_favorite column and its migration step.
```

## 15. Proposed Phase 9 Acceptance Criteria

```
[ ] Existing OSS audited (this document) -- confirmed no applicable wheel for the core capability
[ ] AudioStorage.delete() implemented and unit-tested (LocalAudioStorage)
[ ] Song delete removes Song, Versions, Jobs and audio files atomically (one transaction)
[ ] Song delete removes the Song from any Project's list without touching the Project itself
[ ] PATCH /api/songs/{id} (title, is_favorite) implemented with the same validation rigor as existing endpoints
[ ] GET /api/songs?favorite=true implemented, reusing the existing filter-query pattern (no N+1)
[ ] Library UI: favorite toggle, favorites filter, delete action + confirmation
[ ] Song Details UI: same controls
[ ] Backend unit/integration tests: delete-cascade correctness, orphan prevention, favorite persistence, rename bounds, cross-song id isolation
[ ] Frontend unit tests: toggle/filter/delete UI states, confirmation flow, failure leaves the Song intact
[ ] Real integration: an actual generated Song (with real audio on disk) is deleted and its file is verified gone from the filesystem
[ ] Real E2E: create -> favorite -> filter by favorites -> delete -> confirm gone from Library and from disk
[ ] Security tests: malformed/cross-song ids, no path/internal leakage on delete errors, confirmation required before deletion
[ ] Mutation tests: at least one per new behavior (delete doesn't remove the file / removes the wrong Song / favorite filter ignored / rename bypasses validation)
[ ] Documentation: docs/PHASE-9-SONG-MANAGEMENT.md following the established phase-doc format
[ ] Full regression: all prior backend/frontend/E2E suites still pass
```

## 16. Deferred Capabilities

Stem separation (native ACE-Step base tier or Demucs), export/zip packaging, audio mastering/loudness normalization, version diff/comparison, bulk delete, trash/undo, tags beyond favorite, Project-scoped AI Song Director entry point (already deferred in Phase 7/8 docs), any second LLM/agent framework, any infrastructure beyond the current local-first stack.
