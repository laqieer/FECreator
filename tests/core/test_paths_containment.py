"""Regression tests for the Windows extended-length prefix containment race.

These tests exercise the canonical resolved-path comparison used by
``safe_join``/``is_contained``.  On Windows ``Path.resolve`` may return either an
ordinary ``C:\\...`` form or an extended-length ``\\\\?\\C:\\...`` form depending
on whether intermediate directories already exist.  When concurrent directory
creation flips the representation of a legitimately-contained path between two
resolutions, a naive ``Path.parents`` membership check spuriously reports that
the path escapes its root.  The comparison must therefore normalise the extended
prefix and case before comparing components.
"""

from __future__ import annotations

import contextlib
import os
import threading
from pathlib import Path

import pytest

from fecreator.core.paths import (
    PathEscapeError,
    _is_contained_resolved,
    is_contained,
    safe_join,
)

windows_only = pytest.mark.skipif(os.name != "nt", reason="Windows path semantics only")


@windows_only
@pytest.mark.parametrize(
    ("root", "target"),
    [
        (r"C:\proj\data", r"\\?\C:\proj\data\lineage\.locks\graph"),
        (r"\\?\C:\proj\data", r"C:\proj\data\lineage\a.json"),
        (r"\\?\C:\proj\data", r"\\?\C:\proj\data\lineage"),
        (r"C:\proj\data", r"C:\proj\data"),
        (r"\\?\C:\proj\data", r"C:\proj\data"),
    ],
)
def test_extended_prefix_variants_are_contained(root: str, target: str) -> None:
    assert _is_contained_resolved(Path(root), Path(target)) is True


@windows_only
def test_extended_unc_prefix_is_contained() -> None:
    root = Path(r"\\?\UNC\server\share\data")
    target = Path(r"\\server\share\data\lineage\node.json")
    assert _is_contained_resolved(root, target) is True
    assert (
        _is_contained_resolved(Path(r"\\server\share\data"), Path(r"\\?\UNC\server\share\data\x"))
        is True
    )


@windows_only
def test_containment_is_case_insensitive_on_windows() -> None:
    assert _is_contained_resolved(Path(r"C:\Proj\Data"), Path(r"c:\proj\data\sub")) is True
    assert _is_contained_resolved(Path(r"\\?\C:\PROJ\data"), Path(r"c:\proj\DATA\sub")) is True


@windows_only
def test_different_drive_is_rejected_fail_closed() -> None:
    assert _is_contained_resolved(Path(r"C:\proj\data"), Path(r"D:\proj\data\sub")) is False
    assert _is_contained_resolved(Path(r"\\?\C:\proj\data"), Path(r"\\?\D:\proj\data\sub")) is False


@windows_only
def test_naive_string_prefix_sibling_is_rejected() -> None:
    # C:\root2 must not be considered inside C:\root even though the strings share a prefix.
    assert _is_contained_resolved(Path(r"C:\proj\root"), Path(r"C:\proj\root2\sub")) is False
    assert _is_contained_resolved(Path(r"C:\proj\root2"), Path(r"C:\proj\root\sub")) is False


def test_is_contained_resolved_root_equals_target(tmp_path: Path) -> None:
    root = (tmp_path / "data").resolve()
    root.mkdir()
    assert _is_contained_resolved(root, root) is True


def test_is_contained_resolved_rejects_sibling(tmp_path: Path) -> None:
    root = (tmp_path / "data").resolve()
    sibling = (tmp_path / "data-other").resolve()
    assert _is_contained_resolved(root, sibling) is False


def test_safe_join_creates_nonexistent_then_contained(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    joined = safe_join(root, "lineage", ".locks", "graph")
    assert is_contained(root, joined)
    # Now create the directory chain and re-join: still contained, no spurious escape.
    joined.parent.mkdir(parents=True, exist_ok=True)
    again = safe_join(root, "lineage", ".locks", "graph")
    assert is_contained(root, again)
    assert again == joined


def test_safe_join_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    link = root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted in this environment")
    with pytest.raises(PathEscapeError):
        safe_join(root, "escape", "secret.txt")


def test_safe_join_stable_under_concurrent_directory_creation(tmp_path: Path) -> None:
    """Bounded concurrency regression: a legitimately-contained path must never be
    reported as escaping while sibling directories are created concurrently."""
    root = (tmp_path / "data").resolve()
    root.mkdir()
    workers = 4
    iterations = 400
    errors: list[str] = []
    barrier = threading.Barrier(workers + 1)

    def churn(idx: int) -> None:
        barrier.wait()
        for i in range(iterations):
            target = root / "lineage" / ".locks" / f"w{idx}" / f"g{i % 8}"
            with contextlib.suppress(OSError):
                target.mkdir(parents=True, exist_ok=True)

    def joiner() -> None:
        barrier.wait()
        for _ in range(iterations):
            try:
                safe_join(root, "lineage", ".locks", "graph")
            except PathEscapeError as exc:  # pragma: no cover - failure path
                errors.append(str(exc))
                return

    churners = [threading.Thread(target=churn, args=(i,)) for i in range(workers)]
    joiner_thread = threading.Thread(target=joiner)
    for thread in churners:
        thread.start()
    joiner_thread.start()
    for thread in churners:
        thread.join()
    joiner_thread.join()

    assert errors == [], f"safe_join spuriously rejected a contained path: {errors[:3]}"
