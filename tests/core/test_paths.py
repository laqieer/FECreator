from pathlib import Path

import pytest

from fecreator.core.paths import (
    PathEscapeError,
    ensure_portable_filename,
    is_contained,
    safe_join,
)


def test_safe_join_ok(tmp_path: Path) -> None:
    p = safe_join(tmp_path, "jobs", "abc", "manifest.json")
    assert is_contained(tmp_path, p)
    assert p.name == "manifest.json"


def test_safe_join_rejects_parent_escape(tmp_path: Path) -> None:
    with pytest.raises(PathEscapeError):
        safe_join(tmp_path, "..", "etc", "passwd")


def test_safe_join_rejects_absolute(tmp_path: Path) -> None:
    with pytest.raises(PathEscapeError):
        safe_join(tmp_path, "/abs/path")


def test_is_contained_false_for_sibling(tmp_path: Path) -> None:
    sibling = tmp_path.parent / "other"
    assert is_contained(tmp_path, sibling) is False


@pytest.mark.parametrize(
    "name",
    ["CON.png", "con.png", "nul", "LPT9.tar.gz", "aux", "neutral.png.", "neutral.png "],
)
def test_ensure_portable_filename_rejects_windows_hostile_names(name: str) -> None:
    with pytest.raises(ValueError):
        ensure_portable_filename(name, field_name="filename")


@pytest.mark.parametrize("name", ["neutral.png", "console.png", "com0.png", "lpt10.png"])
def test_ensure_portable_filename_accepts_ordinary_names(name: str) -> None:
    assert ensure_portable_filename(name, field_name="filename") == name
