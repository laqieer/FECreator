from __future__ import annotations

from enum import StrEnum

import cv2
import numpy as np


class ResizeMode(StrEnum):
    ILLUSTRATION_FIT = "illustration_fit"
    PIXEL_PRESERVE = "pixel_preserve"
    PSEUDO_PIXEL_GRID = "pseudo_pixel_grid"
    MANUAL_GRID = "manual_grid"


def _fit(rgb: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    target_w, target_h = size
    shrinking = target_w * target_h < rgb.shape[1] * rgb.shape[0]
    interp = cv2.INTER_AREA if shrinking else cv2.INTER_LANCZOS4
    return cv2.resize(rgb, (target_w, target_h), interpolation=interp)


def resize(
    rgb: np.ndarray, size: tuple[int, int], mode: ResizeMode, grid: object | None = None
) -> np.ndarray:
    if not isinstance(mode, ResizeMode):
        raise ValueError(f"unknown resize mode: {mode!r}")
    if mode is ResizeMode.PIXEL_PRESERVE:
        return cv2.resize(rgb, size, interpolation=cv2.INTER_NEAREST)
    return _fit(rgb, size).astype(np.uint8)
