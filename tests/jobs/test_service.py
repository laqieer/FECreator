from __future__ import annotations

import pytest

from fecreator.contracts.manifest import Manifest, SourceSpec
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


def test_valid_transition(data_root) -> None:
    service = _service(data_root)
    job = service.create_job(_manifest())

    updated = service.transition(job.id, JobState.PLANNING)

    assert updated.state is JobState.PLANNING


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

    assert service.resume(job.id).state is JobState.PLANNING
