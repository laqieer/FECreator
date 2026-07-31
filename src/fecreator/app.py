from __future__ import annotations

import os
import shutil
import stat
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import cast

import fecreator.providers  # noqa: F401
import fecreator.specs  # noqa: F401
from fecreator.assets import register_builtin_assets
from fecreator.assets.base import AssetPlugin, SourcePlan
from fecreator.contracts.diagnostics import Diagnostic, error
from fecreator.contracts.lineage import LineageNode
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import JobResult
from fecreator.contracts.review import CandidateSnapshot
from fecreator.core.atomicio import _fsync_directory, read_json, write_json_atomic
from fecreator.core.config import Settings
from fecreator.core.paths import PathEscapeError, safe_join
from fecreator.core.pipeline import PipelineContext
from fecreator.core.registry import ASSET_REGISTRY, PROVIDER_REGISTRY, SPEC_REGISTRY
from fecreator.jobs.approvals import ApprovalError, ApprovalRecord, ApprovalStore
from fecreator.jobs.candidates import CandidateStore
from fecreator.jobs.events import EventLog, PendingEvent
from fecreator.jobs.model import Job, JobEvent, JobState, ensure_non_empty_text
from fecreator.jobs.service import (
    InvalidTransitionError,
    JobService,
    TransitionPublishHook,
    TransitionRollbackHook,
)
from fecreator.jobs.store import JobStore
from fecreator.lineage.store import LineageStore, UnknownParentAssetError
from fecreator.references.model import ReferencePack
from fecreator.references.store import ReferencePackStore, UnpinnedReferencePackError
from fecreator.reporting.bundle import BundleEntry
from fecreator.reporting.sanitize import JsonObject, as_object, sanitize_json
from fecreator.specs.base import TargetSpec

_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_MANUAL_PROVIDER_ID = "manual"
_SUBMITTED_DIR = "submitted"
_SUBMITTED_STAGE_PREFIX = ".submitted-stage-"
_UPLOAD_STAGE_PREFIX = ".http-upload-"
_ARTIFACT_ROOTS = (("package",), ("candidate", "package"))


class FeCreatorApp:
    def __init__(self, settings: Settings) -> None:
        register_builtin_assets()
        self._settings = settings
        root = settings.data_root
        self._jobs = JobStore(root)
        self._events = EventLog(root)
        self._service = JobService(self._jobs, self._events)
        self._approvals = ApprovalStore(root)
        self._candidates = CandidateStore(root)
        self._lineage = LineageStore(root)
        self._refs = ReferencePackStore(root)

    def list_assets(self) -> list[str]:
        return sorted(ASSET_REGISTRY.ids())

    def list_specs(self) -> list[str]:
        return sorted(SPEC_REGISTRY.ids())

    def list_providers(self) -> list[str]:
        return sorted(PROVIDER_REGISTRY.ids())

    def list_jobs(self) -> list[Job]:
        return self._jobs.list()

    def create_job(self, manifest: Manifest) -> Job:
        pinned = self._pin_reference_pack(manifest)
        self._require_known_parent_asset(pinned)
        return self._service.create_job(pinned)

    def _require_known_parent_asset(self, manifest: Manifest) -> None:
        """Refuse an approved base that is not in the lineage graph.

        ``LineageStore.add()`` enforces the same rule when the candidate is
        published, but that is after the provider has already run. Checking at
        creation keeps the failure cheap, structured, and attributable.
        """

        if manifest.parent_asset_id is None:
            return
        try:
            self._lineage.get(manifest.parent_asset_id)
        except FileNotFoundError as exc:
            raise UnknownParentAssetError(
                f"unknown parent asset: {manifest.parent_asset_id}"
            ) from exc

    def get_job(self, job_id: str) -> Job:
        return self._jobs.load(job_id)

    def get_job_candidate(self, job_id: str) -> CandidateSnapshot:
        return self._candidates.load(job_id)

    def plan_sources(self, job_id: str, out_dir: Path) -> SourcePlan:
        job, plan = self._planned_sources(job_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(out_dir / "source_plan.json", plan.model_dump(mode="json"))
        self._transition_for_sources(job, submitted=False)
        return plan

    def plan_job_sources(self, job_id: str) -> SourcePlan:
        job, plan = self._planned_sources(job_id)
        self._transition_for_sources(job, submitted=False)
        return plan

    def _planned_sources(self, job_id: str) -> tuple[Job, SourcePlan]:
        job = self._jobs.load(job_id)
        plugin = cast(AssetPlugin, ASSET_REGISTRY.get(job.manifest.asset_type))
        plan = plugin.plan_sources(job.manifest, self._reference_pack(job.manifest))
        return job, plan

    def submit_sources(self, job_id: str, sources_dir: Path) -> Job:
        job = self._service.resume(job_id)
        staged_dir = self._stage_sources(job.id, sources_dir)
        submitted_dir = self._submitted_dir(job.id)
        published = False

        def publish_submitted_sources(_candidate_job: Job) -> None:
            nonlocal published
            if submitted_dir.exists():
                raise FileExistsError(f"submitted sources already exist for job {job.id}")
            os.replace(staged_dir, submitted_dir)
            published = True
            _fsync_directory(submitted_dir.parent)

        def rollback_submitted_sources() -> None:
            if published and submitted_dir.exists():
                self._remove_tree(submitted_dir)

        try:
            if job.state is JobState.WAITING_FOR_SOURCES:
                return self._service.record_event(
                    job.id,
                    "sources_submitted",
                    f"from {sources_dir}",
                    before_persist=publish_submitted_sources,
                    rollback=rollback_submitted_sources,
                )
            return self._transition_job(
                job.id,
                JobState.WAITING_FOR_SOURCES,
                before_persist=publish_submitted_sources,
                rollback=rollback_submitted_sources,
                extra_events=(("sources_submitted", f"from {sources_dir}", None),),
            )
        finally:
            self._remove_tree_if_present(staged_dir)

    @contextmanager
    def staged_source_upload(self, job_id: str) -> Iterator[Path]:
        job = self._jobs.load(job_id)
        staged_dir = self._stage_dir(job.id, prefix=_UPLOAD_STAGE_PREFIX)
        staged_dir.mkdir(parents=True, exist_ok=False)
        try:
            yield staged_dir
        finally:
            self._remove_tree_if_present(staged_dir)

    def build(self, job_id: str) -> JobResult:
        job = self._jobs.load(job_id)
        plugin = cast(AssetPlugin, ASSET_REGISTRY.get(job.manifest.asset_type))
        return plugin.build(
            PipelineContext(job_id=job.id, workspace=self._job_workspace(job.id)),
            job.manifest,
        )

    def validate(self, spec_id: str, package_dir: Path) -> list[Diagnostic]:
        return cast(TargetSpec, SPEC_REGISTRY.get(spec_id)).validate(package_dir)

    def validate_job(self, job_id: str) -> list[Diagnostic]:
        job = self._jobs.load(job_id)
        return self.validate(
            job.manifest.target_spec,
            safe_join(self._job_workspace(job.id), "package"),
        )

    def approve(self, job_id: str, stage: str, actor: str) -> ApprovalRecord:
        if stage.strip() == "candidate":
            return self.approve_review(job_id, actor)
        with self._jobs.locked(job_id):
            self._jobs._load_locked(job_id)
            return self._approvals.approve(job_id, stage, actor)

    def reject(self, job_id: str, stage: str, actor: str, reason: str) -> ApprovalRecord:
        if stage.strip() == "candidate":
            return self.reject_review(job_id, actor, reason)
        with self._jobs.locked(job_id):
            self._jobs._load_locked(job_id)
            return self._approvals.reject(job_id, stage, actor, reason)

    def approve_review(self, job_id: str, actor: str) -> ApprovalRecord:
        normalized_actor = ensure_non_empty_text(actor, field_name="actor")
        record: ApprovalRecord | None = None

        def publish_approval(candidate_job: Job) -> None:
            nonlocal record
            self._require_state(candidate_job, JobState.WAITING_FOR_REVIEW)
            record = self._approvals.approve(candidate_job.id, "candidate", normalized_actor)

        def rollback_approval() -> None:
            if record is not None:
                self._approvals.discard_pending(record)

        self._service.record_event(
            job_id,
            "review_approved",
            "candidate approved",
            {"actor": normalized_actor},
            before_persist=publish_approval,
            rollback=rollback_approval,
        )
        if record is None:
            raise RuntimeError("approval event completed without an approval record")
        return record

    def reject_review(self, job_id: str, actor: str, reason: str) -> ApprovalRecord:
        normalized_actor = ensure_non_empty_text(actor, field_name="actor")
        record: ApprovalRecord | None = None

        def publish_rejection(candidate_job: Job) -> None:
            nonlocal record
            record = self._approvals.reject(candidate_job.id, "candidate", normalized_actor, reason)

        def rollback_rejection() -> None:
            if record is not None:
                self._approvals.discard_pending(record)

        with self._jobs.locked(job_id):
            job = self._service.resume_while_job_locked(job_id)
            self._require_state(job, JobState.WAITING_FOR_REVIEW)
            self._service.transition_path_while_job_locked(
                job.id,
                (JobState.FAILED,),
                before_persist=publish_rejection,
                rollback=rollback_rejection,
                extra_events=(
                    ("review_rejected", "candidate rejected", {"actor": normalized_actor}),
                ),
            )
        if record is None:
            raise RuntimeError("rejection transition completed without an approval record")
        return record

    def retry_job(self, job_id: str, actor: str) -> Job:
        normalized_actor = ensure_non_empty_text(actor, field_name="actor")
        candidate = self._candidates.load(job_id)
        expected_candidate_id = f"{job_id}-candidate"
        if candidate.lineage_id != expected_candidate_id:
            raise ValueError(
                "rejected job candidate lineage does not match the required "
                f"identifier: {expected_candidate_id}"
            )

        retry: Job | None = None

        def publish_retry(rejected: Job) -> None:
            nonlocal retry
            self._require_state(rejected, JobState.FAILED)
            self._require_rejected_candidate(rejected.id)
            if any(event.kind == "retry_created" for event in self._events.read(rejected.id)):
                raise InvalidTransitionError(f"retry already created for job {rejected.id}")
            retry = self._service.create_job(
                rejected.manifest,
                parent_candidate_id=expected_candidate_id,
                extra_events=(("retry_created", "retry created", {"actor": normalized_actor}),),
            )

        def rollback_retry() -> None:
            if retry is not None:
                self._jobs.remove(retry.id)

        self._service.record_event(
            job_id,
            "retry_created",
            "retry created",
            {"actor": normalized_actor},
            before_persist=publish_retry,
            rollback=rollback_retry,
        )
        if retry is None:
            raise RuntimeError("retry event completed without a replacement job")
        return retry

    def finalize_job(self, job_id: str) -> JobResult:
        job = self._jobs.load(job_id)
        self._require_state(job, JobState.WAITING_FOR_REVIEW)
        candidate = self._candidates.load(job.id)
        approval = self._candidate_approval(job.id)
        if approval is None or approval.decision != "approved":
            return JobResult(
                job_id=job.id,
                ok=False,
                diagnostics=(error("APPROVAL_MISSING", "candidate is not approved"),),
            )

        plugin = cast(AssetPlugin, ASSET_REGISTRY.get(job.manifest.asset_type))
        return plugin.finalize(
            data_root=self._settings.data_root,
            job=job,
            candidate=candidate,
            approval=approval,
        )

    def list_approval_decisions(self, job_id: str) -> list[ApprovalRecord]:
        job = self._jobs.load(job_id)
        return self._approvals.decisions(job.id)

    def get_reference_pack(self, pack_id: str, revision: int) -> ReferencePack:
        return self._refs.get(pack_id, revision)

    def list_reference_packs(self) -> list[str]:
        return self._refs.list_ids()

    def list_reference_history(self, pack_id: str) -> list[ReferencePack]:
        return self._refs.history(pack_id)

    def get_lineage(self, asset_id: str) -> LineageNode:
        return self._lineage.get(asset_id)

    def list_lineage_ancestors(self, asset_id: str) -> list[LineageNode]:
        return self._lineage.ancestors(asset_id)

    def list_lineage_children(self, asset_id: str) -> list[LineageNode]:
        return self._lineage.children(asset_id)

    def get_job_report(self, job_id: str) -> JsonObject:
        job = self._jobs.load(job_id)
        payload = read_json(self._workspace_regular_file(job.id, "report.json"))
        if not isinstance(payload, dict):
            raise ValueError("job report must contain a JSON object")
        return as_object(sanitize_json(payload, error_cls=ValueError))

    def list_bundle_entries(self, job_id: str) -> list[BundleEntry]:
        job = self._jobs.load(job_id)
        bundle_dir = self._workspace_directory(job.id, "bundle")
        entries: list[BundleEntry] = []
        stack = [bundle_dir]
        while stack:
            directory = stack.pop()
            for entry in sorted(directory.iterdir(), key=lambda path: path.name, reverse=True):
                if self._is_unsafe_workspace_entry(entry):
                    raise ValueError("unsafe bundle entry")
                if entry.is_dir():
                    stack.append(entry)
                    continue
                if not entry.is_file():
                    raise ValueError("bundle entry is not a regular file")
                entries.append(
                    BundleEntry(
                        path=entry.relative_to(bundle_dir).as_posix(),
                        size_bytes=entry.stat(follow_symlinks=False).st_size,
                    )
                )
        return sorted(entries, key=lambda entry: entry.path)

    def read_job_artifact(self, job_id: str, relative_path: str) -> bytes:
        job = self._jobs.load(job_id)
        parts = self._workspace_relative_parts(relative_path)
        if not any(
            len(parts) > len(root) and parts[: len(root)] == root for root in _ARTIFACT_ROOTS
        ):
            raise ValueError(
                "requested path is not a package artifact; job records, reports, and bundle "
                "files have dedicated sanitized reads"
            )
        return self._workspace_regular_file(job.id, relative_path).read_bytes()

    def read_bundle_file(self, job_id: str, relative_path: str) -> bytes:
        job = self._jobs.load(job_id)
        bundle_dir = self._workspace_directory(job.id, "bundle")
        return self._workspace_regular_file_from_root(bundle_dir, relative_path).read_bytes()

    def cancel(self, job_id: str) -> Job:
        return self._service.cancel(job_id)

    def events(self, job_id: str) -> list[JobEvent]:
        return self._events.read(job_id)

    def _candidate_approval(self, job_id: str) -> ApprovalRecord | None:
        decisions = [
            decision
            for decision in self._approvals.decisions(job_id)
            if decision.stage == "candidate"
        ]
        if len(decisions) > 1:
            raise ApprovalError("candidate stage has more than one decision")
        return decisions[0] if decisions else None

    def _require_rejected_candidate(self, job_id: str) -> ApprovalRecord:
        approval = self._candidate_approval(job_id)
        if approval is None or approval.decision != "rejected":
            raise InvalidTransitionError(f"job {job_id} does not have a rejected candidate")
        return approval

    def _require_state(self, job: Job, expected: JobState) -> None:
        if job.state is not expected:
            raise InvalidTransitionError(f"{job.state} is not {expected}")

    def _reference_pack(self, manifest: Manifest) -> ReferencePack | None:
        if manifest.character_ref_pack is None:
            return None
        if manifest.character_ref_pack_rev is None:
            raise UnpinnedReferencePackError(
                "character_ref_pack_rev is required for persisted jobs with character_ref_pack"
            )
        return self._refs.get(manifest.character_ref_pack, manifest.character_ref_pack_rev)

    def _pin_reference_pack(self, manifest: Manifest) -> Manifest:
        if manifest.character_ref_pack is None:
            return manifest
        pack = (
            self._refs.latest(manifest.character_ref_pack)
            if manifest.character_ref_pack_rev is None
            else self._refs.get(manifest.character_ref_pack, manifest.character_ref_pack_rev)
        )
        return manifest.model_copy(update={"character_ref_pack_rev": pack.revision})

    def _transition_for_sources(self, job: Job, *, submitted: bool) -> Job:
        target = (
            JobState.WAITING_FOR_SOURCES
            if submitted or job.manifest.provider == _MANUAL_PROVIDER_ID
            else JobState.WAITING_FOR_PROVIDER
        )
        return self._transition_job(job.id, target)

    def _transition_job(
        self,
        job_id: str,
        target: JobState,
        *,
        before_persist: TransitionPublishHook | None = None,
        rollback: TransitionRollbackHook | None = None,
        extra_events: tuple[PendingEvent, ...] = (),
    ) -> Job:
        job = self._service.resume(job_id)
        steps = self._transition_steps(job.state, target)
        if not steps:
            return job
        if len(steps) == 1:
            return self._service.transition(
                job.id,
                steps[0],
                before_persist=before_persist,
                rollback=rollback,
                extra_events=extra_events,
            )
        return self._service.transition_path(
            job.id,
            steps,
            before_persist=before_persist,
            rollback=rollback,
            extra_events=extra_events,
        )

    def _transition_steps(self, current: JobState, target: JobState) -> tuple[JobState, ...]:
        if current is target:
            return ()
        if target in {JobState.WAITING_FOR_PROVIDER, JobState.WAITING_FOR_SOURCES}:
            if current is JobState.CREATED:
                return (JobState.PLANNING, target)
            if current is JobState.PLANNING:
                return (target,)
        return (target,)

    def _job_workspace(self, job_id: str) -> Path:
        return safe_join(self._settings.data_root, "jobs", job_id)

    def _workspace_directory(self, job_id: str, name: str) -> Path:
        workspace = self._job_workspace(job_id)
        directory = safe_join(workspace, name)
        if self._is_unsafe_workspace_entry(workspace) or self._is_unsafe_workspace_entry(directory):
            raise ValueError("unsafe workspace directory")
        if not directory.is_dir():
            raise FileNotFoundError("workspace directory not found")
        return directory

    def _workspace_regular_file(self, job_id: str, relative_path: str) -> Path:
        return self._workspace_regular_file_from_root(self._job_workspace(job_id), relative_path)

    def _workspace_regular_file_from_root(self, root: Path, relative_path: str) -> Path:
        if self._is_unsafe_workspace_entry(root):
            raise ValueError("unsafe workspace directory")
        if not root.is_dir():
            raise FileNotFoundError("workspace directory not found")
        parts = self._workspace_relative_parts(relative_path)
        unresolved = root
        for part in parts:
            unresolved = unresolved / part
            if self._is_unsafe_workspace_entry(unresolved):
                raise ValueError("unsafe workspace path")
        try:
            path = safe_join(root, *parts)
        except PathEscapeError as exc:
            raise ValueError("unsafe workspace path") from exc
        if not path.is_file():
            raise FileNotFoundError("workspace artifact not found")
        return path

    def _workspace_relative_parts(self, relative_path: str) -> tuple[str, ...]:
        if "\\" in relative_path:
            raise ValueError("unsafe workspace path")
        path = PurePosixPath(relative_path)
        if (
            path.is_absolute()
            or not path.parts
            or any(part == ".." or (len(part) >= 2 and part[1] == ":") for part in path.parts)
        ):
            raise ValueError("unsafe workspace path")
        return path.parts

    def _is_unsafe_workspace_entry(self, path: Path) -> bool:
        return path.is_symlink() or self._is_reparse_point(path)

    def _submitted_dir(self, job_id: str) -> Path:
        return safe_join(self._job_workspace(job_id), _SUBMITTED_DIR)

    def _stage_dir(self, job_id: str, *, prefix: str) -> Path:
        return safe_join(self._job_workspace(job_id), f"{prefix}{uuid.uuid4().hex}")

    def _stage_sources(self, job_id: str, sources_dir: Path) -> Path:
        staged_dir = self._stage_dir(job_id, prefix=_SUBMITTED_STAGE_PREFIX)
        entries = self._validated_source_entries(sources_dir)
        try:
            staged_dir.mkdir(parents=True, exist_ok=False)
            for entry in entries:
                self._copy_regular_file(entry, staged_dir / entry.name)
        except Exception as exc:
            try:
                self._remove_tree_if_present(staged_dir)
            except Exception as cleanup_exc:
                raise cleanup_exc from exc
            raise
        return staged_dir

    def _validated_source_entries(self, sources_dir: Path) -> list[Path]:
        self._reject_unsafe_path(sources_dir)
        resolved_root = sources_dir.resolve(strict=True)
        if not sources_dir.is_dir():
            raise ValueError(f"submitted sources directory does not exist: {sources_dir}")

        entries: list[Path] = []
        for entry in sorted(sources_dir.iterdir(), key=lambda path: path.name):
            self._reject_unsafe_path(entry)
            resolved_entry = entry.resolve(strict=True)
            if resolved_entry.parent != resolved_root:
                raise ValueError(f"unsafe submission path escapes source directory: {entry}")
            if not entry.is_file():
                raise ValueError(f"submitted sources must contain only regular files: {entry}")
            entries.append(entry)
        return entries

    def _reject_unsafe_path(self, path: Path) -> None:
        if path.is_symlink() or self._is_reparse_point(path):
            raise ValueError(f"unsafe submission path is a symlink or reparse point: {path}")

    def _is_reparse_point(self, path: Path) -> bool:
        try:
            attributes = getattr(path.lstat(), "st_file_attributes", 0)
        except OSError:
            return False
        return bool(attributes & _REPARSE_POINT)

    def _copy_regular_file(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as src, destination.open("xb") as dst:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        _fsync_directory(destination.parent)

    def _remove_tree(self, path: Path) -> None:
        shutil.rmtree(path)

    def _remove_tree_if_present(self, path: Path) -> None:
        if path.exists():
            self._remove_tree(path)
