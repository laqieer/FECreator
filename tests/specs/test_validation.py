from __future__ import annotations

import os
import struct
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from fecreator.contracts.diagnostics import Severity, has_errors
from fecreator.imaging.io import save_indexed_png
from fecreator.specs.fire_emblem.gba.portrait_standard.palette import write_jasc
from fecreator.specs.fire_emblem.gba.portrait_standard.validation import validate_package
from tests.fixtures.gba import (
    PALETTE,
    build_indices,
    write_raw_indexed_png,
    write_valid_package,
)


def _error_codes(diags: list) -> set[str]:
    return {d.code for d in diags if d.severity is Severity.ERROR}


def test_valid_package_has_no_errors(tmp_path: Path) -> None:
    write_valid_package(tmp_path)
    diags = validate_package(tmp_path)
    assert not has_errors(diags)


def test_no_warnings_are_emitted(tmp_path: Path) -> None:
    # Canonical validation promotes every contract violation to an error.
    save_indexed_png(tmp_path / "hero.png", build_indices(), np.array(PALETTE, dtype=np.uint8))
    diags = validate_package(tmp_path)
    assert all(d.severity is not Severity.WARNING for d in diags)


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


def test_missing_palette_is_error(tmp_path: Path) -> None:
    save_indexed_png(tmp_path / "hero.png", build_indices(), np.array(PALETTE, dtype=np.uint8))
    diags = validate_package(tmp_path)
    assert any(d.code == "MISSING_PALETTE" and d.severity is Severity.ERROR for d in diags)


def test_extra_foreign_palette_flagged(tmp_path: Path) -> None:
    write_valid_package(tmp_path)
    write_jasc(tmp_path / "other.pal", PALETTE)
    diags = validate_package(tmp_path)
    assert any(d.code == "EXTRA_PALETTE" and d.where == "other.pal" for d in diags)


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


def test_required_slot_empty_flagged(tmp_path: Path) -> None:
    idx = build_indices()
    idx[16:48, 96:128] = 0  # blank the whole mini slot
    save_indexed_png(tmp_path / "hero.png", idx, np.array(PALETTE, dtype=np.uint8))
    write_jasc(tmp_path / "hero.pal", PALETTE)
    diags = validate_package(tmp_path)
    assert any(
        d.code == "SLOT_EMPTY" and d.where == "mini" and d.severity is Severity.ERROR for d in diags
    )


# --- Independent (non-shared-codec) negative fixtures --------------------------


def test_trns_present_isolated(tmp_path: Path) -> None:
    write_raw_indexed_png(tmp_path / "hero.png", build_indices(), PALETTE, trns=[254, 255])
    write_jasc(tmp_path / "hero.pal", PALETTE)
    assert _error_codes(validate_package(tmp_path)) == {"TRNS_PRESENT"}


def test_bad_bit_depth_isolated(tmp_path: Path) -> None:
    write_raw_indexed_png(tmp_path / "hero.png", build_indices(), PALETTE, bit_depth=4)
    write_jasc(tmp_path / "hero.pal", PALETTE)
    assert _error_codes(validate_package(tmp_path)) == {"SHEET_BAD_BIT_DEPTH"}


def test_index_out_of_range_isolated(tmp_path: Path) -> None:
    idx = build_indices()
    idx[60, 60] = 5  # references a palette entry that does not exist
    write_raw_indexed_png(tmp_path / "hero.png", idx, PALETTE)
    write_jasc(tmp_path / "hero.pal", PALETTE)
    assert _error_codes(validate_package(tmp_path)) == {"INDEX_OUT_OF_RANGE"}


def test_non_snapped_palette_isolated(tmp_path: Path) -> None:
    palette = [(0, 248, 0), (81, 96, 200)]  # 81 -> snaps to 80
    write_raw_indexed_png(tmp_path / "hero.png", build_indices(), palette)
    write_jasc_nonsnapped(tmp_path / "hero.pal", palette)
    assert _error_codes(validate_package(tmp_path)) == {"PALETTE_NOT_SNAPPED"}


def write_jasc_nonsnapped(path: Path, palette: list) -> None:
    lines = ["JASC-PAL", "0100", str(len(palette))]
    lines += [f"{r} {g} {b}" for r, g, b in palette]
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))


def test_writer_output_verified_independently(tmp_path: Path) -> None:
    write_valid_package(tmp_path)
    data = (tmp_path / "hero.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"

    # Independently walk chunks and inspect raw IHDR / PLTE bytes.
    offset = 8
    ihdr_body = b""
    plte_body = b""
    while offset < len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        ctype = data[offset + 4 : offset + 8]
        chunk = data[offset + 8 : offset + 8 + length]
        if ctype == b"IHDR":
            ihdr_body = chunk
        elif ctype == b"PLTE":
            plte_body = chunk
        offset += 12 + length
    width, height, bit_depth, colour_type = struct.unpack(">IIBB", ihdr_body[:10])
    assert (width, height, bit_depth, colour_type) == (128, 112, 8, 3)
    expected_plte = b"".join(bytes((r, g, b)) for r, g, b in PALETTE)
    assert plte_body == expected_plte

    # Independently decode to RGB and confirm PLTE is applied as RGB (not BGR).
    rgb = np.asarray(Image.open(tmp_path / "hero.png").convert("RGB"))
    assert tuple(int(v) for v in rgb[60, 60]) == PALETTE[1]  # foreground
    assert tuple(int(v) for v in rgb[0, 0]) == PALETTE[0]  # background border


def test_symlinked_sheet_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside_hero.png"
    save_indexed_png(outside, build_indices(), np.array(PALETTE, dtype=np.uint8))
    package = tmp_path / "pkg"
    package.mkdir()
    link = package / "hero.png"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")
    write_jasc(package / "hero.pal", PALETTE)
    codes = {d.code for d in validate_package(package)}
    assert "UNSAFE_PATH" in codes
