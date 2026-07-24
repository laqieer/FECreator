from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from fecreator.contracts.diagnostics import Diagnostic, error
from fecreator.contracts.lineage import Region
from fecreator.imaging.metrics import protected_region_diff


def _is_in_bounds(region: Region, h: int, w: int) -> bool:
    """True when *region* lies entirely within the (h, w) image dimensions."""
    return region.x < w and region.y < h and region.x + region.w <= w and region.y + region.h <= h


def apply_masked_edit(
    base_rgb: np.ndarray,
    edited_rgb: np.ndarray,
    mask: np.ndarray,
) -> np.ndarray:
    """Apply edits from *edited_rgb* only inside *mask*.

    *mask* must be a bool array with shape matching image H×W exactly.
    *edited_rgb* must have the same shape as *base_rgb*.
    Non-bool dtype, shape mismatch, or image-shape mismatch raises
    ``ValueError`` immediately rather than broadcasting silently.
    """
    if mask.dtype != np.dtype(bool):
        raise ValueError(
            f"mask must have bool dtype, got {mask.dtype!r}; "
            "cast with mask.astype(bool) if intentional"
        )
    expected_hw = base_rgb.shape[:2]
    if mask.shape != expected_hw:
        raise ValueError(f"mask shape {mask.shape} does not match image H×W {expected_hw}")
    if edited_rgb.shape != base_rgb.shape:
        raise ValueError(
            f"edited_rgb shape {edited_rgb.shape} does not match base_rgb shape {base_rgb.shape}"
        )
    return np.where(mask[:, :, None], edited_rgb, base_rgb).astype(np.uint8)


def check_protected_regions(
    base_rgb: np.ndarray,
    result_rgb: np.ndarray,
    regions: Sequence[Region],
    tol: float = 0.02,
) -> list[Diagnostic]:
    """Check each protected region for unwanted changes.

    Out-of-bounds regions are detected by a pre-validation check and produce
    a ``REGION_OUT_OF_BOUNDS`` diagnostic.  Any other error from
    ``protected_region_diff`` (e.g. image-shape mismatch) is allowed to
    propagate so it is not silently masked as a region diagnostic.
    """
    diags: list[Diagnostic] = []
    h, w = base_rgb.shape[:2]
    for region in regions:
        if not _is_in_bounds(region, h, w):
            diags.append(
                error(
                    "REGION_OUT_OF_BOUNDS",
                    f"protected region {region.label!r} is out of bounds for {h}×{w} image",
                    where=region.label,
                )
            )
            continue
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
