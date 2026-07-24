import numpy as np

from fecreator.imaging.color import from_lab, lab_distance, to_lab


def test_lab_roundtrip_is_close():
    rgb = np.array([[[10, 200, 60], [255, 0, 0]]], dtype=np.uint8)
    back = from_lab(to_lab(rgb))
    assert np.max(np.abs(back.astype(int) - rgb.astype(int))) <= 3


def test_lab_distance_zero_for_identical():
    lab = to_lab(np.full((2, 2, 3), 128, dtype=np.uint8))
    d = lab_distance(lab, lab)
    assert np.allclose(d, 0.0)
