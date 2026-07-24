from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from fecreator.specs.fire_emblem.gba.portrait_standard.assembly import preserve_cell_border


def apply_expression(base_cell: np.ndarray, candidate_cell: np.ndarray) -> np.ndarray:
    return preserve_cell_border(candidate_cell, base_cell)


def derive_sequential(base_cell: np.ndarray, candidates: Sequence[np.ndarray]) -> list[np.ndarray]:
    return [apply_expression(base_cell, candidate) for candidate in candidates]
