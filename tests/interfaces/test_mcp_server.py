from __future__ import annotations

import json
from pathlib import Path

from fecreator.app import FeCreatorApp
from fecreator.core.config import Settings
from fecreator.interfaces.mcp_server import TOOL_NAMES, build_mcp, make_handlers


def _app(data_root: Path) -> FeCreatorApp:
    return FeCreatorApp(Settings(data_root=data_root))


def _manifest_payload(*, provider: str = "fake") -> dict[str, object]:
    return {
        "asset_type": "portrait",
        "target_spec": "fe-gba-portrait-standard",
        "workflow": "text_to_portrait",
        "provider": provider,
        "sources": [{"kind": "text", "ref": "hero"}],
    }


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

    assert make_handlers(app)["list_specs"]() == app.list_specs()


def test_create_job_handler_returns_json_payload(data_root: Path) -> None:
    payload = make_handlers(_app(data_root))["create_job"](_manifest_payload())

    assert payload["manifest"]["provider"] == "fake"
    assert payload["state"] == "created"


def test_handlers_return_structured_diagnostic_for_invalid_manifest(data_root: Path) -> None:
    payload = make_handlers(_app(data_root))["create_job"]({"asset_type": "portrait"})

    assert payload == {
        "ok": False,
        "diagnostics": [
            {
                "code": "INVALID_MANIFEST",
                "data": {"error_count": 3},
                "message": "manifest failed validation",
                "severity": "error",
                "where": "manifest",
            }
        ],
    }


def test_handlers_redact_expected_errors_without_tracebacks(
    data_root: Path,
    tmp_path: Path,
) -> None:
    bad_job_id = str(tmp_path / "missing-job")
    payload = make_handlers(_app(data_root))["get_job"](bad_job_id)

    assert payload["ok"] is False
    assert payload["diagnostics"][0] == {
        "code": "UNKNOWN_JOB",
        "data": None,
        "message": "job not found",
        "severity": "error",
        "where": "missing-job",
    }
    assert "Traceback" not in json.dumps(payload)
    assert str(tmp_path) not in json.dumps(payload)


def test_build_mcp_registers_all_tools(data_root: Path) -> None:
    server = build_mcp(_app(data_root))

    assert [tool.name for tool in server._tool_manager.list_tools()] == TOOL_NAMES
