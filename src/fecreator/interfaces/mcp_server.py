from __future__ import annotations

import base64
import functools
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Annotated, Literal, TypeAlias

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, ConfigDict, RootModel, ValidationError

from fecreator.app import FeCreatorApp
from fecreator.assets.base import SourcePlan
from fecreator.contracts.diagnostics import DiagData, Diagnostic, error
from fecreator.contracts.lineage import LineageNode
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import JobResult
from fecreator.contracts.review import CandidateSnapshot
from fecreator.core.atomicio import LockTimeoutError
from fecreator.core.paths import PathEscapeError, normalize_storage_id
from fecreator.core.registry import UnknownIdError
from fecreator.interfaces.errors import store_lock_timeout_diagnostic
from fecreator.jobs.approvals import ApprovalError, ApprovalRecord
from fecreator.jobs.model import Job
from fecreator.jobs.service import InvalidTransitionError
from fecreator.jobs.store import JobCorruptionError
from fecreator.lineage.store import UnknownParentAssetError
from fecreator.references.model import ReferencePack
from fecreator.references.store import ReferencePackCorruptionError, UnknownReferencePackError
from fecreator.reporting.bundle import BundleEntry
from fecreator.reporting.sanitize import (
    OPAQUE_BASE64_KEYS,
    JsonObject,
    as_object,
    sanitize_json,
    sanitize_text,
)

ToolHandler: TypeAlias = Callable[..., CallToolResult]
ManifestToolInput: TypeAlias = object
CREATE_JOB_INPUT_SCHEMA = {
    "properties": {"manifest": Manifest.model_json_schema()},
    "required": ["manifest"],
    "title": "create_jobArguments",
    "type": "object",
}

TOOL_NAMES: list[str] = [
    "list_assets",
    "list_specs",
    "list_providers",
    "list_jobs",
    "create_job",
    "get_job",
    "get_job_candidate",
    "list_approval_decisions",
    "plan_sources",
    "plan_job_sources",
    "submit_sources",
    "build_asset",
    "validate_asset",
    "validate_job",
    "read_job_artifact",
    "get_job_report",
    "list_bundle_entries",
    "read_bundle_file",
    "list_reference_packs",
    "list_reference_history",
    "get_lineage",
    "list_lineage_ancestors",
    "list_lineage_children",
    "approve_stage",
    "reject_stage",
    "approve_review",
    "reject_review",
    "finalize_job",
    "retry_job",
    "cancel_job",
]


class AssetIdsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True]
    asset_ids: tuple[str, ...]


class SpecIdsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True]
    spec_ids: tuple[str, ...]


class ProviderIdsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True]
    provider_ids: tuple[str, ...]


class ToolErrorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[False]
    diagnostics: tuple[Diagnostic, ...]

    def model_post_init(self, __context: object) -> None:
        if not self.diagnostics:
            raise ValueError("error payloads require at least one diagnostic")


class JobsSuccessOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True]
    jobs: tuple[Job, ...]


class JobsOutput(RootModel[JobsSuccessOutput | ToolErrorOutput]):
    pass


class JobSuccessOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True]
    job: Job


class JobOutput(RootModel[JobSuccessOutput | ToolErrorOutput]):
    pass


class CandidateSuccessOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True]
    candidate: CandidateSnapshot


class CandidateOutput(RootModel[CandidateSuccessOutput | ToolErrorOutput]):
    pass


class ApprovalsSuccessOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True]
    approvals: tuple[ApprovalRecord, ...]


class ApprovalsOutput(RootModel[ApprovalsSuccessOutput | ToolErrorOutput]):
    pass


class SourcePlanSuccessOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True]
    source_plan: SourcePlan


class SourcePlanOutput(RootModel[SourcePlanSuccessOutput | ToolErrorOutput]):
    pass


class JobResultSuccessOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True]
    job_result: JobResult


class JobResultOutput(RootModel[JobResultSuccessOutput | ToolErrorOutput]):
    pass


class ApprovalSuccessOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True]
    approval: ApprovalRecord


class ApprovalOutput(RootModel[ApprovalSuccessOutput | ToolErrorOutput]):
    pass


class ValidationSuccessOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True]
    diagnostics: tuple[Diagnostic, ...]


class ValidationOutput(RootModel[ValidationSuccessOutput | ToolErrorOutput]):
    pass


class FileContent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    content_base64: str


class FileSuccessOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True]
    file: FileContent


class FileOutput(RootModel[FileSuccessOutput | ToolErrorOutput]):
    pass


class ReportSuccessOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True]
    report: Mapping[str, object]


class ReportOutput(RootModel[ReportSuccessOutput | ToolErrorOutput]):
    pass


class BundleEntriesSuccessOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True]
    bundle_entries: tuple[BundleEntry, ...]


class BundleEntriesOutput(RootModel[BundleEntriesSuccessOutput | ToolErrorOutput]):
    pass


class ReferencePackIdsSuccessOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True]
    reference_pack_ids: tuple[str, ...]


class ReferencePackIdsOutput(RootModel[ReferencePackIdsSuccessOutput | ToolErrorOutput]):
    pass


class ReferenceHistorySuccessOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True]
    reference_packs: tuple[ReferencePack, ...]


class ReferenceHistoryOutput(RootModel[ReferenceHistorySuccessOutput | ToolErrorOutput]):
    pass


class LineageSuccessOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True]
    lineage: LineageNode


class LineageOutput(RootModel[LineageSuccessOutput | ToolErrorOutput]):
    pass


class LineageListSuccessOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True]
    lineage: tuple[LineageNode, ...]


class LineageListOutput(RootModel[LineageListSuccessOutput | ToolErrorOutput]):
    pass


class ExpectedMcpError(Exception):
    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


def _payload_object(value: BaseModel) -> JsonObject:
    return as_object(
        sanitize_json(
            value.model_dump(mode="json"),
            error_cls=ValueError,
            opaque_keys=OPAQUE_BASE64_KEYS,
        )
    )


def _tool_result(payload: BaseModel, *, is_error: bool) -> CallToolResult:
    structured_content = _payload_object(payload)
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=json.dumps(structured_content, indent=2, sort_keys=True),
            )
        ],
        structuredContent=structured_content,
        isError=is_error,
    )


def _success_result(payload: BaseModel) -> CallToolResult:
    return _tool_result(payload, is_error=False)


def _detail_data(exc: Exception) -> DiagData | None:
    detail = str(exc).strip()
    if not detail:
        return None
    return {"detail": sanitize_text(detail)}


def _load_known_job(app: FeCreatorApp, job_id: str) -> Job:
    try:
        normalized = normalize_storage_id(job_id, field_name="job_id")
        return app.get_job(normalized)
    except (FileNotFoundError, PathEscapeError, ValueError) as exc:
        raise ExpectedMcpError(error("UNKNOWN_JOB", "job not found", where=job_id)) from exc


def _error_result(diagnostic: Diagnostic) -> CallToolResult:
    return _tool_result(ToolErrorOutput(ok=False, diagnostics=(diagnostic,)), is_error=True)


def _file_content(path: str, content: bytes) -> FileContent:
    return FileContent(path=path, content_base64=base64.b64encode(content).decode("ascii"))


def _with_lock_conflict_mapping(name: str, handler: ToolHandler) -> ToolHandler:
    """Report store lock contention as an ordinary structured tool failure.

    Every tool routes through the same locked stores, so the mapping is applied
    once at the tool boundary rather than repeated in thirty handlers. The tool
    name is the only location detail returned; the exception text names absolute
    lock paths and is discarded.
    """

    @functools.wraps(handler)
    def guarded(*args: object, **kwargs: object) -> CallToolResult:
        try:
            return handler(*args, **kwargs)
        except LockTimeoutError:
            return _error_result(store_lock_timeout_diagnostic(where=name))

    return guarded


def make_handlers(app: FeCreatorApp) -> dict[str, ToolHandler]:
    def list_assets() -> Annotated[CallToolResult, AssetIdsOutput]:
        """List registered asset plugin ids."""
        return _success_result(AssetIdsOutput(ok=True, asset_ids=tuple(app.list_assets())))

    def list_specs() -> Annotated[CallToolResult, SpecIdsOutput]:
        """List registered target specification ids."""
        return _success_result(SpecIdsOutput(ok=True, spec_ids=tuple(app.list_specs())))

    def list_providers() -> Annotated[CallToolResult, ProviderIdsOutput]:
        """List registered provider ids."""
        return _success_result(ProviderIdsOutput(ok=True, provider_ids=tuple(app.list_providers())))

    def list_jobs() -> Annotated[CallToolResult, JobsOutput]:
        """List current jobs."""
        try:
            return _success_result(JobsSuccessOutput(ok=True, jobs=tuple(app.list_jobs())))
        except JobCorruptionError:
            return _error_result(
                error("CORRUPT_JOB", "job store contains a corrupt job", where="jobs")
            )

    def create_job(manifest: ManifestToolInput) -> Annotated[CallToolResult, JobOutput]:
        """Create a job from a manifest object."""
        try:
            parsed = Manifest.model_validate(manifest)
        except ValidationError as exc:
            return _tool_result(
                ToolErrorOutput(
                    ok=False,
                    diagnostics=(
                        error(
                            "INVALID_MANIFEST",
                            "manifest failed validation",
                            where="manifest",
                            data={"error_count": len(exc.errors())},
                        ),
                    ),
                ),
                is_error=True,
            )
        try:
            return _success_result(JobSuccessOutput(ok=True, job=app.create_job(parsed)))
        except ReferencePackCorruptionError:
            return _error_result(
                error(
                    "CORRUPT_REFERENCE_PACK",
                    "reference pack is corrupt",
                    where=parsed.character_ref_pack,
                )
            )
        except UnknownReferencePackError:
            return _error_result(
                error(
                    "UNKNOWN_REFERENCE_PACK",
                    "reference pack not found",
                    where=parsed.character_ref_pack,
                )
            )
        except UnknownParentAssetError:
            return _error_result(
                error("UNKNOWN_LINEAGE", "parent asset not found", where=parsed.parent_asset_id)
            )

    def get_job(job_id: str) -> Annotated[CallToolResult, JobOutput]:
        """Get a job snapshot by id."""
        try:
            return _success_result(JobSuccessOutput(ok=True, job=_load_known_job(app, job_id)))
        except ExpectedMcpError as exc:
            return _error_result(exc.diagnostic)

    def get_job_candidate(job_id: str) -> Annotated[CallToolResult, CandidateOutput]:
        """Get a job's current review candidate."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(
                CandidateSuccessOutput(ok=True, candidate=app.get_job_candidate(job.id))
            )
        except ExpectedMcpError as exc:
            return _error_result(exc.diagnostic)
        except FileNotFoundError:
            return _error_result(
                error("CANDIDATE_NOT_FOUND", "job candidate not found", where=job_id)
            )

    def list_approval_decisions(job_id: str) -> Annotated[CallToolResult, ApprovalsOutput]:
        """List persisted approval decisions for a job."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(
                ApprovalsSuccessOutput(
                    ok=True,
                    approvals=tuple(app.list_approval_decisions(job.id)),
                )
            )
        except ExpectedMcpError as exc:
            return _error_result(exc.diagnostic)

    def plan_sources(job_id: str, out_dir: str) -> Annotated[CallToolResult, SourcePlanOutput]:
        """Plan required source files and write a source_plan.json file into out_dir."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(
                SourcePlanSuccessOutput(
                    ok=True,
                    source_plan=app.plan_sources(job.id, Path(out_dir)),
                )
            )
        except ExpectedMcpError as exc:
            return _tool_result(
                ToolErrorOutput(ok=False, diagnostics=(exc.diagnostic,)),
                is_error=True,
            )
        except FileNotFoundError as exc:
            if job.manifest.character_ref_pack is not None:
                return _tool_result(
                    ToolErrorOutput(
                        ok=False,
                        diagnostics=(
                            error(
                                "UNKNOWN_REFERENCE_PACK",
                                "reference pack not found",
                                where=job.manifest.character_ref_pack,
                            ),
                        ),
                    ),
                    is_error=True,
                )
            return _tool_result(
                ToolErrorOutput(
                    ok=False,
                    diagnostics=(
                        error(
                            "PLAN_SOURCES_FAILED",
                            "could not plan sources",
                            where=out_dir,
                            data=_detail_data(exc),
                        ),
                    ),
                ),
                is_error=True,
            )
        except ReferencePackCorruptionError:
            return _tool_result(
                ToolErrorOutput(
                    ok=False,
                    diagnostics=(
                        error(
                            "CORRUPT_REFERENCE_PACK",
                            "reference pack is corrupt",
                            where=job.manifest.character_ref_pack,
                        ),
                    ),
                ),
                is_error=True,
            )
        except LockTimeoutError:
            raise
        except (InvalidTransitionError, OSError, PathEscapeError, ValueError) as exc:
            return _tool_result(
                ToolErrorOutput(
                    ok=False,
                    diagnostics=(
                        error(
                            "PLAN_SOURCES_FAILED",
                            "could not plan sources",
                            where=out_dir,
                            data=_detail_data(exc),
                        ),
                    ),
                ),
                is_error=True,
            )

    def plan_job_sources(job_id: str) -> Annotated[CallToolResult, SourcePlanOutput]:
        """Plan sources for a job without writing an interface-owned plan file."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(
                SourcePlanSuccessOutput(ok=True, source_plan=app.plan_job_sources(job.id))
            )
        except ExpectedMcpError as exc:
            return _error_result(exc.diagnostic)
        except FileNotFoundError as exc:
            if job.manifest.character_ref_pack is not None:
                return _error_result(
                    error(
                        "UNKNOWN_REFERENCE_PACK",
                        "reference pack not found",
                        where=job.manifest.character_ref_pack,
                    )
                )
            return _error_result(
                error(
                    "PLAN_SOURCES_FAILED",
                    "could not plan sources",
                    where=job_id,
                    data=_detail_data(exc),
                )
            )
        except ReferencePackCorruptionError:
            return _error_result(
                error(
                    "CORRUPT_REFERENCE_PACK",
                    "reference pack is corrupt",
                    where=job.manifest.character_ref_pack,
                )
            )
        except LockTimeoutError:
            raise
        except (InvalidTransitionError, OSError, PathEscapeError, ValueError) as exc:
            return _error_result(
                error(
                    "PLAN_SOURCES_FAILED",
                    "could not plan sources",
                    where=job_id,
                    data=_detail_data(exc),
                )
            )

    def submit_sources(job_id: str, sources_dir: str) -> Annotated[CallToolResult, JobOutput]:
        """Submit manually prepared source files from sources_dir for an existing job."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(
                JobSuccessOutput(ok=True, job=app.submit_sources(job.id, Path(sources_dir)))
            )
        except ExpectedMcpError as exc:
            return _tool_result(
                ToolErrorOutput(ok=False, diagnostics=(exc.diagnostic,)),
                is_error=True,
            )
        except LockTimeoutError:
            raise
        except (
            FileExistsError,
            FileNotFoundError,
            InvalidTransitionError,
            OSError,
            PathEscapeError,
            ValueError,
        ) as exc:
            return _tool_result(
                ToolErrorOutput(
                    ok=False,
                    diagnostics=(
                        error(
                            "SUBMIT_SOURCES_FAILED",
                            "could not submit sources",
                            where=sources_dir,
                            data=_detail_data(exc),
                        ),
                    ),
                ),
                is_error=True,
            )

    def build_asset(job_id: str) -> Annotated[CallToolResult, JobResultOutput]:
        """Build an asset for an existing job."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(JobResultSuccessOutput(ok=True, job_result=app.build(job.id)))
        except ReferencePackCorruptionError:
            return _tool_result(
                ToolErrorOutput(
                    ok=False,
                    diagnostics=(
                        error(
                            "CORRUPT_REFERENCE_PACK",
                            "reference pack is corrupt",
                            where=job.manifest.character_ref_pack,
                        ),
                    ),
                ),
                is_error=True,
            )
        except ExpectedMcpError as exc:
            return _tool_result(
                ToolErrorOutput(ok=False, diagnostics=(exc.diagnostic,)),
                is_error=True,
            )
        except LockTimeoutError:
            raise
        except (
            InvalidTransitionError,
            OSError,
            PathEscapeError,
            UnknownIdError,
            ValueError,
        ) as exc:
            return _tool_result(
                ToolErrorOutput(
                    ok=False,
                    diagnostics=(
                        error(
                            "BUILD_ASSET_FAILED",
                            "could not build asset",
                            where=job_id,
                            data=_detail_data(exc),
                        ),
                    ),
                ),
                is_error=True,
            )

    def validate_asset(spec_id: str, path: str) -> Annotated[CallToolResult, ValidationOutput]:
        """Validate an exported package directory against a target spec."""
        try:
            diagnostics = app.validate(spec_id, Path(path))
            return _success_result(ValidationSuccessOutput(ok=True, diagnostics=tuple(diagnostics)))
        except UnknownIdError as exc:
            return _tool_result(
                ToolErrorOutput(
                    ok=False,
                    diagnostics=(
                        error("UNKNOWN_SPEC", "unknown target spec", where=str(exc.args[0])),
                    ),
                ),
                is_error=True,
            )
        except LockTimeoutError:
            raise
        except (OSError, PathEscapeError, ValueError) as exc:
            return _tool_result(
                ToolErrorOutput(
                    ok=False,
                    diagnostics=(
                        error(
                            "VALIDATE_ASSET_FAILED",
                            "could not validate asset",
                            where=path,
                            data=_detail_data(exc),
                        ),
                    ),
                ),
                is_error=True,
            )

    def validate_job(job_id: str) -> Annotated[CallToolResult, ValidationOutput]:
        """Validate the final package published for a job."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(
                ValidationSuccessOutput(ok=True, diagnostics=tuple(app.validate_job(job.id)))
            )
        except ExpectedMcpError as exc:
            return _error_result(exc.diagnostic)
        except LockTimeoutError:
            raise
        except (OSError, PathEscapeError, UnknownIdError, ValueError) as exc:
            return _error_result(
                error(
                    "VALIDATE_JOB_FAILED",
                    "could not validate job",
                    where=job_id,
                    data=_detail_data(exc),
                )
            )

    def read_job_artifact(
        job_id: str,
        relative_path: str,
    ) -> Annotated[CallToolResult, FileOutput]:
        """Read a regular artifact file contained in the job workspace."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(
                FileSuccessOutput(
                    ok=True,
                    file=_file_content(
                        relative_path,
                        app.read_job_artifact(job.id, relative_path),
                    ),
                )
            )
        except ExpectedMcpError as exc:
            return _error_result(exc.diagnostic)
        except LockTimeoutError:
            raise
        except (FileNotFoundError, OSError, PathEscapeError, ValueError) as exc:
            return _error_result(
                error(
                    "READ_ARTIFACT_FAILED",
                    "could not read job artifact",
                    where=relative_path,
                    data=_detail_data(exc),
                )
            )

    def get_job_report(job_id: str) -> Annotated[CallToolResult, ReportOutput]:
        """Read the sanitized final report for a job."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(ReportSuccessOutput(ok=True, report=app.get_job_report(job.id)))
        except ExpectedMcpError as exc:
            return _error_result(exc.diagnostic)
        except LockTimeoutError:
            raise
        except (FileNotFoundError, OSError, PathEscapeError, ValueError) as exc:
            return _error_result(
                error(
                    "READ_REPORT_FAILED",
                    "could not read job report",
                    where=job_id,
                    data=_detail_data(exc),
                )
            )

    def list_bundle_entries(job_id: str) -> Annotated[CallToolResult, BundleEntriesOutput]:
        """List regular files in a job's reproducibility bundle."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(
                BundleEntriesSuccessOutput(
                    ok=True,
                    bundle_entries=tuple(app.list_bundle_entries(job.id)),
                )
            )
        except ExpectedMcpError as exc:
            return _error_result(exc.diagnostic)
        except LockTimeoutError:
            raise
        except (FileNotFoundError, OSError, PathEscapeError, ValueError) as exc:
            return _error_result(
                error(
                    "LIST_BUNDLE_FAILED",
                    "could not list job bundle",
                    where=job_id,
                    data=_detail_data(exc),
                )
            )

    def read_bundle_file(
        job_id: str,
        relative_path: str,
    ) -> Annotated[CallToolResult, FileOutput]:
        """Read a regular file from a job's reproducibility bundle."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(
                FileSuccessOutput(
                    ok=True,
                    file=_file_content(
                        relative_path,
                        app.read_bundle_file(job.id, relative_path),
                    ),
                )
            )
        except ExpectedMcpError as exc:
            return _error_result(exc.diagnostic)
        except LockTimeoutError:
            raise
        except (FileNotFoundError, OSError, PathEscapeError, ValueError) as exc:
            return _error_result(
                error(
                    "READ_BUNDLE_FILE_FAILED",
                    "could not read bundle file",
                    where=relative_path,
                    data=_detail_data(exc),
                )
            )

    def list_reference_packs() -> Annotated[CallToolResult, ReferencePackIdsOutput]:
        """List available reference-pack identifiers."""
        try:
            return _success_result(
                ReferencePackIdsSuccessOutput(
                    ok=True,
                    reference_pack_ids=tuple(app.list_reference_packs()),
                )
            )
        except LockTimeoutError:
            raise
        except (OSError, PathEscapeError, ReferencePackCorruptionError, ValueError):
            return _error_result(
                error(
                    "CORRUPT_REFERENCE_PACK",
                    "reference pack store is corrupt",
                    where="references",
                )
            )

    def list_reference_history(pack_id: str) -> Annotated[CallToolResult, ReferenceHistoryOutput]:
        """List immutable revisions for a reference pack."""
        try:
            normalized_pack_id = normalize_storage_id(pack_id, field_name="pack_id")
            return _success_result(
                ReferenceHistorySuccessOutput(
                    ok=True,
                    reference_packs=tuple(app.list_reference_history(normalized_pack_id)),
                )
            )
        except ReferencePackCorruptionError:
            return _error_result(
                error("CORRUPT_REFERENCE_PACK", "reference pack is corrupt", where=pack_id)
            )
        except (FileNotFoundError, PathEscapeError, ValueError):
            return _error_result(
                error("UNKNOWN_REFERENCE_PACK", "reference pack not found", where=pack_id)
            )

    def get_lineage(asset_id: str) -> Annotated[CallToolResult, LineageOutput]:
        """Get a lineage node by asset identifier."""
        try:
            normalized_asset_id = normalize_storage_id(asset_id, field_name="asset_id")
            return _success_result(
                LineageSuccessOutput(ok=True, lineage=app.get_lineage(normalized_asset_id))
            )
        except (FileNotFoundError, PathEscapeError, ValueError):
            return _error_result(
                error("UNKNOWN_LINEAGE", "lineage asset not found", where=asset_id)
            )

    def list_lineage_ancestors(asset_id: str) -> Annotated[CallToolResult, LineageListOutput]:
        """List ancestors for a lineage node."""
        try:
            normalized_asset_id = normalize_storage_id(asset_id, field_name="asset_id")
            return _success_result(
                LineageListSuccessOutput(
                    ok=True,
                    lineage=tuple(app.list_lineage_ancestors(normalized_asset_id)),
                )
            )
        except (FileNotFoundError, PathEscapeError, ValueError):
            return _error_result(
                error("UNKNOWN_LINEAGE", "lineage asset not found", where=asset_id)
            )

    def list_lineage_children(asset_id: str) -> Annotated[CallToolResult, LineageListOutput]:
        """List children for a lineage node."""
        try:
            normalized_asset_id = normalize_storage_id(asset_id, field_name="asset_id")
            return _success_result(
                LineageListSuccessOutput(
                    ok=True,
                    lineage=tuple(app.list_lineage_children(normalized_asset_id)),
                )
            )
        except (FileNotFoundError, PathEscapeError, ValueError):
            return _error_result(
                error("UNKNOWN_LINEAGE", "lineage asset not found", where=asset_id)
            )

    def approve_stage(
        job_id: str, stage: str, actor: str
    ) -> Annotated[CallToolResult, ApprovalOutput]:
        """Record an approval decision for a job stage."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(
                ApprovalSuccessOutput(ok=True, approval=app.approve(job.id, stage, actor))
            )
        except ExpectedMcpError as exc:
            return _tool_result(
                ToolErrorOutput(ok=False, diagnostics=(exc.diagnostic,)),
                is_error=True,
            )
        except (ApprovalError, ValueError) as exc:
            return _tool_result(
                ToolErrorOutput(
                    ok=False,
                    diagnostics=(
                        error(
                            "APPROVE_STAGE_FAILED",
                            "could not approve stage",
                            where=stage,
                            data=_detail_data(exc),
                        ),
                    ),
                ),
                is_error=True,
            )

    def reject_stage(
        job_id: str,
        stage: str,
        actor: str,
        reason: str,
    ) -> Annotated[CallToolResult, ApprovalOutput]:
        """Record a rejection decision for a job stage."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(
                ApprovalSuccessOutput(ok=True, approval=app.reject(job.id, stage, actor, reason))
            )
        except ExpectedMcpError as exc:
            return _tool_result(
                ToolErrorOutput(ok=False, diagnostics=(exc.diagnostic,)),
                is_error=True,
            )
        except (ApprovalError, ValueError) as exc:
            return _tool_result(
                ToolErrorOutput(
                    ok=False,
                    diagnostics=(
                        error(
                            "REJECT_STAGE_FAILED",
                            "could not reject stage",
                            where=stage,
                            data=_detail_data(exc),
                        ),
                    ),
                ),
                is_error=True,
            )

    def approve_review(job_id: str, actor: str) -> Annotated[CallToolResult, ApprovalOutput]:
        """Approve the current review candidate for a job."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(
                ApprovalSuccessOutput(ok=True, approval=app.approve_review(job.id, actor))
            )
        except ExpectedMcpError as exc:
            return _error_result(exc.diagnostic)
        except (ApprovalError, InvalidTransitionError, ValueError) as exc:
            return _error_result(
                error(
                    "APPROVE_REVIEW_FAILED",
                    "could not approve candidate review",
                    where=job_id,
                    data=_detail_data(exc),
                )
            )

    def reject_review(
        job_id: str,
        actor: str,
        reason: str,
    ) -> Annotated[CallToolResult, ApprovalOutput]:
        """Reject the current review candidate for a job."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(
                ApprovalSuccessOutput(
                    ok=True,
                    approval=app.reject_review(job.id, actor, reason),
                )
            )
        except ExpectedMcpError as exc:
            return _error_result(exc.diagnostic)
        except (ApprovalError, InvalidTransitionError, ValueError) as exc:
            return _error_result(
                error(
                    "REJECT_REVIEW_FAILED",
                    "could not reject candidate review",
                    where=job_id,
                    data=_detail_data(exc),
                )
            )

    def finalize_job(job_id: str) -> Annotated[CallToolResult, JobResultOutput]:
        """Finalize an approved candidate into an immutable package and bundle."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(
                JobResultSuccessOutput(ok=True, job_result=app.finalize_job(job.id))
            )
        except ExpectedMcpError as exc:
            return _error_result(exc.diagnostic)
        except LockTimeoutError:
            raise
        except (ApprovalError, InvalidTransitionError, OSError, PathEscapeError, ValueError) as exc:
            return _error_result(
                error(
                    "FINALIZE_JOB_FAILED",
                    "could not finalize job",
                    where=job_id,
                    data=_detail_data(exc),
                )
            )

    def retry_job(job_id: str, actor: str) -> Annotated[CallToolResult, JobOutput]:
        """Create an immutable retry job from a rejected candidate."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(JobSuccessOutput(ok=True, job=app.retry_job(job.id, actor)))
        except ExpectedMcpError as exc:
            return _error_result(exc.diagnostic)
        except (ApprovalError, InvalidTransitionError, ValueError) as exc:
            return _error_result(
                error(
                    "RETRY_JOB_FAILED",
                    "could not retry job",
                    where=job_id,
                    data=_detail_data(exc),
                )
            )

    def cancel_job(job_id: str) -> Annotated[CallToolResult, JobOutput]:
        """Cancel an existing job."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(JobSuccessOutput(ok=True, job=app.cancel(job.id)))
        except ExpectedMcpError as exc:
            return _tool_result(
                ToolErrorOutput(ok=False, diagnostics=(exc.diagnostic,)),
                is_error=True,
            )
        except InvalidTransitionError as exc:
            return _tool_result(
                ToolErrorOutput(
                    ok=False,
                    diagnostics=(
                        error(
                            "CANCEL_JOB_FAILED",
                            "could not cancel job",
                            where=job_id,
                            data=_detail_data(exc),
                        ),
                    ),
                ),
                is_error=True,
            )

    return {
        name: _with_lock_conflict_mapping(name, handler)
        for name, handler in (
            ("list_assets", list_assets),
            ("list_specs", list_specs),
            ("list_providers", list_providers),
            ("list_jobs", list_jobs),
            ("create_job", create_job),
            ("get_job", get_job),
            ("get_job_candidate", get_job_candidate),
            ("list_approval_decisions", list_approval_decisions),
            ("plan_sources", plan_sources),
            ("plan_job_sources", plan_job_sources),
            ("submit_sources", submit_sources),
            ("build_asset", build_asset),
            ("validate_asset", validate_asset),
            ("validate_job", validate_job),
            ("read_job_artifact", read_job_artifact),
            ("get_job_report", get_job_report),
            ("list_bundle_entries", list_bundle_entries),
            ("read_bundle_file", read_bundle_file),
            ("list_reference_packs", list_reference_packs),
            ("list_reference_history", list_reference_history),
            ("get_lineage", get_lineage),
            ("list_lineage_ancestors", list_lineage_ancestors),
            ("list_lineage_children", list_lineage_children),
            ("approve_stage", approve_stage),
            ("reject_stage", reject_stage),
            ("approve_review", approve_review),
            ("reject_review", reject_review),
            ("finalize_job", finalize_job),
            ("retry_job", retry_job),
            ("cancel_job", cancel_job),
        )
    }


def build_mcp(app: FeCreatorApp) -> FastMCP:
    server = FastMCP("fecreator")
    for name, handler in make_handlers(app).items():
        tool = server._tool_manager.add_tool(handler, name=name)
        if name == "create_job":
            tool.parameters = CREATE_JOB_INPUT_SCHEMA
    return server
