import threading

import numpy as np
import pytest

from fecreator.imaging.quantize import (
    QuantizeError,
    map_to_palette,
    quantize_kmeans_lab,
    quantize_median_cut,
)


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


# --- C-1: median_cut termination ---


def test_median_cut_k1_single_pixel_terminates():
    """k=1 on a 1-pixel image must terminate and return one palette entry."""
    img = np.array([[[50, 100, 150]]], dtype=np.uint8)
    idx, pal = quantize_median_cut(img, 1)
    assert pal.shape[0] == 1


def test_median_cut_k_gt_pixels_raises():
    """k > H*W must raise QuantizeError (not hang)."""
    img = np.zeros((1, 2, 3), dtype=np.uint8)  # 2 pixels
    with pytest.raises(QuantizeError):
        quantize_median_cut(img, 3)


def test_kmeans_k_gt_pixels_raises():
    img = np.zeros((1, 1, 3), dtype=np.uint8)
    with pytest.raises(QuantizeError):
        quantize_kmeans_lab(img, 2)


def test_quantize_empty_image_raises():
    img = np.zeros((0, 4, 3), dtype=np.uint8)
    with pytest.raises(QuantizeError):
        quantize_median_cut(img, 1)
    with pytest.raises(QuantizeError):
        quantize_kmeans_lab(img, 1)


def test_quantize_k_zero_raises():
    img = _three_color_image()
    with pytest.raises(QuantizeError):
        quantize_median_cut(img, 0)
    with pytest.raises(QuantizeError):
        quantize_kmeans_lab(img, 0)


def test_palette_does_not_exceed_k_after_locked():
    """Adding locked colors must not push palette above k."""
    img = _three_color_image()
    _, pal = quantize_median_cut(img, 3, locked=[(1, 1, 1), (2, 2, 2)])
    assert len(pal) <= 3


# --- C-2: chunked map_to_palette (memory-safe large case) ---


def test_map_to_palette_large_no_oom():
    """1000x1000 image with 256-entry palette must complete without OOM."""
    rng = np.random.default_rng(42)
    img = rng.integers(0, 256, (1000, 1000, 3), dtype=np.uint8)
    palette = rng.integers(0, 256, (256, 3), dtype=np.uint8)
    idx = map_to_palette(img, palette)
    assert idx.shape == (1000, 1000)
    assert idx.max() < len(palette)


# --- I-3: kmeans concurrency ---


def test_kmeans_concurrent_same_seed_gives_same_result():
    """Concurrent calls with the same seed must return identical palettes."""
    img = _three_color_image()
    results: list[np.ndarray] = []
    errors: list[Exception] = []

    def run() -> None:
        try:
            _, pal = quantize_kmeans_lab(img, 3, seed=42)
            results.append(pal)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    assert len(results) == 4
    for pal in results[1:]:
        assert np.array_equal(pal, results[0])


# --- M-5: map_to_palette index dtype (palette > 256) ---


def test_map_to_palette_stable_tie_breaking():
    """Ties must break toward the lower-index palette entry (stable argmin)."""
    palette = np.array([(128, 128, 128), (128, 128, 128)], dtype=np.uint8)
    img = np.array([[[128, 128, 128]]], dtype=np.uint8)
    idx = map_to_palette(img, palette)
    assert idx[0, 0] == 0  # lower index wins on tie
