from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from fecreator.assets.base import SourcePlan
from fecreator.assets.portrait import prompt_plan
from fecreator.assets.portrait.candidate import (
    CandidateValidationError,
    prepare_candidate,
)
from fecreator.assets.portrait.manifest import preferred_capabilities, required_capabilities
from fecreator.assets.portrait.workflows import (
    PreparedPortrait,
    WorkflowFailure,
    prepare_concept_to_portrait,
    prepare_text_to_portrait,
)
from fecreator.contracts.capabilities import Capability
from fecreator.contracts.diagnostics import Diagnostic, error
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import JobResult
from fecreator.core.pipeline import PipelineContext
from fecreator.core.registry import PROVIDER_REGISTRY
from fecreator.jobs.events import EventLog
from fecreator.jobs.model import Job, JobState
from fecreator.jobs.service import InvalidTransitionError, JobService
from fecreator.jobs.store import JobStore
from fecreator.providers.base import Provider, ProviderRefusal
from fecreator.references.model import ReferencePack
from fecreator.references.store import ReferencePackStore, UnpinnedReferencePackError

_SUPPORTED_TARGET_SPEC = "fe-gba-portrait-standard"


class PortraitPlugin:
    id = "portrait"

    def required_capabilities(self, workflow: str) -> set[Capability]:
        return required_capabilities(workflow)

    def preferred_capabilities(self, workflow: str) -> set[Capability]:
        return preferred_capabilities(workflow)

    def plan_sources(self, manifest: Manifest, pack: ReferencePack | None) -> SourcePlan:
        return prompt_plan.plan_sources(manifest, pack)

    def build(self, ctx: PipelineContext, manifest: Manifest) -> JobResult:
        self._assert_manifest_supported(manifest)
        if manifest.workflow not in {"text_to_portrait", "concept_to_portrait"}:
            raise NotImplementedError(f"workflow not implemented yet: {manifest.workflow}")

        ctx.workspace.mkdir(parents=True, exist_ok=True)
        data_root = ctx.workspace.parents[1]
        publication_pending = False
        try:
            if self._load_job(data_root, ctx.job_id).state is JobState.WAITING_FOR_REVIEW:
                raise InvalidTransitionError("waiting_for_review -> processing is not allowed")
            pack = self._reference_pack(data_root, manifest)
            provider = cast(Provider, PROVIDER_REGISTRY.get(manifest.provider))
            self._transition_job(data_root, ctx.job_id, JobState.PROCESSING)
            try:
                prepared = self._prepare(manifest, pack, provider, ctx.workspace)
            except ProviderRefusal as exc:
                return self._fail(data_root, ctx.job_id, (error("PROVIDER_FAILED", str(exc)),))
            except WorkflowFailure as exc:
                return self._fail(data_root, ctx.job_id, exc.diagnostics)

            try:
                publication = prepare_candidate(
                    ctx=ctx,
                    manifest=manifest,
                    prepared=prepared,
                    reference_pack=pack,
                )
            except CandidateValidationError as exc:
                return self._fail(data_root, ctx.job_id, prepared.diagnostics + exc.diagnostics)

            publication_pending = True
            self._transition_job(
                data_root,
                ctx.job_id,
                JobState.WAITING_FOR_REVIEW,
                before_persist=lambda _job: publication.publish(ctx.workspace),
                rollback=lambda: publication.rollback(ctx.workspace),
            )
            publication_pending = False
            return JobResult(
                job_id=ctx.job_id,
                ok=True,
                artifacts=publication.snapshot.artifacts,
                diagnostics=publication.snapshot.diagnostics,
                lineage_id=publication.snapshot.lineage_id,
            )
        except InvalidTransitionError:
            raise
        except Exception:
            if not publication_pending:
                self._mark_job_failed_if_possible(data_root, ctx.job_id)
            raise

    def _prepare(
        self,
        manifest: Manifest,
        pack: ReferencePack | None,
        provider: Provider,
        workspace: Path,
    ) -> PreparedPortrait:
        if manifest.workflow == "text_to_portrait":
            return prepare_text_to_portrait(manifest, pack, provider, workspace)
        return prepare_concept_to_portrait(manifest, pack, provider, workspace)

    def _fail(self, data_root: Path, job_id: str, diagnostics: tuple[Diagnostic, ...]) -> JobResult:
        self._transition_job(data_root, job_id, JobState.FAILED)
        return JobResult(job_id=job_id, ok=False, diagnostics=diagnostics)

    def _reference_pack(self, data_root: Path, manifest: Manifest) -> ReferencePack | None:
        if manifest.character_ref_pack is None:
            return None
        if manifest.character_ref_pack_rev is None:
            raise UnpinnedReferencePackError(
                "character_ref_pack_rev is required for persisted jobs with character_ref_pack"
            )
        return ReferencePackStore(data_root).get(
            manifest.character_ref_pack,
            manifest.character_ref_pack_rev,
        )

    def _load_job(self, data_root: Path, job_id: str) -> Job:
        return JobStore(data_root).load(job_id)

    def _assert_manifest_supported(self, manifest: Manifest) -> None:
        if manifest.asset_type != self.id:
            raise ValueError(f"PortraitPlugin requires manifest asset_type='{self.id}'")
        if manifest.target_spec != _SUPPORTED_TARGET_SPEC:
            raise ValueError(
                f"PortraitPlugin requires manifest target_spec='{_SUPPORTED_TARGET_SPEC}'"
            )

    def _mark_job_failed_if_possible(self, data_root: Path, job_id: str) -> Job:
        job = self._load_job(data_root, job_id)
        if job.state in {JobState.WAITING_FOR_REVIEW, JobState.CANCELLED}:
            return job
        try:
            return self._transition_job(data_root, job_id, JobState.FAILED)
        except InvalidTransitionError:
            return self._load_job(data_root, job_id)

    def _transition_job(
        self,
        data_root: Path,
        job_id: str,
        state: JobState,
        *,
        before_persist: Callable[[Job], None] | None = None,
        rollback: Callable[[], None] | None = None,
    ) -> Job:
        service = JobService(JobStore(data_root), EventLog(data_root))
        job = service.resume(job_id)
        if job.state is state and before_persist is None:
            return job

        steps = self._transition_steps(job.state, state)
        for index, next_state in enumerate(steps):
            if job.state is next_state:
                continue
            is_target_step = index == len(steps) - 1
            job = service.transition(
                job_id,
                next_state,
                before_persist=before_persist if is_target_step else None,
                rollback=rollback if is_target_step else None,
            )
        return job

    def _transition_steps(self, current: JobState, target: JobState) -> tuple[JobState, ...]:
        if current is target:
            return ()
        if target is JobState.PROCESSING:
            if current is JobState.CREATED:
                return (JobState.PLANNING, JobState.PROCESSING)
            if current is JobState.PLANNING:
                return (JobState.PROCESSING,)
            return (JobState.PROCESSING,)
        if target is JobState.WAITING_FOR_REVIEW:
            return self._transition_steps(current, JobState.PROCESSING) + (
                JobState.WAITING_FOR_REVIEW,
            )
        if target is JobState.FAILED:
            if current is JobState.CREATED:
                return (JobState.PLANNING, JobState.FAILED)
            return (JobState.FAILED,)
        return (target,)
