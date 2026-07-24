from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from fecreator.contracts.lineage import Region


def palette_distance(a: np.ndarray, b: np.ndarray) -> float:
    a32 = a.astype(np.int32).reshape(-1, 3)
    b32 = b.astype(np.int32).reshape(-1, 3)
    if len(a32) == 0 or len(b32) == 0:
        raise ValueError("palette must not be empty")
    dists = np.sqrt(np.sum((a32[:, None, :] - b32[None, :, :]) ** 2, axis=2))
    return float(dists.min(axis=1).mean())


def silhouette_iou(a_mask: np.ndarray, b_mask: np.ndarray) -> float:
    if a_mask.shape != b_mask.shape:
        raise ValueError(f"mask shape mismatch: {a_mask.shape} vs {b_mask.shape}")
    union = np.logical_or(a_mask, b_mask).sum()
    if union == 0:
        return 1.0
    return float(np.logical_and(a_mask, b_mask).sum() / union)


def masked_perceptual_diff(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float:
    if a.shape != b.shape:
        raise ValueError(f"image shape mismatch: {a.shape} vs {b.shape}")
    if not mask.any():
        return 0.0
    diff = np.abs(a.astype(np.int32) - b.astype(np.int32)).mean(axis=2)
    return float(diff[mask].mean() / 255.0)


def _validate_region(r: Region, h: int, w: int) -> None:
    """Raise ValueError if region is fully or partially outside (h, w) bounds."""
    if r.x >= w or r.y >= h or r.x + r.w > w or r.y + r.h > h:
        raise ValueError(
            f"region ({r.x},{r.y},{r.w},{r.h}) is out-of-bounds for image ({h},{w})"
        )


def protected_region_diff(a: np.ndarray, b: np.ndarray, regions: Sequence[Region]) -> float:
    if a.shape != b.shape:
        raise ValueError(f"image shape mismatch: {a.shape} vs {b.shape}")
    h, w = a.shape[:2]
    worst = 0.0
    for r in regions:
        _validate_region(r, h, w)
        pa = a[r.y : r.y + r.h, r.x : r.x + r.w].astype(np.int32)
        pb = b[r.y : r.y + r.h, r.x : r.x + r.w].astype(np.int32)
        worst = max(worst, float(np.abs(pa - pb).mean() / 255.0))
    return worst
