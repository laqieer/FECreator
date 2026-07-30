from __future__ import annotations

import importlib
import json
from pathlib import Path

import numpy as np

from fecreator.contracts.dialogue_background import (
    DialogueBackgroundPackageManifest,
    DialogueBackgroundSourceRecord,
)
from fecreator.core.hashing import sha256_file
from fecreator.core.registry import SPEC_REGISTRY
from fecreator.specs.base import TargetSpec
from fecreator.specs.fire_emblem.gba.portrait_standard.spec import FeGbaPortraitStandard
from tests.fixtures.gba import write_valid_package


def test_id_and_protocol() -> None:
    spec = FeGbaPortraitStandard()
    assert spec.id == "fe-gba-portrait-standard"
    assert isinstance(spec, TargetSpec)


def test_registered_in_spec_registry() -> None:
    import fecreator.specs  # noqa: F401  (import triggers registration)

    assert "fe-gba-portrait-standard" in SPEC_REGISTRY.ids()


def test_validate_delegates(tmp_path: Path) -> None:
    write_valid_package(tmp_path)
    diags = FeGbaPortraitStandard().validate(tmp_path)
    assert all(d.severity.value != "error" for d in diags)


def _save_canonical_rgb_png(path: Path, rgb: np.ndarray) -> None:
    imaging_io = importlib.import_module("fecreator.imaging.io")
    imaging_io.save_canonical_rgb_png(path, rgb)


def _rgb_many_colors() -> np.ndarray:
    y, x = np.indices((160, 240), dtype=np.uint16)
    return np.stack(
        ((x % 256), (y % 256), ((x * 17 + y * 29) % 256)),
        axis=2,
    ).astype(np.uint8)


def _write_background_package(package: Path) -> None:
    package.mkdir(exist_ok=True)
    png = package / "phantom_city.png"
    _save_canonical_rgb_png(png, _rgb_many_colors())
    manifest = DialogueBackgroundPackageManifest(
        name="phantom_city",
        purpose="Original phantom city",
        provider="manual",
        prompt="A ghostly city",
        source=DialogueBackgroundSourceRecord(
            kind="prompt",
            id="dialogue-background/phantom-city",
            revision="1",
            input_sha256="a" * 64,
        ),
        png_sha256=sha256_file(png),
        license_note="Original repository fixture.",
        source_note="Generated from an original prompt.",
    )
    (package / "phantom_city.manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _background_spec() -> object:
    module = importlib.import_module(
        "fecreator.specs.fire_emblem.gba.dialogue_background_source.spec"
    )
    return module.Fe8DialogueBackgroundSource240x160()


def test_dialogue_background_id_and_protocol() -> None:
    spec = _background_spec()
    assert spec.id == "fe8-dialogue-background-source-240x160"
    assert isinstance(spec, TargetSpec)


def test_dialogue_background_registered_in_spec_registry() -> None:
    import fecreator.specs  # noqa: F401

    assert "fe8-dialogue-background-source-240x160" in SPEC_REGISTRY.ids()


def test_dialogue_background_validate_delegates(tmp_path: Path) -> None:
    _write_background_package(tmp_path)
    assert _background_spec().validate(tmp_path) == []
