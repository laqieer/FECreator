from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import PurePath, PurePosixPath, PureWindowsPath

_AUTH_BEARER_PATTERN = re.compile(r"(?i)\bauthorization\b\s*[:=]\s*Bearer\s+[^\s&]+")
_SECRET_PATTERN = re.compile(
    r"(?i)\b(authorization|bearer|token|api[_-]?key|secret|password|credential|sig|signature)"
    r"\b\s*[:=]\s*([^\s&]+)"
)
_SECRET_KEY_PATTERN = re.compile(
    r"(?i)(^|[_-])(authorization|bearer|token|api[_-]?key|secret|password|credential|sig|signature)([_-]|$)"
)
_BARE_TOKEN_PATTERNS = (
    re.compile(r"\bsk-(?:live|test)-[A-Za-z0-9]{8,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b"),
)
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[^\s&]+")

# An absolute path may contain interior spaces (``C:\Program Files\...``).
# Only a segment anchored by a following separator may contain one, and at most
# a single space: a space-free last segment would leave parent components such
# as ``Files\FEBuilder`` behind, while unlimited spaces would glue trailing
# prose ("...\hero.png into notes\drafts") onto the path. Quoted and
# flag-valued paths have an unambiguous end and are handled separately, so they
# do not need this restriction. Separators are matched one *or two* deep so
# JSON- and log-escaped output (``C:\\Users\\me``) is scrubbed as well.
_WINDOWS_TOKEN = r"[^\\/\s;:,)\"'<>|]+"
_WINDOWS_INNER_SEGMENT = rf"{_WINDOWS_TOKEN}(?: {_WINDOWS_TOKEN})?"
_WINDOWS_LAST_SEGMENT = _WINDOWS_TOKEN
_WINDOWS_SEPARATOR = r"[\\/]{1,2}"
_POSIX_TOKEN = r"[^/\s;:,)\"'<>|]+"
_POSIX_INNER_SEGMENT = rf"{_POSIX_TOKEN}(?: {_POSIX_TOKEN})?"
_POSIX_LAST_SEGMENT = _POSIX_TOKEN
_ABSOLUTE_PATH_START = r"(?:[A-Za-z]:[\\/]|\\{2,4}|/)"

_UNC_PATH_PATTERN = re.compile(
    rf"(?<![\w/])\\{{2,4}}(?:{_WINDOWS_INNER_SEGMENT}{_WINDOWS_SEPARATOR})+{_WINDOWS_LAST_SEGMENT}"
)
_WINDOWS_PATH_PATTERN = re.compile(
    rf"(?<![\w/])[A-Za-z]:{_WINDOWS_SEPARATOR}"
    rf"(?:{_WINDOWS_INNER_SEGMENT}{_WINDOWS_SEPARATOR})*(?:{_WINDOWS_LAST_SEGMENT})?"
)
_POSIX_PATH_PATTERN = re.compile(
    rf"(?<![A-Za-z0-9:/._-])/(?:{_POSIX_INNER_SEGMENT}/)*(?:{_POSIX_LAST_SEGMENT})?"
)
# Quoted and flag-valued paths have an unambiguous end, so the whole value --
# spaces included -- can be replaced by its final component.
_QUOTED_PATH_PATTERN = re.compile(rf"(['\"])({_ABSOLUTE_PATH_START}[^\r\n'\"]*)\1")
_FLAG_PATH_PATTERN = re.compile(
    rf"(?<![\w-])(-{{1,2}}[A-Za-z][\w-]*(?:[=:]|\s+))"
    rf"({_ABSOLUTE_PATH_START}(?:(?!\s+-{{1,2}}[A-Za-z])[^\r\n'\"])*)"
)


def _replace_windows_path(match: re.Match[str]) -> str:
    return _path_basename(match.group(0))


def _replace_posix_path(match: re.Match[str]) -> str:
    return _path_basename(match.group(0))


def _replace_quoted_path(match: re.Match[str]) -> str:
    quote = match.group(1)
    return f"{quote}{_path_basename(match.group(2))}{quote}"


def _replace_flag_path(match: re.Match[str]) -> str:
    return f"{match.group(1)}{_path_basename(match.group(2))}"


def _path_basename(value: str) -> str:
    posix_name = PurePosixPath(value.rstrip("\\/")).name
    return PureWindowsPath(posix_name).name


def _path_variants(value: str) -> tuple[str, ...]:
    """Spellings of one known path that can appear in captured output."""
    windows = value.replace("/", "\\")
    return (
        value,
        value.replace("\\", "/"),
        windows,
        windows.replace("\\", "\\\\"),
    )


def redact_paths(text: str, paths: Iterable[str | PurePath]) -> str:
    """Replace exactly these known paths with their final component.

    Generic path scrubbing is heuristic; the paths a caller *knows* it handed to
    an external process are not. Replacing them first guarantees that a
    configured executable path, a package directory, or an expected directory
    cannot survive redaction because of an unusual spelling (a space, a JSON- or
    log-escaped separator, or a mixed separator style).
    """
    redacted = text
    variants = {variant for path in paths for variant in _path_variants(str(path)) if variant}
    for variant in sorted(variants, key=len, reverse=True):
        redacted = redacted.replace(variant, _path_basename(variant))
    return redacted


def redact(text: str) -> str:
    redacted = _AUTH_BEARER_PATTERN.sub("authorization=***", text)
    redacted = _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=***", redacted)
    redacted = _BEARER_PATTERN.sub("******", redacted)
    for pattern in _BARE_TOKEN_PATTERNS:
        redacted = pattern.sub("***", redacted)
    redacted = _QUOTED_PATH_PATTERN.sub(_replace_quoted_path, redacted)
    redacted = _FLAG_PATH_PATTERN.sub(_replace_flag_path, redacted)
    redacted = _UNC_PATH_PATTERN.sub(_replace_windows_path, redacted)
    redacted = _WINDOWS_PATH_PATTERN.sub(_replace_windows_path, redacted)
    return _POSIX_PATH_PATTERN.sub(_replace_posix_path, redacted)


def contains_secret_key(key: str) -> bool:
    return _SECRET_KEY_PATTERN.search(key) is not None
