from __future__ import annotations

import pytest
from pydantic import ValidationError

from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.jobs.model import ALLOWED_TRANSITIONS, Job, JobEvent, JobState


def _manifest() -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="fake",
        sources=(SourceSpec(kind="text", ref="hero"),),
    )


def test_ten_states() -> None:
    assert len(list(JobState)) == 10
    assert JobState.WAITING_FOR_REVIEW.value == "waiting_for_review"


def test_terminal_states_have_no_transitions() -> None:
    for terminal in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED):
        assert ALLOWED_TRANSITIONS[terminal] == frozenset()


def test_created_can_go_to_planning_or_cancelled() -> None:
    assert ALLOWED_TRANSITIONS[JobState.CREATED] == frozenset(
        {JobState.PLANNING, JobState.CANCELLED}
    )


def test_job_and_event_shapes() -> None:
    job = Job(
        id="j1",
        state=JobState.CREATED,
        manifest=_manifest(),
        revision=1,
        created_at="2026-07-24T00:00:00+00:00",
        updated_at="2026-07-24T00:00:00+00:00",
    )

    assert job.state is JobState.CREATED

    event = JobEvent(
        seq=0,
        at="2026-07-24T00:00:00+00:00",
        kind="created",
        message="job created",
    )

    assert event.data == {}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", " "),
        ("created_at", "2026-07-24T00:00:00"),
        ("updated_at", "not-a-timestamp"),
    ],
)
def test_job_rejects_invalid_identity_and_timestamps(field: str, value: str) -> None:
    payload = {
        "id": "j1",
        "state": JobState.CREATED,
        "manifest": _manifest(),
        "revision": 1,
        "created_at": "2026-07-24T00:00:00+00:00",
        "updated_at": "2026-07-24T00:00:00+00:00",
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        Job(**payload)


def test_job_rejects_non_positive_revision() -> None:
    with pytest.raises(ValidationError):
        Job(
            id="j1",
            state=JobState.CREATED,
            manifest=_manifest(),
            revision=0,
            created_at="2026-07-24T00:00:00+00:00",
            updated_at="2026-07-24T00:00:00+00:00",
        )


def test_job_event_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        JobEvent(seq=0, at="2026-07-24T00:00:00", kind="created", message="job created")
