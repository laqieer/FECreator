import numpy as np
import pytest

from fecreator.imaging.grid import GridEstimate, LowConfidenceGridError, detect_grid


def _blocky(cell: int) -> np.ndarray:
    base = np.random.default_rng(1).integers(0, 255, (8, 8, 3)).astype(np.uint8)
    return np.kron(base, np.ones((cell, cell, 1), dtype=np.uint8))


def test_detects_upscale_factor():
    est = detect_grid(_blocky(4))
    assert isinstance(est, GridEstimate)
    assert est.cell_w == 4 and est.cell_h == 4
    assert est.confidence >= 0.6


def test_low_confidence_raises_on_gradient():
    grad = np.tile(np.linspace(0, 255, 64, dtype=np.uint8).reshape(1, 64, 1), (64, 1, 3))
    with pytest.raises(LowConfidenceGridError):
        detect_grid(grad, min_confidence=0.9)


# --- M-1: grid origin always 0 (detection not implemented) ---

def test_grid_origin_always_zero():
    """Grid origin detection is not implemented; fields are documented as 0."""
    est = detect_grid(_blocky(4))
    assert est.origin_x == 0 and est.origin_y == 0


# --- M-2: non-RGB input rejected ---

def test_detect_grid_grayscale_raises():
    gray = np.zeros((8, 8), dtype=np.uint8)
    with pytest.raises(ValueError, match="channel"):
        detect_grid(gray)  # type: ignore[arg-type]


def test_detect_grid_rgba_raises():
    rgba = np.zeros((8, 8, 4), dtype=np.uint8)
    with pytest.raises(ValueError, match="channel"):
        detect_grid(rgba)
