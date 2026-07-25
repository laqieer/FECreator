from __future__ import annotations

import inspect

import pytest

from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.core.atomicio import JsonlBudgetError
from fecreator.jobs.events import EventLog
from fecreator.jobs.model import JobState
from fecreator.jobs.service import InvalidTransitionError, JobService
from fecreator.jobs.store import JobStore


def _service(data_root) -> JobService:
    return JobService(JobStore(data_root), EventLog(data_root))


def _manifest() -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="fake",
        sources=(SourceSpec(kind="text", ref="hero"),),
    )


def test_create_logs_event(data_root) -> None:
    service = _service(data_root)

    job = service.create_job(_manifest())

    kinds = [event.kind for event in EventLog(data_root).read(job.id)]
    assert "created" in kinds


def test_create_rolls_back_when_event_append_fails(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(data_root)

    def fail_append(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(service._events, "append", fail_append)

    with pytest.raises(OSError, match="boom"):
        service.create_job(_manifest())

    assert JobStore(data_root).list_jobs() == []


def test_valid_transition(data_root) -> None:
    service = _service(data_root)
    job = service.create_job(_manifest())

    updated = service.transition(job.id, JobState.PLANNING)

    assert updated.state is JobState.PLANNING
    assert updated.revision == 2


def test_transition_rolls_back_when_event_append_fails(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(data_root)
    job = service.create_job(_manifest())
    original_append = service._events.append

    def fail_on_transition(job_id: str, kind: str, message: str, data=None):
        if kind == "transition":
            raise OSError("boom")
        return original_append(job_id, kind, message, data)

    monkeypatch.setattr(service._events, "append", fail_on_transition)

    with pytest.raises(OSError, match="boom"):
        service.transition(job.id, JobState.PLANNING)

    reloaded = JobStore(data_root).load(job.id)
    assert reloaded.state is JobState.CREATED
    assert reloaded.revision == 1


def test_invalid_transition_raises(data_root) -> None:
    service = _service(data_root)
    job = service.create_job(_manifest())

    with pytest.raises(InvalidTransitionError):
        service.transition(job.id, JobState.COMPLETED)


def test_cancel_from_created(data_root) -> None:
    service = _service(data_root)
    job = service.create_job(_manifest())

    assert service.cancel(job.id).state is JobState.CANCELLED


def test_cancel_terminal_raises(data_root) -> None:
    service = _service(data_root)
    job = service.create_job(_manifest())
    service.cancel(job.id)

    with pytest.raises(InvalidTransitionError):
        service.cancel(job.id)


def test_resume_reloads_from_disk(data_root) -> None:
    service = _service(data_root)
    job = service.create_job(_manifest())
    service.transition(job.id, JobState.PLANNING)

    resumed = service.resume(job.id)
    assert resumed.state is JobState.PLANNING
    assert resumed.revision == 2


def test_save_requires_expected_revision_keyword(data_root) -> None:
    signature = inspect.signature(JobStore.save)

    assert signature.parameters["expected_revision"].kind is inspect.Parameter.KEYWORD_ONLY


def test_transition_rolls_back_when_event_log_budget_is_exhausted(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(data_root)
    job = service.create_job(_manifest())
    monkeypatch.setattr("fecreator.core.atomicio.MAX_JSONL_RECORDS", 1)

    with pytest.raises(JsonlBudgetError, match="archive or prune") as exc_info:
        service.transition(job.id, JobState.PLANNING)

    assert "current=2" in str(exc_info.value)
    assert "limit=1" in str(exc_info.value)
    reloaded = JobStore(data_root).load(job.id)
    assert reloaded.state is JobState.CREATED
    assert reloaded.revision == 1


def test_transition_rolls_back_published_side_effects_when_event_append_fails(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(data_root)
    job = service.create_job(_manifest())
    marker = data_root / "published.txt"
    original_append = service._events.append

    def fail_on_transition(job_id: str, kind: str, message: str, data=None):
        if kind == "transition":
            raise OSError("boom")
        return original_append(job_id, kind, message, data)

    monkeypatch.setattr(service._events, "append", fail_on_transition)

    def publish(candidate_job) -> None:
        marker.write_text(
            f"{candidate_job.state.value}:{candidate_job.revision}",
            encoding="utf-8",
        )

    def cleanup() -> None:
        marker.unlink(missing_ok=True)

    with pytest.raises(OSError, match="boom"):
        service.transition(
            job.id,
            JobState.PLANNING,
            before_persist=publish,
            rollback=cleanup,
        )

    assert not marker.exists()
    reloaded = JobStore(data_root).load(job.id)
    assert reloaded.state is JobState.CREATED
    assert reloaded.revision == 1


def test_transition_restores_state_even_when_rollback_hook_fails(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(data_root)
    job = service.create_job(_manifest())
    marker = data_root / "published.txt"
    original_append = service._events.append

    def fail_on_transition(job_id: str, kind: str, message: str, data=None):
        if kind == "transition":
            raise OSError("boom")
        return original_append(job_id, kind, message, data)

    monkeypatch.setattr(service._events, "append", fail_on_transition)

    def publish(candidate_job) -> None:
        marker.write_text(
            f"{candidate_job.state.value}:{candidate_job.revision}",
            encoding="utf-8",
        )

    def cleanup() -> None:
        raise OSError("cleanup boom")

    with pytest.raises(OSError, match="cleanup boom"):
        service.transition(
            job.id,
            JobState.PLANNING,
            before_persist=publish,
            rollback=cleanup,
        )

    assert marker.exists()
    reloaded = JobStore(data_root).load(job.id)
    assert reloaded.state is JobState.CREATED
    assert reloaded.revision == 1
