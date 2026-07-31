from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image


def assert_delivered_truecolor_background_png(content: bytes) -> None:
    with Image.open(BytesIO(content)) as image:
        assert image.mode == "RGB"
        assert image.size == (240, 160)
        assert "transparency" not in image.info
        assert np.unique(np.asarray(image).reshape(-1, 3), axis=0).shape[0] > 128


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
