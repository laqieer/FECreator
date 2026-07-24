from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from fecreator.contracts.lineage import Region


def palette_distance(a: np.ndarray, b: np.ndarray) -> float:
    a32 = a.astype(np.int32).reshape(-1, 3)
    b32 = b.astype(np.int32).reshape(-1, 3)
    dists = np.sqrt(np.sum((a32[:, None, :] - b32[None, :, :]) ** 2, axis=2))
    return float(dists.min(axis=1).mean())


def silhouette_iou(a_mask: np.ndarray, b_mask: np.ndarray) -> float:
    union = np.logical_or(a_mask, b_mask).sum()
    if union == 0:
        return 1.0
    return float(np.logical_and(a_mask, b_mask).sum() / union)


def masked_perceptual_diff(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float:
    if not mask.any():
        return 0.0
    diff = np.abs(a.astype(np.int32) - b.astype(np.int32)).mean(axis=2)
    return float(diff[mask].mean() / 255.0)


def protected_region_diff(a: np.ndarray, b: np.ndarray, regions: Sequence[Region]) -> float:
    worst = 0.0
    for r in regions:
        pa = a[r.y : r.y + r.h, r.x : r.x + r.w].astype(np.int32)
        pb = b[r.y : r.y + r.h, r.x : r.x + r.w].astype(np.int32)
        worst = max(worst, float(np.abs(pa - pb).mean() / 255.0))
    return worst
