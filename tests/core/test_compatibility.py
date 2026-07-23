from __future__ import annotations

import pytest

from fecreator.core.compatibility import (
    SUPPORTED_CONTRACT_VERSIONS,
    UnsupportedVersionError,
    check_supported,
)


def test_supported_passes() -> None:
    assert "1.0" in SUPPORTED_CONTRACT_VERSIONS

    check_supported("manifest", "1.0")


def test_unsupported_raises() -> None:
    with pytest.raises(UnsupportedVersionError):
        check_supported("manifest", "2.0")
