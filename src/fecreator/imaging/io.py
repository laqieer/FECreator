from __future__ import annotations

import contextlib
import os
import struct
import tempfile
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


def _check_pixel_budget(width: int, height: int, budget: ResourceBudget) -> None:
    if width * height > budget.max_pixels:
        raise ImageBudgetError(f"{width * height} px exceeds {budget.max_pixels}")


def load_rgb(path: Path, budget: ResourceBudget | None = None) -> np.ndarray:
    if budget is None:
        budget = ResourceBudget()
    with Image.open(path) as im:
        width, height = im.size
        _check_pixel_budget(width, height, budget)
        return np.asarray(im.convert("RGB"), dtype=np.uint8)


def save_png(path: Path, rgb: np.ndarray) -> None:
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"expected (H, W, 3) RGB array, got shape {rgb.shape}")
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_png(path, lambda tmp: Image.fromarray(rgb).save(tmp, format="PNG"))


def save_indexed_png(path: Path, indices: np.ndarray, palette: np.ndarray) -> None:
    """Write a canonical 8-bit indexed PNG (color type 3).

    Validates: palette length 1..256; all index values < len(palette).
    Write is atomic (temp + os.replace) so an interrupted save cannot corrupt
    an existing file at the destination.
    """
    pal = palette.astype(np.uint8).reshape(-1, 3)
    n_colours = len(pal)
    if n_colours == 0:
        raise ValueError("palette must not be empty")
    if n_colours > 256:
        raise ValueError(f"palette has {n_colours} entries; PNG PLTE limit is 256")
    idx = indices.astype(np.uint8)
    if idx.size > 0 and int(idx.max()) >= n_colours:
        raise ValueError(
            f"index value {int(idx.max())} is out of range for palette of {n_colours} colours"
        )
    path.parent.mkdir(parents=True, exist_ok=True)

    def _write(tmp: str) -> None:
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
        Path(tmp).write_bytes(png)

    _atomic_write_png(path, _write)


def _atomic_write_png(path: Path, write_fn: object) -> None:
    """Write via a temp file in the same directory, then os.replace for atomicity."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".png.tmp")
    try:
        os.close(fd)
        write_fn(tmp)  # type: ignore[operator]
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def load_indexed(path: Path, budget: ResourceBudget | None = None) -> tuple[np.ndarray, np.ndarray]:
    if budget is None:
        budget = ResourceBudget()
    w, h = png_dimensions(path)
    _check_pixel_budget(w, h, budget)
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
