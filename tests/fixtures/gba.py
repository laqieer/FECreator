from __future__ import annotations

import struct
import zlib
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from fecreator.imaging.io import save_indexed_png
from fecreator.specs.fire_emblem.gba.portrait_standard.layout import BACKGROUND_ZONES
from fecreator.specs.fire_emblem.gba.portrait_standard.palette import write_jasc

# index 0 = green background, index 1 = foreground
PALETTE: list[tuple[int, int, int]] = [(0, 248, 0), (80, 96, 200)]

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def build_indices() -> np.ndarray:
    idx = np.ones((112, 128), dtype=np.uint8)  # foreground everywhere
    for zone in BACKGROUND_ZONES:  # required background zones -> 0
        idx[zone.y : zone.y + zone.h, zone.x : zone.x + zone.w] = 0
    idx[0, :] = 0  # a border ring of background
    idx[-1, :] = 0
    idx[:, 0] = 0
    idx[:, -1] = 0
    return idx


def write_valid_package(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    save_indexed_png(directory / "hero.png", build_indices(), np.array(PALETTE, dtype=np.uint8))
    write_jasc(directory / "hero.pal", PALETTE)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def write_raw_indexed_png(
    path: Path,
    indices: np.ndarray,
    palette: Sequence[tuple[int, int, int]],
    *,
    bit_depth: int = 8,
    trns: Sequence[int] | None = None,
) -> None:
    """Encode an indexed PNG from scratch, independent of the production codec.

    Supports injecting a ``tRNS`` chunk, a non-8-bit depth, non-snapped
    palettes, and out-of-range indices so negative fixtures cannot share a
    defect with ``save_indexed_png``/``read_png_palette``.
    """
    idx = indices.astype(np.uint8)
    height, width = idx.shape
    ihdr = struct.pack(">IIBBBBB", width, height, bit_depth, 3, 0, 0, 0)
    plte = b"".join(bytes((r, g, b)) for r, g, b in palette)

    raw = bytearray()
    if bit_depth == 8:
        for row in idx:
            raw.append(0)
            raw.extend(row.tobytes())
    elif bit_depth == 4:
        for row in idx:
            raw.append(0)
            values = row.tolist()
            for i in range(0, len(values), 2):
                hi = values[i] & 0x0F
                lo = values[i + 1] & 0x0F if i + 1 < len(values) else 0
                raw.append((hi << 4) | lo)
    else:  # pragma: no cover - only 4/8 used by fixtures
        raise ValueError(f"unsupported bit_depth {bit_depth}")

    body = _PNG_SIG + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"PLTE", plte)
    if trns is not None:
        body += _png_chunk(b"tRNS", bytes(trns))
    body += _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + _png_chunk(b"IEND", b"")
    path.write_bytes(body)
