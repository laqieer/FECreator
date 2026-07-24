from __future__ import annotations

from pathlib import Path

from fecreator.specs.fire_emblem.gba.portrait_standard.palette import (
    read_jasc,
    snap_gba_5bit,
    to_bgr555,
    write_jasc,
)


def test_snap_masks_low_three_bits() -> None:
    assert snap_gba_5bit((255, 130, 7)) == (248, 128, 0)


def test_bgr555_encoding() -> None:
    assert to_bgr555((248, 0, 0)) == 31  # r5=31
    assert to_bgr555((0, 248, 0)) == 31 << 5  # g5=31
    assert to_bgr555((0, 0, 248)) == 31 << 10  # b5=31


def test_jasc_roundtrip_with_crlf(tmp_path: Path) -> None:
    palette = [(0, 0, 0), (248, 128, 0)]
    p = tmp_path / "x.pal"
    write_jasc(p, palette)
    raw = p.read_bytes()
    assert raw.startswith(b"JASC-PAL\r\n0100\r\n2\r\n")
    assert read_jasc(p) == palette


def test_read_jasc_rejects_bad_magic(tmp_path: Path) -> None:
    p = tmp_path / "bad.pal"
    p.write_bytes(b"NOTPAL\r\n0100\r\n1\r\n0 0 0\r\n")
    try:
        read_jasc(p)
    except ValueError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError("expected ValueError for bad JASC magic")


def test_read_jasc_rejects_channel_out_of_range(tmp_path: Path) -> None:
    p = tmp_path / "oor.pal"
    p.write_bytes(b"JASC-PAL\r\n0100\r\n1\r\n256 0 0\r\n")
    try:
        read_jasc(p)
    except ValueError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError("expected ValueError for out-of-range channel")
