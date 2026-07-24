import numpy as np

from fecreator.imaging.quantize import map_to_palette, quantize_kmeans_lab, quantize_median_cut


def _three_color_image() -> np.ndarray:
    img = np.zeros((6, 6, 3), dtype=np.uint8)
    img[:2] = (200, 0, 0)
    img[2:4] = (0, 200, 0)
    img[4:] = (0, 0, 200)
    return img


def test_kmeans_is_deterministic_for_seed():
    img = _three_color_image()
    _, pal_a = quantize_kmeans_lab(img, 3, seed=7)
    _, pal_b = quantize_kmeans_lab(img, 3, seed=7)
    assert np.array_equal(pal_a, pal_b)


def test_median_cut_uses_real_source_colors():
    img = _three_color_image()
    _, palette = quantize_median_cut(img, 3)
    source = {tuple(c) for c in img.reshape(-1, 3)}
    assert all(tuple(c) in source for c in palette)


def test_locked_color_present():
    img = _three_color_image()
    _, palette = quantize_median_cut(img, 3, locked=[(0, 200, 0)])
    assert (0, 200, 0) in {tuple(c) for c in palette}


def test_map_to_palette_nearest():
    palette = np.array([(0, 0, 0), (255, 255, 255)], dtype=np.uint8)
    img = np.array([[[10, 10, 10], [240, 240, 240]]], dtype=np.uint8)
    idx = map_to_palette(img, palette)
    assert idx.tolist() == [[0, 1]]
