from __future__ import annotations

import re
from pathlib import PurePosixPath, PureWindowsPath

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
_UNC_PATH_PATTERN = re.compile(
    r"(?<![\w/])(?:\\\\[^\\\s;:,)\"'<>|]+\\[^\\\s;:,)\"'<>|]+(?:\\[^\\\s;:,)\"'<>|]+)*)"
)
_WINDOWS_PATH_PATTERN = re.compile(
    r"(?<![\w/])(?:[A-Za-z]:\\(?:[^\\\s;:,)\"'<>|]+\\)*[^\\\s;:,)\"'<>|]+)"
)
_POSIX_PATH_PATTERN = re.compile(r"(?<![A-Za-z0-9:/._-])/(?:[^/\s;:,)\"']+/)*[^/\s;:,)\"']+")
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[^\s&]+")


def _replace_windows_path(match: re.Match[str]) -> str:
    return PureWindowsPath(match.group(0)).name


def _replace_posix_path(match: re.Match[str]) -> str:
    return PurePosixPath(match.group(0)).name


def redact(text: str) -> str:
    redacted = _AUTH_BEARER_PATTERN.sub("authorization=***", text)
    redacted = _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=***", redacted)
    redacted = _BEARER_PATTERN.sub("******", redacted)
    for pattern in _BARE_TOKEN_PATTERNS:
        redacted = pattern.sub("***", redacted)
    redacted = _UNC_PATH_PATTERN.sub(_replace_windows_path, redacted)
    redacted = _WINDOWS_PATH_PATTERN.sub(_replace_windows_path, redacted)
    return _POSIX_PATH_PATTERN.sub(_replace_posix_path, redacted)


def contains_secret_key(key: str) -> bool:
    return _SECRET_KEY_PATTERN.search(key) is not None
