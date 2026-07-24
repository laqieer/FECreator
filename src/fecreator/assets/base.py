from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from fecreator.contracts.capabilities import Capability
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import JobResult
from fecreator.core.pipeline import PipelineContext
from fecreator.references.model import ReferencePack


class SourcePlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    prompts: tuple[str, ...]
    reference_roles: dict[str, str]
    expected_filenames: tuple[str, ...]
    required_expressions: tuple[str, ...]
    background_contract: str
    forbidden_colors: tuple[str, ...]
    submission_schema: dict[str, object]


class PromptPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    neutral_prompt: str
    expression_prompts: dict[str, str]


@runtime_checkable
class AssetPlugin(Protocol):
    id: str

    def required_capabilities(self, workflow: str) -> set[Capability]: ...
    def preferred_capabilities(self, workflow: str) -> set[Capability]: ...
    def plan_sources(self, manifest: Manifest, pack: ReferencePack | None) -> SourcePlan: ...
    def build(self, ctx: PipelineContext, manifest: Manifest) -> JobResult: ...
