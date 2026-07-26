from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from fecreator.assets.portrait.manifest import REQUIRED_EXPRESSIONS
from fecreator.specs.fire_emblem.gba.portrait_standard.assembly import (
    extract_rgb_slot,
    preserve_cell_border,
    replace_rgb_slot,
)

_EXPRESSION_SLOTS = tuple(role for role in REQUIRED_EXPRESSIONS if role != "neutral")


def apply_expression(base_cell: np.ndarray, candidate_cell: np.ndarray) -> np.ndarray:
    return preserve_cell_border(candidate_cell, base_cell)


def derive_sequential(base_cell: np.ndarray, candidates: Sequence[np.ndarray]) -> list[np.ndarray]:
    return [apply_expression(base_cell, candidate) for candidate in candidates]


def assemble_refined_expressions(
    base_sheet_rgb: np.ndarray,
    candidates: Mapping[str, np.ndarray],
) -> np.ndarray:
    """Replace all expression cells, retaining each approved cell's outer border."""
    roles = frozenset(candidates)
    expected = frozenset(_EXPRESSION_SLOTS)
    missing = sorted(expected - roles)
    unexpected = sorted(roles - expected)
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing expression roles: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected expression roles: {', '.join(unexpected)}")
        raise ValueError("; ".join(details))

    refined = base_sheet_rgb.copy()
    for role in _EXPRESSION_SLOTS:
        base_cell = extract_rgb_slot(base_sheet_rgb, role)
        candidate = candidates[role]
        if candidate.dtype != np.dtype(np.uint8):
            raise ValueError(f"expression cell {role!r} must have uint8 dtype")
        refined = replace_rgb_slot(refined, role, apply_expression(base_cell, candidate))
    return refined
