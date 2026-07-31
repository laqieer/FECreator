from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image


@pytest.fixture
def truecolor_background_sources(tmp_path: Path) -> Path:
    sources = tmp_path / "sources"
    sources.mkdir()
    y, x = np.indices((160, 240), dtype=np.uint16)
    rgb = np.stack(
        (x % 256, y % 256, (x * 17 + y * 29) % 256),
        axis=2,
    ).astype(np.uint8)
    Image.fromarray(rgb, "RGB").save(sources / "phantom_city.png")
    return sources
