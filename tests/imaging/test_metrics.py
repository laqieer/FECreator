import numpy as np
import pytest

from fecreator.contracts.lineage import Region
from fecreator.imaging.metrics import (
    masked_perceptual_diff,
    palette_distance,
    protected_region_diff,
    silhouette_iou,
)


def test_silhouette_iou_extremes():
    a = np.zeros((4, 4), dtype=bool)
    a[0:2, 0:2] = True
    assert silhouette_iou(a, a) == 1.0
    b = np.zeros((4, 4), dtype=bool)
    b[2:, 2:] = True
    assert silhouette_iou(a, b) == 0.0


def test_palette_distance_zero_for_identical():
    pal = np.array([(0, 0, 0), (255, 255, 255)], dtype=np.uint8)
    assert palette_distance(pal, pal) == 0.0


def test_masked_diff_zero_for_identical():
    img = np.full((4, 4, 3), 100, dtype=np.uint8)
    mask = np.ones((4, 4), dtype=bool)
    assert masked_perceptual_diff(img, img, mask) == 0.0


def test_protected_region_diff_detects_change():
    a = np.zeros((8, 8, 3), dtype=np.uint8)
    b = a.copy()
    b[0:2, 0:2] = 255
    regions = (Region(x=0, y=0, w=2, h=2, label="eye"),)
    assert protected_region_diff(a, b, regions) > 0.0
    assert protected_region_diff(a, a, regions) == 0.0


# --- I-6: shape validation, out-of-bounds regions ---


def test_protected_region_diff_mismatched_shapes_raises():
    a = np.zeros((8, 8, 3), dtype=np.uint8)
    b = np.zeros((4, 8, 3), dtype=np.uint8)
    regions = (Region(x=0, y=0, w=2, h=2, label="eye"),)
    with pytest.raises(ValueError, match="shape"):
        protected_region_diff(a, b, regions)


def test_protected_region_diff_fully_oob_region_raises():
    """Fully out-of-bounds region should raise rather than return NaN."""
    a = np.zeros((4, 4, 3), dtype=np.uint8)
    regions = (Region(x=10, y=10, w=2, h=2, label="eye"),)
    with pytest.raises(ValueError, match="out.of.bounds"):
        protected_region_diff(a, a, regions)


def test_protected_region_diff_partially_oob_region_raises():
    """Partially out-of-bounds region should raise (not silently clip)."""
    a = np.zeros((4, 4, 3), dtype=np.uint8)
    regions = (Region(x=3, y=3, w=4, h=4, label="eye"),)
    with pytest.raises(ValueError, match="out.of.bounds"):
        protected_region_diff(a, a, regions)


def test_protected_region_diff_no_nan():
    """Result must never be NaN for valid in-bounds regions."""
    a = np.zeros((4, 4, 3), dtype=np.uint8)
    b = np.full((4, 4, 3), 255, dtype=np.uint8)
    regions = (Region(x=0, y=0, w=4, h=4, label="all"),)
    result = protected_region_diff(a, b, regions)
    assert result == result  # NaN guard: float('nan') == float('nan') is False


# --- M-3: empty palettes / mismatched shapes ---


def test_palette_distance_empty_a_raises():
    a = np.zeros((0, 3), dtype=np.uint8)
    b = np.array([(0, 0, 0)], dtype=np.uint8)
    with pytest.raises(ValueError, match="empty"):
        palette_distance(a, b)


def test_palette_distance_empty_b_raises():
    a = np.array([(0, 0, 0)], dtype=np.uint8)
    b = np.zeros((0, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="empty"):
        palette_distance(a, b)


def test_silhouette_iou_mismatched_shapes_raises():
    a = np.zeros((4, 4), dtype=bool)
    b = np.zeros((4, 6), dtype=bool)
    with pytest.raises(ValueError, match="shape"):
        silhouette_iou(a, b)


def test_masked_perceptual_diff_mismatched_shapes_raises():
    a = np.zeros((4, 4, 3), dtype=np.uint8)
    b = np.zeros((4, 6, 3), dtype=np.uint8)
    mask = np.ones((4, 4), dtype=bool)
    with pytest.raises(ValueError, match="shape"):
        masked_perceptual_diff(a, b, mask)
