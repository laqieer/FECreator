from __future__ import annotations

from pathlib import Path

import numpy as np

from fecreator.contracts.diagnostics import Diagnostic, error
from fecreator.imaging.io import (
    ImageBudgetError,
    has_trns,
    is_indexed_png,
    load_indexed,
    png_bit_depth,
    png_dimensions,
    read_png_palette,
)
from fecreator.imaging.morphology import connected_components
from fecreator.specs.fire_emblem.gba.portrait_standard.layout import (
    BACKGROUND_ZONES,
    BG_INDEX,
    MAX_COLORS,
    REQUIRED_SLOTS,
    SHEET_H,
    SHEET_W,
    SLOTS,
)
from fecreator.specs.fire_emblem.gba.portrait_standard.palette import read_jasc, snap_gba_5bit

_RGB = tuple[int, int, int]
_PARSE_ERRORS = (ValueError, ImageBudgetError, OSError)
_BY_NAME = {s.name: s for s in SLOTS}


def _pngs(package_dir: Path) -> list[Path]:
    return sorted(package_dir.glob("*.png"))


def _palette_sidecar_paths(package_dir: Path) -> list[Path]:
    pals = [p for p in package_dir.iterdir() if p.is_file() and p.suffix.casefold() == ".pal"]
    return sorted(pals, key=lambda p: (p.suffix.casefold(), p.name.casefold(), p.name))


def _within(package_dir: Path, path: Path) -> bool:
    """True only if ``path`` is a real (non-symlink) file directly inside the
    resolved package directory."""
    try:
        root = package_dir.resolve(strict=True)
        resolved = path.resolve(strict=True)
    except OSError:
        return False
    return not path.is_symlink() and resolved.parent == root


def validate_package(package_dir: Path) -> list[Diagnostic]:
    """Validate a canonical FE GBA portrait package, failing closed.

    Every canonical-contract violation is an ``error`` (no warnings). Checks
    cover exactly-one indexed PNG, resolved-path containment, 8-bit indexed
    color type, canonical dimensions, opacity (no ``tRNS``), palette size and
    GBA 5-bit snapping, PNG/JASC palette equality, exactly-one same-basename
    sidecar (foreign sidecars flagged), used pixel indices within the palette,
    background-zone safety, enclosed background holes, and required-slot
    population. Dark-foreground preservation and patch-border invariance need
    source/destination context and are owned by Portrait-Workflow review gates,
    not this package-level check.
    """
    diags: list[Diagnostic] = []
    pngs = _pngs(package_dir)
    if not pngs:
        return [error("MISSING_SHEET", "package has no PNG", where=str(package_dir))]
    if len(pngs) > 1:
        diags.append(error("MULTIPLE_SHEETS", "package has more than one PNG"))
    sheet = pngs[0]

    if not _within(package_dir, sheet):
        return [
            *diags,
            error("UNSAFE_PATH", "PNG is a symlink or outside the package", where=sheet.name),
        ]

    try:
        if not is_indexed_png(sheet):
            return [*diags, error("NON_INDEXED", "PNG is not indexed", where=sheet.name)]
        width, height = png_dimensions(sheet)
        bit_depth = png_bit_depth(sheet)
        palette = read_png_palette(sheet)
        opaque = not has_trns(sheet)
    except _PARSE_ERRORS as exc:
        return [*diags, error("BAD_PNG", f"cannot parse PNG: {exc}", where=sheet.name)]

    if not opaque:
        diags.append(
            error("TRNS_PRESENT", "indexed PNG must be fully opaque (no tRNS)", where=sheet.name)
        )
    if (width, height) != (SHEET_W, SHEET_H):
        diags.append(
            error(
                "SHEET_BAD_DIMS",
                f"expected {SHEET_W}x{SHEET_H}, got {width}x{height}",
                where=sheet.name,
            )
        )
    if bit_depth != 8:
        diags.append(
            error(
                "SHEET_BAD_BIT_DEPTH",
                f"expected 8-bit indexed, got {bit_depth}-bit",
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
    diags.extend(_snap_diags(palette, sheet.name))
    diags.extend(_palette_sidecar_diags(package_dir, sheet, palette))

    if (width, height) == (SHEET_W, SHEET_H) and bit_depth == 8:
        try:
            indices, _ = load_indexed(sheet)
        except _PARSE_ERRORS as exc:
            diags.append(error("BAD_PNG", f"cannot parse PNG: {exc}", where=sheet.name))
            return diags
        if indices.size and int(indices.max()) >= len(palette):
            diags.append(
                error(
                    "INDEX_OUT_OF_RANGE",
                    f"pixel index {int(indices.max())} >= palette size {len(palette)}",
                    where=sheet.name,
                )
            )
        diags.extend(_background_hole_diags(indices))
        diags.extend(_unsafe_zone_diags(indices))
        diags.extend(_slot_population_diags(indices))
    return diags


def _snap_diags(palette: list[_RGB], where: str) -> list[Diagnostic]:
    unsnapped = [entry for entry in palette if entry != snap_gba_5bit(entry)]
    if unsnapped:
        return [
            error(
                "PALETTE_NOT_SNAPPED",
                f"{len(unsnapped)} entries not GBA 5-bit snapped (e.g. {unsnapped[0]})",
                where=where,
            )
        ]
    return []


def _palette_sidecar_diags(package_dir: Path, sheet: Path, palette: list[_RGB]) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    expected = (sheet.stem + ".pal").casefold()
    pals = _palette_sidecar_paths(package_dir)
    # Basenames are matched case-insensitively so a sidecar differing only by
    # case is the canonical match (and the same file on case-insensitive
    # filesystems), not a foreign sidecar.
    matching = [p for p in pals if p.name.casefold() == expected]
    foreign = [p for p in pals if p.name.casefold() != expected]
    foreign += matching[1:]
    for extra in foreign:
        out.append(error("EXTRA_PALETTE", "unrelated JASC sidecar present", where=extra.name))
    if not matching:
        out.append(error("MISSING_PALETTE", "no matching JASC sidecar", where=sheet.name))
        return out
    pal_path = matching[0]
    if not _within(package_dir, pal_path):
        out.append(
            error(
                "UNSAFE_PATH",
                "sidecar is a symlink or outside the package",
                where=pal_path.name,
            )
        )
        return out
    try:
        jasc = read_jasc(pal_path)
    except (ValueError, OSError) as exc:
        out.append(error("BAD_PALETTE", f"cannot parse JASC sidecar: {exc}", where=pal_path.name))
        return out
    if len(jasc) != len(palette):
        out.append(
            error("PALETTE_COUNT_MISMATCH", "JASC count != PNG palette", where=pal_path.name)
        )
    elif jasc != palette:
        out.append(
            error("PALETTE_COLOR_MISMATCH", "JASC color != PNG palette", where=pal_path.name)
        )
    out.extend(_snap_diags(jasc, pal_path.name))
    return out


def _unsafe_zone_diags(indices: np.ndarray) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for zone in BACKGROUND_ZONES:
        block = indices[zone.y : zone.y + zone.h, zone.x : zone.x + zone.w]
        if bool(np.any(block != BG_INDEX)):
            out.append(
                error("UNSAFE_ZONE", f"zone {zone.label} must be background", where=zone.label)
            )
    return out


def _slot_population_diags(indices: np.ndarray) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for name in REQUIRED_SLOTS:
        slot = _BY_NAME[name]
        block = indices[slot.y : slot.y + slot.h, slot.x : slot.x + slot.w]
        if bool(np.all(block == BG_INDEX)):
            out.append(
                error(
                    "SLOT_EMPTY",
                    f"required slot {name} has no foreground content",
                    where=name,
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
