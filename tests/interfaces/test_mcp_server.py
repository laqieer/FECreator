from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from mcp.types import CallToolResult, Tool

from fecreator.app import FeCreatorApp
from fecreator.contracts.manifest import Manifest
from fecreator.core.config import Settings
from fecreator.interfaces.mcp_server import TOOL_NAMES, build_mcp, make_handlers


def _app(data_root: Path) -> FeCreatorApp:
    return FeCreatorApp(Settings(data_root=data_root))


def _manifest_payload(
    *,
    provider: str = "fake",
    character_ref_pack: str | None = None,
) -> dict[str, object]:
    return {
        "asset_type": "portrait",
        "target_spec": "fe-gba-portrait-standard",
        "workflow": "text_to_portrait",
        "provider": provider,
        "character_ref_pack": character_ref_pack,
        "sources": [{"kind": "text", "ref": "hero"}],
    }


async def _tools_by_name(data_root: Path) -> dict[str, Tool]:
    server = build_mcp(_app(data_root))
    return {tool.name: tool for tool in await server.list_tools()}


def _structured_content(result: CallToolResult) -> dict[str, object]:
    return cast(dict[str, object], result.structuredContent)


def _serialized_result(result: CallToolResult) -> str:
    return json.dumps(result.model_dump(mode="json"), sort_keys=True)


def test_tool_names_match_design() -> None:
    assert TOOL_NAMES == [
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


def test_handlers_cover_all_tools(data_root: Path) -> None:
    handlers = make_handlers(_app(data_root))

    assert list(handlers) == TOOL_NAMES


def test_list_specs_handler_matches_app(data_root: Path) -> None:
    app = _app(data_root)
    result = cast(CallToolResult, make_handlers(app)["list_specs"]())

    assert result.isError is False
    assert _structured_content(result) == {
        "ok": True,
        "spec_ids": ["fe-gba-portrait-standard"],
    }


def test_create_job_handler_returns_structured_payload(data_root: Path) -> None:
    result = cast(CallToolResult, make_handlers(_app(data_root))["create_job"](_manifest_payload()))
    payload = _structured_content(result)

    assert result.isError is False
    assert payload["ok"] is True
    assert payload["job"]["manifest"]["provider"] == "fake"
    assert payload["job"]["state"] == "created"


async def test_build_mcp_exposes_exact_manifest_schema_for_create_job(data_root: Path) -> None:
    create_job = (await _tools_by_name(data_root))["create_job"]

    assert create_job.inputSchema["properties"]["manifest"] == {"$ref": "#/$defs/Manifest"}
    assert create_job.inputSchema["$defs"]["Manifest"]["additionalProperties"] is False
    assert create_job.inputSchema["$defs"]["Manifest"]["required"] == list(
        Manifest.model_json_schema()["required"]
    )
    assert (
        create_job.inputSchema["$defs"]["Manifest"]["properties"]["workflow"]
        == (Manifest.model_json_schema()["properties"]["workflow"])
    )


async def test_build_mcp_publishes_output_schema_for_every_tool(data_root: Path) -> None:
    tools = await _tools_by_name(data_root)

    assert list(tools) == TOOL_NAMES
    assert all(tool.outputSchema is not None for tool in tools.values())
    assert tools["list_assets"].outputSchema == {
        "additionalProperties": False,
        "properties": {
            "ok": {"const": True, "default": True, "title": "Ok", "type": "boolean"},
            "asset_ids": {"items": {"type": "string"}, "title": "Asset Ids", "type": "array"},
        },
        "required": ["asset_ids"],
        "title": "AssetIdsOutput",
        "type": "object",
    }
    assert tools["create_job"].outputSchema["title"] == "JobOutput"
    assert tools["plan_sources"].outputSchema["title"] == "SourcePlanOutput"
    assert tools["validate_asset"].outputSchema["title"] == "ValidationOutput"


async def test_plan_sources_returns_structured_redacted_mcp_error_for_missing_ref_pack(
    data_root: Path,
    tmp_path: Path,
) -> None:
    app = _app(data_root)
    job = app.create_job(
        Manifest.model_validate(_manifest_payload(character_ref_pack="missing-pack"))
    )
    result = cast(
        CallToolResult,
        await build_mcp(app).call_tool(
            "plan_sources",
            {"job_id": job.id, "out_dir": str(tmp_path / "source-plan")},
        ),
    )
    payload = _structured_content(result)

    assert result.isError is True
    assert payload == {
        "ok": False,
        "diagnostics": [
            {
                "code": "UNKNOWN_REFERENCE_PACK",
                "data": None,
                "message": "reference pack not found",
                "severity": "error",
                "where": "missing-pack",
            }
        ],
        "source_plan": None,
    }
    assert "Traceback" not in _serialized_result(result)
    assert str(data_root) not in _serialized_result(result)
    assert str(tmp_path) not in _serialized_result(result)


async def test_build_asset_returns_structured_redacted_mcp_error(
    data_root: Path, tmp_path: Path
) -> None:
    app = _app(data_root)
    job = app.create_job(Manifest.model_validate(_manifest_payload()))

    def fail_build(job_id: str) -> object:
        assert job_id == job.id
        raise ValueError(f"build exploded at {tmp_path}\\nested\\artifact.png")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(app, "build", fail_build)
    try:
        result = cast(
            CallToolResult,
            await build_mcp(app).call_tool("build_asset", {"job_id": job.id}),
        )
    finally:
        monkeypatch.undo()

    payload = _structured_content(result)
    assert result.isError is True
    assert payload == {
        "ok": False,
        "diagnostics": [
            {
                "code": "BUILD_ASSET_FAILED",
                "data": {"detail": "build exploded at artifact.png"},
                "message": "could not build asset",
                "severity": "error",
                "where": job.id,
            }
        ],
        "job_result": None,
    }
    assert str(tmp_path) not in _serialized_result(result)


async def test_validate_asset_unknown_spec_returns_structured_mcp_error(
    data_root: Path,
    tmp_path: Path,
) -> None:
    result = cast(
        CallToolResult,
        await build_mcp(_app(data_root)).call_tool(
            "validate_asset",
            {"spec_id": "missing-spec", "path": str(tmp_path)},
        ),
    )

    assert result.isError is True
    assert _structured_content(result) == {
        "ok": False,
        "diagnostics": [
            {
                "code": "UNKNOWN_SPEC",
                "data": None,
                "message": "unknown target spec",
                "severity": "error",
                "where": "missing-spec",
            }
        ],
    }
