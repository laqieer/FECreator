from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np


def map_to_palette(rgb: np.ndarray, palette: np.ndarray) -> np.ndarray:
    flat = rgb.reshape(-1, 3).astype(np.int32)
    pal = palette.astype(np.int32)
    dists = np.sum((flat[:, None, :] - pal[None, :, :]) ** 2, axis=2)
    return dists.argmin(axis=1).astype(np.uint8).reshape(rgb.shape[:2])


def _finalize(
    rgb: np.ndarray, palette: np.ndarray, locked: Sequence[tuple[int, int, int]]
) -> tuple[np.ndarray, np.ndarray]:
    for color in locked:
        if not any(np.array_equal(entry, color) for entry in palette):
            palette = np.vstack([np.array(locked, dtype=np.uint8), palette])
            break
    _, unique = np.unique(palette, axis=0, return_index=True)
    palette = palette[np.sort(unique)]
    return map_to_palette(rgb, palette), palette


def quantize_kmeans_lab(
    rgb: np.ndarray, k: int, locked: Sequence[tuple[int, int, int]] = (), seed: int = 0
) -> tuple[np.ndarray, np.ndarray]:
    cv2.setRNGSeed(seed)
    rgb32 = rgb.astype(np.float32) / 255.0
    lab = cv2.cvtColor(rgb32, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(  # type: ignore[call-overload]
        lab, k, None, criteria, 1, cv2.KMEANS_PP_CENTERS
    )
    # Convert centers back to RGB via float32 LAB
    centers_lab = centers.reshape(-1, 1, 3).astype(np.float32)
    rgb32_centers = cv2.cvtColor(centers_lab, cv2.COLOR_LAB2RGB)
    palette = np.clip(np.round(rgb32_centers.reshape(-1, 3) * 255.0), 0, 255).astype(np.uint8)
    return _finalize(rgb, palette, locked)


def quantize_median_cut(
    rgb: np.ndarray,
    k: int,
    locked: Sequence[tuple[int, int, int]] = (),
) -> tuple[np.ndarray, np.ndarray]:
    boxes = [rgb.reshape(-1, 3).astype(np.int32)]
    while len(boxes) < k:
        boxes.sort(
            key=lambda b: int((b.max(axis=0) - b.min(axis=0)).max()) if len(b) else 0,
            reverse=True,
        )
        biggest = boxes.pop(0)
        axis = int((biggest.max(axis=0) - biggest.min(axis=0)).argmax())
        order = biggest[biggest[:, axis].argsort()]
        mid = len(order) // 2
        boxes.extend([order[:mid], order[mid:]])
        boxes = [b for b in boxes if len(b)]
    palette = np.array([b[len(b) // 2] for b in boxes], dtype=np.uint8)
    return _finalize(rgb, palette, locked)
