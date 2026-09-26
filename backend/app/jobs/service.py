"""JobService — orchestrates Tunora's job lifecycle over a provider + repository + storage.

Dependency direction (must stay this way):
    JobService -> JobRepository
    JobService -> MusicGenerationProvider
    JobService -> AudioStorage

JobService never speaks HTTP and never knows ACE-Step's response shapes —
that stays inside the provider (see app/providers/ace_step.py). It likewise
never knows whether AudioStorage is local disk, S3, or anything else — see
app/storage/local.py.
"""

from __future__ import annotations

import asyncio
import math
import logging
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Optional

from app.jobs.errors import (
    AudioIntegrityError,
    AudioNotAvailableError,
    InvalidTransitionError,
    JobNotFoundError,
)
from app.jobs.models import TERMINAL_STATUSES, Job, JobStatus, utcnow
from app.jobs.repository import JobRepository
from app.jobs.state_machine import validate_transition
from app.jobs.titles import clean_title, derive_title
from app.projects.errors import InvalidProjectError, ProjectNotFoundError
from app.projects.models import Project, ProjectSongEntry, ProjectSummary
from app.providers.base import GenerationRequest, JobState, MusicGenerationProvider
from app.providers.errors import ProviderError, UnsupportedOperationError
from app.songs import operations as ops
from app.songs.errors import (
    InvalidIdError,
    InvalidOperationError,
    InvalidSongUpdateError,
    SongNotFoundError,
    SourceAudioUnavailableError,
    SourceVersionNotFoundError,
)
from app.songs.ids import is_valid_id, new_project_id, new_song_id, new_version_id
from app.songs.models import Song, SongSummary, Version, VersionAudio, VersionEntry
from app.songs.repository import PROJECT_FILTER_NONE
from app.storage.base import AudioStorage
from app.storage.errors import StorageError
from app.storage.filenames import safe_audio_filename
from app.storage.media_types import guess_media_type

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 3.0
DEFAULT_MAX_POLL_SECONDS = 1800.0  # 30 minutes
_SEARCH_WINDOW = 500

# GenerationResult.metadata may carry provider-transport details that only
# made sense before Tunora had its own storage (e.g. AceStepMusicGenerationProvider
# adds "audio_url"/"audio_paths" pointing at ACE-Step's own `/v1/audio?path=`
# route -- see app/providers/ace_step.py). Once Tunora copies the file into
# its own AudioStorage, those provider-owned locators are stale/irrelevant
# and must not leak into the public job result -- discovered via the real
# Step 13 integration test, not by inspection alone.
_PROVIDER_TRANSPORT_METADATA_KEYS = frozenset({"audio_url", "audio_paths"})


def _strip_provider_transport_metadata(metadata: dict) -> dict:
    return {k: v for k, v in metadata.items() if k not in _PROVIDER_TRANSPORT_METADATA_KEYS}


@dataclass(frozen=True)
class AudioResource:
    """A verified, servable audio artifact for one COMPLETED job."""

    path: Path
    media_type: str
    filename: str
    size_bytes: int


def _valid_seconds(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def _expected_duration(request: GenerationRequest) -> Optional[float]:
    """Length of a creative operation's output when the provider does not report it
    (ACE-Step returns "N/A" for cover/repaint). Verified locally: extend = source + extension,
    remix and repaint keep the source length (docs/PHASE-5B-EXTEND-REMIX-REPAINT.md)."""

    if request.operation == "EXTEND" and request.source_duration and request.extend_seconds:
        return request.source_duration + request.extend_seconds
    if request.operation in ("REMIX", "REPAINT"):
        return request.source_duration
    return None


def _base_spec(request: GenerationRequest) -> GenerationRequest:
    """The reproducible generation inputs of a version, without operation plumbing."""

    return GenerationRequest(
        prompt=request.prompt,
        lyrics=request.lyrics,
        language=request.language,
        duration=request.duration,
        seed=request.seed,
        instrumental=request.instrumental,
        batch_size=request.batch_size,
    )


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InvalidOperationError(f"{name} must be a number.")
    return float(value)


def _default_id_factory() -> str:
    return f"tunora-{uuid.uuid4()}"


class JobService:
    """Owns Tunora's job lifecycle: create -> submit -> poll -> terminal state."""

    def __init__(
        self,
        repository: JobRepository,
        provider: MusicGenerationProvider,
        storage: AudioStorage,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        max_poll_seconds: float = DEFAULT_MAX_POLL_SECONDS,
        id_factory: Callable[[], str] = _default_id_factory,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._storage = storage
        self._poll_interval_seconds = poll_interval_seconds
        self._max_poll_seconds = max_poll_seconds
        self._polling: set[str] = set()  # job ids with an active polling loop (one per job)
        self._id_factory = id_factory

    # -- lifecycle -----------------------------------------------------------

    async def create_and_submit(
        self,
        request: GenerationRequest,
        title: Optional[str] = None,
        song_id: Optional[str] = None,
        *,
        source_version_id: Optional[str] = None,
        operation_params: Optional[dict] = None,
        project_id: Optional[str] = None,
    ) -> Job:
        """Create a Job (and its Version, and a new Song unless `song_id` names an
        existing one) atomically, then submit it to the provider.

        `project_id` only applies to a brand-new Song (organizational metadata,
        Phase 6); it is ignored when `song_id` names an existing one. The database
        transaction commits BEFORE the provider is called, so no transaction is
        ever held open across ACE-Step. Never raises for provider failures: the
        returned Job's status/error reflect the outcome. Raises SongNotFoundError /
        InvalidIdError for a bad `song_id`, ProjectNotFoundError for a bad `project_id`.
        """

        if request.operation not in self._provider.supported_operations:
            raise UnsupportedOperationError(f"Operation {request.operation!r} is not supported by this provider")

        if song_id is not None:
            if not is_valid_id(song_id):
                raise InvalidIdError("Malformed song id.")
            song = self._repository.get_song(song_id)
            if song is None:
                raise SongNotFoundError(song_id)
            new_song = None
            display_title = song.title
        else:
            if project_id is not None:
                self.get_project(project_id)  # 404s a bad/unknown project before anything is created
            display_title = derive_title(request.prompt, title)
            new_song = Song(id=new_song_id(), title=display_title, project_id=project_id)
            song_id = new_song.id

        job = Job(
            id=self._id_factory(),
            provider=self._provider.name,
            status=JobStatus.CREATED,
            # Stored job/version records never keep the source file path; only the provider call does.
            request=replace(request, source_audio_path=None),
            title=display_title,
        )
        version = self._repository.create_generation(
            new_song=new_song,
            version=Version(
                id=new_version_id(),
                song_id=song_id,
                spec=_base_spec(request),
                provider=self._provider.name,
                operation=request.operation,
                source_version_id=source_version_id,
                operation_params=operation_params,
            ),
            job=job,
        )
        logger.info(
            "generation created song_id=%s version_id=%s version_number=%s job_id=%s",
            song_id, version.id, version.version_number, job.id,
        )

        try:
            provider_job = await self._provider.generate(request)
        except ProviderError as exc:
            self._fail(job, str(exc))
            return job

        job.provider_job_id = provider_job.job_id
        self._transition(job, JobStatus.SUBMITTED)
        job.submitted_at = utcnow()
        self._repository.update(job)
        return job

    async def poll_once(self, job_id: str) -> Job:
        """Refresh one job's status from the provider. Idempotent; safe to call
        repeatedly, including after the job has already reached a terminal state.
        """

        job = self._repository.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        if job.status in TERMINAL_STATUSES:
            return job

        try:
            provider_status = await self._provider.get_status(job.provider_job_id)
        except ProviderError as exc:
            self._fail(job, str(exc))
            return job

        try:
            return await self._apply_provider_status(job, provider_status.status, provider_status.message)
        except InvalidTransitionError as exc:
            # A provider reporting a state that doesn't fit our state machine
            # (e.g. going backwards) is treated as a job failure, not a crash
            # of the polling loop — see docs/PHASE-3-JOB-LIFECYCLE.md.
            self._fail(job, f"Invalid state reported by provider: {exc}")
            return job

    async def _apply_provider_status(
        self, job: Job, provider_state: JobState, message: Optional[str]
    ) -> Job:
        if provider_state == JobState.FAILED:
            self._fail(job, message or "Provider reported failure with no detail")
            return job

        if provider_state == JobState.SUCCEEDED:
            try:
                result = await self._provider.get_result(job.provider_job_id)
            except ProviderError as exc:
                self._fail(job, str(exc))
                return job

            # The provider's audio_path is ACE-Step's own temporary output --
            # never persisted as-is. It must survive into Tunora-owned
            # storage before the job may be marked COMPLETED; a storage
            # failure here fails the job instead (no partial artifact is
            # ever reported as COMPLETED).
            media_type = guess_media_type(result.audio_path)
            try:
                stored = self._storage.save(result.audio_path, job_id=job.id, media_type=media_type)
            except StorageError as exc:
                self._fail(job, f"Failed to store generated audio: {exc}")
                return job

            duration = result.duration if _valid_seconds(result.duration) else _expected_duration(job.request)
            self._transition(job, JobStatus.COMPLETED)
            job.started_at = job.started_at or utcnow()
            job.completed_at = utcnow()
            job.result = {
                "audio": {
                    "key": stored.key,
                    "absolute_path": stored.absolute_path,
                    "filename": stored.filename,
                    "media_type": stored.media_type,
                    "size_bytes": stored.size_bytes,
                },
                "duration": duration,
                "metadata": _strip_provider_transport_metadata(result.metadata),
            }
            # Job row + the Version's audio reference commit together.
            self._repository.complete_job(
                job,
                VersionAudio(
                    key=stored.key,
                    filename=stored.filename,
                    media_type=stored.media_type,
                    size_bytes=stored.size_bytes,
                    duration=duration,
                ),
            )
            return job

        if provider_state == JobState.RUNNING:
            if job.status != JobStatus.RUNNING:
                self._transition(job, JobStatus.RUNNING)
                job.started_at = job.started_at or utcnow()
                self._repository.update(job)
            return job

        if provider_state == JobState.QUEUED:
            if job.status != JobStatus.QUEUED:
                self._transition(job, JobStatus.QUEUED)
                self._repository.update(job)
            return job

        self._fail(job, f"Unrecognized provider status: {provider_state!r}")
        return job

    async def run_until_terminal(self, job_id: str) -> Job:
        """Poll a job to a terminal state, sleeping between polls.

        Enforces Tunora's own timeout ceiling (independent of ACE-Step's own
        server-side timeout) so a stuck job cannot poll forever. At most one loop polls a given
        job at a time in this process: a second call returns the job's current state immediately.
        """

        if job_id in self._polling:
            return self.get(job_id)
        self._polling.add(job_id)
        try:
            return await self._poll_to_terminal(job_id)
        finally:
            self._polling.discard(job_id)

    async def _poll_to_terminal(self, job_id: str) -> Job:
        elapsed = 0.0
        while True:
            job = await self.poll_once(job_id)
            if job.status in TERMINAL_STATUSES:
                return job
            if elapsed >= self._max_poll_seconds:
                job = self._repository.get(job_id)
                if job is not None and job.status not in TERMINAL_STATUSES:
                    self._fail(job, f"Timed out after {self._max_poll_seconds}s waiting for provider")
                return job
            await asyncio.sleep(self._poll_interval_seconds)
            elapsed += self._poll_interval_seconds

    async def recover_unfinished_jobs(self) -> dict[str, int]:
        """Resume every job a previous process left unfinished (Phase 16). Called once at startup.

        Only the persisted `provider_job_id` is used: nothing is ever resubmitted, so no second
        provider job, Version or audio file can result. A job that was never submitted (no
        provider id) is failed. Each job is recovered independently: one bad job cannot stop the
        others. Returns counts of what happened.
        """

        unfinished = self._repository.list_unfinished()
        summary = {"found": len(unfinished), "resumed": 0, "completed": 0, "failed": 0, "unsubmitted": 0}
        logger.info("job recovery started: %d unfinished job(s)", len(unfinished))
        resumable: list[Job] = []
        for job in unfinished:
            if not job.provider_job_id:
                self._fail(job, "Recovery: the job was never submitted to the provider.")
                summary["unsubmitted"] += 1
                logger.warning("job recovery: job_id=%s was never submitted; marked FAILED", job.id)
                continue
            try:
                self._provider.register_recovered_job(job.provider_job_id, job.request.operation)
            except Exception:  # noqa: BLE001 -- an unexpected provider bug must not stop other jobs
                logger.exception("job recovery: could not restore provider state for job_id=%s", job.id)
                self._fail(job, "Recovery: the provider state could not be restored.")
                summary["failed"] += 1
                continue
            resumable.append(job)

        outcomes = await asyncio.gather(*(self._recover_one(job) for job in resumable))
        summary["resumed"] = len(resumable)
        summary["completed"] = sum(1 for status in outcomes if status == JobStatus.COMPLETED)
        summary["failed"] += sum(1 for status in outcomes if status != JobStatus.COMPLETED)
        logger.info("job recovery finished: %s", summary)
        return summary

    async def _recover_one(self, job: Job) -> JobStatus:
        logger.info("job recovery: resuming polling job_id=%s status=%s", job.id, job.status.value)
        try:
            recovered = await self.run_until_terminal(job.id)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 -- keep the failure local to this job
            logger.exception("job recovery failed unexpectedly for job_id=%s", job.id)
            current = self._repository.get(job.id)
            if current is not None and current.status not in TERMINAL_STATUSES:
                self._fail(current, "Recovery failed unexpectedly.")
            return JobStatus.FAILED
        logger.info("job recovery: job_id=%s finished as %s", job.id, recovered.status.value)
        return recovered.status

    # -- reads -----------------------------------------------------------------

    def get(self, job_id: str) -> Job:
        job = self._repository.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    def resolve_audio(self, job_id: str) -> AudioResource:
        """Return the verified audio artifact for a COMPLETED job.

        The location comes only from the trusted job record and is resolved
        through AudioStorage (which enforces the storage root); nothing the
        client sends is ever used as a path. Raises JobNotFoundError,
        AudioNotAvailableError (job not COMPLETED) or AudioIntegrityError
        (COMPLETED but the record/file is missing, foreign, unsafe or unreadable).
        """

        job = self.get(job_id)
        if job.status != JobStatus.COMPLETED:
            raise AudioNotAvailableError(job.id, job.status)

        audio = (job.result or {}).get("audio")
        if not isinstance(audio, dict):
            raise AudioIntegrityError(job.id, "no audio artifact recorded")
        key = audio.get("key")
        media_type = audio.get("media_type")
        filename = audio.get("filename")
        if not all(isinstance(v, str) and v for v in (key, media_type, filename)):
            raise AudioIntegrityError(job.id, "incomplete audio artifact record")
        if not key.startswith(f"{job.id}/"):
            raise AudioIntegrityError(job.id, "artifact key does not belong to this job")
        if not media_type.startswith("audio/"):
            raise AudioIntegrityError(job.id, "artifact is not an audio media type")

        try:
            path = self._storage.get_path(key)
            if not path.is_file():
                raise AudioIntegrityError(job.id, "stored file is missing")
            size_bytes = path.stat().st_size
        except AudioIntegrityError:
            raise
        except (StorageError, OSError) as exc:
            raise AudioIntegrityError(job.id, f"storage lookup failed: {exc}") from exc
        if size_bytes == 0:
            raise AudioIntegrityError(job.id, "stored file is empty")

        return AudioResource(
            path=path,
            media_type=media_type,
            filename=safe_audio_filename(filename, job_id=job.id, media_type=media_type),
            size_bytes=size_bytes,
        )

    def list(self, limit: int = 50) -> list[Job]:
        return self._repository.list(limit)

    def get_song(self, song_id: str) -> Song:
        if not is_valid_id(song_id):
            raise InvalidIdError("Malformed song id.")
        song = self._repository.get_song(song_id)
        if song is None:
            raise SongNotFoundError(song_id)
        return song

    def list_versions(self, song_id: str) -> list[Version]:
        self.get_song(song_id)
        return self._repository.list_versions(song_id)

    def versions_for(self, jobs: list[Job]) -> dict[str, Version]:
        """The Version of each job that has one, keyed by version id (one query)."""

        return self._repository.get_versions([j.version_id for j in jobs if j.version_id])

    def search(
        self,
        *,
        status: Optional[JobStatus] = None,
        query: str = "",
        sort: str = "newest",
        limit: int = 200,
    ) -> list[Job]:
        """Filter and sort jobs for the library. Local-first scale: the newest
        `_SEARCH_WINDOW` jobs are loaded and filtered in memory.
        """

        jobs = self._repository.list(_SEARCH_WINDOW)
        if status is not None:
            jobs = [j for j in jobs if j.status == status]
        needle = query.strip().lower()
        if needle:
            jobs = [
                j for j in jobs if needle in (j.title or derive_title(j.request.prompt)).lower() or needle in j.request.prompt.lower()
            ]
        if sort == "oldest":
            jobs.sort(key=lambda j: j.created_at)
        elif sort == "title":
            jobs.sort(key=lambda j: (j.title or derive_title(j.request.prompt)).lower())
        else:
            jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    # -- internals ---------------------------------------------------------------

    def _transition(self, job: Job, target: JobStatus) -> None:
        validate_transition(job.status, target)
        job.status = target

    def _fail(self, job: Job, error_message: str) -> None:
        if job.status not in TERMINAL_STATUSES:
            self._transition(job, JobStatus.FAILED)
        job.error = error_message
        job.failed_at = utcnow()
        self._repository.update(job)

    # -- song-oriented reads (Library, Song Details) ----------------------------------------------

    def list_songs(
        self,
        *,
        query: str = "",
        sort: str = "newest",
        limit: int = 50,
        project: Optional[str] = None,
        favorite: Optional[bool] = None,
    ) -> list[SongSummary]:
        if project is not None and project != PROJECT_FILTER_NONE and not is_valid_id(project):
            raise InvalidIdError("Malformed project id.")
        return self._repository.list_song_summaries(
            query=query, sort=sort, limit=limit, project=project, favorite=favorite
        )

    def song_details(self, song_id: str) -> tuple[Song, list[VersionEntry]]:
        """A song and all of its versions (newest first). Versions are loaded by the
        song's own id, so a version can never be returned under another song."""

        song = self.get_song(song_id)
        return song, self._repository.list_version_entries(song.id)

    # -- song management (Phase 9): rename, favorite, delete -------------------------------------

    _SONG_TITLE_MAX = 80  # matches app.jobs.titles.MAX_TITLE_LENGTH (the derived-title cap)

    def update_song(
        self, song_id: str, *, title: Optional[str] = None, is_favorite: Optional[bool] = None
    ) -> Song:
        """Rename and/or (un)favorite a Song. Neither ever touches a Version, a Job,
        or any audio -- both are plain Song metadata (see docs/PHASE-9-SONG-MANAGEMENT.md).

        Unlike the automatic title Tunora derives from a prompt (which is silently
        truncated), an explicit rename is rejected outright if it is empty or too
        long -- the same "reject, don't silently mutate" rule Project rename already
        uses (JobService._clean_project_fields).
        """

        self.get_song(song_id)  # validates id shape and existence
        clean = None
        if title is not None:
            clean = clean_title(title)  # strips control chars/collapses whitespace only
            if not clean:
                raise InvalidSongUpdateError("Title is required.")
            if len(title.strip()) > self._SONG_TITLE_MAX:
                raise InvalidSongUpdateError(f"Title must be {self._SONG_TITLE_MAX} characters or fewer.")
        if is_favorite is not None and not isinstance(is_favorite, bool):
            raise InvalidSongUpdateError("is_favorite must be true or false.")
        return self._repository.update_song(song_id, title=clean, is_favorite=is_favorite)

    def delete_song(self, song_id: str) -> None:
        """Permanently delete a Song, all of its Versions, their Jobs, and their audio.

        The database rows are removed first, in one transaction (see
        JobRepository.delete_song); the audio files are only deleted afterwards,
        best-effort, since a DB transaction and a filesystem delete cannot be one
        atomic operation. A file that fails to delete is logged, not retried, and
        never turns a successful deletion into a reported failure -- the Song is
        already gone from Tunora's own data by the time any file is touched, which
        is the only thing Tunora's own consistency guarantees are about.
        """

        if not is_valid_id(song_id):
            raise InvalidIdError("Malformed song id.")
        audio_keys = self._repository.delete_song(song_id)
        for key in audio_keys:
            try:
                self._storage.delete(key)
            except StorageError as exc:
                logger.warning("could not delete audio for a deleted song: key=%s error=%s", key, exc)

    # -- creative operations (Phase 5B) ----------------------------------------------------------

    async def create_version_from_operation(
        self,
        song_id: str,
        source_version_id: str,
        operation: str,
        *,
        prompt: Optional[str] = None,
        lyrics: Optional[str] = None,
        extend_seconds: Optional[float] = None,
        repaint_start: Optional[float] = None,
        repaint_end: Optional[float] = None,
        remix_strength: Optional[float] = None,
        track_name: Optional[str] = None,
    ) -> Job:
        """Create a NEW Version of `song_id` by extending / remixing / repainting / extracting a
        track from an existing version of the same song, then submit it as a normal Job.

        The source version is never touched: the new Version gets its own row, Job and audio
        file. All validation happens before anything is written. Raises InvalidIdError,
        SongNotFoundError, SourceVersionNotFoundError (unknown, or another song's version),
        SourceAudioUnavailableError, InvalidOperationError or UnsupportedOperationError.
        """

        if operation not in ops.CREATIVE_OPERATIONS:
            raise InvalidOperationError("Unknown operation.")
        if not is_valid_id(song_id) or not is_valid_id(source_version_id):
            raise InvalidIdError("Malformed id.")
        self.get_song(song_id)
        source = self._repository.get_version(source_version_id)
        if source is None or source.song_id != song_id:
            raise SourceVersionNotFoundError(source_version_id)
        if operation not in self._provider.supported_operations:
            raise UnsupportedOperationError(f"Operation {operation!r} is not supported by this provider")
        if operation == ops.ANOTHER_TAKE:
            return await self._create_another_take(song_id, source)
        if source.audio is None:
            raise SourceAudioUnavailableError("The source version has no audio.")
        try:
            source_path = self._storage.get_path(source.audio.key)
        except StorageError as exc:
            raise SourceAudioUnavailableError("The source audio is unavailable.") from exc
        if not source_path.is_file() or source_path.stat().st_size == 0:
            raise SourceAudioUnavailableError("The source audio is unavailable.")

        spec = source.spec
        new_prompt = (prompt or "").strip() or None
        source_duration = source.audio.duration if _valid_seconds(source.audio.duration) else None
        common: dict = dict(
            lyrics=spec.lyrics if lyrics is None else lyrics,
            language=spec.language,
            seed=spec.seed,
            instrumental=spec.instrumental,
            operation=operation,
            source_audio_path=str(source_path),
            source_duration=source_duration,
        )

        if operation == ops.EXTEND:
            seconds = _finite(extend_seconds, "Extension length")
            if not ops.EXTEND_MIN_SECONDS <= seconds <= ops.EXTEND_MAX_SECONDS:
                raise InvalidOperationError(
                    f"Extend by between {ops.EXTEND_MIN_SECONDS:g} and {ops.EXTEND_MAX_SECONDS:g} seconds."
                )
            if source_duration is None:
                raise InvalidOperationError("The source duration is unknown, so it cannot be extended.")
            request = GenerationRequest(
                prompt=new_prompt or spec.prompt, duration=source_duration + seconds, extend_seconds=seconds, **common
            )
            params = {"extend_seconds": seconds}
        elif operation == ops.REMIX:
            if new_prompt is None:
                raise InvalidOperationError("Describe the new interpretation.")
            strength = ops.DEFAULT_REMIX_STRENGTH if remix_strength is None else _finite(remix_strength, "Strength")
            if not 0.0 <= strength <= 1.0:
                raise InvalidOperationError("Strength must be between 0 and 1.")
            request = GenerationRequest(prompt=new_prompt, duration=source_duration, remix_strength=strength, **common)
            params = {"remix_strength": strength}
        elif operation == ops.REPAINT:
            if new_prompt is None:
                raise InvalidOperationError("Describe what the repainted section should sound like.")
            start = _finite(repaint_start, "Start")
            end = _finite(repaint_end, "End")
            if source_duration is None:
                raise InvalidOperationError("The source duration is unknown, so it cannot be repainted.")
            if start < 0 or end > source_duration + 0.05 or end <= start:
                raise InvalidOperationError("Choose a section inside the song.")
            end = min(end, source_duration)
            if not ops.REPAINT_MIN_SECONDS <= end - start <= ops.REPAINT_MAX_SECONDS:
                raise InvalidOperationError(
                    f"The section must be between {ops.REPAINT_MIN_SECONDS:g} and {ops.REPAINT_MAX_SECONDS:g} seconds."
                )
            request = GenerationRequest(
                prompt=new_prompt, duration=source_duration, repaint_start=start, repaint_end=end, **common
            )
            params = {"repaint_start": start, "repaint_end": end}
        else:  # EXTRACT
            clean_track = (track_name or "").strip().lower()
            if clean_track not in ops.TRACK_NAMES:
                raise InvalidOperationError(f"Choose a track: {', '.join(ops.TRACK_NAMES)}.")
            request = GenerationRequest(
                prompt=spec.prompt, duration=source_duration, track_name=clean_track, **common
            )
            params = {"track_name": clean_track}

        return await self.create_and_submit(
            request, song_id=song_id, source_version_id=source.id, operation_params=params
        )

    async def _create_another_take(self, song_id: str, source: Version) -> Job:
        """Phase 13: generate the same creative idea again as a NEW Version of the same song.

        Copies only the source's creative inputs (prompt, lyrics, language, instrumental,
        duration). The seed is deliberately left unset so the provider picks a fresh random one
        (a fixed source seed would otherwise be reused), and batch_size is never copied: exactly
        one output becomes exactly one Version. No source audio is read; the source is untouched.
        """

        if source.operation == ops.EXTRACT:
            raise InvalidOperationError("Another take is not available for an extracted track.")
        spec = source.spec
        duration = spec.duration
        if duration is None and source.audio is not None and _valid_seconds(source.audio.duration):
            duration = source.audio.duration
        request = GenerationRequest(
            prompt=spec.prompt,
            lyrics=spec.lyrics,
            language=spec.language,
            instrumental=spec.instrumental,
            duration=duration,
            seed=None,
            operation=ops.ANOTHER_TAKE,
        )
        return await self.create_and_submit(request, song_id=song_id, source_version_id=source.id)

    # -- projects (Phase 6): organizational metadata over Songs, no audio/Version involved ---------

    _PROJECT_NAME_MAX = 200
    _PROJECT_DESCRIPTION_MAX = 2000

    def _clean_project_fields(self, name: Optional[str], description: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        if name is not None:
            name = name.strip()
            if not name:
                raise InvalidProjectError("Project name is required.")
            if len(name) > self._PROJECT_NAME_MAX:
                raise InvalidProjectError(f"Project name must be {self._PROJECT_NAME_MAX} characters or fewer.")
        if description is not None:
            description = description.strip()
            if len(description) > self._PROJECT_DESCRIPTION_MAX:
                raise InvalidProjectError(f"Project description must be {self._PROJECT_DESCRIPTION_MAX} characters or fewer.")
        return name, description

    def create_project(self, name: str, description: str = "") -> Project:
        clean_name, clean_description = self._clean_project_fields(name, description or "")
        project = Project(id=new_project_id(), name=clean_name, description=clean_description or "")
        self._repository.create_project(project)
        return project

    def list_projects(self, *, query: str = "", sort: str = "newest", limit: int = 50) -> list[ProjectSummary]:
        return self._repository.list_project_summaries(query=query, sort=sort, limit=limit)

    def get_projects(self, project_ids: set[str]) -> dict[str, Project]:
        """Batched lookup (one query) -- used by Library/Song responses so showing a
        song's Project never costs one query per song."""

        return self._repository.get_projects(list(project_ids))

    def get_project(self, project_id: str) -> Project:
        if not is_valid_id(project_id):
            raise InvalidIdError("Malformed project id.")
        project = self._repository.get_project(project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        return project

    def project_details(self, project_id: str) -> tuple[Project, list[ProjectSongEntry]]:
        project = self.get_project(project_id)
        return project, self._repository.list_project_songs(project.id)

    def update_project(self, project_id: str, *, name: Optional[str] = None, description: Optional[str] = None) -> Project:
        self.get_project(project_id)  # validates id shape and existence
        clean_name, clean_description = self._clean_project_fields(name, description)
        return self._repository.update_project(project_id, name=clean_name, description=clean_description)

    def delete_project(self, project_id: str) -> None:
        """Deletes only the Project row. Its Songs are never deleted; the database's
        ON DELETE SET NULL unassigns them (see app.jobs.migrations._to_v4)."""

        self.get_project(project_id)
        self._repository.delete_project(project_id)

    def add_song_to_project(self, project_id: str, song_id: str) -> Song:
        """Assigns an EXISTING Song to a Project. Creates nothing: no Song, Version,
        Job or audio file -- only `Song.project_id` changes."""

        self.get_project(project_id)
        self.get_song(song_id)
        self._repository.assign_song_to_project(project_id, song_id)
        return self._repository.get_song(song_id)

    def remove_song_from_project(self, project_id: str, song_id: str) -> None:
        """Unassigns a Song. The Song, its Versions and its audio are untouched."""

        self.get_project(project_id)
        self.get_song(song_id)
        self._repository.remove_song_from_project(project_id, song_id)
