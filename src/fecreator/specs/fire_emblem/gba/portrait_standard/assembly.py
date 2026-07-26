from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from fecreator.specs.fire_emblem.gba.portrait_standard.layout import (
    BG_INDEX,
    MAX_COLORS,
    SHEET_H,
    SHEET_W,
    SLOTS,
)

_BY_NAME = {s.name: s for s in SLOTS}


def assemble_sheet(cells: Mapping[str, np.ndarray], palette: np.ndarray) -> np.ndarray:
    """Compose named cells onto a 112x128 indexed sheet.

    The ``palette`` gates the output: it must be a ``(N, 3)`` integer array with
    ``1 <= N <= 16`` (so background index 0 always exists). Every cell must be a
    2D integer index array matching its slot shape, with values in
    ``0 .. N - 1``; negative or out-of-range indices fail closed rather than
    silently wrapping when cast to ``uint8``. Unspecified slots are filled with
    ``BG_INDEX``. Unknown slot names raise ``KeyError``. Input cells are never
    mutated.
    """
    _validate_palette(palette)
    n_colours = int(palette.shape[0])
    sheet = np.full((SHEET_H, SHEET_W), BG_INDEX, dtype=np.uint8)
    for name, cell in cells.items():
        slot = _BY_NAME[name]
        if cell.ndim != 2 or cell.shape != (slot.h, slot.w):
            raise ValueError(f"cell {name!r} has shape {cell.shape}, expected {(slot.h, slot.w)}")
        if not np.issubdtype(cell.dtype, np.integer):
            raise ValueError(f"cell {name!r} must be an integer index array, got {cell.dtype}")
        cell_min = int(cell.min())
        cell_max = int(cell.max())
        if cell_min < 0:
            raise ValueError(f"cell {name!r} has negative index {cell_min}")
        if cell_max >= n_colours:
            raise ValueError(f"cell {name!r} index {cell_max} >= palette size {n_colours}")
        sheet[slot.y : slot.y + slot.h, slot.x : slot.x + slot.w] = cell.astype(np.uint8)
    return sheet


def _validate_palette(palette: np.ndarray) -> None:
    if palette.ndim != 2 or palette.shape[1] != 3:
        raise ValueError(f"palette must be (N, 3), got shape {palette.shape}")
    if not np.issubdtype(palette.dtype, np.integer):
        raise ValueError(f"palette must be an integer array, got {palette.dtype}")
    if not 1 <= palette.shape[0] <= MAX_COLORS:
        raise ValueError(f"palette must have 1..16 entries, got {palette.shape[0]}")


def preserve_cell_border(cell: np.ndarray, base: np.ndarray) -> np.ndarray:
    """Return ``cell`` with its outer 1-px border replaced by ``base``'s border.

    This keeps eye/mouth patch cells seamless against the neutral portrait.
    """
    if cell.shape != base.shape:
        raise ValueError(f"cell shape {cell.shape} does not match base shape {base.shape}")
    out = cell.copy()
    out[0, :] = base[0, :]
    out[-1, :] = base[-1, :]
    out[:, 0] = base[:, 0]
    out[:, -1] = base[:, -1]
    return out


def extract_rgb_slot(sheet_rgb: np.ndarray, name: str) -> np.ndarray:
    """Return a copied RGB cell from a canonical portrait sheet."""
    _validate_rgb_sheet(sheet_rgb)
    slot = _BY_NAME[name]
    return sheet_rgb[slot.y : slot.y + slot.h, slot.x : slot.x + slot.w].copy()


def replace_rgb_slot(sheet_rgb: np.ndarray, name: str, cell_rgb: np.ndarray) -> np.ndarray:
    """Return a copied sheet with one complete RGB cell replaced."""
    _validate_rgb_sheet(sheet_rgb)
    slot = _BY_NAME[name]
    expected = (slot.h, slot.w, 3)
    if cell_rgb.shape != expected:
        raise ValueError(f"cell {name!r} has shape {cell_rgb.shape}, expected {expected}")
    out = sheet_rgb.copy()
    out[slot.y : slot.y + slot.h, slot.x : slot.x + slot.w] = cell_rgb
    return out


def _validate_rgb_sheet(sheet_rgb: np.ndarray) -> None:
    expected = (SHEET_H, SHEET_W, 3)
    if sheet_rgb.shape != expected:
        raise ValueError(f"sheet_rgb must have shape {expected}, got {sheet_rgb.shape}")
    if sheet_rgb.dtype != np.dtype(np.uint8):
        raise ValueError(f"sheet_rgb must have uint8 dtype, got {sheet_rgb.dtype}")
