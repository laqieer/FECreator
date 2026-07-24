import numpy as np
import pytest

from fecreator.imaging.resize import ResizeMode, resize


def test_pixel_preserve_is_nearest_block_replication():
    src = np.array([[[10, 10, 10], [20, 20, 20]]], dtype=np.uint8)  # 1x2
    out = resize(src, (4, 2), ResizeMode.PIXEL_PRESERVE)  # width=4,height=2
    assert out.shape == (2, 4, 3)
    assert tuple(out[0, 0]) == (10, 10, 10)
    assert tuple(out[0, 3]) == (20, 20, 20)


def test_illustration_fit_downscale_shape_and_dtype():
    src = (np.random.default_rng(0).integers(0, 255, (32, 32, 3))).astype(np.uint8)
    out = resize(src, (16, 16), ResizeMode.ILLUSTRATION_FIT)
    assert out.shape == (16, 16, 3) and out.dtype == np.uint8


def test_unknown_mode_type_rejected():
    src = np.zeros((2, 2, 3), dtype=np.uint8)
    with pytest.raises(ValueError):
        resize(src, (4, 4), "bilinear")  # type: ignore[arg-type]


# --- I-4: grid modes fail closed; size validation ---


def test_pseudo_pixel_grid_mode_raises_not_implemented():
    src = np.zeros((8, 8, 3), dtype=np.uint8)
    with pytest.raises(NotImplementedError):
        resize(src, (4, 4), ResizeMode.PSEUDO_PIXEL_GRID)


def test_manual_grid_mode_raises_not_implemented():
    src = np.zeros((8, 8, 3), dtype=np.uint8)
    with pytest.raises(NotImplementedError):
        resize(src, (4, 4), ResizeMode.MANUAL_GRID)


def test_zero_width_raises():
    src = np.zeros((4, 4, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="size"):
        resize(src, (0, 4), ResizeMode.ILLUSTRATION_FIT)


def test_zero_height_raises():
    src = np.zeros((4, 4, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="size"):
        resize(src, (4, 0), ResizeMode.ILLUSTRATION_FIT)


def test_negative_size_raises():
    src = np.zeros((4, 4, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="size"):
        resize(src, (-1, 4), ResizeMode.PIXEL_PRESERVE)
