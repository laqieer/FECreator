from __future__ import annotations

import io
import json
from pathlib import Path
from typing import cast

import httpx
from mcp.types import CallToolResult
from PIL import Image

from fecreator.app import FeCreatorApp
from fecreator.contracts.diagnostics import has_errors
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.core.config import Settings
from fecreator.interfaces import cli_json
from fecreator.interfaces import static as static_module
from fecreator.interfaces.http_api import create_api
from fecreator.interfaces.mcp_server import make_handlers
from fecreator.jobs.model import JobState


def _app(data_root: Path) -> FeCreatorApp:
    return FeCreatorApp(Settings(data_root=data_root))


def _manual_manifest() -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="manual",
        sources=(SourceSpec(kind="text", ref="hero"),),
    )


def _write_png(path: Path, color: tuple[int, int, int] = (0, 0, 0)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (96, 80), color).save(path, format="PNG")


def test_cli_build_fails_closed_before_manual_source_handoff(
    data_root: Path,
) -> None:
    app = _app(data_root)
    job = app.create_job(_manual_manifest())
    out = io.StringIO()

    rc = cli_json.run(app, ["build", "--job", job.id], out)
    payload = json.loads(out.getvalue())
    workspace = data_root / "jobs" / job.id

    assert rc == 2
    assert payload["job_id"] == job.id
    assert payload["ok"] is False
    assert app.get_job(job.id).state is JobState.FAILED
    assert not (workspace / "report.json").exists()
    assert not (workspace / "lineage.json").exists()
    assert not (workspace / "bundle").exists()


def test_mcp_build_only_publishes_lineage_after_manual_sources_are_submitted(
    data_root: Path,
    tmp_path: Path,
) -> None:
    app = _app(data_root)
    job = app.create_job(_manual_manifest())
    workspace = data_root / "jobs" / job.id
    cli_json.run(
        app,
        ["plan-sources", "--job", job.id, "--out", str(tmp_path / "plan")],
        io.StringIO(),
    )
    incoming = tmp_path / "incoming"
    _write_png(incoming / "neutral.png", color=(30, 60, 90))
    cli_json.run(
        app,
        ["submit-sources", "--job", job.id, "--sources", str(incoming)],
        io.StringIO(),
    )

    assert not (workspace / "report.json").exists()
    assert not (workspace / "lineage.json").exists()
    assert not (workspace / "bundle").exists()

    result = cast(CallToolResult, make_handlers(app)["build_asset"](job.id))
    payload = cast(dict[str, object], result.structuredContent)
    package_dir = workspace / "candidate" / "package"

    assert result.isError is False
    assert payload["ok"] is True
    assert cast(dict[str, object], payload["job_result"])["ok"] is True
    assert cast(dict[str, object], payload["job_result"])["lineage_id"] == f"{job.id}-candidate"
    assert app.get_job(job.id).state is JobState.WAITING_FOR_REVIEW
    assert not has_errors(app.validate("fe-gba-portrait-standard", package_dir))
    assert (workspace / "candidate" / "candidate.json").exists()
    assert not (workspace / "report.json").exists()
    assert not (workspace / "lineage.json").exists()
    assert not (workspace / "bundle").exists()


async def test_additive_interfaces_delegate_reference_listing_to_the_app_facade(
    data_root: Path,
    monkeypatch,
) -> None:
    app = _app(data_root)
    monkeypatch.setattr(app, "list_reference_packs", lambda: ["facade-only"])

    assert "list_reference_packs" in make_handlers(app)
    cli_out = io.StringIO()
    cli_rc = cli_json.run(app, ["references", "list"], cli_out)
    mcp_result = cast(CallToolResult, make_handlers(app)["list_reference_packs"]())
    monkeypatch.setattr(static_module, "web_dir", lambda: None)
    transport = httpx.ASGITransport(app=create_api(app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        http_response = await client.get("/api/references")

    assert cli_rc == 0
    assert json.loads(cli_out.getvalue()) == ["facade-only"]
    assert mcp_result.isError is False
    assert cast(dict[str, object], mcp_result.structuredContent) == {
        "ok": True,
        "reference_pack_ids": ["facade-only"],
    }
    assert http_response.status_code == 200
    assert http_response.json() == ["facade-only"]
