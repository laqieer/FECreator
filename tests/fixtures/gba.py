from __future__ import annotations

from pathlib import Path

import numpy as np

from fecreator.imaging.io import save_indexed_png
from fecreator.specs.fire_emblem.gba.portrait_standard.layout import BACKGROUND_ZONES
from fecreator.specs.fire_emblem.gba.portrait_standard.palette import write_jasc

# index 0 = green background, index 1 = foreground
PALETTE: list[tuple[int, int, int]] = [(0, 248, 0), (80, 96, 200)]


def build_indices() -> np.ndarray:
    idx = np.ones((112, 128), dtype=np.uint8)  # foreground everywhere
    for zone in BACKGROUND_ZONES:  # required background zones -> 0
        idx[zone.y : zone.y + zone.h, zone.x : zone.x + zone.w] = 0
    idx[0, :] = 0  # a border ring of background
    idx[-1, :] = 0
    idx[:, 0] = 0
    idx[:, -1] = 0
    return idx


def write_valid_package(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    save_indexed_png(directory / "hero.png", build_indices(), np.array(PALETTE, dtype=np.uint8))
    write_jasc(directory / "hero.pal", PALETTE)
