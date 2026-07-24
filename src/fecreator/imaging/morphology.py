from __future__ import annotations

import cv2
import numpy as np


def _kernel(radius: int) -> np.ndarray:
    size = 2 * radius + 1
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))


def close_mask(mask: np.ndarray, radius: int = 1) -> np.ndarray:
    out = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, _kernel(radius))
    return out.astype(bool)  # type: ignore[no-any-return]


def open_mask(mask: np.ndarray, radius: int = 1) -> np.ndarray:
    out = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, _kernel(radius))
    return out.astype(bool)  # type: ignore[no-any-return]


def fill_holes(mask: np.ndarray) -> np.ndarray:
    inv = (~mask).astype(np.uint8)
    count, labels = cv2.connectedComponents(inv)
    border_labels = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
    filled = mask.copy()
    for label in range(1, count):
        if label not in border_labels:
            filled[labels == label] = True
    return filled


def connected_components(mask: np.ndarray) -> tuple[int, np.ndarray]:
    count, labels = cv2.connectedComponents(mask.astype(np.uint8))
    return count - 1, labels
