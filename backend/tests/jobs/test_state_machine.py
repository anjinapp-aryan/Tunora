import pytest

from app.jobs.errors import InvalidTransitionError
from app.jobs.models import JobStatus
from app.jobs.state_machine import validate_transition


@pytest.mark.parametrize(
    "current,target",
    [
        (JobStatus.CREATED, JobStatus.SUBMITTED),
        (JobStatus.CREATED, JobStatus.FAILED),
        (JobStatus.SUBMITTED, JobStatus.QUEUED),
        (JobStatus.SUBMITTED, JobStatus.RUNNING),
        (JobStatus.SUBMITTED, JobStatus.COMPLETED),
        (JobStatus.SUBMITTED, JobStatus.FAILED),
        (JobStatus.QUEUED, JobStatus.RUNNING),
        (JobStatus.QUEUED, JobStatus.COMPLETED),
        (JobStatus.QUEUED, JobStatus.FAILED),
        (JobStatus.RUNNING, JobStatus.COMPLETED),
        (JobStatus.RUNNING, JobStatus.FAILED),
    ],
)
def test_valid_transitions_do_not_raise(current, target):
    validate_transition(current, target)


@pytest.mark.parametrize("status", list(JobStatus))
def test_same_state_is_always_a_noop(status):
    validate_transition(status, status)


@pytest.mark.parametrize(
    "current,target",
    [
        (JobStatus.COMPLETED, JobStatus.RUNNING),
        (JobStatus.FAILED, JobStatus.COMPLETED),
        (JobStatus.QUEUED, JobStatus.SUBMITTED),
        (JobStatus.RUNNING, JobStatus.QUEUED),
        (JobStatus.CREATED, JobStatus.RUNNING),
        (JobStatus.CREATED, JobStatus.COMPLETED),
        (JobStatus.COMPLETED, JobStatus.FAILED),
    ],
)
def test_invalid_transitions_raise(current, target):
    with pytest.raises(InvalidTransitionError):
        validate_transition(current, target)
