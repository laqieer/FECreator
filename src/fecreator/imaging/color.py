from __future__ import annotations

import cv2
import numpy as np


def to_lab(rgb: np.ndarray) -> np.ndarray:
    rgb32 = rgb.astype(np.float32) / 255.0
    return cv2.cvtColor(rgb32, cv2.COLOR_RGB2LAB).astype(np.float32)


def from_lab(lab: np.ndarray) -> np.ndarray:
    rgb32 = cv2.cvtColor(lab.astype(np.float32), cv2.COLOR_LAB2RGB)
    return np.clip(np.round(rgb32 * 255.0), 0, 255).astype(np.uint8)


def lab_distance(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.sqrt(np.sum((a.astype(np.float32) - b.astype(np.float32)) ** 2, axis=-1))
