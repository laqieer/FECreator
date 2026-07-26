from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import PurePosixPath, PureWindowsPath
from typing import TypeAlias, cast

from fecreator.core.redaction import contains_secret_key, redact

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

_PATH_KEYS = frozenset({"mask", "mask_path", "path", "where"})

OPAQUE_BASE64_KEYS = frozenset({"content_base64"})
"""Keys whose values are opaque base64 transport payloads, never diagnostic text.

Redaction rewrites ``/`` inside path-like substrings, which corrupts valid base64.
Callers opt in explicitly, and only after the underlying file path and access have
already been validated by the domain layer.
"""

_BASE64_PATTERN = re.compile(r"\A(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?\Z")


def _looks_absolute_path(value: str) -> bool:
    return PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute()


def _safe_path_display(value: str) -> str:
    windows_name = PureWindowsPath(value).name
    posix_name = PurePosixPath(value).name
    return windows_name or posix_name or value


def sanitize_text(value: str) -> str:
    return redact(value)


def sanitize_path(value: str) -> str:
    redacted = redact(value)
    if _looks_absolute_path(value):
        return _safe_path_display(redacted)
    if "\\" in redacted:
        return PureWindowsPath(redacted).as_posix()
    if "/" in redacted:
        return PurePosixPath(redacted).as_posix()
    return redacted


def sanitize_json(
    value: object,
    *,
    error_cls: type[Exception],
    key: str | None = None,
    opaque_keys: frozenset[str] = frozenset(),
) -> JsonValue:
    if isinstance(value, Mapping):
        sanitized: JsonObject = {}
        for child_key in sorted(value):
            if contains_secret_key(child_key):
                raise error_cls(
                    f"credential-like key is not allowed in report payload: {child_key}"
                )
            sanitized[child_key] = sanitize_json(
                value[child_key],
                error_cls=error_cls,
                key=child_key,
                opaque_keys=opaque_keys,
            )
        return sanitized
    if isinstance(value, tuple | list):
        return [
            sanitize_json(item, error_cls=error_cls, key=key, opaque_keys=opaque_keys)
            for item in value
        ]
    if isinstance(value, str):
        if key is not None and key in opaque_keys:
            return _opaque_base64(value, key=key, error_cls=error_cls)
        if key in _PATH_KEYS:
            return sanitize_path(value)
        return sanitize_text(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    raise error_cls(f"unsupported report value: {type(value)!r}")


def _opaque_base64(value: str, *, key: str, error_cls: type[Exception]) -> str:
    if _BASE64_PATTERN.fullmatch(value) is None:
        raise error_cls(f"opaque transport field is not base64 text: {key}")
    return value


def as_object(value: JsonValue) -> JsonObject:
    return cast(JsonObject, value)
