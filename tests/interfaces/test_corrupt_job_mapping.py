"""A corrupt persisted job must be reported as corruption on every surface.

A job written before the final v1 contract (a derived workflow with no
``parent_asset_id``) can no longer be loaded. Reporting that as ``UNKNOWN_JOB``
tells an operator to look for a job that is plainly on disk, and reporting it
without naming the job leaves a whole store un-diagnosable. Every adapter action
that loads a job therefore maps it to ``CORRUPT_JOB``, identifies the offending
job id, and never discloses the absolute data root.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from fecreator.app import FeCreatorApp
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.core.config import Settings
from fecreator.interfaces.cli_json import run
from fecreator.interfaces.http_api import create_api
from fecreator.interfaces.mcp_server import make_handlers

CORRUPT_JOB_CODE = "CORRUPT_JOB"


def _app(data_root: Path) -> FeCreatorApp:
    return FeCreatorApp(Settings(data_root=data_root))


def _manifest() -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="fake",
        sources=(SourceSpec(kind="text", ref="hero"),),
    )


def _legacy_derived_job(data_root: Path) -> str:
    """Persist a job whose manifest predates the required ``parent_asset_id``."""
    job = _app(data_root).create_job(_manifest())
    manifest_path = data_root / "jobs" / job.id / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["workflow"] = "expression_refine"
    payload.pop("parent_asset_id", None)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    return job.id


def _assert_no_absolute_root(payload: str, data_root: Path) -> None:
    root = str(data_root)
    assert root not in payload
    assert root.replace("\\", "/") not in payload
    assert root.replace("\\", "\\\\") not in payload


_HTTP_ACTIONS = (
    ("get", "", None),
    ("get", "/candidate", None),
    ("get", "/approvals", None),
    ("post", "/plan-sources", None),
    ("post", "/validate", None),
    ("post", "/build", None),
    ("get", "/report", None),
    ("get", "/bundle", None),
    ("get", "/artifacts/package/portrait.png", None),
    ("get", "/bundle/manifest.json", None),
    ("post", "/approve", {"actor": "reviewer"}),
    ("post", "/reject", {"actor": "reviewer", "reason": "no"}),
    ("post", "/finalize", None),
    ("post", "/retry", {"actor": "reviewer"}),
    ("post", "/cancel", None),
)


@pytest.mark.parametrize(("method", "suffix", "body"), _HTTP_ACTIONS)
def test_http_actions_report_a_corrupt_job_as_a_conflict(
    data_root: Path, method: str, suffix: str, body: dict[str, str] | None
) -> None:
    job_id = _legacy_derived_job(data_root)
    client = TestClient(create_api(_app(data_root)))
    url = f"/api/jobs/{job_id}{suffix}"

    response = client.post(url, json=body) if method == "post" else client.get(url)

    assert response.status_code == 409
    assert [diagnostic["code"] for diagnostic in response.json()] == [CORRUPT_JOB_CODE]
    assert [diagnostic["where"] for diagnostic in response.json()] == [job_id]
    _assert_no_absolute_root(response.text, data_root)


_CLI_ACTIONS = (
    ("status",),
    ("candidate",),
    ("approvals",),
    ("plan-sources",),
    ("validate",),
    ("report",),
    ("bundle",),
    ("finalize",),
    ("cancel",),
)


@pytest.mark.parametrize("command", _CLI_ACTIONS)
def test_cli_actions_report_a_corrupt_job_as_a_failure(
    data_root: Path, command: tuple[str, ...]
) -> None:
    job_id = _legacy_derived_job(data_root)
    out = io.StringIO()

    rc = run(_app(data_root), ["job", *command, job_id], out)

    payload = out.getvalue()
    assert rc == 2
    diagnostics = cast(list[dict[str, object]], json.loads(payload))
    assert [diagnostic["code"] for diagnostic in diagnostics] == [CORRUPT_JOB_CODE]
    assert [diagnostic["where"] for diagnostic in diagnostics] == [job_id]
    _assert_no_absolute_root(payload, data_root)


def test_cli_build_reports_a_corrupt_job_as_a_failure(data_root: Path) -> None:
    job_id = _legacy_derived_job(data_root)
    out = io.StringIO()

    rc = run(_app(data_root), ["build", "--job", job_id], out)

    payload = out.getvalue()
    assert rc == 2
    diagnostics = cast(list[dict[str, object]], json.loads(payload))
    assert [diagnostic["code"] for diagnostic in diagnostics] == [CORRUPT_JOB_CODE]
    assert [diagnostic["where"] for diagnostic in diagnostics] == [job_id]
    _assert_no_absolute_root(payload, data_root)


_MCP_ACTIONS = (
    "get_job",
    "get_job_candidate",
    "list_approval_decisions",
    "plan_job_sources",
    "validate_job",
    "get_job_report",
    "list_bundle_entries",
    "build_asset",
    "finalize_job",
    "cancel_job",
)


@pytest.mark.parametrize("tool", _MCP_ACTIONS)
def test_mcp_actions_report_a_corrupt_job_as_a_tool_error(data_root: Path, tool: str) -> None:
    job_id = _legacy_derived_job(data_root)
    handlers = make_handlers(_app(data_root))

    result = handlers[tool](job_id=job_id)

    structured = cast(dict[str, object], result.structuredContent)
    diagnostics = cast(list[dict[str, object]], structured["diagnostics"])
    assert result.isError is True
    assert structured["ok"] is False
    assert [diagnostic["code"] for diagnostic in diagnostics] == [CORRUPT_JOB_CODE]
    assert [diagnostic["where"] for diagnostic in diagnostics] == [job_id]
    _assert_no_absolute_root(json.dumps(result.model_dump(mode="json")), data_root)


def test_http_listing_identifies_the_offending_job(data_root: Path) -> None:
    job_id = _legacy_derived_job(data_root)
    client = TestClient(create_api(_app(data_root)))

    response = client.get("/api/jobs")

    assert response.status_code == 409
    assert [diagnostic["code"] for diagnostic in response.json()] == [CORRUPT_JOB_CODE]
    assert [diagnostic["where"] for diagnostic in response.json()] == [job_id]
    _assert_no_absolute_root(response.text, data_root)


def test_cli_listing_identifies_the_offending_job(data_root: Path) -> None:
    job_id = _legacy_derived_job(data_root)
    out = io.StringIO()

    rc = run(_app(data_root), ["job", "list"], out)

    payload = out.getvalue()
    assert rc == 2
    diagnostics = cast(list[dict[str, object]], json.loads(payload))
    assert [diagnostic["code"] for diagnostic in diagnostics] == [CORRUPT_JOB_CODE]
    assert [diagnostic["where"] for diagnostic in diagnostics] == [job_id]
    _assert_no_absolute_root(payload, data_root)


def test_mcp_listing_identifies_the_offending_job(data_root: Path) -> None:
    job_id = _legacy_derived_job(data_root)
    handlers = make_handlers(_app(data_root))

    result = handlers["list_jobs"]()

    structured = cast(dict[str, object], result.structuredContent)
    diagnostics = cast(list[dict[str, object]], structured["diagnostics"])
    assert result.isError is True
    assert [diagnostic["code"] for diagnostic in diagnostics] == [CORRUPT_JOB_CODE]
    assert [diagnostic["where"] for diagnostic in diagnostics] == [job_id]
    _assert_no_absolute_root(json.dumps(result.model_dump(mode="json")), data_root)


def test_websocket_closes_with_a_distinct_code_for_a_corrupt_job(data_root: Path) -> None:
    job_id = _legacy_derived_job(data_root)
    client = TestClient(create_api(_app(data_root)))

    with (
        client.websocket_connect(f"/ws/jobs/{job_id}") as ws,
        pytest.raises(WebSocketDisconnect) as exc_info,
    ):
        ws.receive_json()

    assert exc_info.value.code == 1011


def test_a_missing_job_is_still_reported_as_unknown(data_root: Path) -> None:
    """Corruption mapping must not swallow the genuinely-absent case."""
    _legacy_derived_job(data_root)
    client = TestClient(create_api(_app(data_root)))
    out = io.StringIO()

    response = client.get("/api/jobs/never-created")
    rc = run(_app(data_root), ["job", "status", "never-created"], out)

    assert response.status_code == 404
    assert [diagnostic["code"] for diagnostic in response.json()] == ["UNKNOWN_JOB"]
    assert rc == 2
    diagnostics = cast(list[dict[str, object]], json.loads(out.getvalue()))
    assert [diagnostic["code"] for diagnostic in diagnostics] == ["UNKNOWN_JOB"]
