from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal, TypeAlias

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, ConfigDict, RootModel, ValidationError

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


class JobSuccessOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True]
    job: Job


class JobOutput(RootModel[JobSuccessOutput | ToolErrorOutput]):
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
        return _success_result(AssetIdsOutput(ok=True, asset_ids=tuple(app.list_assets())))

    def list_specs() -> Annotated[CallToolResult, SpecIdsOutput]:
        """List registered target specification ids."""
        return _success_result(SpecIdsOutput(ok=True, spec_ids=tuple(app.list_specs())))

    def list_providers() -> Annotated[CallToolResult, ProviderIdsOutput]:
        """List registered provider ids."""
        return _success_result(ProviderIdsOutput(ok=True, provider_ids=tuple(app.list_providers())))

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
        return _success_result(JobSuccessOutput(ok=True, job=app.create_job(parsed)))

    def get_job(job_id: str) -> Annotated[CallToolResult, JobOutput]:
        """Get a job snapshot by id."""
        try:
            return _success_result(JobSuccessOutput(ok=True, job=_load_known_job(app, job_id)))
        except ExpectedMcpError as exc:
            return _tool_result(
                ToolErrorOutput(ok=False, diagnostics=(exc.diagnostic,)),
                is_error=True,
            )

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
        except ExpectedMcpError as exc:
            return _tool_result(
                ToolErrorOutput(ok=False, diagnostics=(exc.diagnostic,)),
                is_error=True,
            )
        except (OSError, PathEscapeError, UnknownIdError, ValueError) as exc:
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
        tool = server._tool_manager.add_tool(handler, name=name)
        if name == "create_job":
            tool.parameters = CREATE_JOB_INPUT_SCHEMA
    return server
