from __future__ import annotations

import numpy as np
import pytest

from fecreator.specs.fire_emblem.gba.portrait_standard.assembly import (
    assemble_sheet,
    preserve_cell_border,
)


def test_assemble_places_main_slot() -> None:
    palette = np.array([(0, 0, 0)], dtype=np.uint8)
    main = np.ones((80, 96), dtype=np.uint8)
    sheet = assemble_sheet({"main": main}, palette)
    assert sheet.shape == (112, 128)
    assert sheet[0, 0] == 1
    assert sheet[0, 100] == 0  # mini slot area left as background


def test_unspecified_cells_are_background() -> None:
    palette = np.array([(0, 0, 0)], dtype=np.uint8)
    sheet = assemble_sheet({}, palette)
    assert sheet.shape == (112, 128)
    assert bool(np.all(sheet == 0))


def test_assemble_rejects_unknown_slot() -> None:
    palette = np.array([(0, 0, 0)], dtype=np.uint8)
    with pytest.raises(KeyError):
        assemble_sheet({"nose": np.ones((16, 32), dtype=np.uint8)}, palette)


def test_assemble_rejects_cell_shape_mismatch() -> None:
    palette = np.array([(0, 0, 0)], dtype=np.uint8)
    with pytest.raises(ValueError, match="shape"):
        assemble_sheet({"mini": np.ones((16, 16), dtype=np.uint8)}, palette)


def test_preserve_cell_border_replaces_edges_only() -> None:
    base = np.zeros((16, 32), dtype=np.uint8)
    cell = np.ones((16, 32), dtype=np.uint8)
    out = preserve_cell_border(cell, base)
    assert out[0, 0] == 0 and out[-1, -1] == 0  # border from base
    assert out[8, 16] == 1  # interior from cell


def test_preserve_cell_border_rejects_shape_mismatch() -> None:
    base = np.zeros((16, 32), dtype=np.uint8)
    cell = np.ones((16, 16), dtype=np.uint8)
    with pytest.raises(ValueError, match="shape"):
        preserve_cell_border(cell, base)
