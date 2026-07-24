from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def save_png(path: Path, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb, "RGB").save(path)
