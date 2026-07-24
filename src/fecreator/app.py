from __future__ import annotations

import shutil
from pathlib import Path
from typing import cast

import fecreator.assets  # noqa: F401  registers asset plugins on import
import fecreator.providers  # noqa: F401  registers provider bridges
import fecreator.specs  # noqa: F401  registers target specs
from fecreator.assets.base import AssetPlugin, SourcePlan
from fecreator.contracts.diagnostics import Diagnostic
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import JobResult
from fecreator.core.atomicio import write_json_atomic
from fecreator.core.config import Settings
from fecreator.core.paths import safe_join
from fecreator.core.pipeline import PipelineContext
from fecreator.core.registry import ASSET_REGISTRY, PROVIDER_REGISTRY, SPEC_REGISTRY
from fecreator.jobs.approvals import ApprovalRecord, ApprovalStore
from fecreator.jobs.events import EventLog
from fecreator.jobs.model import Job, JobEvent
from fecreator.jobs.service import JobService
from fecreator.jobs.store import JobStore
from fecreator.references.store import ReferencePackStore
from fecreator.specs.base import TargetSpec


class FeCreatorApp:
    def __init__(self, settings: Settings) -> None:
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

    def cancel(self, job_id: str) -> Job:
        return self._service.cancel(job_id)

    def approve(self, job_id: str, stage: str, actor: str) -> ApprovalRecord:
        return self._approvals.approve(job_id, stage, actor)

    def reject(self, job_id: str, stage: str, actor: str, reason: str) -> ApprovalRecord:
        return self._approvals.reject(job_id, stage, actor, reason)

    def events(self, job_id: str) -> list[JobEvent]:
        return self._events.read(job_id)

    def validate(self, spec_id: str, package_dir: Path) -> list[Diagnostic]:
        return cast(TargetSpec, SPEC_REGISTRY.get(spec_id)).validate(package_dir)

    def plan_sources(self, job_id: str, out_dir: Path) -> SourcePlan:
        job = self._jobs.load(job_id)
        plugin = cast(AssetPlugin, ASSET_REGISTRY.get(job.manifest.asset_type))
        pack = (
            self._refs.latest(job.manifest.character_ref_pack)
            if job.manifest.character_ref_pack
            else None
        )
        plan = plugin.plan_sources(job.manifest, pack)
        out_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(out_dir / "source_plan.json", plan.model_dump(mode="json"))
        return plan

    def submit_sources(self, job_id: str, sources_dir: Path) -> Job:
        job = self._jobs.load(job_id)
        dest = safe_join(self._settings.data_root, "jobs", job_id, "submitted")
        dest.mkdir(parents=True, exist_ok=True)
        for item in sorted(Path(sources_dir).glob("*")):
            if item.is_file():
                shutil.copy2(item, dest / item.name)
        self._events.append(job_id, "sources_submitted", f"from {sources_dir}")
        return job

    def build(self, job_id: str) -> JobResult:
        job = self._jobs.load(job_id)
        plugin = cast(AssetPlugin, ASSET_REGISTRY.get(job.manifest.asset_type))
        workspace = safe_join(self._settings.data_root, "jobs", job_id)
        ctx = PipelineContext(job_id=job_id, workspace=workspace)
        return plugin.build(ctx, job.manifest)
