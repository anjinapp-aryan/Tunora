"""FastAPI endpoint tests for the Step 12 job API, using a FakeProvider —
no network, no GPU, and no ACE-Step-specific shape should ever appear here.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router as jobs_router
from app.jobs.repository import InMemoryJobRepository
from app.jobs.service import JobService
from app.providers.base import GenerationJob, GenerationStatus, JobState
from tests.jobs.fakes import FakeAudioStorage, FakeProvider


def _make_client(provider: FakeProvider) -> TestClient:
    app = FastAPI()
    app.include_router(jobs_router)
    app.state.job_service = JobService(
        repository=InMemoryJobRepository(),
        provider=provider,
        storage=FakeAudioStorage(),
        poll_interval_seconds=0.0,
    )
    return TestClient(app)


def test_create_job_returns_tunora_shape_only():
    # The response body is a snapshot taken before the scheduled background
    # poll runs, so its "SUBMITTED" status is stable regardless of how the
    # background task below resolves. Two responses are queued (QUEUED then
    # FAILED) purely so that background task terminates cleanly instead of
    # exhausting the fake provider's scripted queue.
    provider = FakeProvider()
    provider.generate_response = GenerationJob(job_id="ace-task-1", provider="ace-step", status=JobState.QUEUED)
    provider.status_responses = [
        GenerationStatus(job_id="ace-task-1", status=JobState.QUEUED),
        GenerationStatus(job_id="ace-task-1", status=JobState.FAILED, message="stub"),
    ]
    client = _make_client(provider)

    response = client.post("/api/jobs", json={"prompt": "an upbeat song"})

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "id", "title", "provider", "status", "created_at", "submitted_at",
        "started_at", "completed_at", "error", "result",
    }
    assert body["status"] == "SUBMITTED"
    assert body["provider"] == "fake"
    assert body["id"].startswith("tunora-")
    # The ACE-Step task id must never leak into the public API shape.
    assert "ace-task-1" not in response.text


def test_get_job_returns_current_state():
    provider = FakeProvider()
    provider.generate_response = GenerationJob(job_id="ace-task-2", provider="ace-step", status=JobState.QUEUED)
    provider.status_responses = [GenerationStatus(job_id="ace-task-2", status=JobState.FAILED, message="stub")]
    client = _make_client(provider)

    created = client.post("/api/jobs", json={"prompt": "p"}).json()
    fetched = client.get(f"/api/jobs/{created['id']}")

    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]


def test_get_unknown_job_returns_404():
    client = _make_client(FakeProvider())
    response = client.get("/api/jobs/does-not-exist")
    assert response.status_code == 404


def test_list_jobs_returns_created_jobs():
    provider = FakeProvider()
    provider.generate_response = GenerationJob(job_id="ace-task-3", provider="ace-step", status=JobState.QUEUED)
    provider.status_responses = [
        GenerationStatus(job_id="ace-task-3", status=JobState.FAILED, message="stub"),
        GenerationStatus(job_id="ace-task-3", status=JobState.FAILED, message="stub"),
    ]
    client = _make_client(provider)

    client.post("/api/jobs", json={"prompt": "p1"})
    client.post("/api/jobs", json={"prompt": "p2"})

    response = client.get("/api/jobs")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_create_job_with_provider_failure_returns_failed_status_not_error():
    from app.providers.errors import ProviderUnavailableError

    provider = FakeProvider()
    provider.generate_response = ProviderUnavailableError("connection refused")
    client = _make_client(provider)

    response = client.post("/api/jobs", json={"prompt": "p"})

    assert response.status_code == 200
    assert response.json()["status"] == "FAILED"
    # Step 16: raw failure text stays server-side; the API returns a fixed message.
    assert response.json()["error"] == "Generation failed."
    assert "connection refused" not in response.text


def test_create_job_accepts_an_optional_title_and_derives_one_otherwise():
    provider = FakeProvider()
    provider.generate_response = GenerationJob(job_id="ace-task-9", provider="ace-step", status=JobState.QUEUED)
    provider.status_responses = [GenerationStatus(job_id="ace-task-9", status=JobState.FAILED, message="stub")] * 4
    client = _make_client(provider)

    named = client.post("/api/jobs", json={"prompt": "quiet piano piece", "title": "  Evening   Rain "}).json()
    derived = client.post("/api/jobs", json={"prompt": "quiet piano piece for a rainy evening walk home"}).json()

    assert named["title"] == "Evening Rain"
    assert derived["title"] == "Quiet piano piece for a rainy"
    assert "tunora-" not in named["title"] + derived["title"]
