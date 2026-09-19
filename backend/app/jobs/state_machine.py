"""Explicit state-transition rules for Tunora generation jobs.

Terminal states (COMPLETED, FAILED) allow no further transitions. Several
"skip-ahead" edges (e.g. QUEUED -> COMPLETED) are intentionally allowed: a
short generation can finish between two polls, so Tunora may never observe
an intermediate RUNNING report from the provider. This was confirmed as a
real possibility during Step 11's smoke test (a 10s generation completed
within roughly one poll interval).
"""

from __future__ import annotations

from app.jobs.errors import InvalidTransitionError
from app.jobs.models import JobStatus

ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.CREATED: frozenset({JobStatus.SUBMITTED, JobStatus.FAILED}),
    JobStatus.SUBMITTED: frozenset(
        {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.COMPLETED, JobStatus.FAILED}
    ),
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.COMPLETED, JobStatus.FAILED}),
    JobStatus.RUNNING: frozenset({JobStatus.COMPLETED, JobStatus.FAILED}),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.FAILED: frozenset(),
}


def validate_transition(current: JobStatus, target: JobStatus) -> None:
    """Raise InvalidTransitionError unless `target` is reachable from `current`.

    A same-state "transition" (e.g. QUEUED -> QUEUED, from repolling before
    anything changed) is always allowed as a no-op.
    """

    if current == target:
        return
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransitionError(current, target)
