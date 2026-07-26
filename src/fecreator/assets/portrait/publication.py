from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from fecreator.contracts.diagnostics import Diagnostic, error, has_errors
from fecreator.contracts.lineage import LineageNode, Operation
from fecreator.contracts.result import Artifact, JobResult, StageResult
from fecreator.contracts.review import CandidateSnapshot
from fecreator.core.atomicio import _fsync_directory, write_json_atomic
from fecreator.core.clock import utc_now_iso
from fecreator.core.hashing import sha256_file
from fecreator.core.paths import safe_join
from fecreator.jobs.approvals import ApprovalRecord
from fecreator.jobs.events import EventLog
from fecreator.jobs.model import Job, JobState
from fecreator.jobs.service import JobService
from fecreator.jobs.store import JobStore
from fecreator.lineage.store import LineageStore
from fecreator.reporting.bundle import build_bundle
from fecreator.reporting.json_report import build_report, write_report
from fecreator.specs.fire_emblem.gba.portrait_standard.spec import FeGbaPortraitStandard

_PUBLICATION_STAGE_PREFIX = ".publication-stage-"


@dataclass
class _FinalPublication:
    data_root: Path
    candidate: CandidateSnapshot
    approval: ApprovalRecord
    diagnostics: tuple[Diagnostic, ...]
    lineage: LineageNode
    lineage_nodes: tuple[LineageNode, ...]
    final_artifacts: tuple[Artifact, ...] = ()
    staged_root: Path | None = None
    package_published: bool = field(init=False, default=False)
    report_published: bool = field(init=False, default=False)
    lineage_file_published: bool = field(init=False, default=False)
    bundle_published: bool = field(init=False, default=False)
    lineage_published: bool = field(init=False, default=False)

    def publish(self, completed_job: Job) -> None:
        workspace = _workspace(self.data_root, completed_job.id)
        self._assert_public_destinations_absent(workspace)
        self.staged_root = safe_join(
            workspace,
            f"{_PUBLICATION_STAGE_PREFIX}{uuid.uuid4().hex}",
        )
        self.staged_root.mkdir(parents=True, exist_ok=False)
        self.final_artifacts = self._stage(completed_job)
        self._publish(workspace)
        _remove_tree(self.staged_root)

    def rollback(self) -> None:
        workspace = _workspace(self.data_root, self.candidate.job_id)
        if self.lineage_published:
            LineageStore(self.data_root).discard_pending(self.lineage.asset_id)
            self.lineage_published = False
        if self.bundle_published:
            _remove_tree(safe_join(workspace, "bundle"))
            self.bundle_published = False
        if self.lineage_file_published:
            safe_join(workspace, "lineage.json").unlink()
            self.lineage_file_published = False
        if self.report_published:
            safe_join(workspace, "report.json").unlink()
            self.report_published = False
        if self.package_published:
            _remove_tree(safe_join(workspace, "package"))
            self.package_published = False
        if self.staged_root is not None:
            _remove_tree(self.staged_root)

    def _assert_public_destinations_absent(self, workspace: Path) -> None:
        destinations = (
            safe_join(workspace, "package"),
            safe_join(workspace, "report.json"),
            safe_join(workspace, "lineage.json"),
            safe_join(workspace, "bundle"),
        )
        existing = [path.name for path in destinations if path.exists()]
        if existing:
            raise FileExistsError(
                "final publication destinations already exist: " + ", ".join(sorted(existing))
            )

    def _stage(self, completed_job: Job) -> tuple[Artifact, ...]:
        if self.staged_root is None:
            raise RuntimeError("final publication staging root was not initialized")
        candidate_package = safe_join(
            self.data_root,
            "jobs",
            completed_job.id,
            "candidate",
            "package",
        )
        staged_package = safe_join(self.staged_root, "package")
        final_artifacts = _copy_candidate_package(
            candidate_package,
            staged_package,
            self.candidate.artifacts,
        )
        candidate_stage = StageResult(
            stage="candidate",
            ok=True,
            artifacts=self.candidate.artifacts,
            metrics=self.candidate.metrics,
            diagnostics=self.candidate.diagnostics,
        )
        final_stage = StageResult(
            stage="finalize",
            ok=True,
            artifacts=final_artifacts,
            metrics=self.candidate.metrics,
            diagnostics=self.diagnostics,
        )
        report = build_report(
            completed_job,
            (candidate_stage, final_stage),
            self.lineage_nodes,
            approval=self.approval,
        )
        write_report(safe_join(self.staged_root, "report.json"), report)
        write_json_atomic(
            safe_join(self.staged_root, "lineage.json"),
            [node.model_dump(mode="json") for node in self.lineage_nodes],
        )
        build_bundle(completed_job, self.staged_root, safe_join(self.staged_root, "bundle"))
        return final_artifacts

    def _publish(self, workspace: Path) -> None:
        if self.staged_root is None:
            raise RuntimeError("final publication staging root was not initialized")
        package = safe_join(self.staged_root, "package")
        report = safe_join(self.staged_root, "report.json")
        lineage_file = safe_join(self.staged_root, "lineage.json")
        bundle = safe_join(self.staged_root, "bundle")

        os.replace(package, safe_join(workspace, "package"))
        self.package_published = True
        _fsync_directory(workspace)
        os.replace(report, safe_join(workspace, "report.json"))
        self.report_published = True
        _fsync_directory(workspace)
        os.replace(lineage_file, safe_join(workspace, "lineage.json"))
        self.lineage_file_published = True
        _fsync_directory(workspace)
        os.replace(bundle, safe_join(workspace, "bundle"))
        self.bundle_published = True
        _fsync_directory(workspace)
        LineageStore(self.data_root).add(self.lineage)
        self.lineage_published = True


def finalize_candidate(
    *,
    data_root: Path,
    job: Job,
    candidate: CandidateSnapshot,
    approval: ApprovalRecord,
) -> JobResult:
    if (
        approval.job_id != job.id
        or approval.stage != "candidate"
        or approval.decision != "approved"
    ):
        return JobResult(
            job_id=job.id,
            ok=False,
            diagnostics=(error("APPROVAL_MISSING", "candidate is not approved"),),
        )
    if candidate.job_id != job.id:
        return JobResult(
            job_id=job.id,
            ok=False,
            diagnostics=(error("CANDIDATE_MISMATCH", "candidate does not belong to this job"),),
        )
    expected_candidate_id = f"{job.id}-candidate"
    if candidate.lineage_id != expected_candidate_id:
        return JobResult(
            job_id=job.id,
            ok=False,
            diagnostics=(
                error(
                    "CANDIDATE_MISMATCH",
                    "candidate lineage does not match the required job candidate identifier",
                ),
            ),
        )

    candidate_package = safe_join(data_root, "jobs", job.id, "candidate", "package")
    diagnostics = tuple(FeGbaPortraitStandard().validate(candidate_package))
    if has_errors(diagnostics):
        return JobResult(job_id=job.id, ok=False, diagnostics=diagnostics)

    return publish_final_artifacts_atomically(
        data_root=data_root,
        job=job,
        candidate=candidate,
        approval=approval,
        diagnostics=diagnostics,
    )


def publish_final_artifacts_atomically(
    *,
    data_root: Path,
    job: Job,
    candidate: CandidateSnapshot,
    approval: ApprovalRecord,
    diagnostics: tuple[Diagnostic, ...],
) -> JobResult:
    lineage_store = LineageStore(data_root)
    candidate_node = lineage_store.get(candidate.lineage_id)
    ancestors = tuple(lineage_store.ancestors(candidate.lineage_id))
    final_artifacts = _final_artifacts(candidate, _candidate_package(data_root, job.id))
    export = LineageNode(
        asset_id=f"{job.id}-export",
        operation=Operation.EXPORT_SPEC,
        parents=(f"{job.id}-candidate",),
        provider=job.manifest.provider,
        params=job.manifest.params,
        metrics=candidate.metrics,
        approved_by=approval.actor,
        output_hashes=tuple(sorted(artifact.sha256 for artifact in final_artifacts)),
        created_at=utc_now_iso(),
    )
    publication = _FinalPublication(
        data_root=data_root,
        candidate=candidate,
        approval=approval,
        diagnostics=diagnostics,
        lineage=export,
        lineage_nodes=(*ancestors, candidate_node, export),
    )
    service = JobService(JobStore(data_root), EventLog(data_root))
    service.transition_path(
        job.id,
        (JobState.VALIDATING, JobState.COMPLETED),
        before_persist=publication.publish,
        rollback=publication.rollback,
    )
    return JobResult(
        job_id=job.id,
        ok=True,
        artifacts=publication.final_artifacts,
        diagnostics=(*candidate.diagnostics, *diagnostics),
        lineage_id=export.asset_id,
    )


def _workspace(data_root: Path, job_id: str) -> Path:
    return safe_join(data_root, "jobs", job_id)


def _candidate_package(data_root: Path, job_id: str) -> Path:
    return safe_join(data_root, "jobs", job_id, "candidate", "package")


def _copy_candidate_package(
    candidate_package: Path,
    staged_package: Path,
    candidate_artifacts: tuple[Artifact, ...],
) -> tuple[Artifact, ...]:
    source_files = sorted(candidate_package.iterdir(), key=lambda path: path.name)
    staged_package.mkdir(parents=True, exist_ok=False)
    for source in source_files:
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"candidate package contains an unsafe entry: {source.name}")
        shutil.copy2(source, safe_join(staged_package, source.name))
    return _final_artifacts(candidate_artifacts, staged_package)


def _final_artifacts(
    candidate_artifacts: CandidateSnapshot | tuple[Artifact, ...],
    package_dir: Path,
) -> tuple[Artifact, ...]:
    artifacts = (
        candidate_artifacts.artifacts
        if isinstance(candidate_artifacts, CandidateSnapshot)
        else candidate_artifacts
    )
    final: list[Artifact] = []
    artifact_paths: set[str] = set()
    for artifact in artifacts:
        if not artifact.path.startswith("candidate/package/"):
            raise ValueError(
                f"candidate artifact is outside the candidate package: {artifact.path}"
            )
        relative = artifact.path.removeprefix("candidate/package/")
        pure_relative = PurePosixPath(relative)
        if (
            "\\" in relative
            or pure_relative.is_absolute()
            or not pure_relative.parts
            or any(part in {"", ".", ".."} for part in pure_relative.parts)
        ):
            raise ValueError(f"candidate artifact path is unsafe: {artifact.path}")
        relative_path = pure_relative.as_posix()
        if relative_path in artifact_paths:
            raise ValueError(f"candidate artifacts duplicate package file: {relative_path}")
        source = safe_join(package_dir, *pure_relative.parts)
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"candidate artifact is missing from the package: {relative_path}")
        actual_hash = sha256_file(source)
        if actual_hash != artifact.sha256:
            raise ValueError(f"candidate artifact hash changed: {relative_path}")
        artifact_paths.add(relative_path)
        final.append(
            Artifact(
                role=artifact.role,
                path=f"package/{relative_path}",
                sha256=actual_hash,
                media_type=artifact.media_type,
            )
        )
    package_files = {
        path.relative_to(package_dir).as_posix()
        for path in package_dir.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    if artifact_paths != package_files:
        raise ValueError("candidate snapshot does not describe exactly the candidate package")
    return tuple(final)


def _remove_tree(path: Path) -> None:
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        return
