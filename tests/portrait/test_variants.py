import numpy as np

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


def test_apply_masked_edit_changes_only_mask():
    base, edited, mask = _festival_hat_scene()
    out = apply_masked_edit(base, edited, mask)
    assert tuple(out[5, 5]) == (230, 40, 40)  # inside mask -> edited
    assert tuple(out[40, 40]) == (60, 90, 200)  # outside mask -> base


def test_protected_region_unchanged_no_error():
    base, edited, mask = _festival_hat_scene()
    result = apply_masked_edit(base, edited, mask)
    face = (Region(x=20, y=40, w=40, h=30, label="face"),)
    assert check_protected_regions(base, result, face) == []


def test_protected_region_violation_flagged():
    base, edited, mask = _festival_hat_scene()
    result = apply_masked_edit(base, edited, mask)
    result[45:55, 25:35] = (0, 0, 0)  # corrupt a protected region
    face = (Region(x=20, y=40, w=40, h=30, label="face"),)
    _, diags = build_variant(base, result, np.ones((80, 96), bool), face)
    assert any(d.code == "PROTECTED_REGION_CHANGED" for d in diags)
