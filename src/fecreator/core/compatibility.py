from __future__ import annotations

SUPPORTED_CONTRACT_VERSIONS: frozenset[str] = frozenset({"1.0"})


class UnsupportedVersionError(Exception):
    """Raised when a contract version is not supported."""


def check_supported(kind: str, version: str) -> None:
    if version not in SUPPORTED_CONTRACT_VERSIONS:
        supported = ", ".join(sorted(SUPPORTED_CONTRACT_VERSIONS))
        raise UnsupportedVersionError(f"{kind} version {version} is not supported; expected one of: {supported}")
