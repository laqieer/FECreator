from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    return root
