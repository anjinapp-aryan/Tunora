"""Tunora-owned generation job domain model.

This is Tunora's own source of truth for a generation job — independent of
whatever `MusicGenerationProvider` is behind it. `provider_job_id` is always
a distinct identity from `Job.id`; regenerating or switching providers must
never require changing a Tunora job's own id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from app.providers.base import GenerationRequest


class JobStatus(str, Enum):
    """Tunora's own job lifecycle states.

    Deliberately does not include CANCELLED: ACE-Step exposes no cancel
    endpoint today, so Tunora does not pretend cancellation exists.
    """

    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


TERMINAL_STATUSES = frozenset({JobStatus.COMPLETED, JobStatus.FAILED})


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Job:
    """A Tunora-owned generation job. Mutable — JobService updates it in place."""

    id: str
    provider: str
    status: JobStatus
    request: GenerationRequest
    created_at: datetime = field(default_factory=utcnow)
    submitted_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    provider_job_id: Optional[str] = None
    error: Optional[str] = None
    result: Optional[dict[str, Any]] = None
