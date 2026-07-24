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
    """Apply edits from *edited_rgb* only inside *mask*.

    *mask* must be a bool array with shape matching image H×W exactly.
    Non-bool dtype or shape mismatch raises ``ValueError`` immediately
    rather than broadcasting silently.
    """
    if mask.dtype != np.dtype(bool):
        raise ValueError(
            f"mask must have bool dtype, got {mask.dtype!r}; "
            "cast with mask.astype(bool) if intentional"
        )
    expected_hw = base_rgb.shape[:2]
    if mask.shape != expected_hw:
        raise ValueError(f"mask shape {mask.shape} does not match image H×W {expected_hw}")
    return np.where(mask[:, :, None], edited_rgb, base_rgb).astype(np.uint8)


def check_protected_regions(
    base_rgb: np.ndarray,
    result_rgb: np.ndarray,
    regions: Sequence[Region],
    tol: float = 0.02,
) -> list[Diagnostic]:
    """Check each protected region for unwanted changes.

    Out-of-bounds regions produce a ``REGION_OUT_OF_BOUNDS`` diagnostic
    rather than raising an uncaught ``ValueError``.
    """
    diags: list[Diagnostic] = []
    h, w = base_rgb.shape[:2]
    for region in regions:
        try:
            diff = protected_region_diff(base_rgb, result_rgb, [region])
        except ValueError:
            diags.append(
                error(
                    "REGION_OUT_OF_BOUNDS",
                    f"protected region {region.label!r} is out of bounds for {h}×{w} image",
                    where=region.label,
                )
            )
            continue
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
