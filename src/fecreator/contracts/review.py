from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from fecreator.contracts._immutable import freeze_mapping
from fecreator.contracts.diagnostics import Diagnostic
from fecreator.contracts.result import Artifact

_AWARE_DATETIME = TypeAdapter(AwareDatetime)


def _ensure_non_empty_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _ensure_aware_iso_timestamp(value: str, *, field_name: str) -> str:
    normalized = _ensure_non_empty_text(value, field_name=field_name)
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware ISO timestamp")
    return normalized


class CandidateSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["1.0"] = "1.0"
    job_id: str
    lineage_id: str
    artifacts: tuple[Artifact, ...]
    diagnostics: tuple[Diagnostic, ...] = ()
    metrics: Mapping[str, float] = Field(default_factory=freeze_mapping)
    created_at: str = Field(json_schema_extra={"format": "date-time"})

    @field_validator("job_id", "lineage_id", mode="after")
    @classmethod
    def _validate_text(cls, value: str, info: object) -> str:
        field_name = getattr(info, "field_name", None) or "text"
        return _ensure_non_empty_text(value, field_name=field_name)

    @field_validator("metrics", mode="after")
    @classmethod
    def _freeze_metrics(cls, value: Mapping[str, float]) -> Mapping[str, float]:
        return freeze_mapping(value)

    @field_validator("created_at", mode="after")
    @classmethod
    def _validate_created_at(cls, value: str) -> str:
        _AWARE_DATETIME.validate_python(value)
        return _ensure_aware_iso_timestamp(value, field_name="created_at")
