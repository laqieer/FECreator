from __future__ import annotations

from pathlib import Path

import pytest

pytest_plugins = ("tests.fixtures.dialogue_background",)


@pytest.fixture()
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    return root
