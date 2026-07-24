import numpy as np
import pytest

from fecreator.assets.portrait.variants import (
    apply_masked_edit,
    build_variant,
    check_protected_regions,
)
from fecreator.contracts.lineage import Region


def _festival_hat_scene() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    base = np.zeros((80, 96, 3), dtype=np.uint8)
    base[:] = (60, 90, 200)  # body/clothes
    edited = base.copy()
    edited[0:20, :] = (230, 40, 40)  # a hat painted over the top region
    mask = np.zeros((80, 96), dtype=bool)
    mask[0:20, :] = True  # edit only the hat region
    return base, edited, mask


def test_apply_masked_edit_changes_only_mask() -> None:
    base, edited, mask = _festival_hat_scene()
    out = apply_masked_edit(base, edited, mask)
    assert tuple(out[5, 5]) == (230, 40, 40)  # inside mask -> edited
    assert tuple(out[40, 40]) == (60, 90, 200)  # outside mask -> base


def test_protected_region_unchanged_no_error() -> None:
    base, edited, mask = _festival_hat_scene()
    result = apply_masked_edit(base, edited, mask)
    face = (Region(x=20, y=40, w=40, h=30, label="face"),)
    assert check_protected_regions(base, result, face) == []


def test_protected_region_violation_flagged() -> None:
    base, edited, mask = _festival_hat_scene()
    result = apply_masked_edit(base, edited, mask)
    result[45:55, 25:35] = (0, 0, 0)  # corrupt a protected region
    face = (Region(x=20, y=40, w=40, h=30, label="face"),)
    _, diags = build_variant(base, result, np.ones((80, 96), bool), face)
    assert any(d.code == "PROTECTED_REGION_CHANGED" for d in diags)


# ---------------------------------------------------------------------------
# NEW: mask dtype/shape validation
# ---------------------------------------------------------------------------


def test_non_bool_mask_raises_value_error() -> None:
    base = np.zeros((80, 96, 3), dtype=np.uint8)
    edited = base.copy()
    float_mask = np.zeros((80, 96), dtype=np.float32)
    with pytest.raises(ValueError, match="bool"):
        apply_masked_edit(base, edited, float_mask)


def test_uint8_mask_raises_value_error() -> None:
    base = np.zeros((80, 96, 3), dtype=np.uint8)
    edited = base.copy()
    uint_mask = np.zeros((80, 96), dtype=np.uint8)
    with pytest.raises(ValueError, match="bool"):
        apply_masked_edit(base, edited, uint_mask)


def test_wrong_height_mask_raises_value_error() -> None:
    base = np.zeros((80, 96, 3), dtype=np.uint8)
    edited = base.copy()
    bad_mask = np.zeros((40, 96), dtype=bool)  # wrong height
    with pytest.raises(ValueError, match="shape"):
        apply_masked_edit(base, edited, bad_mask)


def test_wrong_width_mask_raises_value_error() -> None:
    base = np.zeros((80, 96, 3), dtype=np.uint8)
    edited = base.copy()
    bad_mask = np.zeros((80, 48), dtype=bool)  # wrong width
    with pytest.raises(ValueError, match="shape"):
        apply_masked_edit(base, edited, bad_mask)


# ---------------------------------------------------------------------------
# NEW: OOB protected region → diagnostic, not uncaught ValueError
# ---------------------------------------------------------------------------


def test_oob_region_in_check_protected_regions_gives_diagnostic() -> None:
    base = np.zeros((80, 96, 3), dtype=np.uint8)
    result = base.copy()
    # x+w = 90+20 = 110 > 96 → out-of-bounds
    oob = (Region(x=90, y=0, w=20, h=10, label="out_of_bounds_region"),)
    diags = check_protected_regions(base, result, oob)
    assert any(d.code == "REGION_OUT_OF_BOUNDS" for d in diags)
    assert diags[0].where == "out_of_bounds_region"


def test_oob_region_in_build_variant_gives_diagnostic() -> None:
    base = np.zeros((80, 96, 3), dtype=np.uint8)
    edited = base.copy()
    mask = np.ones((80, 96), dtype=bool)
    # y+h = 70+20 = 90 > 80 → out-of-bounds
    oob = (Region(x=0, y=70, w=10, h=20, label="oob_label"),)
    _, diags = build_variant(base, edited, mask, oob)
    assert any(d.code == "REGION_OUT_OF_BOUNDS" for d in diags)


def test_mixed_valid_and_oob_regions() -> None:
    """Valid region is still checked; OOB region gets diagnostic, no crash."""
    base = np.zeros((80, 96, 3), dtype=np.uint8)
    result = base.copy()
    result[45:55, 25:35] = 255  # corrupt valid region
    regions = (
        Region(x=20, y=40, w=40, h=30, label="face"),  # valid, but changed
        Region(x=90, y=0, w=20, h=10, label="oob"),  # out-of-bounds
    )
    diags = check_protected_regions(base, result, regions)
    codes = {d.code for d in diags}
    assert "PROTECTED_REGION_CHANGED" in codes
    assert "REGION_OUT_OF_BOUNDS" in codes


# ---------------------------------------------------------------------------
# NEW (low findings): edited_rgb shape check; narrow OOB catch
# ---------------------------------------------------------------------------


def test_edited_rgb_height_mismatch_raises_value_error() -> None:
    """edited_rgb must have the same shape as base_rgb."""
    base = np.zeros((80, 96, 3), dtype=np.uint8)
    edited_wrong = np.zeros((40, 96, 3), dtype=np.uint8)
    mask = np.zeros((80, 96), dtype=bool)
    with pytest.raises(ValueError, match="edited_rgb"):
        apply_masked_edit(base, edited_wrong, mask)


def test_edited_rgb_channel_mismatch_raises_value_error() -> None:
    base = np.zeros((80, 96, 3), dtype=np.uint8)
    edited_wrong = np.zeros((80, 96, 4), dtype=np.uint8)  # wrong channels
    mask = np.zeros((80, 96), dtype=bool)
    with pytest.raises(ValueError, match="edited_rgb"):
        apply_masked_edit(base, edited_wrong, mask)


def test_shape_mismatch_between_base_and_result_propagates() -> None:
    """An image-shape mismatch in check_protected_regions must raise, not become OOB diagnostic."""
    base = np.zeros((80, 96, 3), dtype=np.uint8)
    wrong_result = np.zeros((40, 96, 3), dtype=np.uint8)  # different H
    valid_region = (Region(x=0, y=0, w=10, h=10, label="face"),)
    with pytest.raises(ValueError, match="shape mismatch"):
        check_protected_regions(base, wrong_result, valid_region)
