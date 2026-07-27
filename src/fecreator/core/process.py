from __future__ import annotations

import os
from collections.abc import Mapping

from fecreator.core.redaction import redact

_COMMON_SAFE_ENV_KEYS = frozenset({"PATH", "PYTHONIOENCODING"})
_POSIX_SAFE_ENV_KEYS = frozenset(
    {"DYLD_LIBRARY_PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "LD_LIBRARY_PATH", "TMPDIR"}
)
_WINDOWS_SAFE_ENV_KEYS = frozenset(
    {"COMSPEC", "PATHEXT", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE", "WINDIR"}
)

TRUNCATION_SUFFIX = "... [truncated]"


def safe_subprocess_env(
    source_env: Mapping[str, str] | None = None,
    *,
    os_name: str | None = None,
) -> dict[str, str]:
    """Build the allowlisted environment handed to any external process.

    Only the keys required to start a process on the current platform are
    forwarded, so provider credentials and other ambient configuration never
    reach a third-party executable.
    """
    env_source = source_env or os.environ
    safe_env = {"PYTHONIOENCODING": env_source.get("PYTHONIOENCODING", "utf-8")}
    allowed = set(_COMMON_SAFE_ENV_KEYS)
    if (os_name or os.name) == "nt":
        allowed.update(_WINDOWS_SAFE_ENV_KEYS)
    else:
        allowed.update(_POSIX_SAFE_ENV_KEYS)

    for key in sorted(allowed):
        if key == "PYTHONIOENCODING":
            continue
        value = env_source.get(key)
        if value:
            safe_env[key] = value
    return safe_env


def bounded_redacted_text(text: str | None, limit: int) -> str:
    """Redact external output and bound it before it reaches any report."""
    if not text:
        return ""

    redacted = redact(text.strip())
    if len(redacted) <= limit:
        return redacted
    return f"{redacted[:limit]}{TRUNCATION_SUFFIX}"
