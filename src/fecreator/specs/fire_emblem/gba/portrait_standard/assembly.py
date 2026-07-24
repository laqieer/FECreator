from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from fecreator.specs.fire_emblem.gba.portrait_standard.layout import (
    BG_INDEX,
    SHEET_H,
    SHEET_W,
    SLOTS,
)

_BY_NAME = {s.name: s for s in SLOTS}


def assemble_sheet(cells: Mapping[str, np.ndarray], palette: np.ndarray) -> np.ndarray:
    """Compose named cells onto a 112x128 index sheet.

    Unspecified slots are filled with ``BG_INDEX``. Unknown slot names raise
    ``KeyError`` and cells whose shape does not match the slot raise
    ``ValueError`` (fail closed).
    """
    if palette.ndim != 2 or palette.shape[1] != 3:
        raise ValueError(f"palette must be (N, 3), got shape {palette.shape}")
    sheet = np.full((SHEET_H, SHEET_W), BG_INDEX, dtype=np.uint8)
    for name, cell in cells.items():
        slot = _BY_NAME[name]
        if cell.shape != (slot.h, slot.w):
            raise ValueError(f"cell {name!r} has shape {cell.shape}, expected {(slot.h, slot.w)}")
        sheet[slot.y : slot.y + slot.h, slot.x : slot.x + slot.w] = cell
    return sheet


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
