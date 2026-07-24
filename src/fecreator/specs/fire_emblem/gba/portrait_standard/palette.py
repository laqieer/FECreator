from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

RGB = tuple[int, int, int]


def snap_gba_5bit(rgb: RGB) -> RGB:
    """Snap each 8-bit channel to the GBA 5-bit grid: ``(c >> 3) << 3``."""
    r, g, b = rgb
    return ((r >> 3) << 3, (g >> 3) << 3, (b >> 3) << 3)


def to_bgr555(rgb: RGB) -> int:
    """Encode an RGB triple as little-endian BGR555: ``r5 | g5<<5 | b5<<10``."""
    r, g, b = rgb
    return (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)


def write_jasc(path: Path, palette: Sequence[RGB]) -> None:
    """Write a JASC-PAL sidecar with CRLF line endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["JASC-PAL", "0100", str(len(palette))]
    lines += [f"{r} {g} {b}" for r, g, b in palette]
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))


def read_jasc(path: Path) -> list[RGB]:
    """Parse a JASC-PAL sidecar, failing closed on malformed content."""
    rows = path.read_text(encoding="ascii").splitlines()
    if len(rows) < 3 or rows[0] != "JASC-PAL" or rows[1] != "0100":
        raise ValueError(f"not a valid JASC-PAL file: {path.name!r}")
    try:
        count = int(rows[2])
    except ValueError as exc:
        raise ValueError(f"invalid JASC-PAL entry count in {path.name!r}") from exc
    body = rows[3 : 3 + count]
    if len(body) != count:
        raise ValueError(f"JASC-PAL declares {count} entries but has {len(body)} in {path.name!r}")
    out: list[RGB] = []
    for row in body:
        parts = row.split()
        if len(parts) != 3:
            raise ValueError(f"malformed JASC-PAL row {row!r} in {path.name!r}")
        r, g, b = (int(v) for v in parts)
        for channel in (r, g, b):
            if not 0 <= channel <= 255:
                raise ValueError(f"JASC-PAL channel {channel} out of range in {path.name!r}")
        out.append((r, g, b))
    return out
