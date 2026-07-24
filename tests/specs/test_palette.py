from __future__ import annotations

from pathlib import Path

import pytest

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


def test_write_jasc_leaves_no_temp_file(tmp_path: Path) -> None:
    p = tmp_path / "x.pal"
    write_jasc(p, [(0, 0, 0), (248, 128, 0)])
    assert {c.name for c in tmp_path.iterdir()} == {"x.pal"}


def test_write_jasc_rejects_empty_palette(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="1..16"):
        write_jasc(tmp_path / "e.pal", [])


def test_write_jasc_rejects_palette_gt16(tmp_path: Path) -> None:
    palette = [(i, i, i) for i in range(0, 17)]
    with pytest.raises(ValueError, match="1..16"):
        write_jasc(tmp_path / "big.pal", palette)


def test_write_jasc_rejects_channel_out_of_range(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="channel"):
        write_jasc(tmp_path / "oor.pal", [(0, 0, 0), (256, 0, 0)])


def test_read_jasc_rejects_trailing_data(tmp_path: Path) -> None:
    p = tmp_path / "trail.pal"
    p.write_bytes(b"JASC-PAL\r\n0100\r\n1\r\n0 0 0\r\n9 9 9\r\n")
    with pytest.raises(ValueError, match="trailing"):
        read_jasc(p)


def test_read_jasc_allows_trailing_blank_line(tmp_path: Path) -> None:
    p = tmp_path / "blank.pal"
    p.write_bytes(b"JASC-PAL\r\n0100\r\n1\r\n0 0 0\r\n\r\n")
    assert read_jasc(p) == [(0, 0, 0)]


def test_read_jasc_numeric_error_has_context(tmp_path: Path) -> None:
    p = tmp_path / "nan.pal"
    p.write_bytes(b"JASC-PAL\r\n0100\r\n1\r\nxx 0 0\r\n")
    with pytest.raises(ValueError, match="nan.pal"):
        read_jasc(p)


def test_write_jasc_fsyncs_parent_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import fecreator.specs.fire_emblem.gba.portrait_standard.palette as pal

    synced: list[Path] = []
    monkeypatch.setattr(pal, "_fsync_dir", lambda d: synced.append(Path(d)))
    pal.write_jasc(tmp_path / "x.pal", [(0, 0, 0), (248, 128, 0)])
    assert tmp_path in synced
