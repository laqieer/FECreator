import numpy as np
import pytest

from fecreator.imaging.io import (
    ImageBudgetError,
    ResourceBudget,
    has_trns,
    is_indexed_png,
    load_indexed,
    load_rgb,
    png_dimensions,
    read_png_palette,
    save_indexed_png,
    save_png,
)


def test_rgb_roundtrip(tmp_path):
    rgb = np.zeros((4, 6, 3), dtype=np.uint8)
    rgb[0, 0] = (10, 20, 30)
    p = tmp_path / "x.png"
    save_png(p, rgb)
    back = load_rgb(p)
    assert back.shape == (4, 6, 3)
    assert tuple(back[0, 0]) == (10, 20, 30)


def test_budget_enforced(tmp_path):
    rgb = np.zeros((100, 100, 3), dtype=np.uint8)
    p = tmp_path / "big.png"
    save_png(p, rgb)
    with pytest.raises(ImageBudgetError):
        load_rgb(p, ResourceBudget(max_pixels=100))


def test_indexed_roundtrip_and_facts(tmp_path):
    indices = np.array([[0, 1], [1, 0]], dtype=np.uint8)
    palette = np.array([(0, 128, 0), (255, 255, 255)], dtype=np.uint8)
    p = tmp_path / "idx.png"
    save_indexed_png(p, indices, palette)
    idx2, pal2 = load_indexed(p)
    assert np.array_equal(idx2, indices)
    assert [tuple(c) for c in pal2] == [(0, 128, 0), (255, 255, 255)]
    assert png_dimensions(p) == (2, 2)
    assert is_indexed_png(p) is True
    assert has_trns(p) is False
    assert read_png_palette(p) == [(0, 128, 0), (255, 255, 255)]
