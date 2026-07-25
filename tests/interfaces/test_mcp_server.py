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
from fecreator.references.store import ReferencePackCorruptionError


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


def _assert_success_only_schema(
    schema: dict[str, object], *, title: str, payload_field: str
) -> None:
    properties = cast(dict[str, object], schema["properties"])
    ok_schema = cast(dict[str, object], properties["ok"])

    assert schema["title"] == title
    assert schema["type"] == "object"
    assert schema["required"] == ["ok", payload_field]
    assert schema["additionalProperties"] is False
    assert ok_schema["const"] is True
    assert payload_field in properties
    assert "diagnostics" not in properties


def _assert_union_schema(
    schema: dict[str, object], *, title: str, success_name: str, payload_field: str
) -> None:
    defs = cast(dict[str, object], schema["$defs"])
    success_schema = cast(dict[str, object], defs[success_name])
    success_properties = cast(dict[str, object], success_schema["properties"])
    error_schema = cast(dict[str, object], defs["ToolErrorOutput"])
    error_properties = cast(dict[str, object], error_schema["properties"])

    assert schema["title"] == title
    assert schema["anyOf"] == [
        {"$ref": f"#/$defs/{success_name}"},
        {"$ref": "#/$defs/ToolErrorOutput"},
    ]
    assert success_schema["additionalProperties"] is False
    assert success_schema["required"] == ["ok", payload_field]
    assert cast(dict[str, object], success_properties["ok"])["const"] is True
    assert payload_field in success_properties
    assert error_schema["additionalProperties"] is False
    assert error_schema["required"] == ["ok", "diagnostics"]
    assert cast(dict[str, object], error_properties["ok"])["const"] is False
    if payload_field != "diagnostics":
        assert payload_field not in error_properties


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

    assert create_job.inputSchema["properties"]["manifest"] == Manifest.model_json_schema()


async def test_create_job_invalid_manifest_returns_structured_redacted_mcp_error(
    data_root: Path,
    tmp_path: Path,
) -> None:
    bad_path = tmp_path / "secrets" / "manifest.json"
    result = cast(
        CallToolResult,
        await build_mcp(_app(data_root)).call_tool(
            "create_job",
            {
                "manifest": {
                    "provider": "fake",
                    "sources": [{"kind": "text", "ref": "hero"}],
                    "absolute_path": str(bad_path),
                }
            },
        ),
    )

    assert result.isError is True
    assert _structured_content(result) == {
        "ok": False,
        "diagnostics": [
            {
                "code": "INVALID_MANIFEST",
                "data": {"error_count": 4},
                "message": "manifest failed validation",
                "severity": "error",
                "where": "manifest",
            }
        ],
    }
    serialized = _serialized_result(result)
    assert str(bad_path) not in serialized
    assert "absolute_path" not in serialized
    assert "input_value" not in serialized


@pytest.mark.parametrize(
    ("manifest", "forbidden_fragment"),
    [
        pytest.param("C:\\secret\\manifest.json", "C:\\secret\\manifest.json", id="string-path"),
        pytest.param(["C:\\secret\\manifest.json"], "C:\\secret\\manifest.json", id="list-value"),
    ],
)
async def test_create_job_non_object_manifest_returns_structured_redacted_mcp_error(
    data_root: Path,
    manifest: object,
    forbidden_fragment: str,
) -> None:
    result = cast(
        CallToolResult,
        await build_mcp(_app(data_root)).call_tool("create_job", {"manifest": manifest}),
    )

    assert result.isError is True
    assert _structured_content(result) == {
        "ok": False,
        "diagnostics": [
            {
                "code": "INVALID_MANIFEST",
                "data": {"error_count": 1},
                "message": "manifest failed validation",
                "severity": "error",
                "where": "manifest",
            }
        ],
    }
    serialized = _serialized_result(result)
    assert forbidden_fragment not in serialized
    assert "input_value" not in serialized


async def test_build_mcp_publishes_output_schema_for_every_tool(data_root: Path) -> None:
    tools = await _tools_by_name(data_root)

    assert list(tools) == TOOL_NAMES
    assert all(tool.outputSchema is not None for tool in tools.values())
    _assert_success_only_schema(
        cast(dict[str, object], tools["list_assets"].outputSchema),
        title="AssetIdsOutput",
        payload_field="asset_ids",
    )
    _assert_success_only_schema(
        cast(dict[str, object], tools["list_specs"].outputSchema),
        title="SpecIdsOutput",
        payload_field="spec_ids",
    )
    _assert_success_only_schema(
        cast(dict[str, object], tools["list_providers"].outputSchema),
        title="ProviderIdsOutput",
        payload_field="provider_ids",
    )
    assert tools["create_job"].outputSchema == tools["get_job"].outputSchema
    assert tools["create_job"].outputSchema == tools["submit_sources"].outputSchema
    assert tools["create_job"].outputSchema == tools["cancel_job"].outputSchema
    _assert_union_schema(
        cast(dict[str, object], tools["create_job"].outputSchema),
        title="JobOutput",
        success_name="JobSuccessOutput",
        payload_field="job",
    )
    _assert_union_schema(
        cast(dict[str, object], tools["plan_sources"].outputSchema),
        title="SourcePlanOutput",
        success_name="SourcePlanSuccessOutput",
        payload_field="source_plan",
    )
    _assert_union_schema(
        cast(dict[str, object], tools["build_asset"].outputSchema),
        title="JobResultOutput",
        success_name="JobResultSuccessOutput",
        payload_field="job_result",
    )
    assert tools["approve_stage"].outputSchema == tools["reject_stage"].outputSchema
    _assert_union_schema(
        cast(dict[str, object], tools["approve_stage"].outputSchema),
        title="ApprovalOutput",
        success_name="ApprovalSuccessOutput",
        payload_field="approval",
    )
    _assert_union_schema(
        cast(dict[str, object], tools["validate_asset"].outputSchema),
        title="ValidationOutput",
        success_name="ValidationSuccessOutput",
        payload_field="diagnostics",
    )


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
    }
    assert str(tmp_path) not in _serialized_result(result)


async def test_build_asset_returns_structured_redacted_mcp_error_for_mixed_posix_windows_path(
    data_root: Path,
) -> None:
    app = _app(data_root)
    job = app.create_job(Manifest.model_validate(_manifest_payload()))
    linux_tmp_path = "/tmp/pytest-123"

    def fail_build(job_id: str) -> object:
        assert job_id == job.id
        raise ValueError(f"build exploded at {linux_tmp_path}\\nested\\artifact.png")

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
    }
    serialized = _serialized_result(result)
    assert linux_tmp_path not in serialized
    assert "nested" not in serialized


async def test_build_asset_corrupt_reference_pack_returns_structured_mcp_error(
    data_root: Path,
) -> None:
    app = _app(data_root)
    job = app.create_job(
        Manifest.model_validate(_manifest_payload(character_ref_pack="corrupt-pack"))
    )

    def fail_build(job_id: str) -> object:
        assert job_id == job.id
        raise ReferencePackCorruptionError("corrupt")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(app, "build", fail_build)
    try:
        result = cast(
            CallToolResult,
            await build_mcp(app).call_tool("build_asset", {"job_id": job.id}),
        )
    finally:
        monkeypatch.undo()

    assert result.isError is True
    assert _structured_content(result) == {
        "ok": False,
        "diagnostics": [
            {
                "code": "CORRUPT_REFERENCE_PACK",
                "data": None,
                "message": "reference pack is corrupt",
                "severity": "error",
                "where": "corrupt-pack",
            }
        ],
    }


async def test_repeated_build_asset_returns_structured_redacted_transition_error(
    data_root: Path,
) -> None:
    app = _app(data_root)
    server = build_mcp(app)
    job = app.create_job(Manifest.model_validate(_manifest_payload()))

    first_result = cast(
        CallToolResult,
        await server.call_tool("build_asset", {"job_id": job.id}),
    )
    second_result = cast(
        CallToolResult,
        await server.call_tool("build_asset", {"job_id": job.id}),
    )

    assert first_result.isError is False
    assert second_result.isError is True
    assert _structured_content(second_result) == {
        "ok": False,
        "diagnostics": [
            {
                "code": "BUILD_ASSET_FAILED",
                "data": {"detail": "completed -> processing is not allowed"},
                "message": "could not build asset",
                "severity": "error",
                "where": job.id,
            }
        ],
    }
    assert "Traceback" not in _serialized_result(second_result)


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
