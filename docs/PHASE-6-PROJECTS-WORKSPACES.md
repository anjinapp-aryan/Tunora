# Phase 6 — Projects / Workspaces

## 1. Goal

Let users group Songs into named workspaces ("Projects") — e.g. an album or a soundtrack — without changing anything about how Songs, Versions or audio work. A Project is pure organizational metadata: it owns no audio and no Version, and it can never duplicate or move a file.

## 2. Reuse audit

| Need | Candidates considered | Decision |
|---|---|---|
| Project list / cards | none needed — same pattern as the Library (Phase 5A) | **REUSE** the existing Library list/card/search/sort pattern verbatim. |
| Dialogs / confirmation | `@base-ui/react` has no generated Dialog in this project (checked: only `alert`, `button`, `field`, `input`, `native-select`, `select`, `separator`, `switch`, `textarea`); a Radix/base-ui Dialog could be pulled in | **BUILD (inline panel), not a dialog.** Matches the existing Extend/Remix/Repaint pattern (Phase 5B): an inline `<form>`/confirmation block that opens under the button, not a modal. Adding a dialog primitive for two small forms and one confirmation is not justified. |
| Sortable/drag-drop lists | `@dnd-kit`, `react-beautiful-dnd` | **REJECTED.** The prompt explicitly excludes drag/drop unless free; nothing here makes it free, and buttons are sufficient for add/remove. |
| Tabs | `@base-ui/react/tabs` (not generated) | **NOT NEEDED.** Project Details is one page, not a tabbed view. |
| Add-existing-song picker | none needed | **REUSE** `listSongSummaries` (already built for the Library) as the search backend; no new search component. |
| Migration mechanism | Alembic, yoyo | **REUSE** the existing `PRAGMA user_version` stepped migration (`app/jobs/migrations.py`), as every prior phase did. |
| Project persistence | SQLAlchemy, a second SQLite file | **REUSE** the existing `sqlite3`-direct repository and the same database file; a `ProjectRepository` interface implemented by the same `SqliteJobRepository`/`InMemoryJobRepository` classes, exactly like `SongRepository`. |

No new dependency was added, front or back end.

## 3. Architecture decision: Song.project_id vs. a join table

**Decision: Option A — `songs.project_id` (nullable FK to `projects.id`), one Project per Song at a time.**

Why, weighed against a `ProjectSong` join table:
- **Product requirement as stated**: the example in the prompt ("Project: My Movie Album → Song: Opening Theme") and every UI mock is one Project per Song. Nothing in-scope asks for a Song in two Projects simultaneously.
- **Query simplicity**: "which Project is this Song in" and "which Songs are in this Project" are both a single indexed column lookup, not a join, and match the same grouped-query style already used for `list_song_summaries`.
- **Moving a Song between Projects** is one `UPDATE songs SET project_id = ?`, so it's trivially atomic and the audit trail (`updated_at`) falls out for free.
- **Migration/rollback risk**: adding one nullable column is strictly additive and trivially reversible; a join table adds a second table, a second set of constraints, and a second place uniqueness/ordering bugs can hide.
- **Deletion semantics fall out of SQLite itself**: `ON DELETE SET NULL` on the FK means deleting a Project unassigns its Songs as part of the single `DELETE` statement — there is no separate "unassign" step that could be forgotten or fail halfway.
- **Future paths stay open**: nothing here forecloses a join table later (multi-project membership, future AI Song Director cross-referencing, collaboration) — it would be an additive migration on top of this one, and `project_id` could even be kept as a "primary project" convenience column. Building the join table now, with no concrete requirement for many-to-many, would be exactly the premature complexity the reuse law warns against.

## 4. Project domain

```python
Project(id, name, description="", created_at, updated_at)
```
`id` is `proj-<uuid4>` (same shape/validation as `song-`/`ver-` ids, via `app/songs/ids.py`). `updated_at` changes only on rename/edit — never when a Song is added or removed. No cover image, theme, collaboration or sharing field (explicitly deferred).

`Song` gained one field: `project_id: Optional[str] = None`. Everything else about `Song`/`Version`/`VersionAudio` is unchanged.

## 5. Song ↔ Project relationship — see §3.

## 6. Database migration

Schema version 3 → 4 (`app/jobs/migrations.py::_to_v4`), same pattern as every prior step: one `BEGIN IMMEDIATE` transaction, column-existence-guarded (repeat-safe), no data rewritten:
```sql
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
ALTER TABLE songs ADD COLUMN project_id TEXT REFERENCES projects(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_songs_project_id ON songs(project_id);
```
Existing Songs get `project_id = NULL` (SQLite's default for a new nullable column with no `DEFAULT`) — **no fake Project is ever created**. Verified: a v3 database with an existing Song migrates to v4 with that Song's `project_id` unchanged as `NULL`, its title/audio intact, and running the migration twice is a no-op (idempotent, second run inserts nothing and applies no DDL twice).

## 7. API design

Mirrors the existing `/api/songs` conventions (same id-validation pattern, same error mapping, same allowlisted response builders):

```
GET    /api/projects              ?q=&sort=newest|oldest|title&limit=   -> { items: [{...Project, song_count}] }
POST   /api/projects              { name, description? }                -> Project
GET    /api/projects/{id}                                               -> { ...Project, songs: [...] }
PATCH  /api/projects/{id}         { name?, description? }                -> Project
DELETE /api/projects/{id}                                                -> 204
POST   /api/projects/{id}/songs          { song_id }                     -> the assigned song's project row
DELETE /api/projects/{id}/songs/{song_id}                                -> 204
```
No `PUT` for assignment: `POST .../songs` both assigns and moves (idempotent — see §9), so a separate "move" verb would be redundant. `GET /api/songs` gained an optional `?project=` filter (`none` = unassigned, or a Project id); `GET /api/songs` and `GET /api/songs/{id}` responses gained an optional `project: {id, name}` field. `POST /api/jobs` gained an optional `project_id` (only applies when creating a brand-new Song).

Validation: ids validated by the same `^[A-Za-z0-9][A-Za-z0-9-]*$`/≤80-char rule as Song/Version ids; malformed → 422; unknown → 404 (same message shape, no distinction visible to the client). Name required, ≤200 chars; description ≤2000 chars, optional. **Duplicate names are allowed** — no uniqueness constraint. This was a deliberate choice: nothing in the product requirements calls for unique names, users may legitimately want two Projects with the same name (e.g. drafts), and enforcing uniqueness would need locale-aware case folding for no clear benefit. SQL injection, oversized input, and HTML/script content are all handled the same way the rest of the API handles them (parameterized queries; the API returns JSON data, so HTML in a name/description is returned verbatim and is safe — the frontend, like React everywhere else in Tunora, renders it as text, never as markup).

## 8. UI design

Nav: `Create · Library · Projects`. New routes `/projects` and `/projects/{id}`, following the same page-shell pattern as `/library` and `/songs/{id}`. No dialog library: creating a Project, editing one, and adding a song are all inline `<form>` panels (open/close, `Escape`/Cancel, `aria-expanded`), the same shape as Phase 5B's Extend/Remix/Repaint panels. Deleting a Project needs an explicit second click on a confirmation block that states "Deleting this project will not delete its songs or audio." Song Details now shows "Project: <name>" (linked) when the Song has one; the Library row shows the same, and gained an optional Project filter dropdown (hidden entirely when there are no Projects yet, so it adds nothing to the common case). Create Song gained an optional Project `<select>` (hidden when there are no Projects), defaulting to "No Project" — existing behavior when it is left alone.

## 9. Project lifecycle / add-remove semantics

- **Add existing Song**: `POST /api/projects/{id}/songs {song_id}` sets `Song.project_id`. It is **idempotent**: adding the same Song to the same Project again is a no-op; adding it to a *different* Project **moves** it (last write wins) — this is intentional (see §3: one Project per Song). It never creates a Song, Version, Job or audio file — verified by asserting the job/version/file counts are unchanged before and after, and that the file bytes are identical.
- **Remove Song**: `DELETE /api/projects/{id}/songs/{song_id}` sets `project_id = NULL`, but only if the Song is currently in *that* Project — removing a Song from a Project it is not in is a safe no-op (not an error), which matters once moving between Projects is allowed.
- **Immutability across moves**: moving a Song between Projects (or unassigning it) changes only `Song.project_id` and `Song.updated_at`. A dedicated test creates three Versions on one Song, moves it A → B → unassigned, and asserts the Version ids, version numbers, audio keys, audio file hashes and lineage (`operation`/`source_version_id`) are byte-for-byte identical throughout.

## 10. Delete semantics

Deleting a Project deletes only the `projects` row. Its Songs, their Versions, and their audio are **never** touched — enforced at the database level by `ON DELETE SET NULL` on `songs.project_id` (§6), not by application code that could be skipped or get the order wrong. Tested directly: after deleting a Project, the Song still exists, still has the same Version rows, and its audio file is still readable with the same hash.

## 11. Testing (executed this session)

| Check | Result |
|---|---|
| Backend `pytest -m "not smoke"` | **VERIFIED** 375 passed (was 333 before this phase; +42 in `tests/projects/test_projects.py`) |
| Real-GPU smoke (`-m smoke`) | **VERIFIED** `tests/test_project_smoke.py` passed: one real ACE-Step generation, added to and removed from a Project, then the Project deleted — song/version/audio byte-identical throughout |
| Frontend Vitest | **VERIFIED** 278 passed (was 258) |
| tsc / ESLint / `next build` | **VERIFIED** clean; new routes `/projects`, `/projects/[projectId]` build |
| Real E2E (Next → FastAPI → ACE-Step) | **VERIFIED** 9/9, including the new Projects scenario (create → add existing song → open song → remove → Library still has it → delete project → song survives), one real generation reused throughout |
| Mutation checks | **VERIFIED**, all caught then reverted: (1) `assign_song_to_project` made a no-op — 7 tests failed; (2) `delete_project` made to also delete its Songs — 1 failed; (3) Project `song_count` hardcoded to 0 — 4 failed; (4) `remove_song_from_project` made a no-op — 2 failed; (5) `list_project_songs` returning every Song regardless of Project (cross-project leak) — 15 failed; (6) migration v4 skipped — 32 failed; (7) frontend: the add-song picker ignoring which Songs are already in the Project — 1 failed. Final suites pass again after every revert. |
| Responsive (375 / 768 / desktop) | **VERIFIED** for the Project card (375px) and the Song page with a Project link (768/375) in the real E2E |

Existing tests changed for an intentional contract reason: `create-song-form.test.tsx` and `library-list.test.tsx` now route their fetch mocks by URL (the components additionally call `GET /api/projects` to populate the optional Project field/filter); no assertion's *meaning* changed, only how the mock intercepts the extra call. One assertion (`project_id: null` in the POSTed job body) was added because the request body legitimately gained a field.

**Known pre-existing flake, unrelated to this phase**: `version-actions.test.tsx > "selects the new version, moves Latest..."` (a Phase 5B test using a real 2-second poll interval) intermittently times out only when the whole Vitest suite runs under heavy parallel load — confirmed by running it standalone (always passes) and by reproducing the same flake rate on the pre-Phase-6 code. Not modified.

## 12. Security

Verified in `tests/projects/test_projects.py`: SQL injection in a Project name and in the search query (stored/matched literally, table intact afterward); malformed/oversized/traversal-shaped ids on every route (422, nothing looked up); unknown ids (404, same message as malformed); cross-project isolation (two Projects, each only ever returns its own Songs); duplicate/repeated assignment (idempotent, not an error); no filesystem or DB path, provider name, job id, or `/v1/audio` in any Project/Song response.

## 13. Performance / query strategy

`GET /api/projects` computes each Project's `song_count` with one query with a correlated `COUNT` subquery — never one query per Project (a dedicated test wraps the repository's connection and asserts at most one non-PRAGMA statement runs for a list of 12 Projects). `GET /api/projects/{id}` loads its Songs with one `LEFT JOIN ... GROUP BY` for the version count and latest version number — no per-Song follow-up query. `GET /api/songs` with a `?project=` filter reuses the existing single-query Library listing with one extra `WHERE` clause; the Song → Project name join for the Library and Song Details is a single batched `get_projects([...])` lookup, not one query per Song.

## 14. Known limitations

- One Project per Song (see §3): a Song cannot belong to two Projects at once by design, not oversight.
- No cover image, theme, timeline, collaboration, sharing, or permissions on a Project — explicitly deferred.
- Project name uniqueness is not enforced (§7); two Projects can have the same name.
- The add-existing-song search reuses the Library's title/prompt substring search; it is not indexed for full-text search at scale (matches the existing Library's own limitation).
- The E2E database is a throwaway file that accumulates rows across runs; the new Projects E2E test uses a timestamped title/name to avoid colliding with leftovers from earlier runs of itself.

## 15. Deferred (explicitly out of scope for this phase)

AI Song Director, natural-language project orchestration, automatic lyric generation, project collaboration/sharing/permissions, user accounts, cloud sync, project cover art, project timeline, music video, distribution/publishing, additional music providers, advanced waveform/drag-drop timeline editing.
