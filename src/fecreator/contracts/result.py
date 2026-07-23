"""PROVISIONAL bootstrap contract shim.

The contracts task must preserve ``stage`` and ``ok`` while extending StageResult
only with defaulted fields.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fecreator.contracts._immutable import freeze_mapping
from fecreator.contracts.diagnostics import Diagnostic


class Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str
    path: str
    sha256: str
    media_type: str


class StageResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: str
    ok: bool
    artifacts: tuple[Artifact, ...] = ()
    metrics: Mapping[str, float] = Field(default_factory=freeze_mapping)
    diagnostics: tuple[Diagnostic, ...] = ()

    @field_validator("metrics", mode="after")
    @classmethod
    def _freeze_metrics(cls, value: Mapping[str, float]) -> Mapping[str, float]:
        return freeze_mapping(value)


class JobResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str
    ok: bool
    artifacts: tuple[Artifact, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    lineage_id: str | None = None
