from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from fecreator.specs.fire_emblem.gba.portrait_standard.layout import MAX_COLORS

RGB = tuple[int, int, int]


def snap_gba_5bit(rgb: RGB) -> RGB:
    """Snap each 8-bit channel to the GBA 5-bit grid: ``(c >> 3) << 3``."""
    r, g, b = rgb
    return ((r >> 3) << 3, (g >> 3) << 3, (b >> 3) << 3)


def to_bgr555(rgb: RGB) -> int:
    """Encode an RGB triple as little-endian BGR555: ``r5 | g5<<5 | b5<<10``."""
    r, g, b = rgb
    return (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)


def _validate_palette(palette: Sequence[RGB]) -> None:
    if not 1 <= len(palette) <= MAX_COLORS:
        raise ValueError(f"JASC palette must have 1..16 entries, got {len(palette)}")
    for entry in palette:
        if len(entry) != 3:
            raise ValueError(f"JASC palette entry must be RGB, got {entry!r}")
        for channel in entry:
            if not isinstance(channel, int) or not 0 <= channel <= 255:
                raise ValueError(f"JASC palette channel {channel!r} out of range 0..255")


def _fsync_dir(directory: Path) -> None:
    """Best-effort fsync of a directory so a rename is durable.

    POSIX requires syncing the parent directory after ``os.replace`` for the
    new name to survive a crash. Platforms/filesystems that cannot open a
    directory for fsync (notably Windows) are treated as a safe no-op.
    """
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def write_jasc(path: Path, palette: Sequence[RGB]) -> None:
    """Write a JASC-PAL sidecar atomically with CRLF line endings.

    Validates the palette (1..16 entries, integer channels 0..255) and writes
    through a same-directory temp file + fsync + ``os.replace`` so an
    interrupted write can never leave a truncated ``.pal`` at the destination.
    The parent directory is fsynced after the replace so the new name is
    durable (best effort; no-op where unsupported).
    """
    _validate_palette(palette)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["JASC-PAL", "0100", str(len(palette))]
    lines += [f"{r} {g} {b}" for r, g, b in palette]
    payload = ("\r\n".join(lines) + "\r\n").encode("ascii")

    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".pal.tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    _fsync_dir(path.parent)


def read_jasc(path: Path) -> list[RGB]:
    """Parse a JASC-PAL sidecar, failing closed on malformed content.

    Rejects bad magic/version, non-numeric or mismatched counts, malformed
    rows, out-of-range channels, and trailing non-blank data beyond the
    declared entry count (a single trailing blank line is tolerated).
    """
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
    trailing = [line for line in rows[3 + count :] if line.strip()]
    if trailing:
        raise ValueError(f"JASC-PAL has trailing data after {count} entries in {path.name!r}")
    out: list[RGB] = []
    for row in body:
        parts = row.split()
        if len(parts) != 3:
            raise ValueError(f"malformed JASC-PAL row {row!r} in {path.name!r}")
        try:
            r, g, b = (int(v) for v in parts)
        except ValueError as exc:
            raise ValueError(
                f"non-numeric JASC-PAL channel in row {row!r} in {path.name!r}"
            ) from exc
        for channel in (r, g, b):
            if not 0 <= channel <= 255:
                raise ValueError(f"JASC-PAL channel {channel} out of range in {path.name!r}")
        out.append((r, g, b))
    return out
