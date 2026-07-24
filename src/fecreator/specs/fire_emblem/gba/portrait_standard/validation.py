from __future__ import annotations

from pathlib import Path

import numpy as np

from fecreator.contracts.diagnostics import Diagnostic, error, warning
from fecreator.imaging.io import (
    ImageBudgetError,
    is_indexed_png,
    load_indexed,
    png_dimensions,
    read_png_palette,
)
from fecreator.imaging.morphology import connected_components
from fecreator.specs.fire_emblem.gba.portrait_standard.layout import (
    BACKGROUND_ZONES,
    BG_INDEX,
    MAX_COLORS,
    SHEET_H,
    SHEET_W,
)
from fecreator.specs.fire_emblem.gba.portrait_standard.palette import read_jasc

_RGB = tuple[int, int, int]


def _pngs(package_dir: Path) -> list[Path]:
    return sorted(package_dir.glob("*.png"))


def validate_package(package_dir: Path) -> list[Diagnostic]:
    """Validate a canonical FE GBA portrait package, failing closed.

    Emits FEBuilder-mirrored diagnostic codes plus the stricter v1 errors
    ``BACKGROUND_HOLE`` and ``UNSAFE_ZONE``. Patch-border invariance is
    enforced during expression derivation, not at package level.
    """
    diags: list[Diagnostic] = []
    pngs = _pngs(package_dir)
    if not pngs:
        return [error("MISSING_SHEET", "package has no PNG", where=str(package_dir))]
    if len(pngs) > 1:
        diags.append(error("MULTIPLE_SHEETS", "package has more than one PNG"))
    sheet = pngs[0]

    try:
        if not is_indexed_png(sheet):
            return [*diags, error("NON_INDEXED", "PNG is not indexed", where=sheet.name)]
        width, height = png_dimensions(sheet)
        palette = read_png_palette(sheet)
    except (ValueError, ImageBudgetError, OSError) as exc:
        return [*diags, error("BAD_PNG", f"cannot parse PNG: {exc}", where=sheet.name)]

    if (width, height) != (SHEET_W, SHEET_H):
        diags.append(
            error(
                "SHEET_BAD_DIMS",
                f"expected {SHEET_W}x{SHEET_H}, got {width}x{height}",
                where=sheet.name,
            )
        )

    if len(palette) > MAX_COLORS:
        diags.append(
            error(
                "PORTRAIT_PALETTE_GT16",
                f"{len(palette)} palette entries > {MAX_COLORS}",
                where=sheet.name,
            )
        )

    diags.extend(_palette_sidecar_diags(sheet, palette))

    if (width, height) == (SHEET_W, SHEET_H):
        try:
            indices, _ = load_indexed(sheet)
        except (ValueError, ImageBudgetError, OSError) as exc:
            diags.append(error("BAD_PNG", f"cannot parse PNG: {exc}", where=sheet.name))
            return diags
        diags.extend(_background_hole_diags(indices))
        diags.extend(_unsafe_zone_diags(indices))
    return diags


def _palette_sidecar_diags(sheet: Path, palette: list[_RGB]) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    pal_path = sheet.with_suffix(".pal")
    if not pal_path.exists():
        out.append(warning("MISSING_PALETTE", "no matching JASC sidecar", where=sheet.name))
        return out
    try:
        jasc = read_jasc(pal_path)
    except (ValueError, OSError) as exc:
        out.append(error("BAD_PALETTE", f"cannot parse JASC sidecar: {exc}", where=pal_path.name))
        return out
    if len(jasc) != len(palette):
        out.append(
            error(
                "PALETTE_COUNT_MISMATCH",
                "JASC count != PNG palette",
                where=pal_path.name,
            )
        )
    elif jasc != palette:
        out.append(
            error(
                "PALETTE_COLOR_MISMATCH",
                "JASC color != PNG palette",
                where=pal_path.name,
            )
        )
    return out


def _unsafe_zone_diags(indices: np.ndarray) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for zone in BACKGROUND_ZONES:
        block = indices[zone.y : zone.y + zone.h, zone.x : zone.x + zone.w]
        if bool(np.any(block != BG_INDEX)):
            out.append(
                error(
                    "UNSAFE_ZONE",
                    f"zone {zone.label} must be background",
                    where=zone.label,
                )
            )
    return out


def _background_hole_diags(indices: np.ndarray) -> list[Diagnostic]:
    background = indices == BG_INDEX
    _, labels = connected_components(background)
    border = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
    border.discard(0)
    interior = set(np.unique(labels).tolist()) - border - {0}
    if interior:
        return [error("BACKGROUND_HOLE", "enclosed background region inside foreground")]
    return []
