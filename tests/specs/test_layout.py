from __future__ import annotations

from fecreator.specs.fire_emblem.gba.portrait_standard.layout import (
    BACKGROUND_ZONES,
    BG_INDEX,
    MAX_COLORS,
    SHEET_H,
    SHEET_W,
    SLOTS,
    Slot,
)


def test_sheet_constants() -> None:
    assert (SHEET_W, SHEET_H, MAX_COLORS, BG_INDEX) == (128, 112, 16, 0)


def test_twelve_slots_with_main_and_mini() -> None:
    by_name = {s.name: s for s in SLOTS}
    assert len(SLOTS) == 12
    assert by_name["main"] == Slot(name="main", x=0, y=0, w=96, h=80)
    assert by_name["mini"] == Slot(name="mini", x=96, y=16, w=32, h=32)
    assert by_name["closed_eyes"] == Slot(name="closed_eyes", x=96, y=64, w=32, h=16)
    assert by_name["mouth1"] == Slot(name="mouth1", x=0, y=80, w=32, h=16)


def test_background_zones_present() -> None:
    labels = {r.label for r in BACKGROUND_ZONES}
    assert {"upper_left", "upper_right", "top_right_strip", "unused_bottom_right"} <= labels
