# Tunora — Phase 3, Step 13: Audio Storage

## 1. Reuse Audit

| Candidate | License | Verdict | Reasoning |
|---|---|---|---|
| **`pathlib` + `shutil` + `os`** (stdlib) | stdlib | ✅ **REUSE (winner)** | Everything this step actually needs — safe path joining, containment checks (`Path.relative_to`), copying, atomic rename (`os.replace`) — already exists in the standard library, cross-platform (Windows included), zero new dependency. |
| **`fsspec`** | BSD-3-Clause | 🟡 Legitimate future candidate, not adopted now | Genuinely designed for exactly this "swap local/S3/GCS behind one API" problem, and would be the reuse-first choice *if and when* Tunora actually implements a second (e.g. S3) backend — at that point, adopting `fsspec`'s `S3FileSystem` would likely beat hand-writing an `S3AudioStorage` with `boto3`. Not adopted today because the MVP has exactly one backend to support; pulling in `fsspec`'s broader surface (async, caching, glob, many filesystem drivers) now would be scope Tunora doesn't need yet, and a 3-method hand-written interface costs less than the dependency. Re-evaluate at the point object storage is actually built (see §16). |
| **`soundfile`** | BSD-3-Clause (already a locked-stack dependency) | Not used in this step | Could validate that a stored file is genuinely decodable audio, but `libsndfile`'s mp3 support varies by build/version, and ACE-Step emits mp3/wav/flac/ogg/opus/aac — format-specific decode validation would be unreliable across that set without further research. This step validates existence/non-emptiness/basic readability only (see §12); deeper validation is a documented deferral, not silently skipped. |
| **MinIO** | AGPLv3, project archived | ❌ REJECT (reaffirmed) | Already rejected project-wide in `docs/PHASE-1-DECISIONS.md` #7 and `docs/COST-AUDIT.md` — archived April 2026, AGPLv3 licensed. Nothing in this step changes that; local filesystem is what the MVP actually needs. |
| **AWS S3 / other cloud object storage** | n/a | ❌ REJECT (out of scope) | Violates the zero-mandatory-cost, local-first policy for core functionality; no demonstrated need exists yet per `NON-GOALS.md`. |

**Decision:** BUILD a small `AudioStorage` abstraction (3 methods) with one concrete implementation, `LocalAudioStorage`, using only the Python standard library. No new dependency was added in this step.

## 2. Storage Decision

`LocalAudioStorage` persists files under a configurable root (`TUNORA_STORAGE_ROOT` env var, default `./data/audio`) — never a hardcoded `I:\Tunora\...` path.

## 3. Storage Abstraction (`app/storage/base.py`)

```python
class AudioStorage(ABC):
    def save(self, source_path, *, job_id: str, media_type: str) -> StoredAudio: ...
    def get_path(self, key: str) -> Path: ...
    def exists(self, key: str) -> bool: ...
```

No `delete()` — nothing in Phase 3 needs it yet; adding it now would be speculative. `StoredAudio` is a frozen dataclass: `key`, `absolute_path`, `filename`, `media_type`, `size_bytes`. `JobService` (and everything above it) depends only on this interface, never on `LocalAudioStorage` directly — see §11 for the dependency-direction test.

## 4. Local Implementation (`app/storage/local.py`)

`LocalAudioStorage(root)`. Uses `pathlib.Path` throughout (no string concatenation), `shutil.copyfile` + `os.replace` for the write, and `Path.relative_to` for containment checks. The root directory is created (`mkdir(parents=True, exist_ok=True)`) if missing.

## 5. Directory Structure

```
<TUNORA_STORAGE_ROOT>/
  <job_id>/
    <job_id>.<ext>
```

One directory per Tunora job id (never ACE-Step's own temp directory structure or filename). Chosen over a flat `<job_id>.<ext>` layout because a per-job directory leaves room for future companion artifacts (cover art, stems, waveform peaks — all named for later phases, not built now) without a renaming scheme change. Properties satisfied: deterministic (same job id → same path, verified by test), collision-resistant (job ids are unique — verified by a two-jobs-no-collision test), easy to inspect/back up (one folder = one job's artifacts), easy to migrate (copy the folder), independent of ACE-Step's own layout (its temp filename is discarded entirely).

## 6. File Naming

The stored filename is always `<job_id>.<ext>` — the extension is taken from ACE-Step's actual output file (trusted, since it comes from Step 11's provider, not user input), but the base name is always Tunora's own job id, never ACE-Step's UUID-based temp filename. This satisfies "the generated artifact should be traceable to its Tunora job" directly by construction — the filename *is* the job id.

## 7. Security / Path Traversal Protection

`get_path(key)` rejects, before any filesystem access:
- empty keys,
- keys containing a `..` path segment (checked via `PurePosixPath(key).parts`, after normalizing `\` to `/` so this catches both Windows- and POSIX-style traversal attempts regardless of host OS),
- keys that look absolute in either style — a leading `/` or a `:` (drive letter) — specifically because `Path("/etc/passwd").is_absolute()` returns `False` on Windows, which would otherwise let a POSIX-style absolute path slip through `pathlib`'s own absolute-path check on a Windows host.

After that, the candidate path is resolved and checked with `Path.relative_to(storage_root)` as a second, independent containment guard (defense in depth — even if the string-level checks above had a gap, a symlink or `..`-free-but-still-escaping construction would still be caught here). `save()` never accepts a client-supplied path at all — its `source_path` always comes from `GenerationResult.audio_path`, produced internally by Step 11's provider, never from an HTTP request.

Covered by 15 dedicated tests in `tests/storage/test_local_audio_storage.py`, including parametrized Windows-drive-letter, UNC-path, POSIX-absolute-path, and multi-segment `..`-traversal attempts.

## 8. Atomic-Write Decision

**Implemented.** `save()` copies the source into a temp file (`.{filename}.tmp-{uuid4}`) inside the *destination* job directory, then calls `os.replace(tmp_path, final_path)`. This is atomic even when the source file and the storage root live on different filesystems/drives (a plain `os.replace(source, final)` would silently fall back to non-atomic copy+delete across filesystems on some platforms — copying into the same directory as the final destination first, then renaming, avoids that entirely since the rename step is always same-filesystem). A reader can therefore never observe a partially-written file at the canonical path. Verified by `test_save_is_atomic_no_temp_file_left_behind` (no leftover temp file after a 1MB save) and implicitly by every other save-then-read test.

## 9. Metadata

| Field | Status |
|---|---|
| Storage key (`<job_id>/<job_id>.<ext>`) | **Required now** — the only thing the public API exposes for locating the file. |
| Filename | **Required now** — needed for a future download endpoint's `Content-Disposition`. |
| Media type | **Required now** — needed to serve the file with a correct `Content-Type` later; guessed via stdlib `mimetypes` (see `app/storage/media_types.py`), not stored by ACE-Step in a form Tunora trusts as canonical. |
| Byte size | **Required now** — cheap to obtain (`Path.stat().st_size`) and immediately useful for validating a non-empty result. |
| Duration | **Useful later, partially available now** — already returned by the provider's `GenerationResult.duration` (Step 11) and stored alongside the audio metadata in `job.result`, not duplicated inside `StoredAudio` itself (storage doesn't need to know about audio duration — that's provider/domain metadata, not a storage concern). |
| Checksum | **Intentionally deferred** — no current consumer needs integrity verification; add if/when a real corruption case or a sync/migration feature requires it. |
| Absolute filesystem path | **Required internally, deliberately never public** — kept in the persisted `Job.result` (SQLite) for internal use (a future download route resolving bytes), but stripped by `JobResponse._public_result()` before crossing the HTTP boundary (§13). |

No full media catalog (tags, waveform peaks, transcoded variants, etc.) is built — that's Library/Player scope for a later phase.

## 10. SQLite Relationship

Audio bytes are never stored in SQLite. `Job.result` (a JSON column via `SqliteJobRepository`, unchanged mechanism from Step 12) holds only the reference: `{"audio": {"key", "absolute_path", "filename", "media_type", "size_bytes"}, "duration", "metadata"}`. The actual bytes live exclusively under `TUNORA_STORAGE_ROOT` on the filesystem.

## 11. Provider Boundary

`AudioStorage` has no import of, or knowledge about, `AceStepMusicGenerationProvider`, `httpx`, or any ACE-Step response shape — confirmed by inspection of `app/storage/*.py` (no such import exists). The dependency direction is exactly as specified:

```
JobService → MusicGenerationProvider → AceStepMusicGenerationProvider → ACE-Step API
JobService → AudioStorage → LocalAudioStorage → local filesystem
```

`JobService._apply_provider_status()` is the only place that connects the two: it takes `GenerationResult.audio_path` (from the provider) and hands it to `AudioStorage.save()` — a plain string/`Path` argument, not an ACE-Step-shaped object.

## 12. Error Handling

| Condition | Behavior |
|---|---|
| Source artifact missing | `SourceArtifactMissingError` → `JobService` marks the job `FAILED` with "Failed to store generated audio: ...". Job is never marked `COMPLETED`. |
| Source artifact empty (0 bytes) | `SourceArtifactEmptyError` → same as above. |
| Source artifact unreadable (basic 1-byte read fails) | `SourceArtifactUnreadableError` → same as above. |
| Storage write fails (disk/permission/etc., any `OSError` during copy or rename) | `StorageWriteError` → same as above. |
| Invalid/traversal storage key passed to `get_path`/`exists` | `PathTraversalError` (an `InvalidStorageKeyError` subclass) — `exists()` catches this internally and returns `False` rather than raising, since "does this weird key exist" is a reasonable question to answer `False` to; `get_path()` raises, since resolving a bad key to a path is an error, not a `None`. |
| Destination collision (same `job_id` saved twice) | Not an error — `os.replace` overwrites atomically. Treated as idempotent by design (job ids are unique per generation, so this only happens on an intentional re-save), verified by `test_save_path_generation_is_deterministic_for_the_same_job_id`. |

In every failure case, `JobService` transitions the job to `FAILED` via the same `_fail()` helper Step 12 already uses — no new error-handling path was introduced at the job-lifecycle level, and **`COMPLETED` is only ever set after `AudioStorage.save()` returns successfully** (see the code path in `app/jobs/service.py::_apply_provider_status`), which is what guarantees no partial artifact is ever reported as complete.

## 13. API

`GET /api/jobs/{job_id}` (unchanged endpoint from Step 12) now returns, once `COMPLETED`:

```json
{
  "id": "tunora-...",
  "status": "COMPLETED",
  "result": {
    "audio": {
      "key": "tunora-.../tunora-....mp3",
      "filename": "tunora-....mp3",
      "media_type": "audio/mpeg",
      "size_bytes": 160940
    },
    "duration": 10.0,
    "metadata": { "bpm": 125, "genres": "...", "key_scale": "...", "time_signature": "..." }
  }
}
```

`absolute_path` (present in the internal `Job.result` dict for a future download route to use) is stripped by `JobResponse._public_result()` before serialization — confirmed by `test_get_path_...`-adjacent API tests and the real integration test's explicit `"absolute_path" not in audio` assertion. No arbitrary filesystem path or ACE-Step-specific field (`task_id`, `/v1/audio?path=`, its `wrap_response` envelope) reaches the client.

## 14. Tests

**94/94 mocked/unit tests PASSED** (`uv run pytest tests -m "not smoke"`), including:
- 18 dedicated `LocalAudioStorage` tests (`tests/storage/test_local_audio_storage.py`): save/retrieve/exists, correct byte size and media type, deterministic path generation, two jobs not colliding, missing/empty/directory-as-source artifacts, path-traversal and absolute-path rejection (Windows drive letter, UNC path, POSIX absolute, multi-segment `..`), empty-key rejection, storage-root containment, atomic-write (no leftover temp file), a 1MB and a 5MB file, and auto-creation of a missing storage root.
- 6 service-level storage-integration tests (`tests/jobs/test_service_storage_integration.py`, real `LocalAudioStorage` + `FakeProvider`): successful save-through-completion, ACE-Step's temp path never appearing in the persisted result, a storage failure producing a clean `FAILED` job (not `COMPLETED`), a simulated storage-write exception likewise never producing a `COMPLETED` job, and Step 12's own state transitions (`SUBMITTED→QUEUED→RUNNING`) still working with storage wired in.
- 1 restart test (`tests/jobs/test_storage_restart.py`): a completed job's SQLite record *and* its physical audio file both survive fresh `SqliteJobRepository`/`LocalAudioStorage` instances pointed at the same files (simulated process restart).
- Existing Step 11/12 suites (provider, state machine, repository, API) all still pass unmodified in behavior, confirming no regression.

## 15. Real Integration Test

**VERIFIED — PASSED** (`tests/test_job_lifecycle_smoke.py::test_real_job_lifecycle_end_to_end`, real local ACE-Step API server, RTX 5060 Ti). Flow: `POST /api/jobs` (10s instrumental) → real ACE-Step generation → `COMPLETED` → `GET /api/jobs/{id}` returns `result.audio.key == "<job_id>/<job_id>.mp3"`, no `absolute_path` in the public response. Resolved via `storage.get_path(key)`: file exists, non-empty, byte size matches `result.audio.size_bytes` exactly, and the resolved path is contained under the configured storage root (`tmp_path/audio`), not ACE-Step's own temp directory.

**Real bug found and fixed only by running this test, not by inspection**: the first run failed on `assert "/v1/audio" not in json.dumps(final)` — `GenerationResult.metadata` (from Step 11's `AceStepMusicGenerationProvider`) carries its own `audio_url`/`audio_paths` fields pointing at ACE-Step's `/v1/audio?path=` route, and `JobService` was persisting `result.metadata` verbatim, leaking that route through the public API. Fixed by stripping `{"audio_url", "audio_paths"}` from provider metadata in `JobService` before persisting (`app/jobs/service.py::_strip_provider_transport_metadata`) — those fields described how the *provider* served the file before Tunora had its own storage; they're stale once `AudioStorage` takes over. Added a regression test (`test_provider_transport_metadata_is_stripped_from_persisted_result`) and reran both this test and Step 11/12's own smoke tests to confirm no regression (all passed after the fix).

## 16. Restart / Persistence Test (real filesystem, not just mocked)

Covered by the mocked `test_storage_restart.py` above (SQLite + local filesystem are both real in that test — only the provider is fake, since re-running a real GPU generation purely to test restart semantics would waste GPU time for no additional signal beyond what's already proven in §15). The real integration test in §15 additionally proves the whole real-generation path once, end to end.

## Future Migration Path to Object Storage

```
AudioStorage (unchanged interface)
   ├── LocalAudioStorage   (today)
   ├── S3AudioStorage      (future — likely via fsspec's S3FileSystem, per §1)
   └── MinioAudioStorage   (future, only if MinIO's AGPLv3/archived status is ever
                             resolved — currently rejected project-wide)
```

Adding a real object-storage backend later requires: (1) a fresh reuse audit at that time (per the Reuse-First Law — don't assume `fsspec` is still the best answer months from now), (2) one new class implementing the same three `AudioStorage` methods, (3) swapping the concrete class constructed in `app/main.py`'s `lifespan`. `JobService` requires zero changes, by construction — proven today by `LocalAudioStorage` being the only thing `JobService` has ever touched through the `AudioStorage` interface, never directly.

## Known Limitations

1. **No deep audio-content validation** — `save()` confirms the source exists, is non-empty, and is minimally readable (opens and reads 1 byte), but does not decode the audio to confirm it's not corrupted mid-stream. Deferred per §1 (format-specific decode validation across mp3/wav/flac/ogg/opus/aac was judged unreliable to build correctly in this step without further research into `libsndfile`'s current format support).
2. **No storage quota/cleanup** — nothing deletes old artifacts; disk usage grows unbounded. Out of scope for Phase 3 (single-developer-machine POC); a real retention/cleanup policy is Library-phase or later scope.
3. **`delete()` is not implemented** — nothing in Phase 3 needs to remove a stored artifact yet.
4. **Collision handling is "last write wins," not versioned** — acceptable because Tunora's own job ids are unique per generation; if a future feature ever calls `save()` twice for the same `job_id` intentionally (unlikely given the data model), the second write silently replaces the first. Not a concern today since regeneration always creates a new `Job`/`Version` per `ARCHITECTURE-PRINCIPLES.md`, never re-saves into an existing job's slot.
5. **Persistence-failure error messages surface the raw exception text** (`str(exc)`) inside `Job.error`, which is intended for the eventual UI's benefit but has not been scrubbed for user-friendliness or examined for accidental information disclosure (e.g. a raw local path in an `OSError` message) — worth a pass when a real UI consumes this field.
