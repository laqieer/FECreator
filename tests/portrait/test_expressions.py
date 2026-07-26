import numpy as np
import pytest

from fecreator.assets.portrait.expressions import (
    apply_expression,
    assemble_refined_expressions,
    derive_sequential,
)

# ---------------------------------------------------------------------------
# Basic contract (from brief)
# ---------------------------------------------------------------------------


def test_border_preserved_interior_transferred():
    base = np.zeros((16, 32), dtype=np.uint8)
    candidate = np.ones((16, 32), dtype=np.uint8)
    out = apply_expression(base, candidate)
    assert out[0, 0] == 0 and out[-1, -1] == 0  # border from base
    assert out[8, 16] == 1  # interior from candidate


def test_identity_when_candidate_equals_base():
    base = np.arange(16 * 32, dtype=np.uint8).reshape(16, 32)
    out = apply_expression(base, base.copy())
    assert np.array_equal(out, base)


def test_derive_sequential_preserves_all_borders():
    base = np.zeros((16, 32), dtype=np.uint8)
    cands = [np.full((16, 32), 2, np.uint8), np.full((16, 32), 3, np.uint8)]
    frames = derive_sequential(base, cands)
    assert len(frames) == 2
    assert all(f[0, 0] == 0 for f in frames)


# ---------------------------------------------------------------------------
# All four border sides are preserved byte-for-byte from base
# ---------------------------------------------------------------------------


def test_all_four_border_sides_come_from_base():
    base = np.full((8, 12), 7, dtype=np.uint8)
    candidate = np.full((8, 12), 99, dtype=np.uint8)
    out = apply_expression(base, candidate)
    # top row
    assert np.array_equal(out[0, :], base[0, :])
    # bottom row
    assert np.array_equal(out[-1, :], base[-1, :])
    # left column
    assert np.array_equal(out[:, 0], base[:, 0])
    # right column
    assert np.array_equal(out[:, -1], base[:, -1])
    # interior pixel took candidate value
    assert out[4, 6] == 99


# ---------------------------------------------------------------------------
# Immutability: inputs must not be mutated
# ---------------------------------------------------------------------------


def test_base_not_mutated():
    base = np.zeros((16, 32), dtype=np.uint8)
    candidate = np.ones((16, 32), dtype=np.uint8)
    base_copy = base.copy()
    apply_expression(base, candidate)
    assert np.array_equal(base, base_copy)


def test_candidate_not_mutated():
    base = np.zeros((16, 32), dtype=np.uint8)
    candidate = np.ones((16, 32), dtype=np.uint8)
    candidate_copy = candidate.copy()
    apply_expression(base, candidate)
    assert np.array_equal(candidate, candidate_copy)


def test_derive_sequential_does_not_mutate_base():
    base = np.zeros((16, 32), dtype=np.uint8)
    base_copy = base.copy()
    cands = [np.full((16, 32), i, dtype=np.uint8) for i in range(1, 4)]
    derive_sequential(base, cands)
    assert np.array_equal(base, base_copy)


# ---------------------------------------------------------------------------
# Tiny / minimal cell (2×2 — entire cell is border, so output equals base)
# ---------------------------------------------------------------------------


def test_minimal_2x2_cell_is_entirely_border():
    base = np.array([[1, 2], [3, 4]], dtype=np.uint8)
    candidate = np.array([[9, 9], [9, 9]], dtype=np.uint8)
    out = apply_expression(base, candidate)
    # A 2×2 cell has no interior — every pixel is on the border.
    assert np.array_equal(out, base)


# ---------------------------------------------------------------------------
# Malformed: shape mismatch raises ValueError (fail-closed)
# ---------------------------------------------------------------------------


def test_shape_mismatch_raises_value_error():
    base = np.zeros((16, 32), dtype=np.uint8)
    bad = np.zeros((8, 32), dtype=np.uint8)
    with pytest.raises(ValueError, match="shape"):
        apply_expression(base, bad)


# ---------------------------------------------------------------------------
# Empty candidates list returns empty list
# ---------------------------------------------------------------------------


def test_derive_empty_candidates_returns_empty_list():
    base = np.zeros((16, 32), dtype=np.uint8)
    frames = derive_sequential(base, [])
    assert frames == []


def test_assemble_refined_expressions_preserves_other_slots_and_patch_borders():
    base = np.zeros((112, 128, 3), dtype=np.uint8)
    base[48:64, 96:128] = 7
    base[64:80, 96:128] = 8
    base[80:96, 0:32] = 9
    base[80:96, 32:64] = 10
    base[80:96, 64:96] = 11
    original = base.copy()
    candidates = {
        "half_closed_eyes": np.full((16, 32, 3), 40, dtype=np.uint8),
        "closed_eyes": np.full((16, 32, 3), 41, dtype=np.uint8),
        "mouth1": np.full((16, 32, 3), 42, dtype=np.uint8),
        "mouth2": np.full((16, 32, 3), 43, dtype=np.uint8),
        "mouth3": np.full((16, 32, 3), 44, dtype=np.uint8),
    }

    refined = assemble_refined_expressions(base, candidates)

    assert np.array_equal(refined[:48], original[:48])
    assert np.array_equal(refined[48, 96:128], original[48, 96:128])
    assert np.array_equal(refined[63, 96:128], original[63, 96:128])
    assert np.array_equal(refined[48:64, 96], original[48:64, 96])
    assert np.array_equal(refined[48:64, 127], original[48:64, 127])
    assert np.array_equal(refined[56, 112], candidates["half_closed_eyes"][8, 16])
    assert np.array_equal(base, original)


def test_assemble_refined_expressions_requires_every_expression_role():
    base = np.zeros((112, 128, 3), dtype=np.uint8)
    candidates = {
        "half_closed_eyes": np.zeros((16, 32, 3), dtype=np.uint8),
        "closed_eyes": np.zeros((16, 32, 3), dtype=np.uint8),
        "mouth1": np.zeros((16, 32, 3), dtype=np.uint8),
        "mouth2": np.zeros((16, 32, 3), dtype=np.uint8),
    }

    with pytest.raises(ValueError, match="missing"):
        assemble_refined_expressions(base, candidates)
