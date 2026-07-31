from __future__ import annotations

import importlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from fecreator.contracts.dialogue_background import (
    DialogueBackgroundPackageManifest,
    DialogueBackgroundSourceRecord,
)
from fecreator.core.hashing import sha256_file


def _rgb_many_colors() -> np.ndarray:
    y, x = np.indices((160, 240), dtype=np.uint16)
    return np.stack(
        ((x % 256), (y % 256), ((x * 17 + y * 29) % 256)),
        axis=2,
    ).astype(np.uint8)


def _save_canonical_rgb_png(path: Path, rgb: np.ndarray) -> None:
    imaging_io = importlib.import_module("fecreator.imaging.io")
    imaging_io.save_canonical_rgb_png(path, rgb)


def _load_opaque_png_rgb(path: Path) -> tuple[np.ndarray, str]:
    imaging_io = importlib.import_module("fecreator.imaging.io")
    return imaging_io.load_opaque_png_rgb(path)


def _spec() -> object:
    module = importlib.import_module(
        "fecreator.specs.fire_emblem.gba.dialogue_background_source.spec"
    )
    return module.Fe8DialogueBackgroundSource240x160()


def _write_manifest(
    package: Path,
    *,
    name: str,
    png_path: Path,
    manifest_filename: str | None = None,
    png_sha256: str | None = None,
) -> None:
    manifest = DialogueBackgroundPackageManifest(
        name=name,
        purpose="Original phantom city",
        provider="manual",
        prompt="A ghostly city",
        source=DialogueBackgroundSourceRecord(
            kind="prompt",
            id="dialogue-background/phantom-city",
            revision="1",
            input_sha256="a" * 64,
        ),
        png_sha256=png_sha256 or sha256_file(png_path),
        license_note="Original repository fixture.",
        source_note="Generated from an original prompt.",
    )
    filename = manifest_filename or f"{name}.manifest.json"
    (package / filename).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_package(package: Path, *, rgb: np.ndarray | None = None) -> None:
    package.mkdir()
    image = rgb if rgb is not None else _rgb_many_colors()
    png = package / "phantom_city.png"
    _save_canonical_rgb_png(png, image)
    _write_manifest(package, name="phantom_city", png_path=png)


def test_canonical_rgb_png_is_byte_deterministic(tmp_path: Path) -> None:
    rgb = _rgb_many_colors()
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"

    _save_canonical_rgb_png(first, rgb)
    _save_canonical_rgb_png(second, rgb)

    assert first.read_bytes() == second.read_bytes()
    loaded, mode = _load_opaque_png_rgb(first)
    assert mode == "RGB"
    assert np.array_equal(loaded, rgb)


def test_load_opaque_png_accepts_rgb_rgba_and_indexed(tmp_path: Path) -> None:
    rgb = _rgb_many_colors()
    rgb_path = tmp_path / "rgb.png"
    rgba_path = tmp_path / "rgba.png"
    indexed_path = tmp_path / "indexed.png"
    Image.fromarray(rgb, "RGB").save(rgb_path)
    Image.fromarray(
        np.dstack((rgb, np.full((160, 240), 255, dtype=np.uint8))),
        "RGBA",
    ).save(rgba_path)
    indexed = (np.indices((160, 240))[1] % 256).astype(np.uint8)
    indexed_image = Image.fromarray(indexed, "P")
    indexed_palette = [
        component for value in range(256) for component in (value, 255 - value, value)
    ]
    indexed_image.putpalette(indexed_palette)
    indexed_image.save(indexed_path)

    rgb_loaded, rgb_mode = _load_opaque_png_rgb(rgb_path)
    rgba_loaded, rgba_mode = _load_opaque_png_rgb(rgba_path)
    indexed_loaded, indexed_mode = _load_opaque_png_rgb(indexed_path)

    assert rgb_mode == "RGB"
    assert rgba_mode == "RGBA"
    assert indexed_mode == "P"
    assert np.array_equal(rgb_loaded, rgb)
    assert np.array_equal(rgba_loaded, rgb)
    assert tuple(int(value) for value in indexed_loaded[0, 0]) == (0, 255, 0)
    assert tuple(int(value) for value in indexed_loaded[0, 1]) == (1, 254, 1)


def test_target_accepts_truecolor_more_than_128_colors(tmp_path: Path) -> None:
    package = tmp_path / "package"
    _write_package(package)

    assert _spec().validate(package) == []


def test_target_accepts_fully_opaque_rgba_package(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    rgb = _rgb_many_colors()
    png = package / "phantom_city.png"
    rgba = np.dstack((rgb, np.full((160, 240), 255, dtype=np.uint8)))
    Image.fromarray(rgba, "RGBA").save(png)
    _write_manifest(package, name="phantom_city", png_path=png)

    assert _spec().validate(package) == []


def test_target_accepts_indexed_package_without_palette_restrictions(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    png = package / "phantom_city.png"
    indices = (np.arange(160 * 240, dtype=np.uint32) % 256).reshape(160, 240).astype(np.uint8)
    image = Image.fromarray(indices, "P")
    palette = [
        component
        for value in range(256)
        for component in (value, (value * 13) % 256, (value * 29) % 256)
    ]
    image.putpalette(palette)
    image.save(png)
    _write_manifest(package, name="phantom_city", png_path=png)

    assert _spec().validate(package) == []


def test_target_rejects_wrong_dimensions(tmp_path: Path) -> None:
    package = tmp_path / "package"
    _write_package(package, rgb=np.zeros((159, 240, 3), dtype=np.uint8))

    assert "INVALID_BACKGROUND_DIMENSIONS" in {item.code for item in _spec().validate(package)}


def test_target_rejects_nonopaque_rgba(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    rgba = np.zeros((160, 240, 4), dtype=np.uint8)
    rgba[:, :, 3] = 255
    rgba[0, 0, 3] = 0
    png = package / "phantom_city.png"
    Image.fromarray(rgba, "RGBA").save(png)
    _write_manifest(package, name="phantom_city", png_path=png)

    codes = {item.code for item in _spec().validate(package)}
    assert "NON_OPAQUE_BACKGROUND" in codes
    assert "INVALID_BACKGROUND_PNG" not in codes


def test_target_rejects_corrupt_png_without_reporting_opacity(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    png = package / "phantom_city.png"
    png.write_bytes(b"not a real png")
    _write_manifest(package, name="phantom_city", png_path=png)

    codes = {item.code for item in _spec().validate(package)}
    assert "INVALID_BACKGROUND_PNG" in codes
    assert "NON_OPAQUE_BACKGROUND" not in codes


def test_target_rejects_missing_manifest(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    _save_canonical_rgb_png(package / "phantom_city.png", _rgb_many_colors())

    assert "MISSING_BACKGROUND_MANIFEST" in {item.code for item in _spec().validate(package)}


def test_target_rejects_malformed_manifest(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    png = package / "phantom_city.png"
    _save_canonical_rgb_png(png, _rgb_many_colors())
    (package / "phantom_city.manifest.json").write_text("{", encoding="utf-8")

    assert "INVALID_BACKGROUND_MANIFEST" in {item.code for item in _spec().validate(package)}


def test_target_rejects_name_mismatch(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    png = package / "phantom_city.png"
    _save_canonical_rgb_png(png, _rgb_many_colors())
    _write_manifest(
        package,
        name="other_name",
        png_path=png,
        manifest_filename="phantom_city.manifest.json",
    )

    assert "BACKGROUND_NAME_MISMATCH" in {item.code for item in _spec().validate(package)}


def test_target_rejects_hash_mismatch_and_extra_files(tmp_path: Path) -> None:
    package = tmp_path / "package"
    _write_package(package)
    payload = json.loads((package / "phantom_city.manifest.json").read_text("utf-8"))
    payload["png_sha256"] = "0" * 64
    (package / "phantom_city.manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    (package / "extra.bin").write_bytes(b"x")

    codes = {item.code for item in _spec().validate(package)}
    assert {"BACKGROUND_HASH_MISMATCH", "UNEXPECTED_BACKGROUND_PACKAGE_ENTRY"} <= codes


def test_target_rejects_unsafe_directory_entry(tmp_path: Path) -> None:
    package = tmp_path / "package"
    _write_package(package)
    (package / "nested").mkdir()

    codes = {item.code for item in _spec().validate(package)}
    assert "UNSAFE_BACKGROUND_PACKAGE_ENTRY" in codes
    assert "UNEXPECTED_BACKGROUND_PACKAGE_ENTRY" not in codes


def test_target_rejects_canonical_name_symlink_without_unexpected_entry(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    _write_package(package)
    target = package / "phantom_city.manifest.json"
    target.unlink()
    try:
        target.symlink_to(package / "nested", target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks not supported here: {exc}")

    codes = {item.code for item in _spec().validate(package)}
    assert "UNSAFE_BACKGROUND_PACKAGE_ENTRY" in codes
    assert "UNEXPECTED_BACKGROUND_PACKAGE_ENTRY" not in codes


def test_target_rejects_missing_package_directory(tmp_path: Path) -> None:
    codes = {item.code for item in _spec().validate(tmp_path / "missing")}
    assert "MISSING_BACKGROUND_PACKAGE" in codes
