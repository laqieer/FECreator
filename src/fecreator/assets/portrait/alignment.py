from __future__ import annotations

import numpy as np

from fecreator.imaging.masks import background_mask
from fecreator.imaging.resize import ResizeMode, resize


def align_to_main(
    rgb: np.ndarray,
    bg_rgb: tuple[int, int, int],
    size: tuple[int, int] = (96, 80),
) -> np.ndarray:
    width, height = size
    canvas = np.full((height, width, 3), bg_rgb, dtype=np.uint8)
    foreground = ~background_mask(rgb, bg_rgb)
    ys, xs = np.nonzero(foreground)
    if ys.size == 0:
        return canvas
    crop = rgb[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    crop_h, crop_w = crop.shape[:2]
    scale = min(width / crop_w, height / crop_h)
    new_w = max(1, int(round(crop_w * scale)))
    new_h = max(1, int(round(crop_h * scale)))
    fitted = resize(crop, (new_w, new_h), ResizeMode.ILLUSTRATION_FIT)
    off_x = (width - new_w) // 2
    off_y = (height - new_h) // 2
    canvas[off_y : off_y + new_h, off_x : off_x + new_w] = fitted
    return canvas
