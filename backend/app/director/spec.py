"""SongSpec: provider-neutral structured song intent (Phase 7).

Produced by a `SongDirector` from a natural-language request, then reviewed/edited
by the user before generation. Every field here is either something the existing
generation pipeline (`GenerationRequest`) actually accepts, or a small piece of
informational metadata the UI can show. Nothing ACE-Step-specific (task ids,
internal paths, `/v1/audio`, etc.) belongs here -- see `app/providers/ace_step.py`
for where that translation happens instead, on the generation side.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Fields a user can set explicitly before/while asking the Director for a plan.
# Once set, the Director must never overwrite them with an AI guess (see
# docs/PHASE-7-AI-SONG-DIRECTOR.md §11 "user intent has priority").
REQUESTABLE_FIELDS = frozenset({"title", "language", "duration", "instrumental"})


@dataclass(frozen=True)
class SongSpec:
    """A structured, validated song plan. Maps directly onto the fields
    `POST /api/jobs` (CreateJobRequest) already accepts, plus a few
    informational-only hints the provider does not guarantee.

    `requested_fields` records which fields the USER supplied explicitly
    (as opposed to the AI having inferred them) purely for the UI to label
    "requested" vs "inferred" -- it never changes how generation behaves.
    """

    title: str
    prompt: str
    lyrics: str
    language: str
    duration: Optional[float]
    instrumental: bool
    # Informational only: ACE-Step's DiT does not accept these as generation
    # inputs, so they are never sent to `POST /api/jobs`. Shown to the user as
    # AI hints, not guarantees (see docs/PHASE-7-AI-SONG-DIRECTOR.md §"No fake
    # capabilities").
    bpm: Optional[int] = None
    key_scale: Optional[str] = None
    time_signature: Optional[str] = None
    requested_fields: frozenset = field(default_factory=frozenset)

    def to_job_payload(self) -> dict:
        """The subset of fields `POST /api/jobs` (CreateJobRequest) understands."""

        return {
            "title": self.title or None,
            "prompt": self.prompt,
            "lyrics": self.lyrics,
            "language": self.language,
            "duration": self.duration,
            "instrumental": self.instrumental,
        }
