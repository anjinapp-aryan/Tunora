"""Domain-level errors for Tunora's job lifecycle."""

from __future__ import annotations

from app.jobs.models import JobStatus


class JobNotFoundError(Exception):
    """No job exists with the given Tunora job id."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"No job found with id {job_id!r}")
        self.job_id = job_id


class InvalidTransitionError(Exception):
    """An illegal job status transition was attempted."""

    def __init__(self, current: JobStatus, target: JobStatus) -> None:
        super().__init__(f"Cannot transition job from {current.value} to {target.value}")
        self.current = current
        self.target = target


class AudioNotAvailableError(Exception):
    """The job exists but has no audio to serve (not COMPLETED)."""

    def __init__(self, job_id: str, status: JobStatus) -> None:
        super().__init__(f"Job {job_id!r} has no audio (status {status.value})")
        self.job_id = job_id
        self.status = status


class AudioIntegrityError(Exception):
    """A COMPLETED job's audio record is missing, inconsistent, unsafe, or unreadable.

    The message is for logs only; the API never returns it to clients.
    """

    def __init__(self, job_id: str, reason: str) -> None:
        super().__init__(f"Audio for job {job_id!r} is unavailable: {reason}")
        self.job_id = job_id
        self.reason = reason
