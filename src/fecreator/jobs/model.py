from __future__ import annotations

from enum import StrEnum
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fecreator.contracts._immutable import freeze_mapping
from fecreator.contracts.manifest import Manifest

JsonScalar = str | int | float | bool
JsonObject = dict[str, JsonScalar]


class JobState(StrEnum):
    CREATED = "created"
    PLANNING = "planning"
    WAITING_FOR_PROVIDER = "waiting_for_provider"
    WAITING_FOR_SOURCES = "waiting_for_sources"
    PROCESSING = "processing"
    WAITING_FOR_REVIEW = "waiting_for_review"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_CANCEL_OR_FAIL = frozenset({JobState.FAILED, JobState.CANCELLED})

ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.CREATED: frozenset({JobState.PLANNING, JobState.CANCELLED}),
    JobState.PLANNING: frozenset(
        {JobState.WAITING_FOR_PROVIDER, JobState.WAITING_FOR_SOURCES, JobState.PROCESSING}
    )
    | _CANCEL_OR_FAIL,
    JobState.WAITING_FOR_PROVIDER: frozenset({JobState.WAITING_FOR_SOURCES, JobState.PROCESSING})
    | _CANCEL_OR_FAIL,
    JobState.WAITING_FOR_SOURCES: frozenset({JobState.PROCESSING}) | _CANCEL_OR_FAIL,
    JobState.PROCESSING: frozenset({JobState.WAITING_FOR_REVIEW, JobState.VALIDATING})
    | _CANCEL_OR_FAIL,
    JobState.WAITING_FOR_REVIEW: frozenset({JobState.PROCESSING, JobState.VALIDATING})
    | _CANCEL_OR_FAIL,
    JobState.VALIDATING: frozenset({JobState.WAITING_FOR_REVIEW, JobState.COMPLETED})
    | _CANCEL_OR_FAIL,
    JobState.COMPLETED: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.CANCELLED: frozenset(),
}


class Job(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    state: JobState
    manifest: Manifest
    revision: int
    created_at: str
    updated_at: str


class JobEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    seq: int
    at: str
    kind: str
    message: str
    data: JsonObject = Field(default_factory=dict)

    @field_validator("data", mode="after")
    @classmethod
    def _freeze_data(cls, value: JsonObject) -> JsonObject:
        return cast(JsonObject, freeze_mapping(value))
