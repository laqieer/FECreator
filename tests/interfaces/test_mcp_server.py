import pytest

from fecreator.app import FeCreatorApp
from fecreator.core.config import Settings
from fecreator.interfaces.mcp_server import TOOL_NAMES, build_mcp, make_handlers


def _app(tmp_path):  # type: ignore[no-untyped-def]
    return FeCreatorApp(Settings(data_root=tmp_path))


# ── Basic contract tests ───────────────────────────────────────────────────


def test_tool_names_match_design() -> None:
    assert set(TOOL_NAMES) == {
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
    }


def test_handlers_cover_all_tools(tmp_path):  # type: ignore[no-untyped-def]
    handlers = make_handlers(_app(tmp_path))
    assert set(handlers) == set(TOOL_NAMES)


def test_list_specs_handler_matches_app(tmp_path):  # type: ignore[no-untyped-def]
    app = _app(tmp_path)
    assert make_handlers(app)["list_specs"]() == app.list_specs()


def test_build_mcp_returns_server(tmp_path):  # type: ignore[no-untyped-def]
    server = build_mcp(_app(tmp_path))
    assert server is not None


# ── FastMCP protocol tests (async) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_all_tools_have_named_schemas(tmp_path):  # type: ignore[no-untyped-def]
    """Every tool schema must have named properties, not *args/**kwargs."""
    server = build_mcp(_app(tmp_path))
    tools = await server.list_tools()
    assert len(tools) == 14
    tool_map = {t.name: t for t in tools}
    assert set(tool_map.keys()) == set(TOOL_NAMES)

    # Tools with required parameters must expose named properties
    multi_param_tools = {
        "create_job",
        "get_job",
        "plan_sources",
        "generate_asset",
        "build_asset",
        "inspect_asset",
        "cancel_job",
        "approve_stage",
        "reject_stage",
        "validate_asset",
    }
    for name in multi_param_tools:
        schema = tool_map[name].inputSchema
        props = schema.get("properties", {})
        assert props, f"tool {name!r} has no named properties in schema"
        # Ensure no *args or **kwargs leaked
        assert "args" not in props, f"tool {name!r} has leaked *args in schema"
        assert "kwargs" not in props, f"tool {name!r} has leaked **kwargs in schema"


@pytest.mark.asyncio
async def test_zero_arg_call_tool(tmp_path):  # type: ignore[no-untyped-def]
    """list_specs (0-arg) works via the FastMCP call_tool protocol path."""
    server = build_mcp(_app(tmp_path))
    _, extra = await server.call_tool("list_specs", {})
    specs = extra["result"]
    assert "fe-gba-portrait-standard" in specs


@pytest.mark.asyncio
async def test_one_arg_call_tool_missing_job_raises_tool_error(tmp_path):  # type: ignore[no-untyped-def]
    """get_job (1-arg) raises ToolError for missing job via protocol path."""
    from mcp.server.fastmcp.exceptions import ToolError

    server = build_mcp(_app(tmp_path))
    with pytest.raises(ToolError):
        await server.call_tool("get_job", {"job_id": "nonexistent"})


@pytest.mark.asyncio
async def test_multi_arg_call_tool(tmp_path):  # type: ignore[no-untyped-def]
    """approve_stage (3-arg) raises ToolError when job not in review state."""
    from mcp.server.fastmcp.exceptions import ToolError

    from fecreator.contracts.manifest import Manifest, SourceSpec

    app = _app(tmp_path)
    job = app.create_job(
        Manifest(
            asset_type="portrait",
            target_spec="fe-gba-portrait-standard",
            workflow="text_to_portrait",
            provider="fake",
            sources=(SourceSpec(kind="text", ref="hero"),),
        )
    )
    server = build_mcp(app)
    with pytest.raises(ToolError):
        await server.call_tool(
            "approve_stage",
            {"job_id": job.id, "stage": "build", "actor": "reviewer"},
        )


@pytest.mark.asyncio
async def test_tool_error_redacts_message(tmp_path):  # type: ignore[no-untyped-def]
    """ToolError messages must not contain raw absolute paths."""
    from mcp.server.fastmcp.exceptions import ToolError

    server = build_mcp(_app(tmp_path))
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("get_job", {"job_id": "missing"})
    msg = str(exc_info.value)
    # Must NOT contain a Windows-style absolute path (single or double backslash)
    import re

    assert not re.search(r"[A-Za-z]:[/\\]", msg), f"absolute path leaked in ToolError: {msg!r}"
    # Message should indicate not found
    assert "not found" in msg.lower() or "error" in msg.lower()


@pytest.mark.asyncio
async def test_build_asset_blocked_after_cancel(tmp_path):  # type: ignore[no-untyped-def]
    """build_asset cannot bypass gate on cancelled job — raises ToolError."""
    from mcp.server.fastmcp.exceptions import ToolError

    from fecreator.contracts.manifest import Manifest, SourceSpec

    app = _app(tmp_path)
    job = app.create_job(
        Manifest(
            asset_type="portrait",
            target_spec="fe-gba-portrait-standard",
            workflow="text_to_portrait",
            provider="fake",
            sources=(SourceSpec(kind="text", ref="hero"),),
        )
    )
    app.cancel(job.id)
    server = build_mcp(app)
    with pytest.raises(ToolError):
        await server.call_tool("build_asset", {"job_id": job.id})
