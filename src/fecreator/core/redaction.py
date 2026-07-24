from __future__ import annotations

import re

_AUTH_BEARER_PATTERN = re.compile(r"(?i)\bauthorization\b\s*[:=]\s*Bearer\s+[^\s&]+")
SECRET_PATTERN = re.compile(
    r"(?i)\b(authorization|bearer|token|api[_-]?key|secret|password|credential|sig|signature)"
    r"\b\s*[:=]\s*([^\s&]+)"
)
_SECRET_KEY_PATTERN = re.compile(
    r"(?i)(^|[_-])(authorization|bearer|token|api[_-]?key|secret|password|credential|sig|signature)([_-]|$)"
)


def redact(text: str) -> str:
    redacted = _AUTH_BEARER_PATTERN.sub("authorization=***", text)
    redacted = SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=***", redacted)
    return re.sub(r"(?i)\bBearer\s+[^\s&]+", "Bearer ***", redacted)


def contains_secret_key(key: str) -> bool:
    return _SECRET_KEY_PATTERN.search(key) is not None
