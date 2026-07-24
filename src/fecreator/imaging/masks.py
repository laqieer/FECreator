from __future__ import annotations

import numpy as np

from fecreator.imaging.morphology import connected_components


def chroma_key(rgb: np.ndarray, key_rgb: tuple[int, int, int], tol: int = 24) -> np.ndarray:
    diff = np.abs(rgb.astype(np.int16) - np.array(key_rgb, dtype=np.int16))
    return np.all(diff <= tol, axis=2)


def background_mask(rgb: np.ndarray, key_rgb: tuple[int, int, int], tol: int = 24) -> np.ndarray:
    key = chroma_key(rgb, key_rgb, tol)
    _, labels = connected_components(key)
    border = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
    border.discard(0)
    return np.isin(labels, list(border))
