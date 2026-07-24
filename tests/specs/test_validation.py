from __future__ import annotations

from pathlib import Path

import numpy as np

from fecreator.contracts.diagnostics import Severity, has_errors
from fecreator.imaging.io import save_indexed_png
from fecreator.specs.fire_emblem.gba.portrait_standard.palette import write_jasc
from fecreator.specs.fire_emblem.gba.portrait_standard.validation import validate_package
from tests.fixtures.gba import PALETTE, build_indices, write_valid_package


def test_valid_package_has_no_errors(tmp_path: Path) -> None:
    write_valid_package(tmp_path)
    diags = validate_package(tmp_path)
    assert not has_errors(diags)


def test_missing_sheet(tmp_path: Path) -> None:
    diags = validate_package(tmp_path)
    assert any(d.code == "MISSING_SHEET" and d.severity is Severity.ERROR for d in diags)


def test_multiple_sheets(tmp_path: Path) -> None:
    write_valid_package(tmp_path)
    save_indexed_png(tmp_path / "extra.png", build_indices(), np.array(PALETTE, dtype=np.uint8))
    codes = {d.code for d in validate_package(tmp_path)}
    assert "MULTIPLE_SHEETS" in codes


def test_bad_png(tmp_path: Path) -> None:
    (tmp_path / "hero.png").write_bytes(b"not a real png at all")
    codes = {d.code for d in validate_package(tmp_path)}
    assert "BAD_PNG" in codes


def test_bad_dimensions(tmp_path: Path) -> None:
    save_indexed_png(
        tmp_path / "hero.png",
        np.zeros((10, 10), np.uint8),
        np.array(PALETTE, dtype=np.uint8),
    )
    codes = {d.code for d in validate_package(tmp_path)}
    assert "SHEET_BAD_DIMS" in codes


def test_missing_palette(tmp_path: Path) -> None:
    save_indexed_png(tmp_path / "hero.png", build_indices(), np.array(PALETTE, dtype=np.uint8))
    codes = {d.code for d in validate_package(tmp_path)}
    assert "MISSING_PALETTE" in codes


def test_palette_count_mismatch(tmp_path: Path) -> None:
    write_valid_package(tmp_path)
    (tmp_path / "hero.pal").write_bytes(b"JASC-PAL\r\n0100\r\n1\r\n0 248 0\r\n")
    codes = {d.code for d in validate_package(tmp_path)}
    assert "PALETTE_COUNT_MISMATCH" in codes


def test_palette_mismatch(tmp_path: Path) -> None:
    write_valid_package(tmp_path)
    (tmp_path / "hero.pal").write_bytes(b"JASC-PAL\r\n0100\r\n2\r\n0 0 0\r\n1 1 1\r\n")
    codes = {d.code for d in validate_package(tmp_path)}
    assert "PALETTE_COLOR_MISMATCH" in codes


def test_enclosed_background_hole(tmp_path: Path) -> None:
    idx = build_indices()
    idx[50:54, 50:54] = 0  # enclosed background inside foreground
    save_indexed_png(tmp_path / "hero.png", idx, np.array(PALETTE, dtype=np.uint8))
    write_jasc(tmp_path / "hero.pal", PALETTE)
    codes = {d.code for d in validate_package(tmp_path)}
    assert "BACKGROUND_HOLE" in codes


def test_unsafe_zone_flagged(tmp_path: Path) -> None:
    idx = build_indices()
    idx[0:48, 0:16] = 1  # upper_left strip must stay background
    save_indexed_png(tmp_path / "hero.png", idx, np.array(PALETTE, dtype=np.uint8))
    write_jasc(tmp_path / "hero.pal", PALETTE)
    diags = validate_package(tmp_path)
    codes = {d.code for d in diags}
    assert "UNSAFE_ZONE" in codes
    assert any(
        d.code == "UNSAFE_ZONE" and d.where == "upper_left" and d.severity is Severity.ERROR
        for d in diags
    )
