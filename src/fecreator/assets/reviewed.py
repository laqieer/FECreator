from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, Protocol, TypeVar, cast

from fecreator.assets.candidate import CandidatePublication
from fecreator.assets.publication import finalize_candidate
from fecreator.contracts.diagnostics import Diagnostic, error
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import JobResult
from fecreator.contracts.review import CandidateSnapshot
from fecreator.core.atomicio import LockTimeoutError, _path_lock
from fecreator.core.paths import safe_join
from fecreator.core.pipeline import PipelineContext
from fecreator.core.registry import PROVIDER_REGISTRY
from fecreator.jobs.approvals import ApprovalRecord
from fecreator.jobs.events import EventLog
from fecreator.jobs.model import Job, JobState
from fecreator.jobs.service import InvalidTransitionError, JobService
from fecreator.jobs.store import JobStore
from fecreator.providers.base import Provider, ProviderRefusal
from fecreator.references.model import ReferencePack
from fecreator.references.store import ReferencePackStore, UnpinnedReferencePackError


class PreparedAsset(Protocol):
    @property
    def diagnostics(self) -> tuple[Diagnostic, ...]: ...


PreparedT = TypeVar("PreparedT", bound=PreparedAsset)

_CLAIMABLE_STATES = frozenset(
    {
        JobState.CREATED,
        JobState.PLANNING,
        JobState.WAITING_FOR_PROVIDER,
        JobState.WAITING_FOR_SOURCES,
        JobState.PROCESSING,
    }
)
_BUILD_LEASE_TIMEOUT_SECONDS = 0.05
_BUILD_LEASE_POLL_INTERVAL_SECONDS = 0.01


class AssetWorkflowFailure(Exception):
    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        super().__init__(
            ", ".join(f"{diagnostic.code}: {diagnostic.message}" for diagnostic in diagnostics)
        )
        self.diagnostics = diagnostics


class CandidateValidationError(Exception):
    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        super().__init__("candidate package validation failed")
        self.diagnostics = diagnostics


@dataclass(frozen=True)
class _ClaimedBuild:
    """Everything phase A resolved so the provider can run without the lock."""

    pack: ReferencePack | None
    provider: Provider
    parent_candidate_id: str | None


class ReviewedAssetPlugin(Generic[PreparedT]):
    id: str
    target_spec: str
    workflows: frozenset[str]

    def build(self, ctx: PipelineContext, manifest: Manifest) -> JobResult:
        self._assert_manifest_supported(manifest)

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

        Only a failure to *acquire* the lease means "a build is already
        running". The build body takes the job lock for its short claim and
        publish transitions, and that lock can time out for reasons that have
        nothing to do with a second build, so such a timeout is re-raised
        unchanged for the adapters to map to ``STORE_LOCK_TIMEOUT``.
        """

        lease_target = safe_join(data_root, "jobs", ".locks", f"build-{job_id}")
        lease_lock = lease_target.with_name(f"{lease_target.name}.lock")
        acquired = False
        try:
            with _path_lock(
                lease_target,
                lock_path=lease_lock,
                timeout=_BUILD_LEASE_TIMEOUT_SECONDS,
                poll_interval=_BUILD_LEASE_POLL_INTERVAL_SECONDS,
            ):
                acquired = True
                yield
        except LockTimeoutError as exc:
            if acquired:
                raise
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
    ) -> PreparedT | JobResult:
        try:
            return self._prepare(manifest, claimed.pack, claimed.provider, ctx.workspace)
        except ProviderRefusal as exc:
            return self._fail(
                data_root,
                ctx.job_id,
                (error("PROVIDER_FAILED", str(exc)),),
            )
        except AssetWorkflowFailure as exc:
            return self._fail(data_root, ctx.job_id, exc.diagnostics)
        except Exception:
            self._mark_job_failed_if_possible(data_root, ctx.job_id)
            raise

    def _stage_candidate(
        self,
        data_root: Path,
        ctx: PipelineContext,
        manifest: Manifest,
        prepared: PreparedT,
        claimed: _ClaimedBuild,
    ) -> CandidatePublication | JobResult:
        try:
            return self._prepare_candidate(
                ctx=ctx,
                manifest=manifest,
                prepared=prepared,
                reference_pack=claimed.pack,
                parent_candidate_id=claimed.parent_candidate_id,
            )
        except CandidateValidationError as exc:
            return self._fail(data_root, ctx.job_id, prepared.diagnostics + exc.diagnostics)
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
    ) -> PreparedT:
        raise NotImplementedError

    def _prepare_candidate(
        self,
        *,
        ctx: PipelineContext,
        manifest: Manifest,
        prepared: PreparedT,
        reference_pack: ReferencePack | None,
        parent_candidate_id: str | None,
    ) -> CandidatePublication:
        raise NotImplementedError

    def finalize(
        self,
        *,
        data_root: Path,
        job: Job,
        candidate: CandidateSnapshot,
        approval: ApprovalRecord,
    ) -> JobResult:
        return finalize_candidate(
            data_root=data_root,
            job=job,
            candidate=candidate,
            approval=approval,
        )

    def _fail(
        self,
        data_root: Path,
        job_id: str,
        diagnostics: tuple[Diagnostic, ...],
    ) -> JobResult:
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
        plugin_name = type(self).__name__
        if manifest.asset_type != self.id:
            raise ValueError(f"{plugin_name} requires manifest asset_type='{self.id}'")
        if manifest.target_spec != self.target_spec:
            raise ValueError(f"{plugin_name} requires manifest target_spec='{self.target_spec}'")
        if manifest.workflow not in self.workflows:
            raise NotImplementedError(f"workflow not implemented yet: {manifest.workflow}")

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
