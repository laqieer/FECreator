from __future__ import annotations

import threading
from collections.abc import Sequence

import cv2
import numpy as np

# Protect the process-global cv2 RNG from concurrent access.
_KMEANS_LOCK = threading.Lock()


class QuantizeError(ValueError):
    """Raised on invalid quantization parameters."""


def _validate_inputs(rgb: np.ndarray, k: int) -> int:
    n_pixels = rgb.shape[0] * rgb.shape[1] if rgb.ndim >= 2 else 0
    if n_pixels == 0:
        raise QuantizeError("image has no pixels")
    if k < 1:
        raise QuantizeError(f"k must be >= 1, got {k}")
    if k > n_pixels:
        raise QuantizeError(f"k ({k}) exceeds pixel count ({n_pixels})")
    return n_pixels


def map_to_palette(rgb: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """Assign each pixel to its nearest palette entry.

    Iterates over palette entries one at a time (O(N×P) time, O(N) peak
    memory) so peak allocation is bounded regardless of palette or image
    size.  Ties break toward the lower-index entry (strict ``<`` comparison).
    Returns an int32 array shaped (H, W).
    """
    flat = rgb.reshape(-1, 3).astype(np.int32)
    n = len(flat)
    pal = palette.astype(np.int32)
    best_dist = np.full(n, np.iinfo(np.int64).max, dtype=np.int64)
    best_idx = np.zeros(n, dtype=np.int32)
    for pi in range(len(pal)):
        diff = flat - pal[pi]  # (N, 3) int32
        d = np.einsum("ij,ij->i", diff, diff).astype(np.int64)
        mask = d < best_dist  # strict < → lower index wins on tie
        best_dist = np.where(mask, d, best_dist)
        best_idx = np.where(mask, pi, best_idx)
    return best_idx.astype(np.int32).reshape(rgb.shape[:2])


def _finalize(
    rgb: np.ndarray,
    palette: np.ndarray,
    locked: Sequence[tuple[int, int, int]],
    k: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Insert locked colours, dedup, validate, then trim to exactly k entries."""
    if locked:
        # Count unique locked colours *before* merging — determines minimum palette size.
        # Use explicit (r, g, b) construction so Python ints are used for hashing.
        locked_set: set[tuple[int, int, int]] = {(int(c[0]), int(c[1]), int(c[2])) for c in locked}
        if len(locked_set) > k:
            raise QuantizeError(
                f"{len(locked_set)} unique locked colours exceed k={k}; "
                "cannot satisfy all locked-colour constraints"
            )
        locked_arr = np.array(list(locked_set), dtype=np.uint8)
        palette = np.vstack([locked_arr, palette])
    # Stable dedup: keep first occurrence of each unique row
    _, unique = np.unique(palette, axis=0, return_index=True)
    palette = palette[np.sort(unique)]
    # Trim to k entries (locked colours were prepended, so they survive)
    palette = palette[:k]
    return map_to_palette(rgb, palette), palette


def quantize_kmeans_lab(
    rgb: np.ndarray,
    k: int,
    locked: Sequence[tuple[int, int, int]] = (),
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    _validate_inputs(rgb, k)
    rgb32 = rgb.astype(np.float32) / 255.0
    lab = cv2.cvtColor(rgb32, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    with _KMEANS_LOCK:
        cv2.setRNGSeed(seed)
        _, _labels, centers = cv2.kmeans(  # type: ignore[call-overload]
            lab, k, None, criteria, 1, cv2.KMEANS_PP_CENTERS
        )
    centers_lab = centers.reshape(-1, 1, 3).astype(np.float32)
    rgb32_centers = cv2.cvtColor(centers_lab, cv2.COLOR_LAB2RGB)
    palette = np.clip(np.round(rgb32_centers.reshape(-1, 3) * 255.0), 0, 255).astype(np.uint8)
    return _finalize(rgb, palette, locked, k)


def quantize_median_cut(
    rgb: np.ndarray,
    k: int,
    locked: Sequence[tuple[int, int, int]] = (),
) -> tuple[np.ndarray, np.ndarray]:
    _validate_inputs(rgb, k)
    boxes: list[np.ndarray] = [rgb.reshape(-1, 3).astype(np.int32)]
    max_iters = k * 2 + 1  # defensive upper bound
    iters = 0
    while len(boxes) < k and iters < max_iters:
        iters += 1
        # Sort so the widest-range splittable box is first
        boxes.sort(
            key=lambda b: int((b.max(axis=0) - b.min(axis=0)).max()) if len(b) > 1 else 0,
            reverse=True,
        )
        if len(boxes[0]) <= 1:
            break  # no splittable box remains
        biggest = boxes.pop(0)
        axis = int((biggest.max(axis=0) - biggest.min(axis=0)).argmax())
        order = biggest[biggest[:, axis].argsort()]
        mid = max(1, len(order) // 2)
        boxes.extend([order[:mid], order[mid:]])
        boxes = [b for b in boxes if len(b)]
    palette = np.array([b[len(b) // 2] for b in boxes], dtype=np.uint8)
    return _finalize(rgb, palette, locked, k)
