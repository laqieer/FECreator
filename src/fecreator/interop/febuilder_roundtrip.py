from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict

from fecreator.contracts.diagnostics import DiagData, Diagnostic, error, has_errors
from fecreator.core.hashing import sha256_bytes
from fecreator.imaging.io import ImageBudgetError, ResourceBudget, load_indexed, save_indexed_png
from fecreator.reporting.sanitize import sanitize_path, sanitize_text
from fecreator.specs.fire_emblem.gba.portrait_standard.layout import (
    BACKGROUND_ZONES,
    MAX_COLORS,
    SHEET_H,
    SHEET_W,
)
from fecreator.specs.fire_emblem.gba.portrait_standard.palette import read_jasc, write_jasc
from fecreator.specs.fire_emblem.gba.portrait_standard.spec import FeGbaPortraitStandard

_EMPTY_HASH = ""

UNKNOWN_BACKGROUND_INDEX = -1
"""Recorded when decoded pixel data never established a single background index."""

# Expected failures while parsing, decoding, and re-encoding canonical packages.
# Anything else is a programming error and propagates instead of becoming evidence.
_EXPECTED_ERRORS = (ImageBudgetError, ValueError, OSError)

# Bounded, stable exception-type codes. Diagnostic text stays fixed so evidence
# never carries exception messages, temporary basenames, or filesystem paths.
_EXCEPTION_TYPE_CODES: tuple[tuple[type[BaseException], str], ...] = (
    (ImageBudgetError, "image_budget_error"),
    (FileNotFoundError, "file_not_found_error"),
    (PermissionError, "permission_error"),
    (ValueError, "value_error"),
    (OSError, "os_error"),
)


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


class PackageDigest(BaseModel):
    """Path-free digest decoded straight from a canonical package on disk."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dimensions: tuple[int, int]
    color_count: int
    background_index: int
    pixel_sha256: str
    palette_sha256: str


def decode_package_digest(
    package_dir: Path, *, budget: ResourceBudget | None = None
) -> PackageDigest | None:
    """Decode a canonical package into the values roundtrip evidence records.

    Returns ``None`` when the package cannot be decoded through the canonical
    indexed-PNG and JASC boundaries. Callers use this to bind previously
    recorded evidence to the package bytes actually present on disk. ``budget``
    bounds this decode only; callers that pass nothing get the default image
    budgets.
    """
    try:
        sheet_path, palette_path = _canonical_paths(package_dir)
        indices, _ = load_indexed(sheet_path, budget)
        jasc_palette = np.asarray(read_jasc(palette_path), dtype=np.uint8)
    except _EXPECTED_ERRORS:
        return None
    if indices.ndim != 2 or jasc_palette.ndim != 2:
        return None
    return PackageDigest(
        dimensions=(int(indices.shape[1]), int(indices.shape[0])),
        color_count=int(jasc_palette.shape[0]),
        background_index=_decoded_background_index(indices),
        pixel_sha256=_array_sha256(indices),
        palette_sha256=_array_sha256(jasc_palette),
    )


def decode_roundtrip(
    package_dir: Path, *, budget: ResourceBudget | None = None
) -> RoundtripEvidence:
    """Produce deterministic evidence that a valid package survives canonical I/O.

    This is a ROM-free structural probe, not proof that an external FEBuilder
    executable accepted the package. It validates the input first, then uses
    the indexed PNG and JASC boundaries to re-encode, reload, and compare the
    canonical index and ordered-palette representations. Every diagnostic it
    creates has fixed text plus a bounded exception-type code, so evidence is
    reproducible and free of paths and exception messages.

    ``budget`` bounds only this probe's own decode and reload steps. Strict
    target-spec validation runs first and uses its own default image budgets,
    because the spec validation API deliberately takes no budget argument; a
    tighter budget therefore surfaces as ``ROUNDTRIP_DECODE_FAILED`` rather
    than as a validation diagnostic.
    """
    try:
        validation_diagnostics = _safe_diagnostics(FeGbaPortraitStandard().validate(package_dir))
    except _EXPECTED_ERRORS as exc:
        return _failure(
            (
                _typed_error(
                    "ROUNDTRIP_VALIDATION_FAILED",
                    "cannot strictly validate canonical package",
                    exc,
                ),
            )
        )
    if has_errors(validation_diagnostics):
        return _failure(validation_diagnostics)

    try:
        sheet_path, palette_path = _canonical_paths(package_dir)
        indices, png_palette = load_indexed(sheet_path, budget)
        jasc_palette = np.asarray(read_jasc(palette_path), dtype=np.uint8)
    except _EXPECTED_ERRORS as exc:
        return _failure(
            (_typed_error("ROUNDTRIP_DECODE_FAILED", "cannot decode canonical package", exc),)
        )

    dimensions = (int(indices.shape[1]), int(indices.shape[0])) if indices.ndim == 2 else (0, 0)
    color_count = int(jasc_palette.shape[0]) if jasc_palette.ndim == 2 else 0
    background_index = _decoded_background_index(indices)
    pixel_sha256 = _array_sha256(indices)
    palette_sha256 = _array_sha256(jasc_palette)
    source_diagnostics = _source_contract_diagnostics(
        dimensions,
        color_count,
        background_index,
        png_palette,
        jasc_palette,
    )
    if source_diagnostics:
        return _failure(
            source_diagnostics,
            dimensions=dimensions,
            color_count=color_count,
            background_index=background_index,
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
                        error(
                            "ROUNDTRIP_VALIDATION_FAILED",
                            "canonical roundtrip package failed strict validation",
                        ),
                    ),
                    dimensions=dimensions,
                    color_count=color_count,
                    background_index=background_index,
                    pixel_sha256=pixel_sha256,
                    palette_sha256=palette_sha256,
                )

            reloaded_indices, reloaded_png_palette = load_indexed(roundtrip_png, budget)
            reloaded_jasc_palette = np.asarray(read_jasc(roundtrip_pal), dtype=np.uint8)
    except _EXPECTED_ERRORS as exc:
        return _failure(
            (
                _typed_error(
                    "ROUNDTRIP_REENCODE_FAILED",
                    "cannot re-encode or reload canonical package",
                    exc,
                ),
            ),
            dimensions=dimensions,
            color_count=color_count,
            background_index=background_index,
            pixel_sha256=pixel_sha256,
            palette_sha256=palette_sha256,
        )

    roundtrip_pixel_sha256 = _array_sha256(reloaded_indices)
    roundtrip_palette_sha256 = _array_sha256(reloaded_jasc_palette)
    comparison_diagnostics = _comparison_diagnostics(
        dimensions,
        color_count,
        background_index,
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
            background_index=background_index,
            pixel_sha256=pixel_sha256,
            roundtrip_pixel_sha256=roundtrip_pixel_sha256,
            palette_sha256=palette_sha256,
            roundtrip_palette_sha256=roundtrip_palette_sha256,
        )

    return RoundtripEvidence(
        ok=True,
        dimensions=dimensions,
        color_count=color_count,
        background_index=background_index,
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


def _decoded_background_index(indices: np.ndarray) -> int:
    """Read the background index out of decoded canonical background zones.

    The value is earned from pixel data: every canonical background zone must be
    fully present and uniformly filled with one and the same index. Returns
    ``UNKNOWN_BACKGROUND_INDEX`` when decoded data establishes no such index.
    """
    if indices.ndim != 2 or not BACKGROUND_ZONES:
        return UNKNOWN_BACKGROUND_INDEX
    observed: set[int] = set()
    for zone in BACKGROUND_ZONES:
        block = indices[zone.y : zone.y + zone.h, zone.x : zone.x + zone.w]
        if block.shape != (zone.h, zone.w):
            return UNKNOWN_BACKGROUND_INDEX
        observed.update(int(value) for value in np.unique(block).tolist())
        if len(observed) != 1:
            return UNKNOWN_BACKGROUND_INDEX
    return observed.pop()


def _source_contract_diagnostics(
    dimensions: tuple[int, int],
    color_count: int,
    background_index: int,
    png_palette: np.ndarray,
    jasc_palette: np.ndarray,
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    if dimensions != (SHEET_W, SHEET_H):
        diagnostics.append(error("ROUNDTRIP_GEOMETRY_MISMATCH", "source dimensions changed"))
    if not 1 <= color_count <= MAX_COLORS:
        diagnostics.append(error("ROUNDTRIP_COLOR_COUNT_MISMATCH", "source color count is invalid"))
    if background_index == UNKNOWN_BACKGROUND_INDEX:
        diagnostics.append(
            error(
                "ROUNDTRIP_BACKGROUND_INDEX_MISMATCH",
                "decoded background zones do not share one background index",
            )
        )
    elif not 0 <= background_index < color_count:
        diagnostics.append(
            error(
                "ROUNDTRIP_BACKGROUND_INDEX_MISMATCH",
                "decoded background index is outside the decoded palette",
                data={"background_index": background_index},
            )
        )
    if not np.array_equal(png_palette, jasc_palette):
        diagnostics.append(
            error("ROUNDTRIP_SOURCE_PALETTE_MISMATCH", "PNG and JASC palettes differ")
        )
    return tuple(diagnostics)


def _comparison_diagnostics(
    dimensions: tuple[int, int],
    color_count: int,
    background_index: int,
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
            error("ROUNDTRIP_GEOMETRY_MISMATCH", "roundtrip dimensions differ from source")
        )
    if reloaded_jasc_palette.ndim != 2 or int(reloaded_jasc_palette.shape[0]) != color_count:
        diagnostics.append(
            error("ROUNDTRIP_COLOR_COUNT_MISMATCH", "roundtrip color count differs from source")
        )
    reloaded_background_index = _decoded_background_index(reloaded_indices)
    if reloaded_background_index == UNKNOWN_BACKGROUND_INDEX:
        diagnostics.append(
            error(
                "ROUNDTRIP_BACKGROUND_INDEX_MISMATCH",
                "reloaded background zones do not share one background index",
            )
        )
    elif reloaded_background_index != background_index:
        diagnostics.append(
            error(
                "ROUNDTRIP_BACKGROUND_INDEX_MISMATCH",
                "reloaded background index differs from source",
                data={"background_index": reloaded_background_index},
            )
        )
    if not np.array_equal(indices, reloaded_indices):
        diagnostics.append(error("ROUNDTRIP_PIXEL_MISMATCH", "roundtrip index pixels differ"))
    if _array_sha256(indices) != _array_sha256(reloaded_indices):
        diagnostics.append(error("ROUNDTRIP_PIXEL_HASH_MISMATCH", "roundtrip index hash differs"))
    if not np.array_equal(palette, reloaded_png_palette):
        diagnostics.append(error("ROUNDTRIP_PNG_PALETTE_MISMATCH", "roundtrip PNG palette differs"))
    if not np.array_equal(palette, reloaded_jasc_palette):
        diagnostics.append(error("ROUNDTRIP_PALETTE_MISMATCH", "roundtrip JASC palette differs"))
    if _array_sha256(palette) != _array_sha256(reloaded_jasc_palette):
        diagnostics.append(
            error("ROUNDTRIP_PALETTE_HASH_MISMATCH", "roundtrip palette hash differs")
        )
    if not np.array_equal(reloaded_png_palette, reloaded_jasc_palette):
        diagnostics.append(
            error(
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
    background_index: int = UNKNOWN_BACKGROUND_INDEX,
    pixel_sha256: str = _EMPTY_HASH,
    roundtrip_pixel_sha256: str = _EMPTY_HASH,
    palette_sha256: str = _EMPTY_HASH,
    roundtrip_palette_sha256: str = _EMPTY_HASH,
) -> RoundtripEvidence:
    return RoundtripEvidence(
        ok=False,
        dimensions=dimensions,
        color_count=color_count,
        background_index=background_index,
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
                    data=_safe_data(diagnostic.data),
                )
                for diagnostic in diagnostics
            ),
            key=_diagnostic_sort_key,
        )
    )


def _safe_data(data: DiagData | None) -> DiagData | None:
    if data is None:
        return None
    return {
        key: sanitize_text(value) if isinstance(value, str) else value
        for key, value in data.items()
    }


def _typed_error(code: str, message: str, exc: BaseException) -> Diagnostic:
    """Fixed-message diagnostic carrying only a bounded exception-type code."""
    return error(code, message, data={"exception_type": _exception_type_code(exc)})


def _exception_type_code(exc: BaseException) -> str:
    for exception_type, code in _EXCEPTION_TYPE_CODES:
        if isinstance(exc, exception_type):
            return code
    return "unexpected_error"


def _diagnostic_sort_key(diagnostic: Diagnostic) -> tuple[str, str, str, str]:
    return (
        diagnostic.severity.value,
        diagnostic.code,
        diagnostic.where or "",
        diagnostic.message,
    )


def _array_sha256(array: np.ndarray) -> str:
    return sha256_bytes(np.ascontiguousarray(array, dtype=np.uint8).tobytes())
