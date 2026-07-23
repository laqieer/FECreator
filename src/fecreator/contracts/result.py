"""PROVISIONAL bootstrap contract shim.

The contracts task must preserve ``stage`` and ``ok`` while extending StageResult
only with defaulted fields.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

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
    metrics: dict[str, float] = Field(default_factory=dict)
    diagnostics: tuple[Diagnostic, ...] = ()


class JobResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str
    ok: bool
    artifacts: tuple[Artifact, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    lineage_id: str | None = None
