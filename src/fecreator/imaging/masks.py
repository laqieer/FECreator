from __future__ import annotations

import numpy as np

from fecreator.imaging.morphology import connected_components


def _require_3channel(rgb: np.ndarray, fn: str) -> None:
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"{fn}: expected (H, W, 3) 3-channel RGB array, got shape {rgb.shape}")


def chroma_key(rgb: np.ndarray, key_rgb: tuple[int, int, int], tol: int = 24) -> np.ndarray:
    _require_3channel(rgb, "chroma_key")
    diff = np.abs(rgb.astype(np.int16) - np.array(key_rgb, dtype=np.int16))
    return np.all(diff <= tol, axis=2)


def background_mask(rgb: np.ndarray, key_rgb: tuple[int, int, int], tol: int = 24) -> np.ndarray:
    _require_3channel(rgb, "background_mask")
    key = chroma_key(rgb, key_rgb, tol)
    _, labels = connected_components(key)
    border = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
    border.discard(0)
    return np.isin(labels, list(border))
