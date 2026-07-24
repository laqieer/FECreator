from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import fecreator.providers  # noqa: F401  registers provider bridges into PROVIDER_REGISTRY
import fecreator.specs  # noqa: F401  registers target specs into SPEC_REGISTRY
from fecreator.assets.base import AssetPlugin, SourcePlan
from fecreator.contracts.diagnostics import Diagnostic
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import JobResult
from fecreator.core.atomicio import read_json, write_json_atomic
from fecreator.core.config import Settings
from fecreator.core.paths import safe_join
from fecreator.core.pipeline import PipelineContext
from fecreator.core.registry import ASSET_REGISTRY, PROVIDER_REGISTRY, SPEC_REGISTRY, Registry
from fecreator.jobs.approvals import ApprovalRecord, ApprovalStore
from fecreator.jobs.events import EventLog
from fecreator.jobs.model import Job, JobEvent, JobState
from fecreator.jobs.service import JobService
from fecreator.jobs.store import JobStore
from fecreator.references.model import ReferencePack
from fecreator.references.store import ReferencePackStore
from fecreator.specs.base import TargetSpec

_TERMINAL_STATES = frozenset({JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED})
_REVIEW_STATES = frozenset({JobState.WAITING_FOR_REVIEW, JobState.VALIDATING})
_BUILD_BLOCKED_STATES = _TERMINAL_STATES | _REVIEW_STATES
_MAX_SOURCE_FILES = 64
_MAX_SOURCE_BYTES = 50 * 1024 * 1024  # 50 MB


class AppError(Exception):
    """Domain error from FeCreatorApp — safe to surface to callers."""

    def __init__(self, message: str, code: str = "APP_ERROR") -> None:
        super().__init__(message)
        self.code = code


class InvalidStateError(AppError):
    """Job is in a state that does not permit the requested operation."""

    def __init__(self, message: str) -> None:
        super().__init__(message, "INVALID_STATE")


class AssetPluginNotFoundError(AppError):
    """The asset type has no registered plugin."""

    def __init__(self, asset_type: str) -> None:
        super().__init__(
            f"no plugin registered for asset type: {asset_type!r}", "PLUGIN_NOT_FOUND"
        )


class SpecNotFoundError(AppError):
    """The spec ID is not registered."""

    def __init__(self, spec_id: str) -> None:
        super().__init__(f"unknown spec: {spec_id!r}", "SPEC_NOT_FOUND")


class FeCreatorApp:
    def __init__(
        self,
        settings: Settings,
        *,
        asset_registry: Registry[object] | None = None,
        spec_registry: Registry[object] | None = None,
        provider_registry: Registry[object] | None = None,
    ) -> None:
        # Production: import side-effecting modules to populate global registries.
        # Tests: pass custom isolated registries to avoid global-singleton pollution.
        if asset_registry is None:
            import fecreator.assets  # noqa: F401  registers asset plugins on import

            self._asset_reg: Registry[object] = ASSET_REGISTRY
        else:
            self._asset_reg = asset_registry

        self._spec_reg: Registry[object] = (
            SPEC_REGISTRY if spec_registry is None else spec_registry
        )
        self._provider_reg: Registry[object] = (
            PROVIDER_REGISTRY if provider_registry is None else provider_registry
        )

        self._settings = settings
        root = settings.data_root
        self._jobs = JobStore(root)
        self._events = EventLog(root)
        self._service = JobService(self._jobs, self._events)
        self._approvals = ApprovalStore(root)
        self._refs = ReferencePackStore(root)

    # ── registry helpers ──────────────────────────────────────────────────────

    def _get_asset_plugin(self, asset_type: str) -> AssetPlugin:
        from fecreator.core.registry import UnknownIdError

        try:
            return cast(AssetPlugin, self._asset_reg.get(asset_type))
        except UnknownIdError:
            raise AssetPluginNotFoundError(asset_type)

    def _get_spec(self, spec_id: str) -> TargetSpec:
        from fecreator.core.registry import UnknownIdError

        try:
            return cast(TargetSpec, self._spec_reg.get(spec_id))
        except UnknownIdError:
            raise SpecNotFoundError(spec_id)

    def _get_ref_pack(self, pack_id: str | None) -> ReferencePack | None:
        if not pack_id:
            return None
        try:
            return self._refs.latest(pack_id)
        except FileNotFoundError:
            return None

    # ── list operations ────────────────────────────────────────────────────────

    def list_assets(self) -> list[str]:
        return sorted(self._asset_reg.ids())

    def list_specs(self) -> list[str]:
        return sorted(self._spec_reg.ids())

    def list_providers(self) -> list[str]:
        return sorted(self._provider_reg.ids())

    # ── job lifecycle ──────────────────────────────────────────────────────────

    def create_job(self, manifest: Manifest) -> Job:
        return self._service.create_job(manifest)

    def get_job(self, job_id: str) -> Job:
        return self._jobs.load(job_id)

    def resume(self, job_id: str) -> Job:
        return self._jobs.load(job_id)

    def cancel(self, job_id: str) -> Job:
        return self._service.cancel(job_id)

    def events(self, job_id: str) -> list[JobEvent]:
        return self._events.read(job_id)

    # ── source planning & submission ──────────────────────────────────────────

    def plan_sources(self, job_id: str) -> SourcePlan:
        """Plan sources and write source_plan.json to the job workspace."""
        job = self._jobs.load(job_id)
        if job.state in _TERMINAL_STATES:
            raise InvalidStateError(
                f"plan_sources not allowed: job {job_id} is in state {job.state.value}"
            )
        if job.state == JobState.CREATED:
            self._service.transition(job_id, JobState.PLANNING)
        plugin = self._get_asset_plugin(job.manifest.asset_type)
        pack = self._get_ref_pack(job.manifest.character_ref_pack)
        plan = plugin.plan_sources(job.manifest, pack)
        out_path = safe_join(self._settings.data_root, "jobs", job_id, "source_plan.json")
        write_json_atomic(out_path, plan.model_dump(mode="json"))
        return plan

    def submit_sources(self, job_id: str, sources_dir: Path) -> Job:
        """Copy sources into the job workspace.

        Rejects symlinks/junctions, enforces no-overwrite and file count/byte limits.
        """
        job = self._jobs.load(job_id)
        if job.state in _TERMINAL_STATES:
            raise InvalidStateError(
                f"submit_sources not allowed: job {job_id} is in state {job.state.value}"
            )
        src = Path(sources_dir)
        if not src.exists():
            raise AppError(f"sources directory not found: {src}", "NOT_FOUND")
        items = [
            item
            for item in sorted(src.iterdir())
            if item.is_file() and not item.is_symlink()
        ]
        if len(items) > _MAX_SOURCE_FILES:
            raise AppError(
                f"too many source files: {len(items)} > {_MAX_SOURCE_FILES}", "TOO_MANY_FILES"
            )
        total = sum(item.stat().st_size for item in items)
        if total > _MAX_SOURCE_BYTES:
            raise AppError(
                f"sources too large: {total} bytes > {_MAX_SOURCE_BYTES}", "TOO_LARGE"
            )
        dest = safe_join(self._settings.data_root, "jobs", job_id, "submitted")
        dest.mkdir(parents=True, exist_ok=True)
        for item in items:
            target = dest / item.name
            if target.exists():
                raise AppError(f"source already submitted: {item.name!r}", "NO_OVERWRITE")
            target.write_bytes(item.read_bytes())
        self._events.append(job_id, "sources_submitted", f"{len(items)} files")
        return self._jobs.load(job_id)

    # ── generation & build ─────────────────────────────────────────────────────

    def _to_processing(self, job_id: str, job: Job) -> None:
        """Auto-transition job to PROCESSING state if not already there."""
        if job.state == JobState.PROCESSING:
            return
        if job.state == JobState.CREATED:
            self._service.transition(job_id, JobState.PLANNING)
            self._service.transition(job_id, JobState.PROCESSING)
        elif job.state == JobState.PLANNING:
            self._service.transition(job_id, JobState.PROCESSING)
        elif job.state in {JobState.WAITING_FOR_PROVIDER, JobState.WAITING_FOR_SOURCES}:
            self._service.transition(job_id, JobState.PROCESSING)

    def generate(self, job_id: str) -> JobResult:
        """Run generation pipeline step (provider → images)."""
        job = self._jobs.load(job_id)
        if job.state in _BUILD_BLOCKED_STATES:
            raise InvalidStateError(
                f"generate not allowed: job {job_id} is in state {job.state.value}"
            )
        self._to_processing(job_id, job)
        plugin = self._get_asset_plugin(job.manifest.asset_type)
        workspace = safe_join(self._settings.data_root, "jobs", job_id)
        ctx = PipelineContext(job_id=job_id, workspace=workspace)
        result = plugin.build(ctx, job.manifest)
        workspace.mkdir(parents=True, exist_ok=True)
        write_json_atomic(workspace / "generate_result.json", result.model_dump(mode="json"))
        self._events.append(job_id, "generated", "generation step complete")
        return result

    def build(self, job_id: str) -> JobResult:
        """Run build/packaging step and gate on review approval."""
        job = self._jobs.load(job_id)
        if job.state in _BUILD_BLOCKED_STATES:
            raise InvalidStateError(
                f"build not allowed: job {job_id} is in state {job.state.value}"
            )
        self._to_processing(job_id, job)
        plugin = self._get_asset_plugin(job.manifest.asset_type)
        workspace = safe_join(self._settings.data_root, "jobs", job_id)
        ctx = PipelineContext(job_id=job_id, workspace=workspace)
        result = plugin.build(ctx, job.manifest)
        workspace.mkdir(parents=True, exist_ok=True)
        write_json_atomic(workspace / "result.json", result.model_dump(mode="json"))
        self._events.append(job_id, "built", "build step complete")
        self._service.transition(job_id, JobState.WAITING_FOR_REVIEW)
        return result

    # ── validation ─────────────────────────────────────────────────────────────

    def validate(self, spec_id: str, package_dir: Path) -> list[Diagnostic]:
        """Validate an explicit local package (CLI trusted path)."""
        return self._get_spec(spec_id).validate(package_dir)

    def validate_job(self, job_id: str, spec_id: str) -> list[Diagnostic]:
        """Validate the job's submitted sources against the spec (HTTP/MCP safe)."""
        self._jobs.load(job_id)  # ensures job exists
        workspace = safe_join(self._settings.data_root, "jobs", job_id)
        submitted = workspace / "submitted"
        target_dir = submitted if submitted.exists() else workspace
        return self._get_spec(spec_id).validate(target_dir)

    # ── approval & inspection ──────────────────────────────────────────────────

    def approve(self, job_id: str, stage: str, actor: str) -> ApprovalRecord:
        """Approve a review stage; job must be in WAITING_FOR_REVIEW."""
        job = self._jobs.load(job_id)
        if job.state != JobState.WAITING_FOR_REVIEW:
            raise InvalidStateError(
                f"approve requires WAITING_FOR_REVIEW, got {job.state.value}"
            )
        record = self._approvals.approve(job_id, stage, actor)
        self._service.transition(job_id, JobState.VALIDATING)
        return record

    def reject(self, job_id: str, stage: str, actor: str, reason: str) -> ApprovalRecord:
        """Reject a review stage; job must be in WAITING_FOR_REVIEW."""
        job = self._jobs.load(job_id)
        if job.state != JobState.WAITING_FOR_REVIEW:
            raise InvalidStateError(
                f"reject requires WAITING_FOR_REVIEW, got {job.state.value}"
            )
        record = self._approvals.reject(job_id, stage, actor, reason)
        self._service.transition(job_id, JobState.FAILED)
        return record

    def inspect(self, job_id: str) -> dict[str, Any]:
        """Return detailed inspection data for a job (events, approvals, artifacts)."""
        job = self._jobs.load(job_id)
        workspace = safe_join(self._settings.data_root, "jobs", job_id)
        evts = self._events.read(job_id)
        approvals = self._approvals.decisions(job_id)
        result: Any = None
        result_path = workspace / "result.json"
        if result_path.exists():
            result = read_json(result_path)
        source_plan: Any = None
        plan_path = workspace / "source_plan.json"
        if plan_path.exists():
            source_plan = read_json(plan_path)
        return {
            "job": job.model_dump(mode="json"),
            "events": [e.model_dump(mode="json") for e in evts],
            "approvals": [a.model_dump(mode="json") for a in approvals],
            "result": result,
            "source_plan": source_plan,
        }
