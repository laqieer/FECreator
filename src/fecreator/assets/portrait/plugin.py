from __future__ import annotations

from pathlib import Path

from fecreator.assets.base import SourcePlan
from fecreator.assets.candidate import CandidatePublication
from fecreator.assets.portrait import prompt_plan
from fecreator.assets.portrait.candidate import prepare_candidate
from fecreator.assets.portrait.manifest import preferred_capabilities, required_capabilities
from fecreator.assets.portrait.workflows import (
    PreparedPortrait,
    prepare_concept_to_portrait,
    prepare_expression_refine,
    prepare_masked_variant,
    prepare_text_to_portrait,
)
from fecreator.assets.reviewed import ReviewedAssetPlugin
from fecreator.contracts.capabilities import Capability
from fecreator.contracts.manifest import Manifest
from fecreator.core.pipeline import PipelineContext
from fecreator.core.registry import PROVIDER_REGISTRY  # noqa: F401
from fecreator.jobs.events import EventLog  # noqa: F401
from fecreator.providers.base import Provider
from fecreator.references.model import ReferencePack

_SUPPORTED_WORKFLOWS = frozenset(
    {
        "text_to_portrait",
        "concept_to_portrait",
        "expression_refine",
        "masked_variant",
    }
)


class PortraitPlugin(ReviewedAssetPlugin[PreparedPortrait]):
    id = "portrait"
    target_spec = "fe-gba-portrait-standard"
    workflows = _SUPPORTED_WORKFLOWS

    def required_capabilities(self, workflow: str) -> set[Capability]:
        return required_capabilities(workflow)

    def preferred_capabilities(self, workflow: str) -> set[Capability]:
        return preferred_capabilities(workflow)

    def plan_sources(self, manifest: Manifest, pack: ReferencePack | None) -> SourcePlan:
        return prompt_plan.plan_sources(manifest, pack)

    def _prepare(
        self,
        manifest: Manifest,
        pack: ReferencePack | None,
        provider: Provider,
        workspace: Path,
    ) -> PreparedPortrait:
        if manifest.workflow == "text_to_portrait":
            return prepare_text_to_portrait(manifest, pack, provider, workspace)
        if manifest.workflow == "concept_to_portrait":
            return prepare_concept_to_portrait(manifest, pack, provider, workspace)
        if manifest.workflow == "expression_refine":
            return prepare_expression_refine(manifest, pack, provider, workspace)
        return prepare_masked_variant(manifest, pack, provider, workspace)

    def _prepare_candidate(
        self,
        *,
        ctx: PipelineContext,
        manifest: Manifest,
        prepared: PreparedPortrait,
        reference_pack: ReferencePack | None,
        parent_candidate_id: str | None,
    ) -> CandidatePublication:
        return prepare_candidate(
            ctx=ctx,
            manifest=manifest,
            prepared=prepared,
            reference_pack=reference_pack,
            parent_candidate_id=parent_candidate_id,
        )
