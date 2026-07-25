from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal, TypeAlias

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from fecreator.app import FeCreatorApp
from fecreator.assets.base import SourcePlan
from fecreator.contracts.diagnostics import DiagData, Diagnostic, error
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import JobResult
from fecreator.core.paths import PathEscapeError, normalize_storage_id
from fecreator.core.registry import UnknownIdError
from fecreator.jobs.approvals import ApprovalError, ApprovalRecord
from fecreator.jobs.model import Job
from fecreator.jobs.service import InvalidTransitionError
from fecreator.references.store import ReferencePackCorruptionError
from fecreator.reporting.sanitize import JsonObject, as_object, sanitize_json, sanitize_text

ToolHandler: TypeAlias = Callable[..., CallToolResult]

TOOL_NAMES: list[str] = [
    "list_assets",
    "list_specs",
    "list_providers",
    "create_job",
    "get_job",
    "plan_sources",
    "submit_sources",
    "build_asset",
    "validate_asset",
    "approve_stage",
    "reject_stage",
    "cancel_job",
]


class AssetIdsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True] = True
    asset_ids: tuple[str, ...]


class SpecIdsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True] = True
    spec_ids: tuple[str, ...]


class ProviderIdsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True] = True
    provider_ids: tuple[str, ...]


class _ToolStateOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    diagnostics: tuple[Diagnostic, ...]

    @model_validator(mode="after")
    def _validate_diagnostics(self) -> _ToolStateOutput:
        if not self.ok and not self.diagnostics:
            raise ValueError("error payloads require at least one diagnostic")
        return self


class JobOutput(_ToolStateOutput):
    job: Job | None = None

    @model_validator(mode="after")
    def _validate_job(self) -> JobOutput:
        if self.ok:
            if self.job is None:
                raise ValueError("successful payloads require a job")
            if self.diagnostics:
                raise ValueError("successful payloads must not include diagnostics")
        elif self.job is not None:
            raise ValueError("error payloads must not include a job")
        return self


class SourcePlanOutput(_ToolStateOutput):
    source_plan: SourcePlan | None = None

    @model_validator(mode="after")
    def _validate_source_plan(self) -> SourcePlanOutput:
        if self.ok:
            if self.source_plan is None:
                raise ValueError("successful payloads require a source plan")
            if self.diagnostics:
                raise ValueError("successful payloads must not include diagnostics")
        elif self.source_plan is not None:
            raise ValueError("error payloads must not include a source plan")
        return self


class JobResultOutput(_ToolStateOutput):
    job_result: JobResult | None = None

    @model_validator(mode="after")
    def _validate_job_result(self) -> JobResultOutput:
        if self.ok:
            if self.job_result is None:
                raise ValueError("successful payloads require a job result")
            if self.diagnostics:
                raise ValueError("successful payloads must not include diagnostics")
        elif self.job_result is not None:
            raise ValueError("error payloads must not include a job result")
        return self


class ApprovalOutput(_ToolStateOutput):
    approval: ApprovalRecord | None = None

    @model_validator(mode="after")
    def _validate_approval(self) -> ApprovalOutput:
        if self.ok:
            if self.approval is None:
                raise ValueError("successful payloads require an approval record")
            if self.diagnostics:
                raise ValueError("successful payloads must not include diagnostics")
        elif self.approval is not None:
            raise ValueError("error payloads must not include an approval record")
        return self


class ValidationOutput(_ToolStateOutput):
    pass


class ExpectedMcpError(Exception):
    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


def _payload_object(value: BaseModel) -> JsonObject:
    return as_object(sanitize_json(value.model_dump(mode="json"), error_cls=ValueError))


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


def make_handlers(app: FeCreatorApp) -> dict[str, ToolHandler]:
    def list_assets() -> Annotated[CallToolResult, AssetIdsOutput]:
        """List registered asset plugin ids."""
        return _success_result(AssetIdsOutput(asset_ids=tuple(app.list_assets())))

    def list_specs() -> Annotated[CallToolResult, SpecIdsOutput]:
        """List registered target specification ids."""
        return _success_result(SpecIdsOutput(spec_ids=tuple(app.list_specs())))

    def list_providers() -> Annotated[CallToolResult, ProviderIdsOutput]:
        """List registered provider ids."""
        return _success_result(ProviderIdsOutput(provider_ids=tuple(app.list_providers())))

    def create_job(manifest: Manifest) -> Annotated[CallToolResult, JobOutput]:
        """Create a job from a manifest object."""
        try:
            parsed = (
                manifest if isinstance(manifest, Manifest) else Manifest.model_validate(manifest)
            )
        except ValidationError as exc:
            return _tool_result(
                JobOutput(
                    ok=False,
                    job=None,
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
        return _success_result(JobOutput(ok=True, job=app.create_job(parsed), diagnostics=()))

    def get_job(job_id: str) -> Annotated[CallToolResult, JobOutput]:
        """Get a job snapshot by id."""
        try:
            return _success_result(
                JobOutput(ok=True, job=_load_known_job(app, job_id), diagnostics=())
            )
        except ExpectedMcpError as exc:
            return _tool_result(
                JobOutput(ok=False, job=None, diagnostics=(exc.diagnostic,)),
                is_error=True,
            )

    def plan_sources(job_id: str, out_dir: str) -> Annotated[CallToolResult, SourcePlanOutput]:
        """Plan required source files and write a source_plan.json file into out_dir."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(
                SourcePlanOutput(
                    ok=True,
                    source_plan=app.plan_sources(job.id, Path(out_dir)),
                    diagnostics=(),
                )
            )
        except ExpectedMcpError as exc:
            return _tool_result(
                SourcePlanOutput(ok=False, source_plan=None, diagnostics=(exc.diagnostic,)),
                is_error=True,
            )
        except FileNotFoundError as exc:
            if job.manifest.character_ref_pack is not None:
                return _tool_result(
                    SourcePlanOutput(
                        ok=False,
                        source_plan=None,
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
                SourcePlanOutput(
                    ok=False,
                    source_plan=None,
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
                SourcePlanOutput(
                    ok=False,
                    source_plan=None,
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
        except (InvalidTransitionError, OSError, PathEscapeError, ValueError) as exc:
            return _tool_result(
                SourcePlanOutput(
                    ok=False,
                    source_plan=None,
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

    def submit_sources(job_id: str, sources_dir: str) -> Annotated[CallToolResult, JobOutput]:
        """Submit manually prepared source files from sources_dir for an existing job."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(
                JobOutput(
                    ok=True, job=app.submit_sources(job.id, Path(sources_dir)), diagnostics=()
                )
            )
        except ExpectedMcpError as exc:
            return _tool_result(
                JobOutput(ok=False, job=None, diagnostics=(exc.diagnostic,)),
                is_error=True,
            )
        except (
            FileExistsError,
            FileNotFoundError,
            InvalidTransitionError,
            OSError,
            PathEscapeError,
            ValueError,
        ) as exc:
            return _tool_result(
                JobOutput(
                    ok=False,
                    job=None,
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
            return _success_result(
                JobResultOutput(ok=True, job_result=app.build(job.id), diagnostics=())
            )
        except ExpectedMcpError as exc:
            return _tool_result(
                JobResultOutput(ok=False, job_result=None, diagnostics=(exc.diagnostic,)),
                is_error=True,
            )
        except (OSError, PathEscapeError, UnknownIdError, ValueError) as exc:
            return _tool_result(
                JobResultOutput(
                    ok=False,
                    job_result=None,
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
            return _success_result(ValidationOutput(ok=True, diagnostics=tuple(diagnostics)))
        except UnknownIdError as exc:
            return _tool_result(
                ValidationOutput(
                    ok=False,
                    diagnostics=(
                        error("UNKNOWN_SPEC", "unknown target spec", where=str(exc.args[0])),
                    ),
                ),
                is_error=True,
            )
        except (OSError, PathEscapeError, ValueError) as exc:
            return _tool_result(
                ValidationOutput(
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

    def approve_stage(
        job_id: str, stage: str, actor: str
    ) -> Annotated[CallToolResult, ApprovalOutput]:
        """Record an approval decision for a job stage."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(
                ApprovalOutput(ok=True, approval=app.approve(job.id, stage, actor), diagnostics=())
            )
        except ExpectedMcpError as exc:
            return _tool_result(
                ApprovalOutput(ok=False, approval=None, diagnostics=(exc.diagnostic,)),
                is_error=True,
            )
        except (ApprovalError, ValueError) as exc:
            return _tool_result(
                ApprovalOutput(
                    ok=False,
                    approval=None,
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
                ApprovalOutput(
                    ok=True,
                    approval=app.reject(job.id, stage, actor, reason),
                    diagnostics=(),
                )
            )
        except ExpectedMcpError as exc:
            return _tool_result(
                ApprovalOutput(ok=False, approval=None, diagnostics=(exc.diagnostic,)),
                is_error=True,
            )
        except (ApprovalError, ValueError) as exc:
            return _tool_result(
                ApprovalOutput(
                    ok=False,
                    approval=None,
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

    def cancel_job(job_id: str) -> Annotated[CallToolResult, JobOutput]:
        """Cancel an existing job."""
        try:
            job = _load_known_job(app, job_id)
            return _success_result(JobOutput(ok=True, job=app.cancel(job.id), diagnostics=()))
        except ExpectedMcpError as exc:
            return _tool_result(
                JobOutput(ok=False, job=None, diagnostics=(exc.diagnostic,)),
                is_error=True,
            )
        except InvalidTransitionError as exc:
            return _tool_result(
                JobOutput(
                    ok=False,
                    job=None,
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
        "list_assets": list_assets,
        "list_specs": list_specs,
        "list_providers": list_providers,
        "create_job": create_job,
        "get_job": get_job,
        "plan_sources": plan_sources,
        "submit_sources": submit_sources,
        "build_asset": build_asset,
        "validate_asset": validate_asset,
        "approve_stage": approve_stage,
        "reject_stage": reject_stage,
        "cancel_job": cancel_job,
    }


def build_mcp(app: FeCreatorApp) -> FastMCP:
    server = FastMCP("fecreator")
    for name, handler in make_handlers(app).items():
        server.tool(name=name)(handler)
    return server
