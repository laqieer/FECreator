from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from fecreator.contracts.diagnostics import Diagnostic
from fecreator.imaging.io import ResourceBudget, save_indexed_png, save_png
from fecreator.interop.febuilder_roundtrip import (
    UNKNOWN_BACKGROUND_INDEX,
    RoundtripEvidence,
    decode_package_digest,
    decode_roundtrip,
)
from fecreator.specs.fire_emblem.gba.portrait_standard.layout import BACKGROUND_ZONES
from fecreator.specs.fire_emblem.gba.portrait_standard.palette import write_jasc
from tests.fixtures.gba import PALETTE, build_indices, write_raw_indexed_png, write_valid_package


def _codes(evidence: RoundtripEvidence) -> set[str]:
    return {diagnostic.code for diagnostic in evidence.diagnostics}


def _write_too_many_colors(package: Path) -> None:
    palette = [(0, 248, 0), *[(index << 3, 0, 0) for index in range(1, 17)]]
    write_raw_indexed_png(package / "hero.png", build_indices(), palette)
    _write_jasc_without_palette_limit(package / "hero.pal", palette)


def _write_mismatched_palette(package: Path) -> None:
    (package / "hero.pal").write_bytes(b"JASC-PAL\r\n0100\r\n2\r\n0 248 0\r\n8 8 8\r\n")


def _write_invalid_background_border(package: Path) -> None:
    indices = build_indices()
    indices[0, 0] = 1
    save_indexed_png(package / "hero.png", indices, np.asarray(PALETTE, dtype=np.uint8))
    write_jasc(package / "hero.pal", PALETTE)


def _write_wrong_dimensions(package: Path) -> None:
    save_indexed_png(
        package / "hero.png",
        np.zeros((111, 128), dtype=np.uint8),
        np.asarray(PALETTE, dtype=np.uint8),
    )
    write_jasc(package / "hero.pal", PALETTE)


def _write_jasc_without_palette_limit(path: Path, palette: list[tuple[int, int, int]]) -> None:
    rows = ["JASC-PAL", "0100", str(len(palette)), *(f"{r} {g} {b}" for r, g, b in palette)]
    path.write_bytes(("\r\n".join(rows) + "\r\n").encode("ascii"))


def test_roundtrip_preserves_indices_palette_and_hashes(tmp_path: Path) -> None:
    package = tmp_path / "package"
    write_valid_package(package)

    evidence = decode_roundtrip(package)

    assert evidence.ok is True
    assert evidence.dimensions == (128, 112)
    assert evidence.color_count == 2
    assert evidence.background_index == 0
    assert evidence.pixel_sha256 == evidence.roundtrip_pixel_sha256
    assert evidence.palette_sha256 == evidence.roundtrip_palette_sha256
    assert evidence.pixel_sha256 == hashlib.sha256(build_indices().tobytes()).hexdigest()
    assert (
        evidence.palette_sha256
        == hashlib.sha256(np.asarray(PALETTE, dtype=np.uint8).tobytes()).hexdigest()
    )
    assert evidence.diagnostics == ()
    assert str(tmp_path) not in evidence.model_dump_json()


def test_roundtrip_evidence_is_frozen_and_rejects_extra_fields() -> None:
    evidence = RoundtripEvidence(
        ok=True,
        dimensions=(128, 112),
        color_count=2,
        background_index=0,
        pixel_sha256="a" * 64,
        roundtrip_pixel_sha256="a" * 64,
        palette_sha256="b" * 64,
        roundtrip_palette_sha256="b" * 64,
    )

    with pytest.raises(ValidationError):
        RoundtripEvidence.model_validate({**evidence.model_dump(), "temporary_path": "unsafe"})
    with pytest.raises(ValidationError):
        evidence.ok = False  # type: ignore[misc]


def test_roundtrip_rejects_rgb_png(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    save_png(package / "hero.png", np.zeros((112, 128, 3), dtype=np.uint8))
    write_jasc(package / "hero.pal", PALETTE)

    evidence = decode_roundtrip(package)

    assert evidence.ok is False
    assert "NON_INDEXED" in _codes(evidence)
    assert evidence.pixel_sha256 == ""
    assert str(tmp_path) not in evidence.model_dump_json()


@pytest.mark.parametrize(
    ("name", "prepare", "expected_code"),
    [
        (
            "mismatched-palette",
            _write_mismatched_palette,
            "PALETTE_COLOR_MISMATCH",
        ),
        (
            "more-than-16-colors",
            lambda package: _write_too_many_colors(package),
            "PORTRAIT_PALETTE_GT16",
        ),
        (
            "invalid-background-border",
            lambda package: _write_invalid_background_border(package),
            "UNSAFE_ZONE",
        ),
        (
            "noncanonical-dimensions",
            lambda package: _write_wrong_dimensions(package),
            "SHEET_BAD_DIMS",
        ),
    ],
)
def test_roundtrip_fails_closed_for_invalid_canonical_packages(
    tmp_path: Path,
    name: str,
    prepare: Callable[[Path], None],
    expected_code: str,
) -> None:
    package = tmp_path / name
    write_valid_package(package)
    prepare(package)

    evidence = decode_roundtrip(package)

    assert evidence.ok is False
    assert expected_code in _codes(evidence)
    assert evidence.roundtrip_pixel_sha256 == ""
    assert evidence.roundtrip_palette_sha256 == ""


def test_roundtrip_detects_corrupt_reloaded_indices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "package"
    write_valid_package(package)
    import fecreator.interop.febuilder_roundtrip as roundtrip_module

    original_load = roundtrip_module.load_indexed
    loads = 0

    def corrupt_second_load(
        path: Path, budget: ResourceBudget | None = None
    ) -> tuple[np.ndarray, np.ndarray]:
        nonlocal loads
        loads += 1
        indices, palette = original_load(path, budget)
        if loads == 2:
            indices = indices.copy()
            indices[60, 60] = 0
        return indices, palette

    monkeypatch.setattr(roundtrip_module, "load_indexed", corrupt_second_load)

    evidence = decode_roundtrip(package)

    assert evidence.ok is False
    assert "ROUNDTRIP_PIXEL_MISMATCH" in _codes(evidence)
    assert "ROUNDTRIP_PIXEL_HASH_MISMATCH" in _codes(evidence)
    assert evidence.pixel_sha256 != evidence.roundtrip_pixel_sha256


def test_roundtrip_returns_safe_diagnostic_when_decode_exceeds_budget(tmp_path: Path) -> None:
    package = tmp_path / "package"
    write_valid_package(package)

    evidence = decode_roundtrip(package, budget=ResourceBudget(max_pixels=1))

    assert evidence.ok is False
    assert "ROUNDTRIP_DECODE_FAILED" in _codes(evidence)
    assert str(tmp_path) not in evidence.model_dump_json()


def test_roundtrip_returns_safe_diagnostic_for_symlinked_package_input(tmp_path: Path) -> None:
    outside = tmp_path / "outside.png"
    save_indexed_png(outside, build_indices(), np.asarray(PALETTE, dtype=np.uint8))
    package = tmp_path / "package"
    package.mkdir()
    try:
        (package / "hero.png").symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation not permitted on this platform")
    write_jasc(package / "hero.pal", PALETTE)

    evidence = decode_roundtrip(package)

    assert evidence.ok is False
    assert "UNSAFE_PATH" in _codes(evidence)
    assert str(tmp_path) not in evidence.model_dump_json()


def _patch_indexed_loader(
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[int, np.ndarray], np.ndarray],
) -> None:
    import fecreator.interop.febuilder_roundtrip as roundtrip_module

    original_load = roundtrip_module.load_indexed
    loads = 0

    def patched(path: Path, budget: ResourceBudget | None = None) -> tuple[np.ndarray, np.ndarray]:
        nonlocal loads
        loads += 1
        indices, palette = original_load(path, budget)
        return mutate(loads, indices.copy()), palette

    monkeypatch.setattr(roundtrip_module, "load_indexed", patched)


def test_roundtrip_decode_failure_is_path_free_and_typed(tmp_path: Path) -> None:
    package = tmp_path / "package"
    write_valid_package(package)

    evidence = decode_roundtrip(package, budget=ResourceBudget(max_pixels=1))

    failures = [
        diagnostic
        for diagnostic in evidence.diagnostics
        if diagnostic.code == "ROUNDTRIP_DECODE_FAILED"
    ]
    assert len(failures) == 1
    assert failures[0].message == "cannot decode canonical package"
    assert failures[0].where is None
    assert failures[0].data == {"exception_type": "image_budget_error"}
    assert "hero" not in evidence.model_dump_json()


def test_roundtrip_validation_failure_hides_exception_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "package"
    write_valid_package(package)
    import fecreator.interop.febuilder_roundtrip as roundtrip_module

    class _ExplodingSpec:
        def validate(self, package_dir: Path) -> list[Diagnostic]:
            raise OSError(f"cannot read {package_dir / 'hero.png'}")

    monkeypatch.setattr(roundtrip_module, "FeGbaPortraitStandard", _ExplodingSpec)

    evidence = decode_roundtrip(package)

    assert evidence.ok is False
    assert evidence.background_index == UNKNOWN_BACKGROUND_INDEX
    diagnostic = evidence.diagnostics[0]
    assert diagnostic.code == "ROUNDTRIP_VALIDATION_FAILED"
    assert diagnostic.message == "cannot strictly validate canonical package"
    assert diagnostic.data == {"exception_type": "os_error"}
    assert str(tmp_path) not in evidence.model_dump_json()
    assert "cannot read" not in evidence.model_dump_json()


def test_roundtrip_reencode_failure_is_path_free_and_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "package"
    write_valid_package(package)
    import fecreator.interop.febuilder_roundtrip as roundtrip_module

    def refuse(path: Path, indices: np.ndarray, palette: np.ndarray) -> None:
        raise OSError(f"cannot write {path}")

    monkeypatch.setattr(roundtrip_module, "save_indexed_png", refuse)

    evidence = decode_roundtrip(package)

    assert evidence.ok is False
    failures = [
        diagnostic
        for diagnostic in evidence.diagnostics
        if diagnostic.code == "ROUNDTRIP_REENCODE_FAILED"
    ]
    assert len(failures) == 1
    assert failures[0].message == "cannot re-encode or reload canonical package"
    assert failures[0].data == {"exception_type": "os_error"}
    assert "roundtrip" not in failures[0].message
    assert "fecreator-febuilder-roundtrip" not in evidence.model_dump_json()


def test_roundtrip_does_not_swallow_programming_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "package"
    write_valid_package(package)
    import fecreator.interop.febuilder_roundtrip as roundtrip_module

    def explode(path: Path, budget: ResourceBudget | None = None) -> tuple[np.ndarray, np.ndarray]:
        raise TypeError("programming error")

    monkeypatch.setattr(roundtrip_module, "load_indexed", explode)

    with pytest.raises(TypeError):
        decode_roundtrip(package)


def test_roundtrip_background_index_is_read_from_decoded_zones(tmp_path: Path) -> None:
    package = tmp_path / "package"
    write_valid_package(package)
    zone = BACKGROUND_ZONES[0]
    observed = int(build_indices()[zone.y, zone.x])

    evidence = decode_roundtrip(package)

    assert evidence.ok is True
    assert evidence.background_index == observed

    digest = decode_package_digest(package)

    assert digest is not None
    assert digest.background_index == observed
    assert digest.pixel_sha256 == evidence.pixel_sha256
    assert digest.palette_sha256 == evidence.palette_sha256


def test_roundtrip_rejects_decoded_background_zones_that_are_not_uniform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "package"
    write_valid_package(package)
    zone = BACKGROUND_ZONES[0]

    def corrupt_background(_load: int, indices: np.ndarray) -> np.ndarray:
        indices[zone.y, zone.x] = 1
        return indices

    _patch_indexed_loader(monkeypatch, corrupt_background)

    evidence = decode_roundtrip(package)

    assert evidence.ok is False
    assert "ROUNDTRIP_BACKGROUND_INDEX_MISMATCH" in _codes(evidence)
    assert evidence.background_index == UNKNOWN_BACKGROUND_INDEX


def test_roundtrip_detects_reloaded_background_index_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "package"
    write_valid_package(package)
    zone = BACKGROUND_ZONES[0]

    def corrupt_reloaded_background(load: int, indices: np.ndarray) -> np.ndarray:
        if load == 2:
            indices[zone.y, zone.x] = 1
        return indices

    _patch_indexed_loader(monkeypatch, corrupt_reloaded_background)

    evidence = decode_roundtrip(package)

    assert evidence.ok is False
    assert "ROUNDTRIP_BACKGROUND_INDEX_MISMATCH" in _codes(evidence)


def test_decode_package_digest_returns_none_for_undecodable_package(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    save_png(package / "hero.png", np.zeros((112, 128, 3), dtype=np.uint8))
    write_jasc(package / "hero.pal", PALETTE)

    assert decode_package_digest(package) is None
    assert decode_package_digest(tmp_path / "absent") is None
