from __future__ import annotations

from pathlib import Path

from fecreator.assets.base import SourcePlan
from fecreator.assets.candidate import CandidatePublication
from fecreator.assets.dialogue_background import prompt_plan
from fecreator.assets.dialogue_background.candidate import prepare_candidate
from fecreator.assets.dialogue_background.manifest import (
    WORKFLOWS,
    preferred_capabilities,
    required_capabilities,
)
from fecreator.assets.dialogue_background.workflows import (
    PreparedDialogueBackground,
    prepare_concept_to_dialogue_background,
    prepare_masked_variant,
    prepare_text_to_dialogue_background,
)
from fecreator.assets.reviewed import ReviewedAssetPlugin
from fecreator.contracts.capabilities import Capability
from fecreator.contracts.manifest import Manifest
from fecreator.core.pipeline import PipelineContext
from fecreator.providers.base import Provider
from fecreator.references.model import ReferencePack


class DialogueBackgroundPlugin(ReviewedAssetPlugin[PreparedDialogueBackground]):
    id = "dialogue_background"
    target_spec = "fe8-dialogue-background-source-240x160"
    workflows = WORKFLOWS

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
    ) -> PreparedDialogueBackground:
        if manifest.workflow == "text_to_dialogue_background":
            return prepare_text_to_dialogue_background(manifest, pack, provider, workspace)
        if manifest.workflow == "concept_to_dialogue_background":
            return prepare_concept_to_dialogue_background(manifest, pack, provider, workspace)
        return prepare_masked_variant(manifest, pack, provider, workspace)

    def _prepare_candidate(
        self,
        *,
        ctx: PipelineContext,
        manifest: Manifest,
        prepared: PreparedDialogueBackground,
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
