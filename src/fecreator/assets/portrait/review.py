from __future__ import annotations

from pydantic import BaseModel

from fecreator.contracts.diagnostics import Diagnostic, error


class ReviewThresholds(BaseModel):
    identity_min: float = 0.85
    silhouette_min: float = 0.90
    protected_max: float = 0.02
    palette_max: float = 20.0


_DEFAULT_THRESHOLDS = ReviewThresholds()


def review_gate(
    metrics: dict[str, float],
    thresholds: ReviewThresholds = _DEFAULT_THRESHOLDS,
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    if metrics.get("identity", 0.0) < thresholds.identity_min:
        diags.append(error("IDENTITY_BELOW_THRESHOLD", "identity similarity too low"))
    if metrics.get("silhouette", 0.0) < thresholds.silhouette_min:
        diags.append(error("SILHOUETTE_BELOW_THRESHOLD", "silhouette IoU too low"))
    if metrics.get("protected_diff", 1.0) > thresholds.protected_max:
        diags.append(error("PROTECTED_DIFF_TOO_HIGH", "protected-region difference too high"))
    if metrics.get("palette_distance", 1e9) > thresholds.palette_max:
        diags.append(error("PALETTE_DISTANCE_TOO_HIGH", "palette distance too high"))
    return diags
