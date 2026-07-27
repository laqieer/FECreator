from pathlib import Path

import pytest

from scripts.validate_release_tag import validate_release_tag


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


@pytest.mark.parametrize(
    ("tag", "project_version", "package_version"),
    [
        ("0.1.0", "0.1.0", "0.1.0"),
        ("v01.0.0", "1.0.0", "1.0.0"),
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
