from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import cast

import httpx
import pytest
from mcp.types import CallToolResult
from PIL import Image

from fecreator.app import FeCreatorApp
from fecreator.contracts.diagnostics import Diagnostic
from fecreator.contracts.manifest import AssetMetadata, Manifest, SourceIdentity, SourceSpec
from fecreator.core.config import Settings
from fecreator.interfaces import cli_json
from fecreator.interfaces import static as static_module
from fecreator.interfaces.http_api import create_api
from fecreator.interfaces.mcp_server import make_handlers
from fecreator.jobs.model import JobState
from fecreator.reporting.sanitize import as_object, sanitize_json
from tests.fixtures.dialogue_background import assert_delivered_truecolor_background_png


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


def _mcp_payload(result: CallToolResult) -> dict[str, object]:
    return cast(dict[str, object], result.structuredContent)


def _mcp_diagnostics(result: CallToolResult) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], _mcp_payload(result)["diagnostics"])


def _write_png(path: Path, color: tuple[int, int, int] = (0, 0, 0)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (96, 80), color).save(path, format="PNG")


def _assert_matching_files(*roots: Path) -> None:
    expected_files = sorted(
        path.relative_to(roots[0]) for path in roots[0].rglob("*") if path.is_file()
    )

    assert roots
    assert expected_files
    for root in roots[1:]:
        assert sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file()) == (
            expected_files
        )
    for relative_path in expected_files:
        expected_bytes = (roots[0] / relative_path).read_bytes()
        for root in roots[1:]:
            assert (root / relative_path).read_bytes() == expected_bytes


def _diagnostics_payload(diagnostics: list[Diagnostic]) -> list[dict[str, object]]:
    return [
        cast(
            dict[str, object],
            as_object(sanitize_json(diagnostic.model_dump(mode="json"), error_cls=ValueError)),
        )
        for diagnostic in diagnostics
    ]


def _client(app: FeCreatorApp, monkeypatch: pytest.MonkeyPatch) -> httpx.AsyncClient:
    monkeypatch.setattr(static_module, "web_dir", lambda: None)
    transport = httpx.ASGITransport(app=create_api(app))
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def test_cli_mcp_http_and_app_agree_on_list_specs(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(data_root)
    out = io.StringIO()

    rc = cli_json.run(app, ["list-specs"], out)
    cli_specs = json.loads(out.getvalue())
    mcp_result = cast(CallToolResult, make_handlers(app)["list_specs"]())

    async with _client(app, monkeypatch) as client:
        http_response = await client.get("/api/specs")

    assert rc == 0
    assert http_response.status_code == 200
    assert cli_specs == app.list_specs() == http_response.json()
    assert mcp_result.isError is False
    assert _mcp_payload(mcp_result) == {"ok": True, "spec_ids": cli_specs}


async def test_cli_mcp_http_and_app_agree_on_job_snapshot(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(data_root)
    job = app.create_job(_manifest())
    expected = cast(dict[str, object], job.model_dump(mode="json"))
    out = io.StringIO()

    rc = cli_json.run(app, ["job", "status", job.id], out)
    mcp_result = cast(CallToolResult, make_handlers(app)["get_job"](job.id))

    async with _client(app, monkeypatch) as client:
        http_response = await client.get(f"/api/jobs/{job.id}")

    assert rc == 0
    assert http_response.status_code == 200
    assert json.loads(out.getvalue()) == expected == http_response.json()
    assert mcp_result.isError is False
    assert _mcp_payload(mcp_result) == {"ok": True, "job": expected}


async def test_cli_mcp_http_and_app_agree_on_validation_diagnostics(
    data_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(data_root)
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    expected = _diagnostics_payload(app.validate("fe-gba-portrait-standard", package_dir))
    out = io.StringIO()

    rc = cli_json.run(
        app,
        ["validate", "--spec", "fe-gba-portrait-standard", "--path", str(package_dir)],
        out,
    )
    mcp_result = cast(
        CallToolResult,
        make_handlers(app)["validate_asset"]("fe-gba-portrait-standard", str(package_dir)),
    )

    async with _client(app, monkeypatch) as client:
        http_response = await client.post(
            "/api/validate",
            json={"spec_id": "fe-gba-portrait-standard", "package_dir": str(package_dir)},
        )

    assert rc == 2
    assert http_response.status_code == 200
    assert json.loads(out.getvalue()) == expected == http_response.json()
    assert mcp_result.isError is False
    assert _mcp_payload(mcp_result) == {"ok": True, "diagnostics": expected}


def _manual_manifest() -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="manual",
        sources=(SourceSpec(kind="text", ref="hero"),),
    )


def _manual_dialogue_background_manifest() -> Manifest:
    return Manifest(
        asset_type="dialogue_background",
        target_spec="fe8-dialogue-background-source-240x160",
        workflow="text_to_dialogue_background",
        provider="manual",
        metadata=AssetMetadata(
            name="phantom_city",
            purpose="Original phantom city",
            source=SourceIdentity(kind="prompt", id="bg/phantom-city", revision="1"),
            license_note="Original repository fixture.",
            source_note="Generated from an original prompt.",
        ),
        sources=(SourceSpec(kind="text", ref="phantom city"),),
        params={"width": 240, "height": 160},
    )


async def test_cli_mcp_and_http_preserve_truecolor_dialogue_background_candidates(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    truecolor_background_sources: Path,
) -> None:
    source = truecolor_background_sources / "phantom_city.png"
    assert_delivered_truecolor_background_png(source.read_bytes())

    cli_app = _app(data_root / "cli")
    mcp_app = _app(data_root / "mcp")
    http_app = _app(data_root / "http")
    cli_job = cli_app.create_job(_manual_dialogue_background_manifest())
    mcp_job = mcp_app.create_job(_manual_dialogue_background_manifest())
    cli_plan = cli_json.run(
        cli_app,
        ["plan-sources", "--job", cli_job.id, "--out", str(tmp_path / "cli-plan")],
        io.StringIO(),
    )
    cli_submit = cli_json.run(
        cli_app,
        ["submit-sources", "--job", cli_job.id, "--sources", str(truecolor_background_sources)],
        io.StringIO(),
    )
    cli_build = cli_json.run(cli_app, ["build", "--job", cli_job.id], io.StringIO())
    mcp_plan = cast(
        CallToolResult,
        make_handlers(mcp_app)["plan_sources"](mcp_job.id, str(tmp_path / "mcp-plan")),
    )
    mcp_submit = cast(
        CallToolResult,
        make_handlers(mcp_app)["submit_sources"](mcp_job.id, str(truecolor_background_sources)),
    )
    mcp_build = cast(CallToolResult, make_handlers(mcp_app)["build_asset"](mcp_job.id))

    async with _client(http_app, monkeypatch) as client:
        created = await client.post(
            "/api/jobs",
            json=_manual_dialogue_background_manifest().model_dump(mode="json"),
        )
        http_job_id = created.json()["id"]
        http_plan = await client.post(f"/api/jobs/{http_job_id}/plan-sources")
        http_submit = await client.post(
            f"/api/jobs/{http_job_id}/sources",
            files=[("files", ("phantom_city.png", source.read_bytes(), "image/png"))],
        )
        http_build = await client.post(f"/api/jobs/{http_job_id}/build")

    assert cli_plan == cli_submit == cli_build == 0
    assert mcp_plan.isError is False
    assert mcp_submit.isError is False
    assert mcp_build.isError is False
    assert created.status_code == 201
    assert http_plan.status_code == http_submit.status_code == 200
    assert http_build.status_code == 200
    assert http_build.json()["ok"] is True
    assert all(
        app.get_job(job_id).state is JobState.WAITING_FOR_REVIEW
        for app, job_id in (
            (cli_app, cli_job.id),
            (mcp_app, mcp_job.id),
            (http_app, http_job_id),
        )
    )
    _assert_matching_files(
        data_root / "cli" / "jobs" / cli_job.id / "candidate" / "package",
        data_root / "mcp" / "jobs" / mcp_job.id / "candidate" / "package",
        data_root / "http" / "jobs" / http_job_id / "candidate" / "package",
    )


def _without_job_identity(payload: dict[str, object]) -> dict[str, object]:
    normalized = dict(payload)
    if "id" in normalized:
        normalized["id"] = "<job>"
    normalized["job_id"] = "<job>"
    if "created_at" in normalized:
        normalized["created_at"] = "<created>"
    if "updated_at" in normalized:
        normalized["updated_at"] = "<updated>"
    if normalized.get("lineage_id") is not None:
        normalized["lineage_id"] = "<job>"
    return normalized


def _without_diagnostic_identity(
    diagnostics: list[dict[str, object]],
) -> list[dict[str, object]]:
    normalized_diagnostics: list[dict[str, object]] = []
    for diagnostic in diagnostics:
        normalized = dict(diagnostic)
        if normalized.get("where") is not None:
            normalized["where"] = "<job>"
        normalized_diagnostics.append(normalized)
    return normalized_diagnostics


def test_cli_and_mcp_plan_sources_match_app_for_manual_jobs(
    data_root: Path,
    tmp_path: Path,
) -> None:
    cli_app = _app(data_root / "cli")
    mcp_app = _app(data_root / "mcp")
    app_direct = _app(data_root / "app")
    cli_job = cli_app.create_job(_manual_manifest())
    mcp_job = mcp_app.create_job(_manual_manifest())
    direct_job = app_direct.create_job(_manual_manifest())
    cli_out = io.StringIO()

    cli_rc = cli_json.run(
        cli_app,
        ["plan-sources", "--job", cli_job.id, "--out", str(tmp_path / "cli-plan")],
        cli_out,
    )
    cli_payload = json.loads(cli_out.getvalue())
    mcp_result = cast(
        CallToolResult,
        make_handlers(mcp_app)["plan_sources"](mcp_job.id, str(tmp_path / "mcp-plan")),
    )
    direct_payload = cast(
        dict[str, object],
        app_direct.plan_sources(direct_job.id, tmp_path / "app-plan").model_dump(mode="json"),
    )

    assert cli_rc == 0
    assert cli_payload == direct_payload
    assert mcp_result.isError is False
    assert _mcp_payload(mcp_result) == {"ok": True, "source_plan": direct_payload}
    _assert_matching_files(tmp_path / "cli-plan", tmp_path / "mcp-plan", tmp_path / "app-plan")


def test_cli_and_mcp_submit_sources_match_app_for_manual_jobs(
    data_root: Path,
    tmp_path: Path,
) -> None:
    cli_app = _app(data_root / "cli")
    mcp_app = _app(data_root / "mcp")
    app_direct = _app(data_root / "app")
    cli_job = cli_app.create_job(_manual_manifest())
    mcp_job = mcp_app.create_job(_manual_manifest())
    direct_job = app_direct.create_job(_manual_manifest())
    cli_json.run(
        cli_app,
        ["plan-sources", "--job", cli_job.id, "--out", str(tmp_path / "cli-plan")],
        io.StringIO(),
    )
    mcp_plan_result = cast(
        CallToolResult,
        make_handlers(mcp_app)["plan_sources"](mcp_job.id, str(tmp_path / "mcp-plan")),
    )
    app_direct.plan_sources(direct_job.id, tmp_path / "app-plan")
    cli_sources = tmp_path / "cli-sources"
    mcp_sources = tmp_path / "mcp-sources"
    app_sources = tmp_path / "app-sources"
    _write_png(cli_sources / "neutral.png", color=(10, 20, 30))
    _write_png(mcp_sources / "neutral.png", color=(10, 20, 30))
    _write_png(app_sources / "neutral.png", color=(10, 20, 30))
    cli_out = io.StringIO()

    cli_rc = cli_json.run(
        cli_app,
        ["submit-sources", "--job", cli_job.id, "--sources", str(cli_sources)],
        cli_out,
    )
    cli_payload = cast(dict[str, object], json.loads(cli_out.getvalue()))
    mcp_result = cast(
        CallToolResult,
        make_handlers(mcp_app)["submit_sources"](mcp_job.id, str(mcp_sources)),
    )
    direct_payload = cast(
        dict[str, object],
        app_direct.submit_sources(direct_job.id, app_sources).model_dump(mode="json"),
    )

    assert cli_rc == 0
    assert mcp_plan_result.isError is False
    assert _without_job_identity(cli_payload) == _without_job_identity(direct_payload)
    assert mcp_result.isError is False
    assert _without_job_identity(cast(dict[str, object], _mcp_payload(mcp_result)["job"])) == (
        _without_job_identity(direct_payload)
    )
    _assert_matching_files(
        data_root / "cli" / "jobs" / cli_job.id / "submitted",
        data_root / "mcp" / "jobs" / mcp_job.id / "submitted",
        data_root / "app" / "jobs" / direct_job.id / "submitted",
    )


def test_cli_and_mcp_build_match_app_for_manual_jobs_after_source_handoff(
    data_root: Path,
    tmp_path: Path,
) -> None:
    cli_app = _app(data_root / "cli")
    mcp_app = _app(data_root / "mcp")
    app_direct = _app(data_root / "app")
    cli_job = cli_app.create_job(_manual_manifest())
    mcp_job = mcp_app.create_job(_manual_manifest())
    direct_job = app_direct.create_job(_manual_manifest())
    cli_json.run(
        cli_app,
        ["plan-sources", "--job", cli_job.id, "--out", str(tmp_path / "cli-plan")],
        io.StringIO(),
    )
    mcp_plan_result = cast(
        CallToolResult,
        make_handlers(mcp_app)["plan_sources"](mcp_job.id, str(tmp_path / "mcp-plan")),
    )
    app_direct.plan_sources(direct_job.id, tmp_path / "app-plan")
    cli_sources = tmp_path / "cli-sources"
    mcp_sources = tmp_path / "mcp-sources"
    app_sources = tmp_path / "app-sources"
    _write_png(cli_sources / "neutral.png", color=(30, 60, 90))
    _write_png(mcp_sources / "neutral.png", color=(30, 60, 90))
    _write_png(app_sources / "neutral.png", color=(30, 60, 90))
    cli_json.run(
        cli_app,
        ["submit-sources", "--job", cli_job.id, "--sources", str(cli_sources)],
        io.StringIO(),
    )
    mcp_submit_result = cast(
        CallToolResult,
        make_handlers(mcp_app)["submit_sources"](mcp_job.id, str(mcp_sources)),
    )
    app_direct.submit_sources(direct_job.id, app_sources)
    cli_out = io.StringIO()

    cli_rc = cli_json.run(cli_app, ["build", "--job", cli_job.id], cli_out)
    cli_payload = cast(dict[str, object], json.loads(cli_out.getvalue()))
    mcp_result = cast(CallToolResult, make_handlers(mcp_app)["build_asset"](mcp_job.id))
    direct_payload = cast(
        dict[str, object],
        app_direct.build(direct_job.id).model_dump(mode="json"),
    )

    assert cli_rc == 0
    assert mcp_plan_result.isError is False
    assert mcp_submit_result.isError is False
    assert _without_job_identity(cli_payload) == _without_job_identity(direct_payload)
    assert mcp_result.isError is False
    assert _without_job_identity(
        cast(dict[str, object], _mcp_payload(mcp_result)["job_result"])
    ) == _without_job_identity(direct_payload)
    _assert_matching_files(
        data_root / "cli" / "jobs" / cli_job.id / "candidate" / "package",
        data_root / "mcp" / "jobs" / mcp_job.id / "candidate" / "package",
        data_root / "app" / "jobs" / direct_job.id / "candidate" / "package",
    )
    for workspace in (
        data_root / "cli" / "jobs" / cli_job.id,
        data_root / "mcp" / "jobs" / mcp_job.id,
        data_root / "app" / "jobs" / direct_job.id,
    ):
        assert (workspace / "candidate" / "candidate.json").exists()
        assert not (workspace / "report.json").exists()
        assert not (workspace / "lineage.json").exists()
        assert not (workspace / "bundle").exists()


def test_cli_and_mcp_build_failure_match_before_manual_sources_are_submitted(
    data_root: Path,
) -> None:
    cli_app = _app(data_root / "cli")
    mcp_app = _app(data_root / "mcp")
    cli_job = cli_app.create_job(_manual_manifest())
    mcp_job = mcp_app.create_job(_manual_manifest())
    cli_out = io.StringIO()

    cli_rc = cli_json.run(cli_app, ["build", "--job", cli_job.id], cli_out)
    cli_payload = cast(dict[str, object], json.loads(cli_out.getvalue()))
    mcp_result = cast(CallToolResult, make_handlers(mcp_app)["build_asset"](mcp_job.id))

    assert cli_rc == 2
    assert _without_job_identity(cli_payload) == _without_job_identity(
        cast(dict[str, object], _mcp_payload(mcp_result)["job_result"])
    )


def test_cli_and_mcp_repeated_build_errors_match_after_manual_source_handoff(
    data_root: Path,
    tmp_path: Path,
) -> None:
    cli_app = _app(data_root / "cli")
    mcp_app = _app(data_root / "mcp")
    cli_job = cli_app.create_job(_manual_manifest())
    mcp_job = mcp_app.create_job(_manual_manifest())
    cli_sources = tmp_path / "cli-sources"
    mcp_sources = tmp_path / "mcp-sources"
    _write_png(cli_sources / "neutral.png", color=(30, 60, 90))
    _write_png(mcp_sources / "neutral.png", color=(30, 60, 90))

    cli_json.run(
        cli_app,
        ["plan-sources", "--job", cli_job.id, "--out", str(tmp_path / "cli-plan")],
        io.StringIO(),
    )
    cli_json.run(
        cli_app,
        ["submit-sources", "--job", cli_job.id, "--sources", str(cli_sources)],
        io.StringIO(),
    )
    cli_json.run(cli_app, ["build", "--job", cli_job.id], io.StringIO())
    cast(
        CallToolResult,
        make_handlers(mcp_app)["plan_sources"](mcp_job.id, str(tmp_path / "mcp-plan")),
    )
    cast(
        CallToolResult,
        make_handlers(mcp_app)["submit_sources"](mcp_job.id, str(mcp_sources)),
    )
    cast(CallToolResult, make_handlers(mcp_app)["build_asset"](mcp_job.id))
    cli_out = io.StringIO()

    cli_rc = cli_json.run(cli_app, ["build", "--job", cli_job.id], cli_out)
    cli_payload = cast(list[dict[str, object]], json.loads(cli_out.getvalue()))
    mcp_result = cast(CallToolResult, make_handlers(mcp_app)["build_asset"](mcp_job.id))

    assert cli_rc == 2
    assert mcp_result.isError is True
    assert _without_diagnostic_identity(cli_payload) == _without_diagnostic_identity(
        _mcp_diagnostics(mcp_result)
    )


def test_cli_and_mcp_plan_sources_reject_invalid_job_ids_consistently(
    data_root: Path,
    tmp_path: Path,
) -> None:
    app = _app(data_root)
    cli_out = io.StringIO()

    cli_rc = cli_json.run(
        app,
        ["plan-sources", "--job", "..", "--out", str(tmp_path / "plan")],
        cli_out,
    )
    cli_payload = json.loads(cli_out.getvalue())
    mcp_result = cast(
        CallToolResult,
        make_handlers(app)["plan_sources"]("..", str(tmp_path / "plan")),
    )

    assert cli_rc == 2
    assert cli_payload == cast(dict[str, object], _mcp_payload(mcp_result)["diagnostics"])


async def test_candidate_approval_and_finalization_are_equivalent_across_surfaces(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    direct_app = _app(data_root / "direct")
    cli_app = _app(data_root / "cli")
    mcp_app = _app(data_root / "mcp")
    http_app = _app(data_root / "http")
    direct_job = direct_app.create_job(_manifest())
    cli_job = cli_app.create_job(_manifest())
    mcp_job = mcp_app.create_job(_manifest())
    http_job = http_app.create_job(_manifest())
    assert direct_app.build(direct_job.id).ok
    assert cli_app.build(cli_job.id).ok
    assert mcp_app.build(mcp_job.id).ok

    direct_approval = direct_app.approve_review(direct_job.id, "reviewer")
    direct_result = direct_app.finalize_job(direct_job.id)
    cli_approval_out = io.StringIO()
    cli_finalize_out = io.StringIO()
    cli_approval_rc = cli_json.run(
        cli_app,
        ["job", "approve", cli_job.id, "--actor", "reviewer"],
        cli_approval_out,
    )
    cli_finalize_rc = cli_json.run(cli_app, ["job", "finalize", cli_job.id], cli_finalize_out)
    mcp_approval = cast(
        CallToolResult,
        make_handlers(mcp_app)["approve_review"](mcp_job.id, "reviewer"),
    )
    mcp_finalization = cast(
        CallToolResult,
        make_handlers(mcp_app)["finalize_job"](mcp_job.id),
    )

    async with _client(http_app, monkeypatch) as client:
        http_build = await client.post(f"/api/jobs/{http_job.id}/build")
        http_approval = await client.post(
            f"/api/jobs/{http_job.id}/approve",
            json={"actor": "reviewer"},
        )
        http_finalization = await client.post(f"/api/jobs/{http_job.id}/finalize")

    assert direct_approval.decision == "approved"
    assert direct_result.ok is True
    assert cli_approval_rc == cli_finalize_rc == 0
    assert json.loads(cli_approval_out.getvalue())["decision"] == "approved"
    assert json.loads(cli_finalize_out.getvalue())["lineage_id"].endswith("-export")
    assert mcp_approval.isError is False
    assert _mcp_payload(mcp_approval)["approval"]["decision"] == "approved"
    assert mcp_finalization.isError is False
    assert _mcp_payload(mcp_finalization)["job_result"]["lineage_id"].endswith("-export")
    assert http_build.status_code == 200
    assert http_build.json()["ok"] is True
    assert http_approval.status_code == 200
    assert http_approval.json()["decision"] == "approved"
    assert http_finalization.status_code == 200
    assert http_finalization.json()["lineage_id"].endswith("-export")
    assert all(
        app.get_job(job.id).state is JobState.COMPLETED
        for app, job in (
            (direct_app, direct_job),
            (cli_app, cli_job),
            (mcp_app, mcp_job),
            (http_app, http_job),
        )
    )


def _high_entropy_bytes() -> bytes:
    """Deterministic bytes whose base64 text contains ``+/`` and leading slashes."""

    return bytes(range(256)) + bytes([3, 239, 192]) + bytes([255, 224, 0])


async def test_cli_mcp_and_http_decode_binary_artifacts_byte_for_byte(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(data_root)
    job = app.create_job(_manifest())
    workspace = data_root / "jobs" / job.id
    payload = _high_entropy_bytes()
    (workspace / "package").mkdir()
    (workspace / "package" / "portrait.png").write_bytes(payload)
    (workspace / "bundle").mkdir()
    (workspace / "bundle" / "package").mkdir()
    (workspace / "bundle" / "package" / "portrait.png").write_bytes(payload)
    cli_artifact = io.StringIO()
    cli_bundle = io.StringIO()

    cli_artifact_rc = cli_json.run(
        app, ["job", "artifact", job.id, "package/portrait.png"], cli_artifact
    )
    cli_bundle_rc = cli_json.run(
        app, ["job", "bundle-file", job.id, "package/portrait.png"], cli_bundle
    )
    mcp_artifact = cast(
        CallToolResult,
        make_handlers(app)["read_job_artifact"](job.id, "package/portrait.png"),
    )
    mcp_bundle = cast(
        CallToolResult,
        make_handlers(app)["read_bundle_file"](job.id, "package/portrait.png"),
    )

    async with _client(app, monkeypatch) as client:
        http_artifact = await client.get(f"/api/jobs/{job.id}/artifacts/package/portrait.png")
        http_bundle = await client.get(f"/api/jobs/{job.id}/bundle/package/portrait.png")

    assert cli_artifact_rc == cli_bundle_rc == 0
    assert http_artifact.status_code == http_bundle.status_code == 200
    assert http_artifact.content == payload
    assert http_bundle.content == payload
    assert base64.b64decode(json.loads(cli_artifact.getvalue())["content_base64"]) == payload
    assert base64.b64decode(json.loads(cli_bundle.getvalue())["content_base64"]) == payload
    assert mcp_artifact.isError is False
    assert mcp_bundle.isError is False
    artifact_file = cast(dict[str, object], _mcp_payload(mcp_artifact)["file"])
    bundle_file = cast(dict[str, object], _mcp_payload(mcp_bundle)["file"])
    assert base64.b64decode(cast(str, artifact_file["content_base64"])) == payload
    assert base64.b64decode(cast(str, bundle_file["content_base64"])) == payload
