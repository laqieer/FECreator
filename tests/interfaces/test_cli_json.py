from __future__ import annotations

import argparse
import base64
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import fecreator.cli as cli_module
from fecreator import __version__
from fecreator.app import FeCreatorApp
from fecreator.cli import main
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.contracts.result import Artifact
from fecreator.core.config import Settings
from fecreator.interfaces.cli_json import build_parser, run
from fecreator.jobs.model import Job
from fecreator.references.model import ReferencePack
from fecreator.references.store import ReferencePackStore

REPO_ROOT = Path(__file__).resolve().parents[2]
TASK9_PLAN = (
    REPO_ROOT / "docs" / "superpowers" / "plans" / "2026-07-24-fecreator-providers-interfaces.md"
)


def _app(data_root: Path) -> FeCreatorApp:
    return FeCreatorApp(Settings(data_root=data_root))


def _reference_pack(pack_id: str = "corrupt-pack") -> ReferencePack:
    return ReferencePack(
        id=pack_id,
        revision=99,
        source="synthetic fixture prompt",
        concept_art=(
            Artifact(
                role="concept_art",
                path="incoming/front.png",
                sha256="a" * 64,
                media_type="image/png",
            ),
        ),
        traits={"hair": "blue"},
        swatches=("#112233",),
        forbidden_changes=("change face shape",),
        provenance="synthetic-fixture",
        rights="original",
    )


def _create_pinned_job(
    data_root: Path, *, pack_id: str = "corrupt-pack"
) -> tuple[FeCreatorApp, Job]:
    app = _app(data_root)
    store = ReferencePackStore(data_root)
    store.create(_reference_pack(pack_id))
    job = app.create_job(
        Manifest(
            asset_type="portrait",
            target_spec="fe-gba-portrait-standard",
            workflow="text_to_portrait",
            provider="fake",
            character_ref_pack=pack_id,
            sources=(SourceSpec(kind="text", ref="hero"),),
        )
    )
    return app, job


def _run_cli(data_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["FECREATOR_DATA_ROOT"] = str(data_root)
    return subprocess.run(
        [sys.executable, "-m", "fecreator.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def test_list_specs_json(data_root: Path) -> None:
    out = io.StringIO()

    rc = run(_app(data_root), ["list-specs"], out)

    assert rc == 0
    assert json.loads(out.getvalue()) == ["fe-gba-portrait-standard"]


def test_validate_missing_sheet(data_root: Path) -> None:
    out = io.StringIO()

    rc = run(
        _app(data_root),
        ["validate", "--spec", "fe-gba-portrait-standard", "--path", str(data_root)],
        out,
    )

    codes = {diagnostic["code"] for diagnostic in json.loads(out.getvalue())}
    assert rc == 2
    assert "MISSING_SHEET" in codes


def test_job_create_and_status(data_root: Path, tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "asset_type": "portrait",
                "target_spec": "fe-gba-portrait-standard",
                "workflow": "text_to_portrait",
                "provider": "fake",
                "sources": [{"kind": "text", "ref": "hero"}],
            }
        ),
        encoding="utf-8",
    )
    out = io.StringIO()

    create_rc = run(_app(data_root), ["job", "create", "--manifest", str(manifest)], out)

    job_payload = json.loads(out.getvalue())
    status_out = io.StringIO()
    status_rc = run(_app(data_root), ["job", "status", job_payload["id"]], status_out)

    assert create_rc == 0
    assert status_rc == 0
    assert json.loads(status_out.getvalue())["state"] == "created"


def test_additive_job_reference_and_lineage_commands_emit_deterministic_json(
    data_root: Path,
) -> None:
    parser = build_parser()
    job_parser = next(
        action
        for action in parser._subparsers._group_actions
        if isinstance(action, argparse._SubParsersAction) and action.dest == "command"
    ).choices["job"]
    job_commands = next(
        action
        for action in job_parser._subparsers._group_actions
        if isinstance(action, argparse._SubParsersAction) and action.dest == "job_command"
    ).choices

    assert {
        "list",
        "candidate",
        "approvals",
        "plan-sources",
        "validate",
        "artifact",
        "report",
        "bundle",
        "bundle-file",
        "approve",
        "reject",
        "finalize",
        "retry",
        "cancel",
    } <= set(job_commands)
    app = _app(data_root)
    job = app.create_job(
        Manifest(
            asset_type="portrait",
            target_spec="fe-gba-portrait-standard",
            workflow="text_to_portrait",
            provider="fake",
            sources=(SourceSpec(kind="text", ref="hero"),),
        )
    )
    workspace = data_root / "jobs" / job.id
    (workspace / "package").mkdir()
    (workspace / "package" / "portrait.png").write_bytes(b"portrait")
    (workspace / "bundle").mkdir()
    (workspace / "bundle" / "manifest.json").write_text("{}", encoding="utf-8")
    (workspace / "report.json").write_text(
        '{"path":"C:\\\\private\\\\report.json"}',
        encoding="utf-8",
    )
    ReferencePackStore(data_root).create(_reference_pack("hero-pack"))
    out = io.StringIO()

    assert run(app, ["job", "list"], out) == 0
    assert [item["id"] for item in json.loads(out.getvalue())] == [job.id]
    out = io.StringIO()
    assert run(app, ["job", "report", job.id], out) == 0
    assert json.loads(out.getvalue()) == {"path": "report.json"}
    out = io.StringIO()
    assert run(app, ["job", "artifact", job.id, "package/portrait.png"], out) == 0
    assert json.loads(out.getvalue()) == {
        "content_base64": base64.b64encode(b"portrait").decode("ascii"),
        "path": "package/portrait.png",
    }
    out = io.StringIO()
    assert run(app, ["references", "list"], out) == 0
    assert json.loads(out.getvalue()) == ["hero-pack"]


def test_run_invalid_manifest_returns_json_diagnostic(data_root: Path, tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"asset_type":"portrait"}', encoding="utf-8")
    out = io.StringIO()

    rc = run(_app(data_root), ["job", "create", "--manifest", str(manifest)], out)

    assert rc == 2
    assert json.loads(out.getvalue()) == [
        {
            "code": "INVALID_MANIFEST",
            "data": {"error_count": 3},
            "message": "manifest failed validation",
            "severity": "error",
            "where": "manifest.json",
        }
    ]


@pytest.mark.parametrize(
    ("argv", "expected_code", "expected_where"),
    [
        (["job", "status", "missing-job"], "UNKNOWN_JOB", "missing-job"),
        (
            ["validate", "--spec", "missing-spec", "--path", "."],
            "UNKNOWN_SPEC",
            "missing-spec",
        ),
    ],
)
def test_main_expected_errors_write_json_and_exit_2(
    data_root: Path,
    tmp_path: Path,
    argv: list[str],
    expected_code: str,
    expected_where: str,
) -> None:
    package_dir = tmp_path / "package"
    package_dir.mkdir()

    result = _run_cli(
        data_root,
        *[str(package_dir) if arg == "." else arg for arg in argv],
    )

    assert result.returncode == 2
    assert result.stderr == ""
    assert json.loads(result.stdout) == [
        {
            "code": expected_code,
            "data": None,
            "message": "job not found" if expected_code == "UNKNOWN_JOB" else "unknown target spec",
            "severity": "error",
            "where": expected_where,
        }
    ]


def test_run_plan_sources_rejects_invalid_job_id_with_json_diagnostic(
    data_root: Path,
    tmp_path: Path,
) -> None:
    out = io.StringIO()

    rc = run(
        _app(data_root),
        ["plan-sources", "--job", "..", "--out", str(tmp_path / "plan")],
        out,
    )

    assert rc == 2
    assert json.loads(out.getvalue()) == [
        {
            "code": "UNKNOWN_JOB",
            "data": None,
            "message": "job not found",
            "severity": "error",
            "where": "..",
        }
    ]


def test_run_build_corrupt_reference_pack_returns_json_diagnostic(
    data_root: Path,
) -> None:
    app, job = _create_pinned_job(data_root)
    (data_root / "refs" / "corrupt-pack" / "1.json").write_text("{not-json", encoding="utf-8")
    out = io.StringIO()

    rc = run(app, ["build", "--job", job.id], out)

    assert rc == 2
    assert json.loads(out.getvalue()) == [
        {
            "code": "CORRUPT_REFERENCE_PACK",
            "data": None,
            "message": "reference pack is corrupt",
            "severity": "error",
            "where": "corrupt-pack",
        }
    ]


@pytest.mark.parametrize(
    ("argv", "flag"),
    [
        (["validate", "--sp", "missing-spec", "--path", "."], "--sp"),
        (["validate", "--spec", "missing-spec", "--pa", "."], "--pa"),
        (["job", "create", "--man", "manifest.json"], "--man"),
    ],
)
def test_build_parser_rejects_abbreviated_options(
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    flag: str,
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(argv)

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert captured.out == ""
    assert f"unrecognized arguments: {flag}" in captured.err


def test_build_parser_preserves_end_of_options_for_job_status() -> None:
    args = build_parser().parse_args(["job", "status", "--", "--abc"])

    assert args.job_id == "--abc"


def test_build_parser_help_advertises_version() -> None:
    help_text = build_parser().format_help()

    assert "--version" in help_text


def test_task9_plan_keeps_reports_out_of_plan_doc() -> None:
    plan_text = TASK9_PLAN.read_text(encoding="utf-8")
    task9_start = plan_text.index("## Task 9: JSON CLI")
    task10_start = plan_text.index("## Task 10: FastAPI HTTP API and static mount", task9_start)
    task9_section = plan_text[task9_start:task10_start]

    assert "\nReport:\n" not in task9_section


def test_main_writes_single_json_newline(
    data_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FECREATOR_DATA_ROOT", str(data_root))

    rc = main(["list-specs"])

    captured = capsys.readouterr()
    assert rc == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert json.loads(captured.out) == ["fe-gba-portrait-standard"]


def test_main_version_does_not_require_data_root(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("FECREATOR_DATA_ROOT", raising=False)

    rc = main(["--version"])

    captured = capsys.readouterr()
    assert rc == 0
    assert captured.err == ""
    assert captured.out == f"fecreator {__version__}\n"


def test_main_version_does_not_require_settings_or_app_construction(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _fail_settings() -> object:
        pytest.fail("settings requested")

    def _fail_app(*_args: object, **_kwargs: object) -> object:
        pytest.fail("app constructed")

    monkeypatch.setattr(cli_module, "get_settings", _fail_settings)
    monkeypatch.setattr(cli_module, "FeCreatorApp", _fail_app)

    rc = cli_module.main(["--version"])

    captured = capsys.readouterr()
    assert rc == 0
    assert captured.err == ""
    assert captured.out == f"fecreator {__version__}\n"


def test_main_help_does_not_require_data_root(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("FECREATOR_DATA_ROOT", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert captured.err == ""
    assert "usage: fecreator" in captured.out
