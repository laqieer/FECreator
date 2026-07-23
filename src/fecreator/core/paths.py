from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath


class PathEscapeError(Exception):
    """Raised when a path would resolve outside its workspace root."""


def _has_absolute_part(parts: tuple[str, ...]) -> bool:
    for part in parts:
        if PurePosixPath(part).is_absolute() or PureWindowsPath(part).is_absolute():
            return True
        if len(part) >= 2 and part[1] == ":":
            return True
    return False


def safe_join(root: Path, *parts: str) -> Path:
    if _has_absolute_part(parts):
        raise PathEscapeError(f"absolute segment not allowed: {parts!r}")
    root = root.resolve()
    candidate = root.joinpath(*parts).resolve()
    if not is_contained(root, candidate):
        raise PathEscapeError(f"{candidate} escapes {root}")
    return candidate


def is_contained(root: Path, target: Path) -> bool:
    root = root.resolve()
    target = target.resolve()
    return root == target or root in target.parents
