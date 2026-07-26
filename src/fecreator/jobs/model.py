from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from fecreator.contracts._immutable import freeze_mapping
from fecreator.contracts.manifest import Manifest

JsonScalar = str | int | float | bool
JsonObject = dict[str, JsonScalar]


def ensure_non_empty_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def ensure_aware_iso_timestamp(value: str, *, field_name: str) -> str:
    normalized = ensure_non_empty_text(value, field_name=field_name)
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware ISO timestamp")
    return normalized


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
    parent_candidate_id: str | None = None
    revision: int = Field(ge=1)
    created_at: str
    updated_at: str

    @field_validator("id", mode="after")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        return ensure_non_empty_text(value, field_name="id")

    @field_validator("parent_candidate_id", mode="after")
    @classmethod
    def _validate_parent_candidate_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return ensure_non_empty_text(value, field_name="parent_candidate_id")

    @field_validator("created_at", "updated_at", mode="after")
    @classmethod
    def _validate_timestamps(cls, value: str, info: ValidationInfo) -> str:
        field_name = info.field_name or "timestamp"
        return ensure_aware_iso_timestamp(value, field_name=field_name)


class JobEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    seq: int = Field(ge=0)
    at: str
    kind: str
    message: str
    data: JsonObject = Field(default_factory=dict)

    @field_validator("at", mode="after")
    @classmethod
    def _validate_at(cls, value: str) -> str:
        return ensure_aware_iso_timestamp(value, field_name="at")

    @field_validator("kind", "message", mode="after")
    @classmethod
    def _validate_text_fields(cls, value: str, info: ValidationInfo) -> str:
        field_name = info.field_name or "text"
        return ensure_non_empty_text(value, field_name=field_name)

    @field_validator("data", mode="after")
    @classmethod
    def _freeze_data(cls, value: JsonObject) -> JsonObject:
        return cast(JsonObject, freeze_mapping(value))
