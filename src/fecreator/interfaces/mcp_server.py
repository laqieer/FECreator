from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TypeAlias, cast

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ValidationError

from fecreator.app import FeCreatorApp
from fecreator.contracts.diagnostics import DiagData, Diagnostic, error
from fecreator.contracts.manifest import Manifest
from fecreator.core.paths import PathEscapeError, normalize_storage_id
from fecreator.core.registry import UnknownIdError
from fecreator.jobs.approvals import ApprovalError
from fecreator.jobs.service import InvalidTransitionError
from fecreator.reporting.sanitize import JsonObject, JsonValue, as_object, sanitize_json

ToolHandler: TypeAlias = Callable[..., object]

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


class ExpectedMcpError(Exception):
    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


def _payload(value: object) -> JsonValue:
    if isinstance(value, BaseModel):
        return sanitize_json(value.model_dump(mode="json"), error_cls=ValueError)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        items = [
            item.model_dump(mode="json") if isinstance(item, BaseModel) else item for item in value
        ]
        return sanitize_json(items, error_cls=ValueError)
    if isinstance(value, Mapping):
        return sanitize_json(dict(value), error_cls=ValueError)
    return sanitize_json(value, error_cls=ValueError)


def _payload_object(value: object) -> JsonObject:
    return as_object(_payload(value))


def _diagnostics_payload(diagnostics: Sequence[Diagnostic]) -> list[JsonObject]:
    return cast(list[JsonObject], _payload(diagnostics))


def _failure_payload(diagnostic: Diagnostic) -> JsonObject:
    return {
        "ok": False,
        "diagnostics": cast(JsonValue, _diagnostics_payload((diagnostic,))),
    }


def _detail_data(exc: Exception) -> DiagData | None:
    detail = str(exc).strip()
    if not detail:
        return None
    return {"detail": detail}


def _normalize_known_job_id(app: FeCreatorApp, job_id: str) -> str:
    try:
        normalized = normalize_storage_id(job_id, field_name="job_id")
        app.get_job(normalized)
    except (FileNotFoundError, PathEscapeError, ValueError) as exc:
        raise ExpectedMcpError(error("UNKNOWN_JOB", "job not found", where=job_id)) from exc
    return normalized


def make_handlers(app: FeCreatorApp) -> dict[str, ToolHandler]:
    def list_assets() -> list[str]:
        """List registered asset plugin ids."""
        return app.list_assets()

    def list_specs() -> list[str]:
        """List registered target specification ids."""
        return app.list_specs()

    def list_providers() -> list[str]:
        """List registered provider ids."""
        return app.list_providers()

    def create_job(manifest: dict[str, object]) -> JsonObject:
        """Create a job from a manifest object."""
        try:
            parsed = Manifest.model_validate(manifest)
        except ValidationError as exc:
            return _failure_payload(
                error(
                    "INVALID_MANIFEST",
                    "manifest failed validation",
                    where="manifest",
                    data={"error_count": len(exc.errors())},
                )
            )
        return _payload_object(app.create_job(parsed))

    def get_job(job_id: str) -> JsonObject:
        """Get a job snapshot by id."""
        try:
            normalized_job_id = _normalize_known_job_id(app, job_id)
            return _payload_object(app.get_job(normalized_job_id))
        except ExpectedMcpError as exc:
            return _failure_payload(exc.diagnostic)

    def plan_sources(job_id: str, out_dir: str) -> JsonObject:
        """Plan required source files and write a source_plan.json file into out_dir."""
        try:
            normalized_job_id = _normalize_known_job_id(app, job_id)
            return _payload_object(app.plan_sources(normalized_job_id, Path(out_dir)))
        except ExpectedMcpError as exc:
            return _failure_payload(exc.diagnostic)
        except InvalidTransitionError as exc:
            return _failure_payload(
                error(
                    "PLAN_SOURCES_FAILED",
                    "could not plan sources",
                    where=out_dir,
                    data=_detail_data(exc),
                )
            )

    def submit_sources(job_id: str, sources_dir: str) -> JsonObject:
        """Submit manually prepared source files from sources_dir for an existing job."""
        try:
            normalized_job_id = _normalize_known_job_id(app, job_id)
            return _payload_object(app.submit_sources(normalized_job_id, Path(sources_dir)))
        except ExpectedMcpError as exc:
            return _failure_payload(exc.diagnostic)
        except (
            FileExistsError,
            FileNotFoundError,
            InvalidTransitionError,
            PathEscapeError,
            ValueError,
        ) as exc:
            return _failure_payload(
                error(
                    "SUBMIT_SOURCES_FAILED",
                    "could not submit sources",
                    where=sources_dir,
                    data=_detail_data(exc),
                )
            )

    def build_asset(job_id: str) -> JsonObject:
        """Build an asset for an existing job."""
        try:
            normalized_job_id = _normalize_known_job_id(app, job_id)
            return _payload_object(app.build(normalized_job_id))
        except ExpectedMcpError as exc:
            return _failure_payload(exc.diagnostic)

    def validate_asset(spec_id: str, path: str) -> list[JsonObject] | JsonObject:
        """Validate an exported package directory against a target spec."""
        try:
            return cast(list[JsonObject], _payload(app.validate(spec_id, Path(path))))
        except UnknownIdError as exc:
            return _failure_payload(
                error("UNKNOWN_SPEC", "unknown target spec", where=cast(str, exc.args[0]))
            )

    def approve_stage(job_id: str, stage: str, actor: str) -> JsonObject:
        """Record an approval decision for a job stage."""
        try:
            normalized_job_id = _normalize_known_job_id(app, job_id)
            return _payload_object(app.approve(normalized_job_id, stage, actor))
        except ExpectedMcpError as exc:
            return _failure_payload(exc.diagnostic)
        except (ApprovalError, ValueError) as exc:
            return _failure_payload(
                error(
                    "APPROVE_STAGE_FAILED",
                    "could not approve stage",
                    where=stage,
                    data=_detail_data(exc),
                )
            )

    def reject_stage(job_id: str, stage: str, actor: str, reason: str) -> JsonObject:
        """Record a rejection decision for a job stage."""
        try:
            normalized_job_id = _normalize_known_job_id(app, job_id)
            return _payload_object(app.reject(normalized_job_id, stage, actor, reason))
        except ExpectedMcpError as exc:
            return _failure_payload(exc.diagnostic)
        except (ApprovalError, ValueError) as exc:
            return _failure_payload(
                error(
                    "REJECT_STAGE_FAILED",
                    "could not reject stage",
                    where=stage,
                    data=_detail_data(exc),
                )
            )

    def cancel_job(job_id: str) -> JsonObject:
        """Cancel an existing job."""
        try:
            normalized_job_id = _normalize_known_job_id(app, job_id)
            return _payload_object(app.cancel(normalized_job_id))
        except ExpectedMcpError as exc:
            return _failure_payload(exc.diagnostic)
        except InvalidTransitionError as exc:
            return _failure_payload(
                error(
                    "CANCEL_JOB_FAILED",
                    "could not cancel job",
                    where=job_id,
                    data=_detail_data(exc),
                )
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
        server.tool(name=name, structured_output=False)(handler)
    return server
