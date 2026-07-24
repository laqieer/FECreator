from __future__ import annotations

import math

from pydantic import BaseModel

from fecreator.contracts.diagnostics import Diagnostic, error


class ReviewThresholds(BaseModel):
    identity_min: float = 0.85
    silhouette_min: float = 0.90
    protected_max: float = 0.02
    palette_max: float = 20.0


_DEFAULT_THRESHOLDS = ReviewThresholds()


def _finite_or_worst(value: float, worst: float) -> float:
    """Return *value* if finite; otherwise return *worst* (fail-closed)."""
    return value if math.isfinite(value) else worst


def review_gate(
    metrics: dict[str, float],
    thresholds: ReviewThresholds = _DEFAULT_THRESHOLDS,
) -> list[Diagnostic]:
    """Check the four numeric quality metrics against thresholds.

    Missing metrics are treated as worst-case (fail closed). Non-finite
    values (NaN, +inf, -inf) are also treated as worst-case regardless of
    sign, because non-finite inputs indicate a measurement failure.

    NOTE: Required-expression completeness, provenance acceptance, and
    human approval are orchestration gates enforced in Tasks 8–9; this
    gate checks only the four numeric metrics listed below.
    """
    diags: list[Diagnostic] = []

    identity = _finite_or_worst(metrics.get("identity", 0.0), 0.0)
    silhouette = _finite_or_worst(metrics.get("silhouette", 0.0), 0.0)
    protected_diff = _finite_or_worst(metrics.get("protected_diff", 1.0), 1.0)
    palette_distance = _finite_or_worst(metrics.get("palette_distance", 1e9), 1e9)

    if identity < thresholds.identity_min:
        diags.append(error("IDENTITY_BELOW_THRESHOLD", "identity similarity too low"))
    if silhouette < thresholds.silhouette_min:
        diags.append(error("SILHOUETTE_BELOW_THRESHOLD", "silhouette IoU too low"))
    if protected_diff > thresholds.protected_max:
        diags.append(error("PROTECTED_DIFF_TOO_HIGH", "protected-region difference too high"))
    if palette_distance > thresholds.palette_max:
        diags.append(error("PALETTE_DISTANCE_TOO_HIGH", "palette distance too high"))

    return diags
