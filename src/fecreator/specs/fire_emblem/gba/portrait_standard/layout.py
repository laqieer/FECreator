from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from fecreator.contracts.lineage import Region

SHEET_W = 128
SHEET_H = 112
MAX_COLORS = 16
BG_INDEX = 0


class Slot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    x: int
    y: int
    w: int
    h: int


SLOTS: tuple[Slot, ...] = (
    Slot(name="main", x=0, y=0, w=96, h=80),
    Slot(name="mini", x=96, y=16, w=32, h=32),
    Slot(name="half_closed_eyes", x=96, y=48, w=32, h=16),
    Slot(name="closed_eyes", x=96, y=64, w=32, h=16),
    Slot(name="mouth1", x=0, y=80, w=32, h=16),
    Slot(name="mouth2", x=32, y=80, w=32, h=16),
    Slot(name="mouth3", x=64, y=80, w=32, h=16),
    Slot(name="mouth4_status", x=96, y=80, w=32, h=16),
    Slot(name="mouth5", x=0, y=96, w=32, h=16),
    Slot(name="mouth6", x=32, y=96, w=32, h=16),
    Slot(name="mouth7", x=64, y=96, w=32, h=16),
    Slot(name="unused", x=96, y=96, w=32, h=16),
)

# Regions that must remain background (index 0). Coordinates from the
# FEBuilder-interop research: the upper-left and upper-right strips of the
# 96x80 main portrait, the full-sheet top-right strip, and the unused
# bottom-right slot.
BACKGROUND_ZONES: tuple[Region, ...] = (
    Region(x=0, y=0, w=16, h=48, label="upper_left"),
    Region(x=80, y=0, w=16, h=48, label="upper_right"),
    Region(x=96, y=0, w=32, h=16, label="top_right_strip"),
    Region(x=96, y=96, w=32, h=16, label="unused_bottom_right"),
)

# FE-Repo Standard content zones within the 96x80 main portrait.
SAFE_ZONES: tuple[Region, ...] = (
    Region(x=16, y=0, w=64, h=48, label="upper_content"),
    Region(x=0, y=48, w=96, h=32, label="lower_content"),
)

# Slots that must contain non-background content in a canonical package: every
# slot except the always-background "unused" bottom-right cell. mouth4_status is
# required (FEBuilder-interop research treats the status mouth frame as present).
REQUIRED_SLOTS: tuple[str, ...] = tuple(s.name for s in SLOTS if s.name != "unused")
