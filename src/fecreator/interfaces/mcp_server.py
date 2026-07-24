from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from fecreator.app import FeCreatorApp
from fecreator.contracts.manifest import Manifest

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


def make_handlers(app: FeCreatorApp) -> dict[str, Callable[..., object]]:
    return {
        "list_assets": lambda: app.list_assets(),
        "list_specs": lambda: app.list_specs(),
        "list_providers": lambda: app.list_providers(),
        "create_job": lambda manifest: app.create_job(Manifest.model_validate(manifest)).model_dump(
            mode="json"
        ),
        "get_job": lambda job_id: app.get_job(job_id).model_dump(mode="json"),
        "plan_sources": lambda job_id, out_dir: app.plan_sources(job_id, Path(out_dir)).model_dump(
            mode="json"
        ),
        "submit_sources": lambda job_id, sources_dir: app.submit_sources(
            job_id, Path(sources_dir)
        ).model_dump(mode="json"),
        "build_asset": lambda job_id: app.build(job_id).model_dump(mode="json"),
        "validate_asset": lambda spec_id, path: [
            d.model_dump(mode="json") for d in app.validate(spec_id, Path(path))
        ],
        "approve_stage": lambda job_id, stage, actor: app.approve(job_id, stage, actor).model_dump(
            mode="json"
        ),
        "reject_stage": lambda job_id, stage, actor, reason: app.reject(
            job_id, stage, actor, reason
        ).model_dump(mode="json"),
        "cancel_job": lambda job_id: app.cancel(job_id).model_dump(mode="json"),
    }


def build_mcp(app: FeCreatorApp) -> FastMCP:
    server = FastMCP("fecreator")
    for name, handler in make_handlers(app).items():
        server.tool(name=name)(handler)
    return server
