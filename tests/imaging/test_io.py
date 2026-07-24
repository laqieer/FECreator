import struct

import numpy as np
import pytest

from fecreator.imaging.io import (
    ImageBudgetError,
    ResourceBudget,
    _chunks,
    has_trns,
    is_indexed_png,
    load_indexed,
    load_rgb,
    png_dimensions,
    read_png_palette,
    save_indexed_png,
    save_png,
)


def test_rgb_roundtrip(tmp_path):
    rgb = np.zeros((4, 6, 3), dtype=np.uint8)
    rgb[0, 0] = (10, 20, 30)
    p = tmp_path / "x.png"
    save_png(p, rgb)
    back = load_rgb(p)
    assert back.shape == (4, 6, 3)
    assert tuple(back[0, 0]) == (10, 20, 30)


def test_budget_enforced(tmp_path):
    rgb = np.zeros((100, 100, 3), dtype=np.uint8)
    p = tmp_path / "big.png"
    save_png(p, rgb)
    with pytest.raises(ImageBudgetError):
        load_rgb(p, ResourceBudget(max_pixels=100))


def test_indexed_roundtrip_and_facts(tmp_path):
    indices = np.array([[0, 1], [1, 0]], dtype=np.uint8)
    palette = np.array([(0, 128, 0), (255, 255, 255)], dtype=np.uint8)
    p = tmp_path / "idx.png"
    save_indexed_png(p, indices, palette)
    idx2, pal2 = load_indexed(p)
    assert np.array_equal(idx2, indices)
    assert [tuple(c) for c in pal2] == [(0, 128, 0), (255, 255, 255)]
    assert png_dimensions(p) == (2, 2)
    assert is_indexed_png(p) is True
    assert has_trns(p) is False
    assert read_png_palette(p) == [(0, 128, 0), (255, 255, 255)]


# --- I-2: load_indexed budget enforcement ---


def test_load_indexed_budget_enforced(tmp_path):
    indices = np.zeros((100, 100), dtype=np.uint8)
    palette = np.array([(0, 0, 0)], dtype=np.uint8)
    p = tmp_path / "big_idx.png"
    save_indexed_png(p, indices, palette)
    with pytest.raises(ImageBudgetError):
        load_indexed(p, ResourceBudget(max_pixels=100))


# --- I-7: save_indexed_png validation ---


def test_save_indexed_palette_too_large_raises(tmp_path):
    indices = np.zeros((2, 2), dtype=np.uint8)
    palette = np.zeros((257, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="palette"):
        save_indexed_png(tmp_path / "bad.png", indices, palette)


def test_save_indexed_index_out_of_range_raises(tmp_path):
    indices = np.array([[0, 2]], dtype=np.uint8)  # index 2 but only 2 colours
    palette = np.zeros((2, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="index"):
        save_indexed_png(tmp_path / "bad.png", indices, palette)


def test_save_indexed_empty_palette_raises(tmp_path):
    indices = np.zeros((2, 2), dtype=np.uint8)
    palette = np.zeros((0, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="palette"):
        save_indexed_png(tmp_path / "bad.png", indices, palette)


def test_atomic_write_preserves_original_on_bad_dtype(tmp_path):
    """save_png with wrong dtype should not corrupt an existing file."""
    p = tmp_path / "x.png"
    rgb = np.zeros((2, 2, 3), dtype=np.uint8)
    save_png(p, rgb)
    original = p.read_bytes()
    with pytest.raises(ValueError):
        save_png(p, np.zeros((2, 2, 4), dtype=np.uint8))  # wrong channels
    assert p.read_bytes() == original  # file unchanged


# --- Fix 2: bounded PNG streaming ---


def _make_raw_chunk(tag: bytes, data: bytes) -> bytes:
    import zlib

    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def test_chunks_rejects_bad_png_signature(tmp_path):
    """File with invalid PNG signature raises ValueError."""
    p = tmp_path / "bad.bin"
    p.write_bytes(b"not a png" + b"\x00" * 50)
    with pytest.raises(ValueError, match="signature"):
        list(_chunks(p))


def test_chunks_rejects_oversized_file(tmp_path):
    """PNG larger than max_file_bytes raises ImageBudgetError."""
    indices = np.zeros((100, 100), dtype=np.uint8)
    palette = np.array([(0, 0, 0)], dtype=np.uint8)
    p = tmp_path / "big.png"
    save_indexed_png(p, indices, palette)
    # File should be >100 bytes; any valid 100x100 indexed PNG will be
    with pytest.raises(ImageBudgetError, match="byte"):
        list(_chunks(p, max_file_bytes=100))


def test_chunks_rejects_truncated_chunk_data(tmp_path):
    """PNG truncated mid-chunk-data raises ValueError."""
    indices = np.zeros((4, 4), dtype=np.uint8)
    palette = np.array([(0, 0, 0)], dtype=np.uint8)
    p = tmp_path / "ok.png"
    save_indexed_png(p, indices, palette)
    raw = p.read_bytes()
    truncated = tmp_path / "trunc.png"
    truncated.write_bytes(raw[: len(raw) // 2])
    with pytest.raises(ValueError):
        list(_chunks(truncated))


def test_chunks_rejects_oversized_non_idat_chunk(tmp_path):
    """A non-IDAT chunk claiming >4 MiB raises ImageBudgetError (bomb guard)."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 3, 0, 0, 0)
    ihdr_chunk = _make_raw_chunk(b"IHDR", ihdr_data)
    # Craft a PLTE chunk header claiming 5 MiB (don't write actual data)
    fake_len = struct.pack(">I", 5 * 1024 * 1024)
    p = tmp_path / "bomb.png"
    p.write_bytes(sig + ihdr_chunk + fake_len + b"PLTE")
    with pytest.raises((ImageBudgetError, ValueError)):
        list(_chunks(p))


def test_chunks_file_byte_budget_via_resource_budget(tmp_path):
    """ResourceBudget.max_file_bytes is respected when scanning all chunks."""
    indices = np.zeros((4, 4), dtype=np.uint8)
    palette = np.array([(0, 0, 0)], dtype=np.uint8)
    p = tmp_path / "ok.png"
    save_indexed_png(p, indices, palette)
    # 50 bytes fits sig+IHDR+PLTE but not IDAT → triggers limit mid-scan
    budget = ResourceBudget(max_file_bytes=50)
    with pytest.raises(ImageBudgetError):
        has_trns(p, budget)  # reads all chunks; hits limit before IEND
