from __future__ import annotations

import json
import os
import sys
import textwrap
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from fecreator.interop.febuilder_cli import (
    FeBuilderCliError,
    FeBuilderCliResult,
    build_argv,
    febuilder_cli_from_env,
    normalize_cli_argv,
    run_febuilder_cli,
)

_FAKE_CLI = """
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def main() -> int:
    mode = sys.argv[1]
    args = sys.argv[2:]
    if mode == "ok":
        print(json.dumps(args))
        return 0
    if mode == "echo":
        print(" ".join(args))
        return 0
    if mode == "fail":
        print("partial stdout")
        print("asset rejected by fake cli", file=sys.stderr)
        return 3
    if mode == "hang":
        marker = Path(args[0])
        time.sleep(30)
        marker.write_text("finished", encoding="utf-8")
        return 0
    if mode == "flood":
        sys.stdout.write("x" * 200000)
        sys.stderr.write("y" * 200000)
        return 0
    if mode == "secret":
        print("api_key=fake-value-1234 in " + args[0])
        print("authorization: Bearer fake-token-value", file=sys.stderr)
        return 0
    if mode == "env":
        print(json.dumps(dict(os.environ)))
        return 0
    if mode == "badbytes":
        sys.stdout.buffer.write(b"\\xff\\xfe valid ascii tail")
        sys.stdout.buffer.flush()
        return 0
    print("unknown mode", file=sys.stderr)
    return 9


if __name__ == "__main__":
    raise SystemExit(main())
"""


def _fake_cli_script(tmp_path: Path) -> Path:
    script = tmp_path / "fake_febuilder.py"
    script.write_text(textwrap.dedent(_FAKE_CLI).strip() + "\n", encoding="utf-8", newline="\n")
    return script


def _cli(tmp_path: Path, mode: str, *extra: str) -> tuple[str, ...]:
    return (sys.executable, str(_fake_cli_script(tmp_path)), mode, *extra)


def _source_env(**extra: str) -> dict[str, str]:
    """Build a realistic parent environment: allowlisted keys plus caller extras."""
    inherited = (
        "PATH",
        "SYSTEMROOT",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "WINDIR",
        "USERPROFILE",
        "HOME",
        "LANG",
    )
    env = {key: os.environ[key] for key in inherited if key in os.environ}
    env.update(extra)
    return env


def _package(tmp_path: Path, name: str = "package") -> Path:
    package_dir = tmp_path / name
    package_dir.mkdir(parents=True)
    (package_dir / "hero.png").write_bytes(b"fake")
    return package_dir


def test_missing_cli_is_explicitly_not_run(tmp_path: Path) -> None:
    result = run_febuilder_cli(None, "validate-asset", _package(tmp_path))

    assert result.status == "not_run"
    assert result.exit_code is None
    assert result.command == "validate-asset"
    assert result.stdout == ""
    assert result.stderr == ""


def test_empty_argv_is_not_run(tmp_path: Path) -> None:
    assert run_febuilder_cli((), "validate-asset", _package(tmp_path)).status == "not_run"


def test_result_is_frozen_and_forbids_extra_fields() -> None:
    result = FeBuilderCliResult(status="not_run", command="validate-asset")

    with pytest.raises(ValidationError):
        FeBuilderCliResult(status="not_run", command="validate-asset", argv=["fe.exe"])
    with pytest.raises(ValidationError):
        FeBuilderCliResult(status="maybe", command="validate-asset")
    with pytest.raises(ValidationError):
        result.status = "passed"


def test_string_cli_is_one_token_and_never_shell_split() -> None:
    assert normalize_cli_argv(r"C:\Program Files\FEBuilder\fe builder.exe") == (
        r"C:\Program Files\FEBuilder\fe builder.exe",
    )
    assert normalize_cli_argv(Path("/opt/fe builder/cli")) == (str(Path("/opt/fe builder/cli")),)
    assert normalize_cli_argv(("mono", "FEBuilder.exe")) == ("mono", "FEBuilder.exe")
    assert normalize_cli_argv(None) == ()
    assert normalize_cli_argv("") == ()
    with pytest.raises(FeBuilderCliError):
        normalize_cli_argv(("fe.exe", ""))
    with pytest.raises(FeBuilderCliError):
        normalize_cli_argv(("fe.exe", "--flag\x00"))
    with pytest.raises(FeBuilderCliError):
        normalize_cli_argv("fe\x00.exe")


def test_febuilder_cli_from_env_reads_one_token() -> None:
    assert febuilder_cli_from_env({}) is None
    assert febuilder_cli_from_env({"FEBUILDER_CLI": "   "}) is None
    assert febuilder_cli_from_env({"FEBUILDER_CLI": r"C:\fe builder\FEBuilderGBA.exe"}) == (
        r"C:\fe builder\FEBuilderGBA.exe",
    )


def test_build_argv_matches_the_febuilder_contract(tmp_path: Path) -> None:
    package_dir = _package(tmp_path)
    expect_dir = _package(tmp_path, "expected")

    assert build_argv(("fe.exe",), "validate-asset", package_dir) == [
        "fe.exe",
        "--validate-asset",
        "--kind=portrait-package",
        f"--path={package_dir}",
    ]
    assert build_argv(("mono", "fe.exe"), "roundtrip-asset", package_dir, expect_dir) == [
        "mono",
        "fe.exe",
        "--roundtrip-asset",
        "--kind=portrait-package",
        f"--path={package_dir}",
        f"--expect={expect_dir}",
    ]


def test_cli_uses_argv_and_redacts_output(tmp_path: Path) -> None:
    package_dir = _package(tmp_path)

    result = run_febuilder_cli(
        _cli(tmp_path, "echo"),
        "validate-asset",
        package_dir,
        env=_source_env(),
    )

    assert result.status == "passed"
    assert result.exit_code == 0
    assert str(tmp_path) not in result.stdout
    assert str(package_dir) not in result.stdout
    assert "--kind=portrait-package" in result.stdout


def test_cli_passes_paths_with_spaces_as_single_arguments(tmp_path: Path) -> None:
    package_dir = _package(tmp_path, "package with spaces")
    expect_dir = _package(tmp_path, "expected with spaces")

    result = run_febuilder_cli(
        _cli(tmp_path, "ok"),
        "roundtrip-asset",
        package_dir,
        expect_dir,
        env=_source_env(),
    )

    assert result.status == "passed"
    assert json.loads(result.stdout) == [
        "--roundtrip-asset",
        "--kind=portrait-package",
        f"--path={package_dir.resolve()}",
        f"--expect={expect_dir.resolve()}",
    ]


def test_missing_executable_fails_without_leaking_the_path(tmp_path: Path) -> None:
    missing = tmp_path / "no such febuilder.exe"

    result = run_febuilder_cli((str(missing),), "validate-asset", _package(tmp_path))

    assert result.status == "failed"
    assert result.exit_code is None
    assert str(tmp_path) not in result.stderr
    assert "not found" in result.stderr


def test_nonzero_exit_is_failed_with_bounded_output(tmp_path: Path) -> None:
    result = run_febuilder_cli(
        _cli(tmp_path, "fail"),
        "validate-asset",
        _package(tmp_path),
        env=_source_env(),
    )

    assert result.status == "failed"
    assert result.exit_code == 3
    assert "asset rejected by fake cli" in result.stderr
    assert "partial stdout" in result.stdout


def test_timeout_fails_and_kills_the_child(tmp_path: Path) -> None:
    marker = tmp_path / "marker.txt"

    result = run_febuilder_cli(
        _cli(tmp_path, "hang", str(marker)),
        "validate-asset",
        _package(tmp_path),
        env=_source_env(),
        timeout_seconds=1.0,
    )

    assert result.status == "failed"
    assert result.exit_code is None
    assert "timed out" in result.stderr
    time.sleep(2.0)
    assert not marker.exists()


def test_output_is_bounded(tmp_path: Path) -> None:
    result = run_febuilder_cli(
        _cli(tmp_path, "flood"),
        "validate-asset",
        _package(tmp_path),
        env=_source_env(),
        max_output_chars=256,
    )

    assert result.status == "passed"
    assert len(result.stdout) <= 256 + len("... [truncated]")
    assert result.stdout.endswith("... [truncated]")
    assert len(result.stderr) <= 256 + len("... [truncated]")


def test_secrets_and_absolute_paths_are_redacted(tmp_path: Path) -> None:
    package_dir = _package(tmp_path)

    result = run_febuilder_cli(
        _cli(tmp_path, "secret"),
        "validate-asset",
        package_dir,
        env=_source_env(),
    )

    assert result.status == "passed"
    assert "fake-value-1234" not in result.stdout
    assert "api_key=***" in result.stdout
    assert str(package_dir) not in result.stdout
    assert "fake-token-value" not in result.stderr


def test_environment_is_allowlisted(tmp_path: Path) -> None:
    result = run_febuilder_cli(
        _cli(tmp_path, "env"),
        "validate-asset",
        _package(tmp_path),
        env=_source_env(
            FECREATOR_API_TOKEN="fake-token-value",
            AWS_SECRET_ACCESS_KEY="fake-secret-value",
            FEBUILDER_ROM="rom.gba",
        ),
    )

    assert result.status == "passed"
    child_env = json.loads(result.stdout)
    assert "FECREATOR_API_TOKEN" not in child_env
    assert "AWS_SECRET_ACCESS_KEY" not in child_env
    assert "FEBUILDER_ROM" not in child_env
    assert child_env["PYTHONIOENCODING"] == "utf-8"
    assert "PATH" in child_env


def test_undecodable_output_is_failed(tmp_path: Path) -> None:
    result = run_febuilder_cli(
        _cli(tmp_path, "badbytes"),
        "validate-asset",
        _package(tmp_path),
        env=_source_env(),
    )

    assert result.status == "failed"
    assert result.exit_code is None
    assert "not valid utf-8" in result.stderr
    assert result.stdout == ""


def test_missing_package_directory_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(FeBuilderCliError):
        run_febuilder_cli(("fe.exe",), "validate-asset", tmp_path / "absent")


def test_regular_file_package_argument_fails_loudly(tmp_path: Path) -> None:
    package_file = tmp_path / "package.png"
    package_file.write_bytes(b"fake")

    with pytest.raises(FeBuilderCliError):
        run_febuilder_cli(("fe.exe",), "validate-asset", package_file)


def test_paths_outside_the_root_fail_loudly(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    inside = _package(root)
    outside = _package(tmp_path, "outside")

    with pytest.raises(FeBuilderCliError):
        run_febuilder_cli(("fe.exe",), "validate-asset", outside, root=root)
    with pytest.raises(FeBuilderCliError):
        run_febuilder_cli(("fe.exe",), "roundtrip-asset", inside, outside, root=root)


def test_symlinked_package_directory_fails_loudly(tmp_path: Path) -> None:
    package_dir = _package(tmp_path)
    link = tmp_path / "link"
    try:
        link.symlink_to(package_dir, target_is_directory=True)
    except (OSError, NotImplementedError):  # pragma: no cover - needs privileges on Windows
        pytest.skip("symlink creation is not supported in this environment")

    with pytest.raises(FeBuilderCliError):
        run_febuilder_cli(("fe.exe",), "validate-asset", link)


def test_unknown_command_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(FeBuilderCliError):
        run_febuilder_cli(("fe.exe",), "delete-rom", _package(tmp_path))  # type: ignore[arg-type]


def test_expect_directory_requires_the_roundtrip_command(tmp_path: Path) -> None:
    package_dir = _package(tmp_path)
    expect_dir = _package(tmp_path, "expected")

    with pytest.raises(FeBuilderCliError):
        run_febuilder_cli(("fe.exe",), "validate-asset", package_dir, expect_dir)
