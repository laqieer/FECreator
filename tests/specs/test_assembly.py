from __future__ import annotations

import numpy as np
import pytest

from fecreator.specs.fire_emblem.gba.portrait_standard.assembly import (
    assemble_sheet,
    preserve_cell_border,
)

_PAL2 = np.array([(0, 0, 0), (255, 255, 255)], dtype=np.uint8)


def test_assemble_places_main_slot() -> None:
    main = np.ones((80, 96), dtype=np.uint8)
    sheet = assemble_sheet({"main": main}, _PAL2)
    assert sheet.shape == (112, 128)
    assert sheet[0, 0] == 1
    assert sheet[0, 100] == 0  # mini slot area left as background


def test_unspecified_cells_are_background() -> None:
    sheet = assemble_sheet({}, _PAL2)
    assert sheet.shape == (112, 128)
    assert bool(np.all(sheet == 0))


def test_assemble_rejects_unknown_slot() -> None:
    with pytest.raises(KeyError):
        assemble_sheet({"nose": np.ones((16, 32), dtype=np.uint8)}, _PAL2)


def test_assemble_rejects_cell_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="shape"):
        assemble_sheet({"mini": np.ones((16, 16), dtype=np.uint8)}, _PAL2)


def test_assemble_rejects_empty_palette() -> None:
    with pytest.raises(ValueError, match="1..16"):
        assemble_sheet({}, np.empty((0, 3), dtype=np.uint8))


def test_assemble_rejects_palette_gt16() -> None:
    palette = np.zeros((17, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="1..16"):
        assemble_sheet({}, palette)


def test_assemble_rejects_non_integer_cell() -> None:
    main = np.ones((80, 96), dtype=np.float64)
    with pytest.raises(ValueError, match="integer"):
        assemble_sheet({"main": main}, _PAL2)


def test_assemble_rejects_non_2d_cell() -> None:
    main = np.ones((80, 96, 1), dtype=np.uint8)
    with pytest.raises(ValueError, match="shape"):
        assemble_sheet({"main": main}, _PAL2)


def test_assemble_rejects_negative_cell_value() -> None:
    main = np.zeros((80, 96), dtype=np.int16)
    main[0, 0] = -1
    with pytest.raises(ValueError, match="negative"):
        assemble_sheet({"main": main}, _PAL2)


def test_assemble_rejects_index_ge_palette() -> None:
    main = np.full((80, 96), 5, dtype=np.uint8)
    with pytest.raises(ValueError, match="palette"):
        assemble_sheet({"main": main}, _PAL2)


def test_assemble_preserves_input_cells() -> None:
    main = np.ones((80, 96), dtype=np.uint8)
    before = main.copy()
    assemble_sheet({"main": main}, _PAL2)
    assert np.array_equal(main, before)


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
