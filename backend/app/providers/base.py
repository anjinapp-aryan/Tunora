"""Provider-agnostic music generation domain model.

Tunora's UI/domain layer talks only to `MusicGenerationProvider` and the
dataclasses below. No provider-specific request/response shape (ACE-Step's
or any future model's) may leak past a provider implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class JobState(str, Enum):
    """Provider-agnostic generation job state."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class GenerationRequest:
    """A song generation request, independent of any provider's API shape."""

    prompt: str
    lyrics: str = ""
    language: str = "en"
    duration: Optional[float] = None
    seed: Optional[int] = None
    instrumental: bool = False
    batch_size: Optional[int] = None


@dataclass(frozen=True)
class GenerationJob:
    """Returned immediately after a generation request is accepted."""

    job_id: str
    provider: str
    status: JobState


@dataclass(frozen=True)
class GenerationStatus:
    """Point-in-time status of a previously submitted job."""

    job_id: str
    status: JobState
    progress: Optional[float] = None
    message: Optional[str] = None


@dataclass(frozen=True)
class GenerationResult:
    """The output of a successfully completed generation job."""

    job_id: str
    audio_path: str
    duration: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class MusicGenerationProvider(ABC):
    """Interface every music generation backend must implement.

    Tunora's domain/UI layer depends only on this interface — never on a
    specific provider's request/response schema.
    """

    @abstractmethod
    async def generate(self, request: GenerationRequest) -> GenerationJob:
        """Submit a generation request and return the accepted job."""

    @abstractmethod
    async def get_status(self, job_id: str) -> GenerationStatus:
        """Return the current status of a previously submitted job."""

    @abstractmethod
    async def get_result(self, job_id: str) -> GenerationResult:
        """Return the result of a completed job.

        Raises whatever provider-specific error applies if the job is not
        yet finished or failed — callers should check `get_status` first.
        """
