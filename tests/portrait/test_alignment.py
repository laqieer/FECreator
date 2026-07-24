import numpy as np

from fecreator.assets.portrait.alignment import align_to_main

GREEN = (0, 248, 0)


def test_output_shape_and_background():
    src = np.full((40, 40, 3), GREEN, dtype=np.uint8)
    src[10:30, 10:30] = (200, 30, 30)  # centered foreground block
    out = align_to_main(src, GREEN)
    assert out.shape == (80, 96, 3)
    assert tuple(out[0, 0]) == GREEN  # corner stays background
    assert (out != np.array(GREEN)).any()  # foreground present


def test_all_background_returns_background_canvas():
    src = np.full((20, 20, 3), GREEN, dtype=np.uint8)
    out = align_to_main(src, GREEN)
    assert (out == np.array(GREEN, dtype=np.uint8)).all()
