from __future__ import annotations

import numpy as np
from pydantic import BaseModel


class GridEstimate(BaseModel):
    cell_w: int
    cell_h: int
    origin_x: int
    origin_y: int
    confidence: float


class LowConfidenceGridError(Exception):
    """Raised when grid periodicity cannot be detected confidently."""


def _axis_period(gray: np.ndarray, axis: int) -> tuple[int, float]:
    diff = np.abs(np.diff(gray.astype(np.int16), axis=axis))
    edges = diff.mean(axis=1 - axis)
    boundaries = np.flatnonzero(edges > edges.mean() + edges.std())
    if boundaries.size < 2:
        return 1, 0.0
    gaps = np.diff(boundaries)
    period = int(np.median(gaps))
    confidence = float(np.mean(gaps == period)) if period > 1 else 0.0
    return max(period, 1), confidence


def detect_grid(rgb: np.ndarray, min_confidence: float = 0.6) -> GridEstimate:
    gray = rgb.mean(axis=2)
    cell_w, conf_w = _axis_period(gray, axis=1)
    cell_h, conf_h = _axis_period(gray, axis=0)
    confidence = min(conf_w, conf_h)
    if confidence < min_confidence:
        raise LowConfidenceGridError(f"grid confidence {confidence:.2f} < {min_confidence}")
    return GridEstimate(cell_w=cell_w, cell_h=cell_h, origin_x=0, origin_y=0, confidence=confidence)
