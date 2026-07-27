from pathlib import Path

import pytest

from scripts.validate_release_tag import main, validate_release_tag


def _files(tmp_path: Path, project_version: str, package_version: str) -> tuple[Path, Path]:
    pyproject = tmp_path / "pyproject.toml"
    package_init = tmp_path / "__init__.py"
    pyproject.write_text(
        f'[project]\nname = "fecreator"\nversion = "{project_version}"\n',
        encoding="utf-8",
    )
    package_init.write_text(f'__version__ = "{package_version}"\n', encoding="utf-8")
    return pyproject, package_init


def test_validate_release_tag_returns_matching_version(tmp_path: Path) -> None:
    pyproject, package_init = _files(tmp_path, "0.1.0", "0.1.0")

    assert validate_release_tag("v0.1.0", pyproject, package_init) == "0.1.0"


def test_validate_release_tag_propagates_syntax_error_from_package_init(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    package_init = tmp_path / "__init__.py"
    pyproject.write_text('[project]\nname = "fecreator"\nversion = "0.1.0"\n', encoding="utf-8")
    package_init.write_text('__version__ = "0.1.0"\n(', encoding="utf-8")

    with pytest.raises(SyntaxError):
        validate_release_tag("v0.1.0", pyproject, package_init)


def test_main_returns_generic_error_for_malformed_package_init(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    package_init = tmp_path / "__init__.py"
    pyproject.write_text('[project]\nname = "fecreator"\nversion = "0.1.0"\n', encoding="utf-8")
    package_init.write_text('__version__ = "0.1.0"\n(', encoding="utf-8")

    rc = main(
        ["--tag", "v0.1.0", "--pyproject", str(pyproject), "--package-init", str(package_init)]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == "invalid release tag\n"
    assert "Traceback" not in captured.err
    assert str(tmp_path) not in captured.err


@pytest.mark.parametrize(
    ("pyproject_text", "package_init_text", "missing_path"),
    [
        ('[project]\nname = "fecreator"\nversion = \n', '__version__ = "0.1.0"\n', None),
        (
            '[project]\nname = "fecreator"\nversion = "0.1.0"\n',
            '__version__ = "0.1.0"\n',
            "pyproject",
        ),
        (
            '[project]\nname = "fecreator"\nversion = "0.1.0"\n',
            '__version__ = "0.1.0"\n',
            "package",
        ),
    ],
)
def test_main_returns_generic_error_for_invalid_cli_inputs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    pyproject_text: str,
    package_init_text: str,
    missing_path: str | None,
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    package_init = tmp_path / "__init__.py"
    pyproject.write_text(pyproject_text, encoding="utf-8")
    package_init.write_text(package_init_text, encoding="utf-8")
    if missing_path == "pyproject":
        pyproject.unlink()
    if missing_path == "package":
        package_init.unlink()

    rc = main(
        ["--tag", "v0.1.0", "--pyproject", str(pyproject), "--package-init", str(package_init)]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == "invalid release tag\n"
    assert "Traceback" not in captured.err
    assert str(tmp_path) not in captured.err


def test_main_returns_matching_version_for_valid_cli_input(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pyproject, package_init = _files(tmp_path, "0.1.0", "0.1.0")

    rc = main(
        ["--tag", "v0.1.0", "--pyproject", str(pyproject), "--package-init", str(package_init)]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == "0.1.0\n"
    assert captured.err == ""


@pytest.mark.parametrize(
    ("tag", "project_version", "package_version"),
    [
        ("0.1.0", "0.1.0", "0.1.0"),
        ("v01.0.0", "1.0.0", "1.0.0"),
        ("v1.0.0", "01.0.0", "1.0.0"),
        ("v1.0.0", "1.0.0", "1.00.0"),
        ("v0.1", "0.1.0", "0.1.0"),
        ("v0.1.1", "0.1.0", "0.1.0"),
        ("v0.1.0", "0.1.0", "0.1.1"),
    ],
)
def test_validate_release_tag_rejects_invalid_or_mismatched_versions(
    tmp_path: Path,
    tag: str,
    project_version: str,
    package_version: str,
) -> None:
    pyproject, package_init = _files(tmp_path, project_version, package_version)

    with pytest.raises(ValueError):
        validate_release_tag(tag, pyproject, package_init)
