from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath

RESERVED_STORAGE_IDS = frozenset({"locks", ".locks"})

_WIN_EXTENDED_UNC_PREFIX = "\\\\?\\UNC\\"
_WIN_EXTENDED_PREFIX = "\\\\?\\"


class PathEscapeError(Exception):
    """Raised when a path would resolve outside its workspace root."""


def _has_absolute_part(parts: tuple[str, ...]) -> bool:
    for part in parts:
        if PurePosixPath(part).is_absolute() or PureWindowsPath(part).is_absolute():
            return True
        if len(part) >= 2 and part[1] == ":":
            return True
    return False


def _strip_windows_extended_prefix(text: str) -> str:
    """Collapse Windows extended-length prefixes to their ordinary equivalent.

    ``\\\\?\\C:\\x`` becomes ``C:\\x`` and ``\\\\?\\UNC\\srv\\share\\x`` becomes
    ``\\\\srv\\share\\x`` so that a path resolved with the extended prefix compares
    equal to the same path resolved without it.
    """

    if text.startswith(_WIN_EXTENDED_UNC_PREFIX):
        return "\\\\" + text[len(_WIN_EXTENDED_UNC_PREFIX) :]
    if text.startswith(_WIN_EXTENDED_PREFIX):
        return text[len(_WIN_EXTENDED_PREFIX) :]
    return text


def _canonical_parts(path: Path) -> tuple[str, ...]:
    """Return canonical, comparable path components for an absolute resolved path.

    On Windows the extended-length prefix is normalised away and components are
    case-folded to match the platform's case-insensitive semantics.  On POSIX the
    components are returned verbatim to preserve case-sensitive behaviour.
    """

    if os.name == "nt":
        normalized = _strip_windows_extended_prefix(str(path))
        return tuple(part.casefold() for part in PureWindowsPath(normalized).parts)
    return path.parts


def _is_contained_resolved(root: Path, target: Path) -> bool:
    """Component-aware containment check for already-resolved paths.

    Both arguments must already be resolved; this performs no further resolution,
    so it is safe to call with a single canonical resolution per path.  Different
    drives / anchors and any error fail closed (return ``False``).  Containment is
    determined by matching whole path components, never a naive string prefix, so
    ``C:\\root2`` is not treated as inside ``C:\\root``.
    """

    try:
        root_parts = _canonical_parts(root)
        target_parts = _canonical_parts(target)
    except ValueError:
        return False
    prefix_len = len(root_parts)
    if len(target_parts) < prefix_len:
        return False
    return target_parts[:prefix_len] == root_parts


def safe_join(root: Path, *parts: str) -> Path:
    if _has_absolute_part(parts):
        raise PathEscapeError(f"absolute segment not allowed: {parts!r}")
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*parts).resolve()
    if not _is_contained_resolved(resolved_root, candidate):
        raise PathEscapeError(f"{candidate} escapes {resolved_root}")
    return candidate


def is_contained(root: Path, target: Path) -> bool:
    return _is_contained_resolved(root.resolve(), target.resolve())


def normalize_storage_id(value: str, *, field_name: str) -> str:
    if value != value.strip():
        raise ValueError(f"{field_name} must not have leading or trailing whitespace")

    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    if _has_absolute_part((normalized,)):
        raise PathEscapeError(f"absolute segment not allowed: {(normalized,)!r}")
    if normalized in {".", ".."}:
        raise ValueError(f"{field_name} must not be '.' or '..'")
    if normalized.startswith("."):
        raise ValueError(f"{field_name} must not start with '.'")
    if normalized in RESERVED_STORAGE_IDS:
        raise ValueError(f"{field_name} uses a reserved namespace: {normalized!r}")
    if "/" in normalized or "\\" in normalized:
        raise ValueError(f"{field_name} must not contain path separators: {normalized!r}")
    return normalized


def ensure_storage_id_not_reserved(
    value: str,
    *,
    field_name: str,
    reserved_values: set[str] | frozenset[str] = frozenset(),
    reserved_prefixes: tuple[str, ...] = (),
) -> str:
    if value in reserved_values:
        raise ValueError(f"{field_name} uses a reserved namespace: {value!r}")
    for prefix in reserved_prefixes:
        if value.startswith(prefix):
            raise ValueError(f"{field_name} uses a reserved namespace: {value!r}")
    return value
