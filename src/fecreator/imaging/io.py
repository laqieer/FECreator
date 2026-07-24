from __future__ import annotations

import struct
import zlib
from collections.abc import Iterator
from pathlib import Path

import numpy as np
from PIL import Image
from pydantic import BaseModel

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


class ResourceBudget(BaseModel):
    max_pixels: int = 8_000_000
    max_palette: int = 256


class ImageBudgetError(Exception):
    """Raised when an image exceeds a configured resource budget."""


def load_rgb(path: Path, budget: ResourceBudget | None = None) -> np.ndarray:
    if budget is None:
        budget = ResourceBudget()
    with Image.open(path) as im:
        width, height = im.size
        if width * height > budget.max_pixels:
            raise ImageBudgetError(f"{width * height} px exceeds {budget.max_pixels}")
        return np.asarray(im.convert("RGB"), dtype=np.uint8)


def save_png(path: Path, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb, mode="RGB").save(path, format="PNG")


def save_indexed_png(path: Path, indices: np.ndarray, palette: np.ndarray) -> None:
    """Write a canonical 8-bit indexed PNG (color type 3) with exactly len(palette)
    PLTE entries and no tRNS chunk, so the palette count is fully deterministic."""
    path.parent.mkdir(parents=True, exist_ok=True)
    idx = indices.astype(np.uint8)
    pal = palette.astype(np.uint8).reshape(-1, 3)
    height, width = idx.shape
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0)
    raw = bytearray()
    for row in idx:
        raw.append(0)  # PNG filter type 0 (none)
        raw.extend(row.tobytes())
    idat = zlib.compress(bytes(raw), 9)
    png = (
        _PNG_SIG
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"PLTE", pal.tobytes())
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def load_indexed(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with Image.open(path) as im:
        indices = np.asarray(im, dtype=np.uint8)
    palette = np.array(read_png_palette(path), dtype=np.uint8)
    return indices, palette


def _iter_chunks(data: bytes) -> Iterator[tuple[str, bytes]]:
    offset = len(_PNG_SIG)
    while offset < len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        ctype = data[offset + 4 : offset + 8].decode("ascii")
        start = offset + 8
        yield ctype, data[start : start + length]
        offset = start + length + 4


def _chunks(path: Path) -> Iterator[tuple[str, bytes]]:
    return _iter_chunks(path.read_bytes())


def png_dimensions(path: Path) -> tuple[int, int]:
    for ctype, body in _chunks(path):
        if ctype == "IHDR":
            width, height = struct.unpack(">II", body[:8])
            return int(width), int(height)
    raise ValueError("no IHDR chunk")


def is_indexed_png(path: Path) -> bool:
    for ctype, body in _chunks(path):
        if ctype == "IHDR":
            return body[9] == 3
    return False


def read_png_palette(path: Path) -> list[tuple[int, int, int]]:
    for ctype, body in _chunks(path):
        if ctype == "PLTE":
            return [(body[i], body[i + 1], body[i + 2]) for i in range(0, len(body), 3)]
    return []


def has_trns(path: Path) -> bool:
    return any(ctype == "tRNS" for ctype, _ in _chunks(path))
