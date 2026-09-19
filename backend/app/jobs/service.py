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
import uuid
from dataclasses import dataclass
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
from app.jobs.titles import derive_title
from app.providers.base import GenerationRequest, JobState, MusicGenerationProvider
from app.providers.errors import ProviderError
from app.storage.base import AudioStorage
from app.storage.errors import StorageError
from app.storage.filenames import safe_audio_filename
from app.storage.media_types import guess_media_type

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
        self._id_factory = id_factory

    # -- lifecycle -----------------------------------------------------------

    async def create_and_submit(self, request: GenerationRequest, title: Optional[str] = None) -> Job:
        """Create a Tunora job and submit it to the provider. Never raises for
        provider failures — the returned Job's status/error reflect the outcome.
        """

        job = Job(
            id=self._id_factory(),
            provider=self._provider.name,
            status=JobStatus.CREATED,
            request=request,
            title=derive_title(request.prompt, title),
        )
        self._repository.create(job)

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
                "duration": result.duration,
                "metadata": _strip_provider_transport_metadata(result.metadata),
            }
            self._repository.update(job)
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
        server-side timeout) so a stuck job cannot poll forever.
        """

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
