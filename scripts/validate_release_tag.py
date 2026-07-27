from __future__ import annotations

import argparse
import ast
import re
import sys
import tomllib
from pathlib import Path

TAG_PATTERN = re.compile(r"^v(?P<version>(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))$")


def _canonical_version(value: str) -> bool:
    return TAG_PATTERN.fullmatch(f"v{value}") is not None


def _read_project_version(pyproject: Path) -> str:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    try:
        version = data["project"]["version"]
    except (KeyError, TypeError) as error:
        raise ValueError("invalid project version") from error
    if not isinstance(version, str) or not _canonical_version(version):
        raise ValueError("invalid project version")
    return version


def _read_package_version(package_init: Path) -> str:
    tree = ast.parse(package_init.read_text(encoding="utf-8"))
    for node in tree.body:
        match node:
            case ast.Assign(
                targets=[ast.Name(id="__version__")],
                value=ast.Constant(value=value),
            ) if isinstance(value, str) and _canonical_version(value):
                return value
            case ast.AnnAssign(
                target=ast.Name(id="__version__"),
                value=ast.Constant(value=value),
            ) if isinstance(value, str) and _canonical_version(value):
                return value
    raise ValueError("invalid package version")


def validate_release_tag(tag: str, pyproject: Path, package_init: Path) -> str:
    match = TAG_PATTERN.fullmatch(tag)
    if match is None:
        raise ValueError("invalid release tag")
    version = match.group("version")
    if version != _read_project_version(pyproject):
        raise ValueError("invalid release tag")
    if version != _read_package_version(package_init):
        raise ValueError("invalid release tag")
    return version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="validate_release_tag")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument(
        "--package-init",
        type=Path,
        default=Path("src/fecreator/__init__.py"),
    )
    args = parser.parse_args(argv)
    try:
        print(validate_release_tag(args.tag, args.pyproject, args.package_init))
    except (OSError, SyntaxError, ValueError, tomllib.TOMLDecodeError):
        print("invalid release tag", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
