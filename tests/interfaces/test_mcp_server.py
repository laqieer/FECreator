from fecreator.app import FeCreatorApp
from fecreator.core.config import Settings
from fecreator.interfaces.mcp_server import TOOL_NAMES, build_mcp, make_handlers


def _app(tmp_path):  # type: ignore[no-untyped-def]
    return FeCreatorApp(Settings(data_root=tmp_path))


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


def test_get_job_handler_returns_error_for_missing(tmp_path):  # type: ignore[no-untyped-def]
    """Handlers must return structured error dicts, not raise exceptions."""
    handlers = make_handlers(_app(tmp_path))
    result = handlers["get_job"]("nonexistent-job")
    assert isinstance(result, dict)
    assert result.get("error") == "NOT_FOUND"


def test_build_asset_blocked_after_cancel(tmp_path):  # type: ignore[no-untyped-def]
    """build_asset cannot bypass gate on cancelled job — returns INVALID_STATE error."""

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
    handlers = make_handlers(app)
    result = handlers["build_asset"](job.id)
    assert isinstance(result, dict)
    assert result.get("error") == "INVALID_STATE"
