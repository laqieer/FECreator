from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fecreator import __version__
from fecreator.app import FeCreatorApp
from fecreator.cli import main
from fecreator.core.config import Settings
from fecreator.interfaces.cli_json import build_parser, run

REPO_ROOT = Path(__file__).resolve().parents[2]


def _app(data_root: Path) -> FeCreatorApp:
    return FeCreatorApp(Settings(data_root=data_root))


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
