from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fecreator.contracts._immutable import freeze_mapping
from fecreator.contracts.capabilities import Capability
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import JobResult
from fecreator.core.pipeline import PipelineContext
from fecreator.references.model import ReferencePack


class SubmissionSchema(BaseModel):
    """Typed, deeply-frozen submission metadata carried by every SourcePlan.

    Provenance, rights, and canonical swatches are surfaced here so consumers
    can verify lineage without leaking absolute paths or secrets.
    Required-expression completeness, provenance acceptance, and human approval
    are orchestration gates enforced in Tasks 8–9, not here.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    forbidden_changes: tuple[str, ...] = ()
    canonical_swatches: tuple[str, ...] = ()
    traits: Mapping[str, str] = Field(default_factory=freeze_mapping)
    provenance: str = ""
    rights: str = ""
    files: str = ""

    @field_validator("traits", mode="after")
    @classmethod
    def _freeze_traits(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        return freeze_mapping(value)


class SourcePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompts: tuple[str, ...]
    reference_roles: Mapping[str, str] = Field(default_factory=freeze_mapping)
    expected_filenames: tuple[str, ...]
    required_expressions: tuple[str, ...]
    background_contract: str
    forbidden_colors: tuple[str, ...]
    submission_schema: SubmissionSchema

    @field_validator("reference_roles", mode="after")
    @classmethod
    def _freeze_reference_roles(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        return freeze_mapping(value)


class PromptPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    neutral_prompt: str
    expression_prompts: Mapping[str, str] = Field(default_factory=freeze_mapping)

    @field_validator("expression_prompts", mode="after")
    @classmethod
    def _freeze_expression_prompts(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        return freeze_mapping(value)


@runtime_checkable
class AssetPlugin(Protocol):
    id: str

    def required_capabilities(self, workflow: str) -> set[Capability]: ...
    def preferred_capabilities(self, workflow: str) -> set[Capability]: ...
    def plan_sources(self, manifest: Manifest, pack: ReferencePack | None) -> SourcePlan: ...
    def build(self, ctx: PipelineContext, manifest: Manifest) -> JobResult: ...
