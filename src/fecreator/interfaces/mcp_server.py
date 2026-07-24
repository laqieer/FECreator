from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from fecreator.app import AppError, FeCreatorApp, InvalidStateError
from fecreator.contracts.manifest import Manifest
from fecreator.core.redaction import redact

TOOL_NAMES: list[str] = [
    "list_assets",
    "list_specs",
    "list_providers",
    "create_job",
    "get_job",
    "plan_sources",
    "submit_sources",
    "generate_asset",
    "build_asset",
    "validate_asset",
    "inspect_asset",
    "approve_stage",
    "reject_stage",
    "cancel_job",
]


def _wrap(fn: Any) -> Any:
    """Wrap a named handler so domain errors become ToolError (redacted)."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except FileNotFoundError:
            # Never echo path from FileNotFoundError — use fixed safe message
            raise ToolError("not found") from None
        except (InvalidStateError, AppError) as exc:
            raise ToolError(redact(str(exc))) from exc
        except Exception:
            raise ToolError("internal error") from None

    return wrapper


def make_handlers(app: FeCreatorApp) -> dict[str, Any]:
    def list_assets() -> list[str]:
        """List all registered asset types."""
        return app.list_assets()

    def list_specs() -> list[str]:
        """List all registered target specifications."""
        return app.list_specs()

    def list_providers() -> list[str]:
        """List all registered image providers."""
        return app.list_providers()

    def create_job(manifest: dict[str, Any]) -> dict[str, Any]:
        """Create a new job from a manifest dict. Returns the created Job."""
        return app.create_job(Manifest.model_validate(manifest)).model_dump(mode="json")

    def get_job(job_id: str) -> dict[str, Any]:
        """Get current state of a job by ID."""
        return app.get_job(job_id).model_dump(mode="json")

    def plan_sources(job_id: str) -> dict[str, Any]:
        """Plan source files for a job. Writes source_plan.json to job workspace."""
        return app.plan_sources(job_id).model_dump(mode="json")

    def submit_sources(job_id: str, staged_subdir: str = "staged") -> dict[str, Any]:
        """Submit sources from the job staged subdirectory into submitted area."""
        from fecreator.core.paths import safe_join

        workspace = safe_join(app._settings.data_root, "jobs", job_id)
        sources_dir = safe_join(workspace, staged_subdir)
        return app.submit_sources(job_id, sources_dir).model_dump(mode="json")

    def generate_asset(job_id: str) -> dict[str, Any]:
        """Run the generation pipeline step (provider -> images) for a job."""
        return app.generate(job_id).model_dump(mode="json")

    def build_asset(job_id: str) -> dict[str, Any]:
        """Run the build/packaging step. Requires review approval to proceed past gate."""
        return app.build(job_id).model_dump(mode="json")

    def validate_asset(job_id: str, spec_id: str) -> list[dict[str, Any]]:
        """Validate the job workspace against a spec. Returns diagnostics."""
        return [d.model_dump(mode="json") for d in app.validate_job(job_id, spec_id)]

    def inspect_asset(job_id: str) -> dict[str, Any]:
        """Return detailed inspection data for a job (events, approvals, artifacts)."""
        return app.inspect(job_id)

    def approve_stage(job_id: str, stage: str, actor: str) -> dict[str, Any]:
        """Approve a review stage. Job must be in WAITING_FOR_REVIEW state."""
        return app.approve(job_id, stage, actor).model_dump(mode="json")

    def reject_stage(job_id: str, stage: str, actor: str, reason: str) -> dict[str, Any]:
        """Reject a review stage with reason. Job must be in WAITING_FOR_REVIEW state."""
        return app.reject(job_id, stage, actor, reason).model_dump(mode="json")

    def cancel_job(job_id: str) -> dict[str, Any]:
        """Cancel a job."""
        return app.cancel(job_id).model_dump(mode="json")

    raw: dict[str, Any] = {
        "list_assets": list_assets,
        "list_specs": list_specs,
        "list_providers": list_providers,
        "create_job": create_job,
        "get_job": get_job,
        "plan_sources": plan_sources,
        "submit_sources": submit_sources,
        "generate_asset": generate_asset,
        "build_asset": build_asset,
        "validate_asset": validate_asset,
        "inspect_asset": inspect_asset,
        "approve_stage": approve_stage,
        "reject_stage": reject_stage,
        "cancel_job": cancel_job,
    }
    return {name: _wrap(fn) for name, fn in raw.items()}


def build_mcp(app: FeCreatorApp) -> FastMCP:
    server = FastMCP("fecreator")
    for name, handler in make_handlers(app).items():
        server.tool(name=name)(handler)
    return server
