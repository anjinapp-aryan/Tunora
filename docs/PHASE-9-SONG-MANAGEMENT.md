# Phase 9: Song Management (Rename, Favorite, Favorite Filter, Safe Whole-Song Delete)

This is the implementation record for the capability recommended by
`docs/PHASE-9-CAPABILITY-GAP-AUDIT.md` (that document is the audit; this one is
what was actually built, and is not a rewrite of it).

## 1. Scope

**In scope and built:** rename a Song, favorite/unfavorite a Song, filter the
Library by favorite (composable with the existing search and Project filter),
and permanently delete a Song (all its Versions, their Jobs, and their audio).

**Explicitly out of scope, not built:** Trash/undo delete, bulk delete,
export/ZIP, tags, playlists, version comparison, audio mastering, stem
separation, a new music provider, a second LLM or agent framework,
collaboration, authentication, cloud storage. None of these were needed to
implement rename/favorite/delete, and none were added.

**New dependencies added: zero.** Every part of this phase is CRUD on
Tunora's own schema plus one filesystem delete, exactly as the audit
predicted — see `docs/PHASE-9-CAPABILITY-GAP-AUDIT.md` section 7 (Reuse
Matrix).

## 2. Reuse decisions

- **`SongRepository`/`JobRepository`**: extended, not replaced. `update_song`
  and `delete_song` were added as new abstract methods alongside the existing
  `get_song`, `list_versions`, etc., implemented identically in both
  `InMemoryJobRepository` (tests) and `SqliteJobRepository` (production).
- **Migration framework** (`app/jobs/migrations.py`, `PRAGMA user_version`):
  reused unchanged. Added one new step, `4 -> 5` (`_to_v5`), following the
  exact additive/idempotent pattern of every prior step.
- **`app/songs/ids.py`** (`is_valid_id`): reused unchanged for validating
  song ids on every new method and route — no new id-validation logic.
- **Existing allowlisted API response pattern** (`app/api/schemas.py`):
  `is_favorite` was added to `SongSummaryResponse`/`SongDetailsResponse`
  exactly like every other field there; the same 404/422 mapping conventions
  from `routes_songs.py` were reused for `PATCH`/`DELETE`.
- **Phase 6 Project delete-confirmation UI** (`DeleteProjectButton` in
  `project-details.tsx`): the exact same "click to arm, then confirm inside an
  `alertdialog` with Cancel" shape was copied into `DeleteSongButton` in
  `song-details.tsx`, changing only the wording and the destination route.
- **Phase 6 Project Library filter pattern** (`project` query param,
  `NativeSelect`): the Favorites filter reuses the same
  "optional query param, composed with the existing `WHERE`/`AND` SQL
  fragments" shape as `project=`, just as a boolean instead of an id.

## 3. Rename

`PATCH /api/songs/{song_id}` with `{"title": "..."}`. Implemented in
`JobService.update_song` (`app/jobs/service.py`), which validates the id,
cleans the title with the existing `clean_title()` (strips control
characters and collapses whitespace only — it does **not** truncate), and
rejects outright (422, `InvalidSongUpdateError`) if the cleaned title is
empty or the original (pre-clean) input exceeds 80 characters. This
deliberately differs from `derive_title()`'s automatic, truncating behavior
used when a Song is first created from a generation prompt: an explicit user
rename is a deliberate action, so it is rejected rather than silently
mutated, mirroring the Project rename convention
(`JobService._clean_project_fields`).

Rename changes only `songs.title` and `songs.updated_at`. It never touches a
Version, a Job, `source_version_id`/`operation` lineage, the storage key, or
any provider metadata — verified directly by
`test_rename_persists_and_does_not_touch_versions_jobs_or_audio` and
`test_api_patch_creates_no_job_or_version`.

Frontend: `SongTitle` in `song-details.tsx` — an inline `[Edit Title]` control
that swaps to a text input with Save/Cancel (Escape also cancels). No modal,
no new dependency.

## 4. Favorite

Same `PATCH /api/songs/{song_id}` endpoint, with `{"is_favorite": true|false}`
(and both fields may be sent together in one request). `is_favorite` is a
plain `bool`; anything else (a string, a number, an array) is rejected by
Pydantic at the schema layer before it reaches the service, and a value that
somehow reaches `JobService.update_song` as a non-`bool` is rejected there
too (`InvalidSongUpdateError`) as defense in depth.

Favorite is completely independent of rename and of Delete: toggling it
creates no Version and no Job (`test_favorite_toggles_and_persists_independently_of_rename`).

Frontend: a star button next to the title on the Song page
(`song-favorite-toggle`) and one per row in the Library
(`favorite-toggle`), both `aria-pressed` and optimistically updated with
rollback-on-failure.

## 5. Favorite filter

`GET /api/songs?favorite=true|false`, implemented as one additional optional
SQL clause (`AND s.is_favorite = ?`) in `SqliteJobRepository.list_song_summaries`,
appended alongside (not replacing) the existing Project-filter and
search clauses — so `?favorite=true&project=X&q=text` all apply together,
exactly as required. Omitting `favorite` returns every Song, unaffected.
Verified in both directions: favorite composed with search, favorite composed
with Project, and Project alone still working exactly as it did before this
phase (`test_existing_project_filter_is_unaffected_by_the_favorite_filter`).

Frontend: a "Favorites only" checkbox in `LibraryList`, added to the existing
debounced-search/sort/Project-filter state, all passed straight through to
`listSongSummaries()`.

## 6. Delete

`DELETE /api/songs/{song_id}`. Deletes the Song, every Version of it, every
Job that produced one of those Versions, and every audio file any of those
Versions referenced. A source-of-truth statement: **the database is the
source of truth for whether a Song exists; the filesystem is best-effort
cleanup.** See sections 8 and 9 for exactly what that means under failure.

`JobRepository.delete_song(song_id) -> list[str]` (the list of audio keys to
clean up) runs one `BEGIN IMMEDIATE` transaction:

```sql
DELETE FROM jobs WHERE version_id IN (SELECT id FROM versions WHERE song_id = ?);
DELETE FROM versions WHERE song_id = ?;
DELETE FROM songs WHERE id = ?;
```

Order matters and was verified empirically before being written, not
assumed: `versions.source_version_id` is a self-referential foreign key with
no `ON DELETE` clause (Extend/Remix/Repaint lineage — see the parent
`CLAUDE.md`), so a naive per-row delete could hit a constraint violation
against a sibling version in the same batch. A standalone script against the
real migrated schema, with `PRAGMA foreign_keys = ON` and a 3-version lineage
chain (`v1 -> v2 EXTEND -> v3 REPAINT`) plus 2 jobs, confirmed that SQLite
checks foreign-key constraints at statement completion, not per row, so a
single multi-row `DELETE FROM versions WHERE song_id = ?` succeeds even
across an internal lineage chain, as long as jobs are deleted first. This is
why the delete order is jobs, then versions, then the song itself — never any
other order, and never mirroring `Project` deletion (`ON DELETE SET NULL`,
which is correct for Projects because they are non-destructive to Songs, and
wrong here because Versions and Jobs must actually be removed).

`JobService.delete_song` then deletes each collected audio key via
`AudioStorage.delete()`, outside the DB transaction, logging (not raising) on
any individual failure.

Frontend: `DeleteSongButton` in `song-details.tsx`, an exact structural copy
of the Phase 6 `DeleteProjectButton` pattern — click `[Delete Song]` to arm a
confirmation `alertdialog` with the destructive wording specified for this
phase, `[Cancel]`/`[Delete Song]`, a disabled/loading state during the
request, navigation to `/library` only on a real 204, and a safe error with
the page left intact on failure.

## 7. Database migration

`app/jobs/migrations.py`, step `4 -> 5` (current `LATEST_VERSION = 5`):

```python
def _to_v5(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(songs)")}
    if "is_favorite" not in columns:
        conn.execute("ALTER TABLE songs ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_songs_is_favorite ON songs(is_favorite)")
```

Additive, transactional (one `BEGIN IMMEDIATE` per step, like every other
migration step), and idempotent (the `IF NOT EXISTS`/column-presence checks
mean re-running it, or running it against a DB that already has the column,
is a no-op). Existing songs get `is_favorite = 0` (false) via the column
default — no backfill script needed. No separate favorites table was
introduced; a boolean column is sufficient for a single-user, per-Song flag.

The index exists because the favorite filter is a plain `WHERE` on this
column and Tunora's own convention (see the existing indexes created by
earlier migration steps) is to index a column that a Library query filters
on directly.

## 8. Filesystem deletion strategy

**DB-first, then best-effort file cleanup.** The database transaction
(section 6) commits completely before any file is touched. Only after that
commit does `JobService.delete_song` iterate the audio keys the transaction
returned and call `AudioStorage.delete()` on each.

This was chosen over the "quarantine" alternative sketched in the governing
prompt (move files aside, then delete on DB commit, then permanently delete
quarantined files) because quarantining adds a second piece of state (the
quarantine location, and what to do if quarantine itself fails or a process
crashes mid-quarantine) without removing the fundamental problem: a SQLite
transaction and a filesystem operation still cannot be one atomic unit, no
matter how many intermediate steps are added. DB-first with best-effort
cleanup gets the one guarantee that actually matters (Tunora's own records
are never inconsistent) with the least additional mechanism, in keeping with
the reuse-first/no-added-complexity-without-reason rule.

`LocalAudioStorage.delete(key)` (`app/storage/local.py`) reuses the existing
`get_path()` traversal/key validation before touching the filesystem, so it
rejects the same `../`, absolute-path, drive-letter, UNC, and malformed-key
inputs that `get_path()` already rejected for reads — verified directly by
`test_local_storage_delete_rejects_path_traversal_and_absolute_keys`. It
treats a missing file as success (not an error), which is what makes a
repeated or partially-failed delete safe to call again. After unlinking the
audio file it also removes the now-empty per-job directory
(`<root>/<job_id>/`), swallowing the error if the directory is not actually
empty or already gone.

## 9. Failure semantics

Two cases were reasoned about explicitly, as required, rather than assuming
atomicity that does not exist:

- **Case A — the DB delete succeeds, a file delete then fails** (disk error,
  permissions, the file already gone, an open file handle on Windows). The
  Song is already gone from Tunora's own data by the time any file is
  touched, so this cannot corrupt Tunora's state. The failure is logged
  (`logger.warning`, key and error only, never a full path) and swallowed;
  the caller sees the same success as if the file deletion had worked. The
  cost is a leaked file — an orphaned artifact taking up disk space that
  Tunora no longer references anywhere. This was accepted deliberately: a
  file that failed to delete becoming a permanently un-deletable Song would
  be a worse outcome for the user than an invisible leaked file. There is no
  retry and no background sweep for these leaks in this phase (see section
  14, Deferred).
- **Case B — an audio file is deleted, but the DB transaction then fails.**
  This is structurally impossible by construction: no file is ever touched
  until after `conn.commit()` returns successfully. If the DB transaction
  raises for any reason (a constraint violation, a lock timeout, a simulated
  failure), the `except BaseException: conn.rollback(); raise` block in
  `SqliteJobRepository.delete_song` ensures every row deleted in that
  transaction is restored, and `JobService.delete_song` never reaches the
  file-deletion loop because the exception propagates out of
  `self._repository.delete_song(song_id)` first. Verified directly by
  `test_delete_rolls_back_completely_if_the_db_transaction_fails`.

**Repeated delete is safe, by design, but not idempotent in the HTTP sense of
returning 204 twice.** The first `DELETE` succeeds (204). A second `DELETE`
on the same (now nonexistent) Song id returns 404 — a correct, honest "this
Song is not here," not a crash, not a silent no-op success, and not an
attempt to re-delete files that were already handled. This was verified for
both the repository layer (`SongNotFoundError` on the second call) and the
full HTTP route (`test_api_delete_removes_the_song_and_a_repeated_delete_is_a_safe_404`).

## 10. Security

- Every song id passed to `update_song`/`delete_song` is validated by the
  existing `is_valid_id()` before touching the database; the HTTP layer
  additionally constrains the path parameter with the existing
  `_ID_PATTERN` regex in `routes_songs.py`, shared with every other Song
  route.
- `AudioStorage.delete()` only ever receives keys the database itself
  returned for the Song being deleted (`SELECT audio_key FROM versions WHERE
  song_id = ?`), never a client-supplied path — there is no route or
  parameter anywhere that lets a caller name an arbitrary storage key.
  Combined with `delete()` reusing `get_path()`'s traversal checks, this
  makes cross-song audio deletion and path traversal both structurally
  unreachable, not just validated away — verified directly by
  `test_delete_never_touches_an_unrelated_songs_audio` and
  `test_local_storage_delete_cannot_reach_another_songs_directory_via_key_confusion`.
  A mutation that deliberately made the audio-key query ignore
  `song_id` was introduced and confirmed caught by the first test before
  being reverted (see section 11).
- API responses never include a filesystem path, the storage root, an
  ACE-Step task id, or the raw text of an internal exception — `PATCH`
  and `DELETE` reuse the exact same `SongDetailsResponse`/empty-204 shapes
  and 404/422 mapping as every other Song route, and
  `test_api_delete_response_leaks_no_internal_detail` asserts the delete
  response specifically.
- Malformed/traversal/SQL-injection-shaped ids, oversized/empty/whitespace
  titles, and an invalid `is_favorite` type are all rejected before they
  reach a SQL statement (parameterized throughout; no string-built SQL
  anywhere in this phase) — see the full parametrized test lists in
  `test_song_management.py`.

## 11. Testing

Backend: `backend/tests/songs/test_song_management.py` (53 tests) covering
rename (persistence, validation, malformed/unknown ids), favorite (toggle,
independence from rename, invalid type), the favorite filter (alone and
composed with search/Project), whole-song delete (DB cascade across a real
multi-version/multi-job Song, cross-song isolation, unknown/malformed ids,
repeated delete, transaction rollback), real-filesystem delete (real
`LocalAudioStorage` over `tmp_path`, Version 1/2/3 each with its own audio
file, all removed, an unrelated Song's file untouched, a storage failure not
failing the overall delete), `AudioStorage.delete()` security/idempotency,
the v4→v5 migration (existing DB, defaults, idempotent re-run), and the full
HTTP surface (`PATCH`/`DELETE`/`?favorite=` including validation and
leak-freedom). Full existing backend suite: **482 passed, 9 deselected
(smoke)** after this phase's changes — zero regressions.

**Mutation testing** — each of the 10 specified mutations was applied to a
backed-up copy of the affected file, confirmed to make the relevant test(s)
fail, then reverted and the full suite re-confirmed green:

1. Delete the Song but leave Versions — caught (10 tests failed).
2. Delete the Song but leave Jobs — caught (11 tests failed).
3. Delete DB rows but skip audio deletion — caught.
4. Delete audio but skip DB deletion — caught (broadly; this mutation guts
   the whole delete statement).
5. Favorite endpoint always returns true — caught.
6. Rename endpoint ignores the supplied title — caught (8 tests failed).
7. Favorite filter ignores the favorite parameter — caught (3 tests failed).
8. Delete wrong Song's audio (drop the `song_id` filter on the audio-key
   query) — caught by the cross-song-isolation test.
9. Remove the transaction boundary — the first attempt (deleting the
   explicit `BEGIN IMMEDIATE` line) was **not** caught, because Python's
   `sqlite3` module opens an implicit transaction before any DML statement
   regardless, so `conn.rollback()` still worked. A second, stronger mutation
   (committing after each of the three `DELETE` statements individually,
   genuinely removing single-transaction atomicity) **was** caught by the
   rollback test. Both attempts are recorded here because the first result
   is itself a real finding: the explicit `BEGIN IMMEDIATE` in this codebase
   exists for write-lock concurrency behavior, not for atomicity that Python
   sqlite3 already provides implicitly.
10. UI reports deletion success even when the API fails — caught by
    `song-details.test.tsx`'s failed-delete test (`push` was asserted never
    called; the mutation made it always navigate away).

Frontend: `library-list.test.tsx` (+4 tests: favorites filter alone and
composed with search, PATCH-backed toggle, optimistic-toggle rollback on
failure) and `song-details.test.tsx` (+7 tests: rename persistence, empty-title
rejection, Escape-cancels, favorite toggle, delete-then-navigate,
failed-delete-stays-and-shows-safe-error, cancel-sends-no-request). Full
frontend suite: **319 passed** (Vitest), `tsc --noEmit` clean, `eslint .`
clean, `next build` clean. The pre-existing, documented
`version-actions.test.tsx` real-timer flake (`CLAUDE.md`, "Testing
conventions") appeared once during a full-suite run and passed cleanly when
re-run alone — not a regression from this phase.

Real filesystem test (backend):
`test_delete_removes_real_audio_files_for_every_version_from_disk` creates a
Song with three real Versions/audio files via `LocalAudioStorage` over
`tmp_path`, deletes the Song, and asserts both the files and their per-job
directories are gone, while a sibling Song's file (from a separate test)
survives untouched.

## 12. E2E

Real-GPU backend smoke test:
`backend/tests/test_song_management_smoke.py` — a real ACE-Step generation
through the full HTTP stack, followed by `DELETE /api/songs/{id}`, asserting
the real audio file is physically gone from disk and every DB row (song,
version, job) is gone. Run against a live ACE-Step server on an RTX 5060 Ti:
**1 passed** (41s). The full existing smoke suite was also re-run afterward
against the same live server: **10 passed** (all real-GPU integration
tests), confirming no regression in Create/Extend/Remix/Repaint/Director/
Projects flows.

Real Playwright E2E, appended to `frontend/e2e/create-song.spec.ts`
following the file's established helper-reuse convention
(`generateRealSong`, `fetchCompletedJob`, `expectNoInternalLeak`,
unique `Date.now()`-suffixed titles):

- **Song management A — rename**: real generation, rename via the UI,
  refresh the page (title survives, proving it comes from the backend, not
  React state), then verify the Library shows and searches by the new title.
- **Song management B — favorite**: real generation, favorite from the Song
  page, verify it appears under the Library's Favorites filter, unfavorite
  from the Library row itself, verify it drops out of the filter.
- **Song management C — delete**: real generation with real audio, delete
  with confirmation from the Song page, verify navigation to the Library and
  absence there, verify `GET /api/songs/{id}`, `GET /api/jobs/{id}` and
  `GET /api/jobs/{id}/audio` all 404, and (with `E2E_STORAGE_ROOT` set)
  verify the real audio file and its per-job directory are physically gone
  from disk.

All three passed against the real stack (Next.js on a throwaway
`E2E_DIST_DIR`, FastAPI on a throwaway `E2E_BACKEND_PORT`/`TUNORA_DB_PATH`/
`TUNORA_STORAGE_ROOT`, real ACE-Step on :8001). The full existing Playwright
suite was re-run in the same session for full regression (see the final
report for the pass count at the time of that run).

## 13. Known limitations

- A file that fails to delete during Case A (section 9) is not retried and
  is not swept up later; it remains on disk, unreferenced, until an operator
  removes it manually. This is a deliberate, documented trade-off, not an
  oversight.
- The favorite filter is a single boolean; there is no "sort by favorited
  first" and no per-Project favorite scoping. Neither was requested.
- Deleting a Song does not check whether it belongs to a Project before
  deleting; it simply deletes the Song, which cascades naturally (a Project
  never owns audio or Versions, so nothing about a Project needs cleanup
  beyond the Song row itself, which `ON DELETE SET NULL` on
  `songs.project_id` already assumed for other reasons unrelated to this
  phase).

## 14. Deferred work

Everything explicitly out of scope for this phase (section 1) remains
deferred, plus: an audit or sweep job for orphaned audio files left behind by
a failed Case-A file deletion; a "recently deleted" trash/undo mechanism;
bulk operations across multiple Songs at once. None of these are needed by
the current product surface and none should be started without an explicit
new instruction, per this phase's stop condition.
