import numpy as np

from fecreator.imaging.masks import background_mask, chroma_key
from fecreator.imaging.morphology import (
    close_mask, connected_components, fill_holes, open_mask,
)

GREEN = (0, 255, 0)


def _image_with_hole() -> np.ndarray:
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    img[:] = GREEN                      # green background everywhere
    img[2:8, 2:8] = (200, 100, 50)      # foreground block
    img[4:6, 4:6] = GREEN               # enclosed green hole inside foreground
    return img


def test_chroma_key_flags_all_green():
    img = _image_with_hole()
    mask = chroma_key(img, GREEN)
    assert mask[0, 0] and mask[4, 4] and not mask[2, 2]


def test_background_mask_excludes_enclosed_hole():
    img = _image_with_hole()
    bg = background_mask(img, GREEN)
    assert bg[0, 0] is np.True_ or bg[0, 0]
    assert not bg[4, 4]                  # enclosed hole is NOT background


def test_connected_components_counts_blocks():
    mask = np.zeros((5, 9), dtype=bool)
    mask[1, 1] = True
    mask[3, 6] = True
    count, _ = connected_components(mask)
    assert count == 2


def test_fill_and_morph_shapes():
    mask = np.zeros((6, 6), dtype=bool)
    mask[1:5, 1:5] = True
    mask[2:4, 2:4] = False
    assert fill_holes(mask)[3, 3]
    assert close_mask(mask).shape == mask.shape
    assert open_mask(mask).shape == mask.shape
