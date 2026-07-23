from pathlib import Path

import pytest

from fecreator.core.paths import PathEscapeError, safe_join


@pytest.mark.parametrize("evil", ["../secret", "a/../../secret", "sub/../../..", "C:/Windows"])
def test_workspace_paths_cannot_escape(tmp_path: Path, evil: str) -> None:
    with pytest.raises(PathEscapeError):
        safe_join(tmp_path, *evil.split("/"))
