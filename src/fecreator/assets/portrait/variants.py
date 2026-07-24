from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from fecreator.contracts.diagnostics import Diagnostic, error
from fecreator.contracts.lineage import Region
from fecreator.imaging.metrics import protected_region_diff


def apply_masked_edit(
    base_rgb: np.ndarray,
    edited_rgb: np.ndarray,
    mask: np.ndarray,
) -> np.ndarray:
    return np.where(mask[:, :, None], edited_rgb, base_rgb).astype(np.uint8)


def check_protected_regions(
    base_rgb: np.ndarray,
    result_rgb: np.ndarray,
    regions: Sequence[Region],
    tol: float = 0.02,
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    for region in regions:
        diff = protected_region_diff(base_rgb, result_rgb, [region])
        if diff > tol:
            diags.append(
                error(
                    "PROTECTED_REGION_CHANGED",
                    f"protected region {region.label!r} changed by {diff:.3f}",
                    where=region.label,
                )
            )
    return diags


def build_variant(
    base_rgb: np.ndarray,
    edited_rgb: np.ndarray,
    mask: np.ndarray,
    protected_regions: Sequence[Region],
    tol: float = 0.02,
) -> tuple[np.ndarray, list[Diagnostic]]:
    result = apply_masked_edit(base_rgb, edited_rgb, mask)
    return result, check_protected_regions(base_rgb, result, protected_regions, tol)
