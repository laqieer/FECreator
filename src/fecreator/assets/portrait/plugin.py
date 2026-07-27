from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from fecreator.assets.base import SourcePlan
from fecreator.assets.portrait import prompt_plan
from fecreator.assets.portrait.candidate import (
    CandidatePublication,
    CandidateValidationError,
    prepare_candidate,
)
from fecreator.assets.portrait.manifest import preferred_capabilities, required_capabilities
from fecreator.assets.portrait.workflows import (
    PreparedPortrait,
    WorkflowFailure,
    prepare_concept_to_portrait,
    prepare_expression_refine,
    prepare_masked_variant,
    prepare_text_to_portrait,
)
from fecreator.contracts.capabilities import Capability
from fecreator.contracts.diagnostics import Diagnostic, error
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import JobResult
from fecreator.core.atomicio import LockTimeoutError, _path_lock
from fecreator.core.paths import safe_join
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
_SUPPORTED_WORKFLOWS = frozenset(
    {
        "text_to_portrait",
        "concept_to_portrait",
        "expression_refine",
        "masked_variant",
    }
)
_CLAIMABLE_STATES = frozenset(
    {
        JobState.CREATED,
        JobState.PLANNING,
        JobState.WAITING_FOR_PROVIDER,
        JobState.WAITING_FOR_SOURCES,
        # `processing` is claimable only behind the build lease below. The lease
        # proves no other build is live, so an interrupted build (crash, kill,
        # failed publication) stays resumable instead of being stranded in a
        # non-terminal state no operation can leave.
        JobState.PROCESSING,
    }
)
_BUILD_LEASE_TIMEOUT_SECONDS = 0.05
_BUILD_LEASE_POLL_INTERVAL_SECONDS = 0.01


@dataclass(frozen=True)
class _ClaimedBuild:
    """Everything phase A resolved so the provider can run without the lock."""

    pack: ReferencePack | None
    provider: Provider
    parent_candidate_id: str | None


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
        if manifest.workflow not in _SUPPORTED_WORKFLOWS:
            raise NotImplementedError(f"workflow not implemented yet: {manifest.workflow}")

        ctx.workspace.mkdir(parents=True, exist_ok=True)
        data_root = ctx.workspace.parents[1]
        with self._build_lease(data_root, ctx.job_id):
            claimed = self._claim_build(data_root, ctx.job_id, manifest)
            prepared = self._run_provider(data_root, ctx, manifest, claimed)
            if isinstance(prepared, JobResult):
                return prepared
            publication = self._stage_candidate(data_root, ctx, manifest, prepared, claimed)
            if isinstance(publication, JobResult):
                return publication
            return self._publish_candidate(data_root, ctx, publication)

    @contextmanager
    def _build_lease(self, data_root: Path, job_id: str) -> Iterator[None]:
        """Hold an exclusive, OS-released lease for the whole build.

        The job lock cannot serialize builds any more, because it is
        deliberately released while the provider runs. A separate sidecar lease
        keeps exactly one build in flight per job across threads *and*
        processes, and the operating system drops it if the owner dies, so a
        stranded ``processing`` job can be built again.
        """

        lease_target = safe_join(data_root, "jobs", ".locks", f"build-{job_id}")
        try:
            with _path_lock(
                lease_target,
                lock_path=lease_target.with_suffix(".lock"),
                timeout=_BUILD_LEASE_TIMEOUT_SECONDS,
                poll_interval=_BUILD_LEASE_POLL_INTERVAL_SECONDS,
            ):
                yield
        except LockTimeoutError as exc:
            raise InvalidTransitionError(
                f"a build is already running for job {job_id}; "
                f"{JobState.PROCESSING.value} -> {JobState.PROCESSING.value} is not allowed"
            ) from exc

    def _claim_build(self, data_root: Path, job_id: str, manifest: Manifest) -> _ClaimedBuild:
        """Take exclusive ownership of the build under a short lock.

        The caller already holds the build lease, so ``processing`` here can only
        be a previous build that is no longer running. Terminal and review
        states are still refused before any provider work happens.
        """

        store = JobStore(data_root)
        with store.locked(job_id):
            job = store._load_locked(job_id)
            if job.state not in _CLAIMABLE_STATES:
                raise InvalidTransitionError(
                    f"{job.state.value} -> {JobState.PROCESSING.value} is not allowed"
                )
            try:
                pack = self._reference_pack(data_root, manifest)
                provider = cast(Provider, PROVIDER_REGISTRY.get(manifest.provider))
                self._transition_job(data_root, job_id, JobState.PROCESSING, job_locked=True)
            except InvalidTransitionError:
                raise
            except Exception:
                self._mark_job_failed_if_possible(data_root, job_id, job_locked=True)
                raise
            return _ClaimedBuild(pack, provider, job.parent_candidate_id)

    def _run_provider(
        self,
        data_root: Path,
        ctx: PipelineContext,
        manifest: Manifest,
        claimed: _ClaimedBuild,
    ) -> PreparedPortrait | JobResult:
        try:
            return self._prepare(manifest, claimed.pack, claimed.provider, ctx.workspace)
        except ProviderRefusal as exc:
            return self._fail(
                data_root,
                ctx.job_id,
                (error("PROVIDER_FAILED", str(exc)),),
            )
        except WorkflowFailure as exc:
            return self._fail(data_root, ctx.job_id, exc.diagnostics)
        except Exception:
            self._mark_job_failed_if_possible(data_root, ctx.job_id)
            raise

    def _stage_candidate(
        self,
        data_root: Path,
        ctx: PipelineContext,
        manifest: Manifest,
        prepared: PreparedPortrait,
        claimed: _ClaimedBuild,
    ) -> CandidatePublication | JobResult:
        try:
            return prepare_candidate(
                ctx=ctx,
                manifest=manifest,
                prepared=prepared,
                reference_pack=claimed.pack,
                parent_candidate_id=claimed.parent_candidate_id,
            )
        except CandidateValidationError as exc:
            return self._fail(
                data_root,
                ctx.job_id,
                prepared.diagnostics + exc.diagnostics,
            )
        except Exception:
            self._mark_job_failed_if_possible(data_root, ctx.job_id)
            raise

    def _publish_candidate(
        self,
        data_root: Path,
        ctx: PipelineContext,
        publication: CandidatePublication,
    ) -> JobResult:
        store = JobStore(data_root)
        publish_attempted = False

        def publish(_job: Job) -> None:
            nonlocal publish_attempted
            publish_attempted = True
            publication.publish(ctx.workspace)

        try:
            with store.locked(ctx.job_id):
                self._transition_job(
                    data_root,
                    ctx.job_id,
                    JobState.WAITING_FOR_REVIEW,
                    before_persist=publish,
                    rollback=lambda: publication.rollback(ctx.workspace),
                    job_locked=True,
                )
        except BaseException:
            # The transition is validated before ``before_persist`` runs, so a
            # job cancelled during the lock-free provider phase never reaches the
            # service's own rollback and would strand the staged package.
            if not publish_attempted:
                publication.rollback(ctx.workspace)
            raise
        return JobResult(
            job_id=ctx.job_id,
            ok=True,
            artifacts=publication.snapshot.artifacts,
            diagnostics=publication.snapshot.diagnostics,
            lineage_id=publication.snapshot.lineage_id,
        )

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

    def _fail(
        self,
        data_root: Path,
        job_id: str,
        diagnostics: tuple[Diagnostic, ...],
    ) -> JobResult:
        # The job lock is not held during the provider phase, so the job may have
        # been cancelled meanwhile. Recording the failure must not swallow the
        # diagnostics that explain why the build did not produce a candidate.
        self._mark_job_failed_if_possible(data_root, job_id)
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

    def _mark_job_failed_if_possible(
        self,
        data_root: Path,
        job_id: str,
        *,
        job_locked: bool = False,
    ) -> Job:
        job = (
            JobStore(data_root)._load_locked(job_id)
            if job_locked
            else self._load_job(data_root, job_id)
        )
        if job.state in {JobState.WAITING_FOR_REVIEW, JobState.CANCELLED}:
            return job
        try:
            return self._transition_job(data_root, job_id, JobState.FAILED, job_locked=job_locked)
        except InvalidTransitionError:
            return (
                JobStore(data_root)._load_locked(job_id)
                if job_locked
                else self._load_job(data_root, job_id)
            )

    def _transition_job(
        self,
        data_root: Path,
        job_id: str,
        state: JobState,
        *,
        before_persist: Callable[[Job], None] | None = None,
        rollback: Callable[[], None] | None = None,
        job_locked: bool = False,
    ) -> Job:
        service = JobService(JobStore(data_root), EventLog(data_root))
        job = service.resume_while_job_locked(job_id) if job_locked else service.resume(job_id)
        if job.state is state and before_persist is None:
            return job

        steps = self._transition_steps(job.state, state)
        for index, next_state in enumerate(steps):
            if job.state is next_state:
                continue
            is_target_step = index == len(steps) - 1
            if job_locked:
                job = service.transition_path_while_job_locked(
                    job_id,
                    (next_state,),
                    before_persist=before_persist if is_target_step else None,
                    rollback=rollback if is_target_step else None,
                )
            else:
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
