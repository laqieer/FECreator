from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict

from fecreator.contracts.diagnostics import Diagnostic, error, has_errors
from fecreator.core.hashing import sha256_bytes
from fecreator.imaging.io import ResourceBudget, load_indexed, save_indexed_png
from fecreator.reporting.sanitize import sanitize_path, sanitize_text
from fecreator.specs.fire_emblem.gba.portrait_standard.layout import (
    BG_INDEX,
    MAX_COLORS,
    SHEET_H,
    SHEET_W,
)
from fecreator.specs.fire_emblem.gba.portrait_standard.palette import read_jasc, write_jasc
from fecreator.specs.fire_emblem.gba.portrait_standard.spec import FeGbaPortraitStandard

_EMPTY_HASH = ""


class RoundtripEvidence(BaseModel):
    """Path-free evidence from a deterministic canonical package roundtrip."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    dimensions: tuple[int, int]
    color_count: int
    background_index: int
    pixel_sha256: str
    roundtrip_pixel_sha256: str
    palette_sha256: str
    roundtrip_palette_sha256: str
    diagnostics: tuple[Diagnostic, ...] = ()


def decode_roundtrip(
    package_dir: Path, *, budget: ResourceBudget | None = None
) -> RoundtripEvidence:
    """Produce deterministic evidence that a valid package survives canonical I/O.

    This is a ROM-free structural probe, not proof that an external FEBuilder
    executable accepted the package. It validates the input first, then uses
    the indexed PNG and JASC boundaries to re-encode, reload, and compare the
    canonical index and ordered-palette representations.
    """
    try:
        validation_diagnostics = _safe_diagnostics(FeGbaPortraitStandard().validate(package_dir))
    except Exception as exc:
        return _failure(
            (
                _safe_error(
                    "ROUNDTRIP_VALIDATION_FAILED",
                    f"cannot strictly validate canonical package: {exc}",
                ),
            )
        )
    if has_errors(validation_diagnostics):
        return _failure(validation_diagnostics)

    try:
        sheet_path, palette_path = _canonical_paths(package_dir)
        indices, png_palette = load_indexed(sheet_path, budget)
        jasc_palette = np.asarray(read_jasc(palette_path), dtype=np.uint8)
    except Exception as exc:
        return _failure(
            (
                _safe_error(
                    "ROUNDTRIP_DECODE_FAILED",
                    f"cannot decode canonical package: {exc}",
                ),
            )
        )

    dimensions = (int(indices.shape[1]), int(indices.shape[0])) if indices.ndim == 2 else (0, 0)
    color_count = int(jasc_palette.shape[0]) if jasc_palette.ndim == 2 else 0
    pixel_sha256 = _array_sha256(indices)
    palette_sha256 = _array_sha256(jasc_palette)
    source_diagnostics = _source_contract_diagnostics(
        dimensions,
        color_count,
        png_palette,
        jasc_palette,
    )
    if source_diagnostics:
        return _failure(
            source_diagnostics,
            dimensions=dimensions,
            color_count=color_count,
            pixel_sha256=pixel_sha256,
            palette_sha256=palette_sha256,
        )

    try:
        with tempfile.TemporaryDirectory(prefix="fecreator-febuilder-roundtrip-") as temp_root:
            roundtrip_dir = Path(temp_root) / "package"
            roundtrip_dir.mkdir()
            roundtrip_png = roundtrip_dir / "roundtrip.png"
            roundtrip_pal = roundtrip_dir / "roundtrip.pal"
            save_indexed_png(roundtrip_png, indices, jasc_palette)
            roundtrip_palette = [(int(row[0]), int(row[1]), int(row[2])) for row in jasc_palette]
            write_jasc(roundtrip_pal, roundtrip_palette)

            roundtrip_validation = _safe_diagnostics(
                FeGbaPortraitStandard().validate(roundtrip_dir)
            )
            if has_errors(roundtrip_validation):
                return _failure(
                    (
                        _safe_error(
                            "ROUNDTRIP_VALIDATION_FAILED",
                            "canonical roundtrip package failed strict validation",
                        ),
                    ),
                    dimensions=dimensions,
                    color_count=color_count,
                    pixel_sha256=pixel_sha256,
                    palette_sha256=palette_sha256,
                )

            reloaded_indices, reloaded_png_palette = load_indexed(roundtrip_png, budget)
            reloaded_jasc_palette = np.asarray(read_jasc(roundtrip_pal), dtype=np.uint8)
    except Exception as exc:
        return _failure(
            (
                _safe_error(
                    "ROUNDTRIP_REENCODE_FAILED",
                    f"cannot re-encode or reload canonical package: {exc}",
                ),
            ),
            dimensions=dimensions,
            color_count=color_count,
            pixel_sha256=pixel_sha256,
            palette_sha256=palette_sha256,
        )

    roundtrip_pixel_sha256 = _array_sha256(reloaded_indices)
    roundtrip_palette_sha256 = _array_sha256(reloaded_jasc_palette)
    comparison_diagnostics = _comparison_diagnostics(
        dimensions,
        color_count,
        indices,
        jasc_palette,
        reloaded_indices,
        reloaded_png_palette,
        reloaded_jasc_palette,
    )
    if comparison_diagnostics:
        return _failure(
            comparison_diagnostics,
            dimensions=dimensions,
            color_count=color_count,
            pixel_sha256=pixel_sha256,
            roundtrip_pixel_sha256=roundtrip_pixel_sha256,
            palette_sha256=palette_sha256,
            roundtrip_palette_sha256=roundtrip_palette_sha256,
        )

    return RoundtripEvidence(
        ok=True,
        dimensions=dimensions,
        color_count=color_count,
        background_index=BG_INDEX,
        pixel_sha256=pixel_sha256,
        roundtrip_pixel_sha256=roundtrip_pixel_sha256,
        palette_sha256=palette_sha256,
        roundtrip_palette_sha256=roundtrip_palette_sha256,
    )


def _canonical_paths(package_dir: Path) -> tuple[Path, Path]:
    sheets = sorted(package_dir.glob("*.png"))
    if len(sheets) != 1:
        raise ValueError("strict validation did not leave exactly one PNG")
    sheet = sheets[0]
    expected_palette_name = f"{sheet.stem}.pal".casefold()
    palettes = sorted(
        (
            path
            for path in package_dir.iterdir()
            if path.is_file()
            and path.suffix.casefold() == ".pal"
            and path.name.casefold() == expected_palette_name
        ),
        key=lambda path: (path.name.casefold(), path.name),
    )
    if len(palettes) != 1:
        raise ValueError("strict validation did not leave exactly one matching JASC palette")
    return sheet, palettes[0]


def _source_contract_diagnostics(
    dimensions: tuple[int, int],
    color_count: int,
    png_palette: np.ndarray,
    jasc_palette: np.ndarray,
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    if dimensions != (SHEET_W, SHEET_H):
        diagnostics.append(_safe_error("ROUNDTRIP_GEOMETRY_MISMATCH", "source dimensions changed"))
    if not 1 <= color_count <= MAX_COLORS:
        diagnostics.append(
            _safe_error("ROUNDTRIP_COLOR_COUNT_MISMATCH", "source color count is invalid")
        )
    if BG_INDEX != 0:
        diagnostics.append(
            _safe_error("ROUNDTRIP_BACKGROUND_INDEX_MISMATCH", "background index is invalid")
        )
    if not np.array_equal(png_palette, jasc_palette):
        diagnostics.append(
            _safe_error("ROUNDTRIP_SOURCE_PALETTE_MISMATCH", "PNG and JASC palettes differ")
        )
    return tuple(diagnostics)


def _comparison_diagnostics(
    dimensions: tuple[int, int],
    color_count: int,
    indices: np.ndarray,
    palette: np.ndarray,
    reloaded_indices: np.ndarray,
    reloaded_png_palette: np.ndarray,
    reloaded_jasc_palette: np.ndarray,
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    reloaded_dimensions = (
        (int(reloaded_indices.shape[1]), int(reloaded_indices.shape[0]))
        if reloaded_indices.ndim == 2
        else (0, 0)
    )
    if reloaded_dimensions != dimensions:
        diagnostics.append(
            _safe_error("ROUNDTRIP_GEOMETRY_MISMATCH", "roundtrip dimensions differ from source")
        )
    if reloaded_jasc_palette.ndim != 2 or int(reloaded_jasc_palette.shape[0]) != color_count:
        diagnostics.append(
            _safe_error(
                "ROUNDTRIP_COLOR_COUNT_MISMATCH", "roundtrip color count differs from source"
            )
        )
    if BG_INDEX != 0:
        diagnostics.append(
            _safe_error("ROUNDTRIP_BACKGROUND_INDEX_MISMATCH", "background index is invalid")
        )
    if not np.array_equal(indices, reloaded_indices):
        diagnostics.append(_safe_error("ROUNDTRIP_PIXEL_MISMATCH", "roundtrip index pixels differ"))
    if _array_sha256(indices) != _array_sha256(reloaded_indices):
        diagnostics.append(
            _safe_error("ROUNDTRIP_PIXEL_HASH_MISMATCH", "roundtrip index hash differs")
        )
    if not np.array_equal(palette, reloaded_png_palette):
        diagnostics.append(
            _safe_error("ROUNDTRIP_PNG_PALETTE_MISMATCH", "roundtrip PNG palette differs")
        )
    if not np.array_equal(palette, reloaded_jasc_palette):
        diagnostics.append(
            _safe_error("ROUNDTRIP_PALETTE_MISMATCH", "roundtrip JASC palette differs")
        )
    if _array_sha256(palette) != _array_sha256(reloaded_jasc_palette):
        diagnostics.append(
            _safe_error("ROUNDTRIP_PALETTE_HASH_MISMATCH", "roundtrip palette hash differs")
        )
    if not np.array_equal(reloaded_png_palette, reloaded_jasc_palette):
        diagnostics.append(
            _safe_error(
                "ROUNDTRIP_RELOADED_PALETTE_MISMATCH",
                "roundtrip PNG and JASC palettes differ",
            )
        )
    return tuple(diagnostics)


def _failure(
    diagnostics: tuple[Diagnostic, ...],
    *,
    dimensions: tuple[int, int] = (0, 0),
    color_count: int = 0,
    pixel_sha256: str = _EMPTY_HASH,
    roundtrip_pixel_sha256: str = _EMPTY_HASH,
    palette_sha256: str = _EMPTY_HASH,
    roundtrip_palette_sha256: str = _EMPTY_HASH,
) -> RoundtripEvidence:
    return RoundtripEvidence(
        ok=False,
        dimensions=dimensions,
        color_count=color_count,
        background_index=BG_INDEX,
        pixel_sha256=pixel_sha256,
        roundtrip_pixel_sha256=roundtrip_pixel_sha256,
        palette_sha256=palette_sha256,
        roundtrip_palette_sha256=roundtrip_palette_sha256,
        diagnostics=tuple(sorted(diagnostics, key=_diagnostic_sort_key)),
    )


def _safe_diagnostics(diagnostics: list[Diagnostic]) -> tuple[Diagnostic, ...]:
    return tuple(
        sorted(
            (
                Diagnostic(
                    code=diagnostic.code,
                    severity=diagnostic.severity,
                    message=sanitize_text(diagnostic.message),
                    where=sanitize_path(diagnostic.where) if diagnostic.where else None,
                )
                for diagnostic in diagnostics
            ),
            key=_diagnostic_sort_key,
        )
    )


def _safe_error(code: str, message: str) -> Diagnostic:
    return error(code, sanitize_text(message))


def _diagnostic_sort_key(diagnostic: Diagnostic) -> tuple[str, str, str, str]:
    return (
        diagnostic.severity.value,
        diagnostic.code,
        diagnostic.where or "",
        diagnostic.message,
    )


def _array_sha256(array: np.ndarray) -> str:
    return sha256_bytes(np.ascontiguousarray(array, dtype=np.uint8).tobytes())
