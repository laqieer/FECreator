import numpy as np

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
