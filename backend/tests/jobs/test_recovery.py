"""Phase 16: restart-safe job recovery.

A backend restart used to strand every in-flight job (the polling loop lived only in memory).
`JobService.recover_unfinished_jobs` resumes them from the persisted `provider_job_id`: it never
resubmits, reuses `run_until_terminal` (so completion/failure use the existing pipelines), keeps
one polling loop per job, isolates failures per job, and preserves the Phase 14 Extract model
check for recovered Extract jobs.
"""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.jobs.models import JobStatus
from app.jobs.service import JobService
from app.providers.ace_step import AceStepMusicGenerationProvider
from app.providers.base import GenerationJob, GenerationRequest, GenerationResult, GenerationStatus, JobState
from app.providers.errors import ProviderResponseError, ProviderUnavailableError
from tests.jobs.fakes import FakeProvider
from tests.songs.test_operations import first_version
from tests.songs.test_service_versions import Harness

ALL_OPS = frozenset({"ORIGINAL", "EXTEND", "REMIX", "REPAINT", "EXTRACT", "ANOTHER_TAKE"})


class ScriptedProvider(FakeProvider):
    """Per-provider-job scripted answers, so several recovered jobs can be told apart."""

    def __init__(self) -> None:
        super().__init__()
        self.supported_operations = ALL_OPS
        self.script: dict[str, dict] = {}
        self.registered: list[tuple[str, str]] = []
        self.next_id = 0
        self.delay = 0.0  # a real await inside get_status, so concurrent loops genuinely overlap
        self.active = 0
        self.max_active = 0

    async def generate(self, request):
        self.generate_calls.append(request)
        self.next_id += 1
        return GenerationJob(job_id=f"ace-{self.next_id}", provider="fake", status=JobState.QUEUED)

    async def get_status(self, job_id):
        self.status_calls.append(job_id)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
        finally:
            self.active -= 1
        answers = self.script[job_id]["statuses"]
        item = answers.pop(0) if len(answers) > 1 else answers[0]
        if isinstance(item, Exception):
            raise item
        return GenerationStatus(job_id=job_id, status=item)

    async def get_result(self, job_id):
        self.result_calls.append(job_id)
        result = self.script[job_id]["result"]
        if isinstance(result, Exception):
            raise result
        return result

    def register_recovered_job(self, job_id, operation):
        self.registered.append((job_id, operation))


@pytest.fixture
def world(tmp_path):
    h = Harness(tmp_path)
    provider = ScriptedProvider()
    h.provider = provider
    h.service = JobService(repository=h.repository, provider=provider, storage=h.storage, poll_interval_seconds=0.0)
    return h


def _audio(h, name: str) -> GenerationResult:
    return GenerationResult(job_id="x", audio_path=h.source_audio(name, name.encode() * 50), duration=10.0, metadata={})


async def _submit(h, prompt="a song", *, statuses, result=None):
    """A job the 'previous process' submitted: provider id `ace-N` is persisted, then the process dies."""
    job = await h.service.create_and_submit(GenerationRequest(prompt=prompt))
    h.provider.script[job.provider_job_id] = {"statuses": list(statuses), "result": result or _audio(h, f"{prompt}.mp3")}
    return job


def _restart(h) -> JobService:
    """A fresh JobService over the same database, storage and provider: what a restarted backend has."""
    return JobService(repository=h.repository, provider=h.provider, storage=h.storage, poll_interval_seconds=0.0)


# -- discovery and resumption --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_unfinished_jobs_means_nothing_to_do(world):
    summary = await _restart(world).recover_unfinished_jobs()
    assert summary["found"] == 0 and world.provider.status_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stored", [JobStatus.SUBMITTED, JobStatus.QUEUED, JobStatus.RUNNING])
async def test_unfinished_jobs_are_resumed_and_completed_through_the_existing_pipeline(world, stored):
    job = await _submit(world, statuses=[JobState.SUCCEEDED])
    if stored != JobStatus.SUBMITTED:  # what the previous process last saw
        stored_job = world.repository.get(job.id)
        stored_job.status = stored
        world.repository.update(stored_job)

    summary = await _restart(world).recover_unfinished_jobs()

    done = world.repository.get(job.id)
    assert done.status is JobStatus.COMPLETED and summary["completed"] == 1
    version = world.repository.get_version(done.version_id)
    assert version.audio is not None and world.storage.get_path(version.audio.key).read_bytes()
    assert len(world.repository.list_versions(version.song_id)) == 1  # one Version, not a second
    assert len(world.provider.generate_calls) == 1  # never resubmitted


@pytest.mark.asyncio
async def test_a_job_the_provider_still_reports_running_is_polled_until_it_finishes(world):
    job = await _submit(world, statuses=[JobState.RUNNING, JobState.RUNNING, JobState.SUCCEEDED])
    await _restart(world).recover_unfinished_jobs()
    assert world.repository.get(job.id).status is JobStatus.COMPLETED
    assert world.provider.status_calls.count(job.provider_job_id) == 3


@pytest.mark.asyncio
async def test_several_unfinished_jobs_are_all_recovered(world):
    jobs = [await _submit(world, f"song {i}", statuses=[JobState.SUCCEEDED]) for i in range(4)]
    summary = await _restart(world).recover_unfinished_jobs()
    assert summary["found"] == summary["resumed"] == summary["completed"] == 4
    assert all(world.repository.get(j.id).status is JobStatus.COMPLETED for j in jobs)
    assert len({world.repository.get(j.id).version_id for j in jobs}) == 4  # distinct Versions


@pytest.mark.asyncio
async def test_finished_jobs_are_ignored_and_untouched(world):
    done = await _submit(world, "done", statuses=[JobState.SUCCEEDED])
    await world.service.poll_once(done.id)
    failed = await _submit(world, "failed", statuses=[JobState.FAILED])
    await world.service.poll_once(failed.id)
    before = (world.repository.get(done.id), world.repository.get(failed.id))
    calls = list(world.provider.status_calls)

    summary = await _restart(world).recover_unfinished_jobs()

    assert summary["found"] == 0 and world.provider.status_calls == calls
    assert (world.repository.get(done.id), world.repository.get(failed.id)) == before


# -- failure handling -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_job_without_a_provider_id_is_failed_never_resubmitted(world):
    job = await world.service.create_and_submit(GenerationRequest(prompt="p"))
    stored = world.repository.get(job.id)
    stored.provider_job_id, stored.status = None, JobStatus.CREATED  # the process died before the provider answered
    world.repository.update(stored)
    submitted_before = len(world.provider.generate_calls)

    summary = await _restart(world).recover_unfinished_jobs()

    assert world.repository.get(job.id).status is JobStatus.FAILED and summary["unsubmitted"] == 1
    assert len(world.provider.generate_calls) == submitted_before
    assert world.provider.status_calls == []


@pytest.mark.asyncio
async def test_a_provider_reported_failure_fails_the_job(world):
    job = await _submit(world, statuses=[JobState.FAILED])
    summary = await _restart(world).recover_unfinished_jobs()
    assert world.repository.get(job.id).status is JobStatus.FAILED and summary["failed"] == 1
    assert world.repository.get_version(world.repository.get(job.id).version_id).audio is None


@pytest.mark.asyncio
async def test_an_unavailable_provider_fails_the_job_visibly(world):
    job = await _submit(world, statuses=[ProviderUnavailableError("down")])
    await _restart(world).recover_unfinished_jobs()
    assert world.repository.get(job.id).status is JobStatus.FAILED


@pytest.mark.asyncio
async def test_an_unexpected_provider_exception_fails_only_that_job(world):
    bad = await _submit(world, "bad", statuses=[RuntimeError("boom")])
    good = await _submit(world, "good", statuses=[JobState.SUCCEEDED])
    summary = await _restart(world).recover_unfinished_jobs()
    assert world.repository.get(bad.id).status is JobStatus.FAILED
    assert world.repository.get(good.id).status is JobStatus.COMPLETED
    assert summary["failed"] == 1 and summary["completed"] == 1


@pytest.mark.asyncio
async def test_a_malformed_result_does_not_block_the_other_jobs(world):
    bad = await _submit(world, "bad", statuses=[JobState.SUCCEEDED], result=ProviderResponseError("no audio"))
    good = await _submit(world, "good", statuses=[JobState.SUCCEEDED])
    await _restart(world).recover_unfinished_jobs()
    assert world.repository.get(bad.id).status is JobStatus.FAILED
    assert world.repository.get(good.id).status is JobStatus.COMPLETED


@pytest.mark.asyncio
async def test_a_provider_hook_error_fails_that_job_and_recovery_continues(world):
    a = await _submit(world, "a", statuses=[JobState.SUCCEEDED])
    b = await _submit(world, "b", statuses=[JobState.SUCCEEDED])
    real = world.provider.register_recovered_job

    def flaky(job_id, operation):
        if job_id == a.provider_job_id:
            raise RuntimeError("cannot restore")
        real(job_id, operation)

    world.provider.register_recovered_job = flaky
    await _restart(world).recover_unfinished_jobs()
    assert world.repository.get(a.id).status is JobStatus.FAILED
    assert world.repository.get(b.id).status is JobStatus.COMPLETED


# -- duplicate protection and idempotency ---------------------------------------------------------


@pytest.mark.asyncio
async def test_only_one_loop_polls_a_job_at_a_time(world):
    world.provider.delay = 0.01
    job = await _submit(world, statuses=[JobState.RUNNING, JobState.RUNNING, JobState.SUCCEEDED])
    service = _restart(world)
    results = await asyncio.gather(*[service.run_until_terminal(job.id) for _ in range(5)])
    assert world.repository.get(job.id).status is JobStatus.COMPLETED
    assert world.provider.max_active == 1  # never two loops querying the provider for the job at once
    assert len(world.provider.result_calls) == 1
    assert len(results) == 5
    assert service._polling == set()  # noqa: SLF001 -- the registry is released


@pytest.mark.asyncio
async def test_concurrent_recoveries_do_not_duplicate_work(world):
    world.provider.delay = 0.01
    job = await _submit(world, statuses=[JobState.RUNNING, JobState.RUNNING, JobState.SUCCEEDED])
    service = _restart(world)
    await asyncio.gather(service.recover_unfinished_jobs(), service.recover_unfinished_jobs())
    assert world.provider.max_active == 1
    assert len(world.provider.result_calls) == 1
    assert len(world.repository.list_versions(world.repository.get_version(world.repository.get(job.id).version_id).song_id)) == 1


@pytest.mark.asyncio
async def test_repeated_restarts_stay_idempotent(world):
    job = await _submit(world, statuses=[JobState.SUCCEEDED])
    for _ in range(4):
        await _restart(world).recover_unfinished_jobs()
    done = world.repository.get(job.id)
    assert done.status is JobStatus.COMPLETED
    assert len(world.provider.result_calls) == 1 and len(world.provider.generate_calls) == 1
    assert len(list(world.storage.get_path(world.repository.get_version(done.version_id).audio.key).parent.iterdir())) == 1


@pytest.mark.asyncio
async def test_recovery_preserves_lineage(world):
    source = await _submit(world, "source", statuses=[JobState.SUCCEEDED])
    await world.service.poll_once(source.id)
    v1 = world.repository.get_version(world.repository.get(source.id).version_id)
    take = await world.service.create_version_from_operation(v1.song_id, v1.id, "ANOTHER_TAKE")
    world.provider.script[take.provider_job_id] = {"statuses": [JobState.SUCCEEDED], "result": _audio(world, "take.mp3")}
    await _restart(world).recover_unfinished_jobs()

    version = world.repository.get_version(world.repository.get(take.id).version_id)
    assert (version.operation, version.source_version_id, version.version_number) == ("ANOTHER_TAKE", v1.id, 2)
    assert version.audio is not None


# -- Phase 14: an Extract job keeps its base-model requirement across a restart -----------------------

BASE_URL = "http://127.0.0.1:8001"


def _wrap(data):
    return {"data": data, "code": 200, "error": None, "timestamp": 0, "extra": None}


def _result(path: str, **item_fields):
    item = {"file": f"/v1/audio?path={path}", "status": 1, "stage": "succeeded", "metas": {}, **item_fields}
    return _wrap([{"task_id": "task-x", "result": json.dumps([item]), "status": 1}])


async def _extract_in_flight_then_restart(tmp_path):
    """Submit a real-provider Extract job, then 'restart': a new provider instance with no memory."""
    h = Harness(tmp_path)
    _, v1 = await first_version(h)
    old = JobService(
        repository=h.repository, provider=AceStepMusicGenerationProvider(base_url=BASE_URL),
        storage=h.storage, poll_interval_seconds=0.0,
    )
    produced = tmp_path / "produced.mp3"
    produced.write_bytes(b"EXTRACTED")
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/release_task").mock(return_value=httpx.Response(200, json=_wrap({"task_id": "task-x"})))
        job = await old.create_version_from_operation(v1.song_id, v1.id, "EXTRACT", track_name="vocals")
    restarted = JobService(
        repository=h.repository, provider=AceStepMusicGenerationProvider(base_url=BASE_URL),
        storage=h.storage, poll_interval_seconds=0.0,
    )
    return h, restarted, job, produced


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields,expected",
    [
        ({"dit_model": "acestep-v15-base"}, JobStatus.COMPLETED),
        ({"dit_model": "acestep-v15-turbo"}, JobStatus.FAILED),
        ({}, JobStatus.FAILED),
        ({"dit_model": None}, JobStatus.FAILED),
    ],
)
async def test_a_recovered_extract_is_still_held_to_the_base_model(tmp_path, fields, expected):
    h, restarted, job, produced = await _extract_in_flight_then_restart(tmp_path)
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/query_result").mock(return_value=httpx.Response(200, json=_result(str(produced), **fields)))
        await restarted.recover_unfinished_jobs()

    done = h.repository.get(job.id)
    assert done.status is expected
    assert (h.repository.get_version(done.version_id).audio is not None) is (expected is JobStatus.COMPLETED)


@pytest.mark.asyncio
async def test_a_recovered_non_extract_job_is_not_subject_to_the_extract_check(tmp_path):
    h = Harness(tmp_path)
    old = JobService(
        repository=h.repository, provider=AceStepMusicGenerationProvider(base_url=BASE_URL),
        storage=h.storage, poll_interval_seconds=0.0,
    )
    produced = tmp_path / "produced.mp3"
    produced.write_bytes(b"NORMAL")
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/release_task").mock(return_value=httpx.Response(200, json=_wrap({"task_id": "task-x"})))
        job = await old.create_and_submit(GenerationRequest(prompt="p"))
    restarted = JobService(
        repository=h.repository, provider=AceStepMusicGenerationProvider(base_url=BASE_URL),
        storage=h.storage, poll_interval_seconds=0.0,
    )
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/query_result").mock(
            return_value=httpx.Response(200, json=_result(str(produced), dit_model="acestep-v15-turbo"))
        )
        await restarted.recover_unfinished_jobs()
    assert h.repository.get(job.id).status is JobStatus.COMPLETED


# -- application startup and shutdown -----------------------------------------------------------------


def _app(monkeypatch, tmp_path):
    import app.main as main

    monkeypatch.setattr(main, "DB_PATH", str(tmp_path / "tunora.db"))
    monkeypatch.setattr(main, "STORAGE_ROOT", str(tmp_path / "audio"))
    monkeypatch.setattr(main, "ACE_STEP_BASE_URL", BASE_URL)
    return main.create_app()


def test_startup_recovers_a_stranded_job_and_the_public_api_hides_provider_ids(monkeypatch, tmp_path):
    h = Harness(tmp_path)
    h.provider.generate_response = GenerationJob(job_id="task-x", provider="ace-step", status=JobState.QUEUED)
    job = asyncio.run(h.service.create_and_submit(GenerationRequest(prompt="stranded")))  # then the process 'dies'
    produced = tmp_path / "produced.mp3"
    produced.write_bytes(b"RECOVERED-AUDIO" * 20)

    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/query_result").mock(return_value=httpx.Response(200, json=_result(str(produced))))
        with TestClient(_app(monkeypatch, tmp_path)) as client:
            deadline = time.time() + 10
            body = client.get(f"/api/jobs/{job.id}").json()
            while body["status"] != "COMPLETED" and time.time() < deadline:
                time.sleep(0.1)
                body = client.get(f"/api/jobs/{job.id}").json()
            assert body["status"] == "COMPLETED"
            assert client.get(f"/api/jobs/{job.id}/audio").content == b"RECOVERED-AUDIO" * 20
            assert "task-x" not in json.dumps(body) and "provider_job_id" not in json.dumps(body)
            assert len(client.get(f"/api/songs/{body['song_id']}").json()["versions"]) == 1


def test_shutdown_cancels_an_unfinished_recovery_cleanly(monkeypatch, tmp_path):
    h = Harness(tmp_path)
    h.provider.generate_response = GenerationJob(job_id="task-x", provider="ace-step", status=JobState.QUEUED)
    job = asyncio.run(h.service.create_and_submit(GenerationRequest(prompt="never finishes")))
    running = _wrap([{"task_id": "task-x", "result": json.dumps([{"file": "", "status": 0, "stage": "running"}]), "status": 0}])

    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/query_result").mock(return_value=httpx.Response(200, json=running))
        started = time.time()
        with TestClient(_app(monkeypatch, tmp_path)) as client:
            time.sleep(0.5)  # recovery is polling in the background while the API answers
            assert client.get(f"/api/jobs/{job.id}").status_code == 200
        assert time.time() - started < 8  # leaving the app did not wait for the job
