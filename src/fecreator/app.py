from __future__ import annotations

import os
import shutil
import stat
import uuid
from pathlib import Path
from typing import cast

import fecreator.providers  # noqa: F401
import fecreator.specs  # noqa: F401
from fecreator.assets import register_builtin_assets
from fecreator.assets.base import AssetPlugin, SourcePlan
from fecreator.contracts.diagnostics import Diagnostic
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import JobResult
from fecreator.core.atomicio import _fsync_directory, write_json_atomic
from fecreator.core.config import Settings
from fecreator.core.paths import safe_join
from fecreator.core.pipeline import PipelineContext
from fecreator.core.registry import ASSET_REGISTRY, PROVIDER_REGISTRY, SPEC_REGISTRY
from fecreator.jobs.approvals import ApprovalRecord, ApprovalStore
from fecreator.jobs.events import EventLog, PendingEvent
from fecreator.jobs.model import Job, JobEvent, JobState
from fecreator.jobs.service import JobService, TransitionPublishHook, TransitionRollbackHook
from fecreator.jobs.store import JobStore
from fecreator.references.model import ReferencePack
from fecreator.references.store import ReferencePackStore
from fecreator.specs.base import TargetSpec

_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_MANUAL_PROVIDER_ID = "manual"
_SUBMITTED_DIR = "submitted"
_SUBMITTED_STAGE_PREFIX = ".submitted-stage-"


class FeCreatorApp:
    def __init__(self, settings: Settings) -> None:
        register_builtin_assets()
        self._settings = settings
        root = settings.data_root
        self._jobs = JobStore(root)
        self._events = EventLog(root)
        self._service = JobService(self._jobs, self._events)
        self._approvals = ApprovalStore(root)
        self._refs = ReferencePackStore(root)

    def list_assets(self) -> list[str]:
        return sorted(ASSET_REGISTRY.ids())

    def list_specs(self) -> list[str]:
        return sorted(SPEC_REGISTRY.ids())

    def list_providers(self) -> list[str]:
        return sorted(PROVIDER_REGISTRY.ids())

    def create_job(self, manifest: Manifest) -> Job:
        return self._service.create_job(manifest)

    def get_job(self, job_id: str) -> Job:
        return self._jobs.load(job_id)

    def plan_sources(self, job_id: str, out_dir: Path) -> SourcePlan:
        job = self._jobs.load(job_id)
        plugin = cast(AssetPlugin, ASSET_REGISTRY.get(job.manifest.asset_type))
        plan = plugin.plan_sources(job.manifest, self._reference_pack(job.manifest))
        out_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(out_dir / "source_plan.json", plan.model_dump(mode="json"))
        self._transition_for_sources(job, submitted=False)
        return plan

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

    def build(self, job_id: str) -> JobResult:
        job = self._jobs.load(job_id)
        plugin = cast(AssetPlugin, ASSET_REGISTRY.get(job.manifest.asset_type))
        return plugin.build(
            PipelineContext(job_id=job.id, workspace=self._job_workspace(job.id)),
            job.manifest,
        )

    def validate(self, spec_id: str, package_dir: Path) -> list[Diagnostic]:
        return cast(TargetSpec, SPEC_REGISTRY.get(spec_id)).validate(package_dir)

    def approve(self, job_id: str, stage: str, actor: str) -> ApprovalRecord:
        return self._approvals.approve(job_id, stage, actor)

    def reject(self, job_id: str, stage: str, actor: str, reason: str) -> ApprovalRecord:
        return self._approvals.reject(job_id, stage, actor, reason)

    def cancel(self, job_id: str) -> Job:
        return self._service.cancel(job_id)

    def events(self, job_id: str) -> list[JobEvent]:
        return self._events.read(job_id)

    def _reference_pack(self, manifest: Manifest) -> ReferencePack | None:
        if manifest.character_ref_pack is None:
            return None
        return self._refs.latest(manifest.character_ref_pack)

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
