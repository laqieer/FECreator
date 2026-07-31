# Issue #2 Dialogue Background Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, review-gated FE8 240x160 dialogue-background source asset that works through every existing FECreator interface without adding FE8 palette/TSA/ROM responsibilities.

**Architecture:** Extract the existing build/review/finalization lifecycle into asset-neutral modules, then implement a separate dialogue-background plugin and target spec. Dialogue backgrounds normalize accepted opaque PNG modes to a canonical RGB PNG and package it with deterministic metadata; target-aware bundle evidence keeps the existing portrait roundtrip unchanged.

**Tech Stack:** Python 3.11-3.13, Pydantic v2, NumPy, Pillow, FastAPI, MCP, React/TypeScript, pytest, Vitest, Ruff, mypy.

## Global Constraints

- Keep the feature limited to `dialogue_background` and `fe8-dialogue-background-source-240x160`.
- The source image is exactly 240x160 and opaque.
- Accept RGB, opaque RGBA, and indexed `P` PNG input; impose no source color-count, palette-bank, indexed-output, or tile-count limit.
- Do not implement built-in quantization, TSA generation, compression, ROM insertion, or Makefile orchestration.
- Preserve existing portrait package bytes and strict `fe-gba-portrait-standard` behavior.
- Keep providers and interfaces thin; image and package rules belong in asset/spec modules.
- Keep demo mode deterministic and offline; it remains portrait-only.
- Add no runtime dependency.
- Use workspace-relative, hash-checked regular files and the existing path, lock, atomic-I/O, and redaction helpers.
- Every public contract model remains frozen and extra-forbidden.

---

### Task 1: Add the public manifest and package contracts

**Files:**
- Create: `src/fecreator/contracts/dialogue_background.py`
- Modify: `src/fecreator/contracts/manifest.py`
- Modify: `src/fecreator/contracts/__init__.py`
- Modify: `src/fecreator/contracts/schemas.py`
- Modify: `tests/contracts/test_manifest.py`
- Modify: `tests/contracts/test_contract_freeze.py`
- Modify: `tests/contracts/test_schemas.py`
- Create: `tests/dialogue_background/__init__.py`
- Create: `tests/dialogue_background/test_contract.py`
- Regenerate: `schemas/*.schema.json`

**Interfaces:**
- Produces: `SourceIdentity`, `AssetMetadata`, `DialogueBackgroundSourceRecord`, and `DialogueBackgroundPackageManifest`.
- Produces: additive `Manifest` literals and `Manifest.metadata: AssetMetadata | None`.
- Consumes later: `DialogueBackgroundPackageManifest.model_validate()`, `AssetMetadata.name`, `AssetMetadata.source`, and `AssetMetadata.requested_downstream_profile`.

- [ ] **Step 1: Write failing manifest tests**

Add these cases to `tests/contracts/test_manifest.py`:

```python
from fecreator.contracts.manifest import AssetMetadata, SourceIdentity


def _background_metadata() -> AssetMetadata:
    return AssetMetadata(
        name="phantom_city",
        purpose="Original phantom-city dialogue background",
        source=SourceIdentity(
            kind="prompt",
            id="dialogue-background/phantom-city",
            revision="1",
        ),
        license_note="Original repository fixture.",
        source_note="Generated from an original prompt.",
        requested_downstream_profile="fe8-dialogue-background-feimg2",
    )


def test_dialogue_background_manifest_accepts_normative_identifiers() -> None:
    manifest = Manifest(
        asset_type="dialogue_background",
        target_spec="fe8-dialogue-background-source-240x160",
        workflow="text_to_dialogue_background",
        provider="fake",
        metadata=_background_metadata(),
        sources=(SourceSpec(kind="text", ref="phantom city"),),
    )

    assert manifest.metadata == _background_metadata()


@pytest.mark.parametrize(
    ("asset_type", "target_spec", "workflow"),
    [
        ("dialogue_background", "fe-gba-portrait-standard", "text_to_dialogue_background"),
        ("portrait", "fe8-dialogue-background-source-240x160", "text_to_portrait"),
        ("dialogue_background", "fe8-dialogue-background-source-240x160", "text_to_portrait"),
    ],
)
def test_manifest_rejects_cross_asset_contracts(
    asset_type: str,
    target_spec: str,
    workflow: str,
) -> None:
    with pytest.raises(ValidationError):
        Manifest(
            asset_type=asset_type,
            target_spec=target_spec,
            workflow=workflow,
            provider="fake",
            metadata=_background_metadata() if asset_type == "dialogue_background" else None,
        )


def test_dialogue_background_requires_metadata() -> None:
    with pytest.raises(ValidationError, match="metadata"):
        Manifest(
            asset_type="dialogue_background",
            target_spec="fe8-dialogue-background-source-240x160",
            workflow="text_to_dialogue_background",
            provider="fake",
        )


def test_portrait_rejects_dialogue_background_metadata() -> None:
    payload = _manifest().model_dump(mode="python")
    payload["metadata"] = _background_metadata().model_dump(mode="python")

    with pytest.raises(ValidationError, match="metadata"):
        Manifest.model_validate(payload)
```

- [ ] **Step 2: Write failing package-contract tests**

Create `tests/dialogue_background/test_contract.py`:

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from fecreator.contracts.dialogue_background import (
    DialogueBackgroundPackageManifest,
    DialogueBackgroundSourceRecord,
)


def _package_manifest() -> DialogueBackgroundPackageManifest:
    return DialogueBackgroundPackageManifest(
        name="phantom_city",
        purpose="Original phantom-city dialogue background",
        provider="manual",
        prompt="A ghostly imperial city at twilight",
        source=DialogueBackgroundSourceRecord(
            kind="prompt",
            id="dialogue-background/phantom-city",
            revision="1",
            input_sha256="a" * 64,
        ),
        png_sha256="b" * 64,
        license_note="Original repository fixture.",
        source_note="Generated from an original prompt.",
        requested_downstream_profile="fe8-dialogue-background-feimg2",
    )


def test_package_manifest_pins_normative_contract() -> None:
    manifest = _package_manifest()

    assert manifest.version == "1.0"
    assert manifest.contract_version == "1.0"
    assert manifest.asset_type == "dialogue_background"
    assert manifest.target_spec == "fe8-dialogue-background-source-240x160"
    assert (manifest.width, manifest.height, manifest.opaque) == (240, 160, True)


@pytest.mark.parametrize("field", ["input_sha256", "png_sha256"])
def test_package_manifest_rejects_invalid_hashes(field: str) -> None:
    payload = _package_manifest().model_dump(mode="python")
    if field == "input_sha256":
        payload["source"]["input_sha256"] = "not-a-hash"
    else:
        payload[field] = "not-a-hash"

    with pytest.raises(ValidationError):
        DialogueBackgroundPackageManifest.model_validate(payload)
```

- [ ] **Step 3: Run the focused tests and confirm they fail**

Run:

```powershell
pytest -q tests/contracts/test_manifest.py tests/dialogue_background/test_contract.py
```

Expected: collection or assertion failures because the new models and literals do not exist.

- [ ] **Step 4: Implement the additive manifest contract**

In `src/fecreator/contracts/manifest.py`, add:

```python
from typing import Literal

from pydantic import ValidationInfo

from fecreator.core.paths import ensure_portable_filename, normalize_storage_id

PORTRAIT_WORKFLOWS = frozenset(
    {"text_to_portrait", "concept_to_portrait", "expression_refine", "masked_variant"}
)
DIALOGUE_BACKGROUND_WORKFLOWS = frozenset(
    {"text_to_dialogue_background", "concept_to_dialogue_background", "masked_variant"}
)


def _non_empty(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


class SourceIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    id: str
    revision: str

    @field_validator("kind", "id", "revision", mode="after")
    @classmethod
    def _validate_text(cls, value: str, info: ValidationInfo) -> str:
        return _non_empty(value, field_name=info.field_name or "source identity")


class AssetMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    purpose: str
    source: SourceIdentity
    license_note: str
    source_note: str
    requested_downstream_profile: Literal["fe8-dialogue-background-feimg2"] | None = None

    @field_validator("name", mode="after")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        normalized = normalize_storage_id(value, field_name="name")
        return ensure_portable_filename(normalized, field_name="name")

    @field_validator("purpose", "license_note", "source_note", mode="after")
    @classmethod
    def _validate_text(cls, value: str, info: ValidationInfo) -> str:
        return _non_empty(value, field_name=info.field_name or "metadata")
```

Change the existing literals to:

```python
class SourceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["text", "concept_art", "approved_portrait", "approved_dialogue_background"]
    ref: str


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["1.0"] = "1.0"
    asset_type: Literal["portrait", "dialogue_background"]
    target_spec: Literal[
        "fe-gba-portrait-standard",
        "fe8-dialogue-background-source-240x160",
    ]
    workflow: Literal[
        "text_to_portrait",
        "concept_to_portrait",
        "expression_refine",
        "masked_variant",
        "text_to_dialogue_background",
        "concept_to_dialogue_background",
    ]
    provider: str
    character_ref_pack: str | None = None
    character_ref_pack_rev: int | None = Field(default=None, ge=1)
    parent_asset_id: str | None = None
    sources: tuple[SourceSpec, ...] = ()
    edit: EditSpec | None = None
    metadata: AssetMetadata | None = None
    params: Params = Field(default_factory=freeze_mapping)
```

Add this model validator:

```python
    @model_validator(mode="after")
    def _asset_contract_matches(self) -> Manifest:
        if self.asset_type == "portrait":
            if self.target_spec != "fe-gba-portrait-standard":
                raise ValueError("portrait requires target_spec='fe-gba-portrait-standard'")
            if self.workflow not in PORTRAIT_WORKFLOWS:
                raise ValueError(f"portrait does not support workflow={self.workflow!r}")
            if self.metadata is not None:
                raise ValueError("metadata is only supported for dialogue_background")
            return self

        if self.target_spec != "fe8-dialogue-background-source-240x160":
            raise ValueError(
                "dialogue_background requires "
                "target_spec='fe8-dialogue-background-source-240x160'"
            )
        if self.workflow not in DIALOGUE_BACKGROUND_WORKFLOWS:
            raise ValueError(
                f"dialogue_background does not support workflow={self.workflow!r}"
            )
        if self.metadata is None:
            raise ValueError("metadata is required for dialogue_background")
        return self
```

- [ ] **Step 5: Implement the package manifest contract**

Create `src/fecreator/contracts/dialogue_background.py`:

```python
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator, model_validator

from fecreator.core.paths import ensure_portable_filename, normalize_storage_id

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _non_empty(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


class DialogueBackgroundSourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    id: str
    revision: str
    input_sha256: str

    @field_validator("kind", "id", "revision", mode="after")
    @classmethod
    def _validate_text(cls, value: str, info: ValidationInfo) -> str:
        return _non_empty(value, field_name=info.field_name or "source")

    @field_validator("input_sha256", mode="after")
    @classmethod
    def _validate_input_hash(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("input_sha256 must be a lowercase SHA-256 hex digest")
        return value


class DialogueBackgroundPackageManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["1.0"] = "1.0"
    contract_version: Literal["1.0"] = "1.0"
    asset_type: Literal["dialogue_background"] = "dialogue_background"
    asset_type_version: Literal["1.0"] = "1.0"
    target_spec: Literal["fe8-dialogue-background-source-240x160"] = (
        "fe8-dialogue-background-source-240x160"
    )
    target_spec_version: Literal["1.0"] = "1.0"
    name: str
    purpose: str
    width: Literal[240] = 240
    height: Literal[160] = 160
    opaque: Literal[True] = True
    provider: str
    model: str | None = None
    prompt: str | None = None
    reference_pack: str | None = None
    reference_pack_rev: int | None = None
    source: DialogueBackgroundSourceRecord
    png_sha256: str
    license_note: str
    source_note: str
    requested_downstream_profile: Literal["fe8-dialogue-background-feimg2"] | None = None

    @field_validator("name", mode="after")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        normalized = normalize_storage_id(value, field_name="name")
        return ensure_portable_filename(normalized, field_name="name")

    @field_validator("purpose", "provider", "license_note", "source_note", mode="after")
    @classmethod
    def _validate_text(cls, value: str, info: ValidationInfo) -> str:
        return _non_empty(value, field_name=info.field_name or "package metadata")

    @field_validator("png_sha256", mode="after")
    @classmethod
    def _validate_png_hash(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("png_sha256 must be a lowercase SHA-256 hex digest")
        return value

    @model_validator(mode="after")
    def _reference_revision_matches(self) -> DialogueBackgroundPackageManifest:
        if (self.reference_pack is None) != (self.reference_pack_rev is None):
            raise ValueError("reference_pack and reference_pack_rev must be set together")
        return self
```

Export both new contract models from `contracts/__init__.py`, and add:

```python
"dialogue_background_package": DialogueBackgroundPackageManifest,
```

to `SCHEMA_MODELS`.

- [ ] **Step 6: Update freeze and schema tests**

Change the expected manifest fields, literals, source kinds, registered schema names,
and model inventories in `test_contract_freeze.py` and `test_schemas.py`. Assert:

```python
assert _literal_values(Manifest, "asset_type") == ("portrait", "dialogue_background")
assert _literal_values(Manifest, "target_spec") == (
    "fe-gba-portrait-standard",
    "fe8-dialogue-background-source-240x160",
)
assert _literal_values(SourceSpec, "kind") == (
    "text",
    "concept_art",
    "approved_portrait",
    "approved_dialogue_background",
)
assert "dialogue_background_package" in SCHEMA_MODELS
```

- [ ] **Step 7: Regenerate schemas and run contract tests**

Run:

```powershell
python -c "from pathlib import Path; from fecreator.contracts.schemas import export_schemas; export_schemas(Path('schemas'))"
pytest -q tests/contracts tests/dialogue_background/test_contract.py
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit the contract**

```powershell
git add src/fecreator/contracts tests/contracts tests/dialogue_background schemas
git commit -m "feat: define dialogue background contracts" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: Add deterministic opaque PNG I/O and the target spec

**Files:**
- Modify: `src/fecreator/imaging/io.py`
- Create: `src/fecreator/specs/fire_emblem/gba/dialogue_background_source/__init__.py`
- Create: `src/fecreator/specs/fire_emblem/gba/dialogue_background_source/spec.py`
- Create: `src/fecreator/specs/fire_emblem/gba/dialogue_background_source/validation.py`
- Modify: `src/fecreator/specs/__init__.py`
- Create: `tests/dialogue_background/test_spec.py`
- Modify: `tests/specs/test_spec.py`

**Interfaces:**
- Produces: `load_opaque_png_rgb(path: Path, budget: ResourceBudget | None = None) -> tuple[np.ndarray, str]`.
- Produces: `save_canonical_rgb_png(path: Path, rgb: np.ndarray) -> None`.
- Produces: `validate_package(package_dir: Path) -> list[Diagnostic]`.
- Produces: `Fe8DialogueBackgroundSource240x160.id`.

- [ ] **Step 1: Write failing deterministic-I/O tests**

Add to `tests/dialogue_background/test_spec.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from fecreator.contracts.dialogue_background import (
    DialogueBackgroundPackageManifest,
    DialogueBackgroundSourceRecord,
)
from fecreator.core.hashing import sha256_file
from fecreator.imaging.io import load_opaque_png_rgb, save_canonical_rgb_png
from fecreator.specs.fire_emblem.gba.dialogue_background_source.spec import (
    Fe8DialogueBackgroundSource240x160,
)


def _rgb_many_colors() -> np.ndarray:
    y, x = np.indices((160, 240), dtype=np.uint16)
    return np.stack(
        ((x % 256), (y % 256), ((x * 17 + y * 29) % 256)),
        axis=2,
    ).astype(np.uint8)


def test_canonical_rgb_png_is_byte_deterministic(tmp_path: Path) -> None:
    rgb = _rgb_many_colors()
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"

    save_canonical_rgb_png(first, rgb)
    save_canonical_rgb_png(second, rgb)

    assert first.read_bytes() == second.read_bytes()
    loaded, mode = load_opaque_png_rgb(first)
    assert mode == "RGB"
    assert np.array_equal(loaded, rgb)


def test_load_opaque_png_accepts_rgb_rgba_and_indexed(tmp_path: Path) -> None:
    rgb = _rgb_many_colors()
    rgb_path = tmp_path / "rgb.png"
    rgba_path = tmp_path / "rgba.png"
    indexed_path = tmp_path / "indexed.png"
    Image.fromarray(rgb, "RGB").save(rgb_path)
    Image.fromarray(np.dstack((rgb, np.full((160, 240), 255, dtype=np.uint8))), "RGBA").save(
        rgba_path
    )
    Image.fromarray((np.indices((160, 240))[1] % 256).astype(np.uint8), "P").save(indexed_path)

    assert load_opaque_png_rgb(rgb_path)[1] == "RGB"
    assert load_opaque_png_rgb(rgba_path)[1] == "RGBA"
    assert load_opaque_png_rgb(indexed_path)[1] == "P"
```

- [ ] **Step 2: Write failing target-validation tests**

Use this package helper:

```python
def _write_package(package: Path, *, rgb: np.ndarray | None = None) -> None:
    package.mkdir()
    image = rgb if rgb is not None else _rgb_many_colors()
    png = package / "phantom_city.png"
    save_canonical_rgb_png(png, image)
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
```

Add tests that assert:

```python
def test_target_accepts_truecolor_more_than_128_colors(tmp_path: Path) -> None:
    package = tmp_path / "package"
    _write_package(package)

    assert Fe8DialogueBackgroundSource240x160().validate(package) == []


def test_target_rejects_wrong_dimensions(tmp_path: Path) -> None:
    package = tmp_path / "package"
    _write_package(package, rgb=np.zeros((159, 240, 3), dtype=np.uint8))

    assert "INVALID_BACKGROUND_DIMENSIONS" in {
        item.code for item in Fe8DialogueBackgroundSource240x160().validate(package)
    }


def test_target_rejects_nonopaque_rgba(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    rgba = np.zeros((160, 240, 4), dtype=np.uint8)
    rgba[:, :, 3] = 255
    rgba[0, 0, 3] = 0
    png = package / "phantom_city.png"
    Image.fromarray(rgba, "RGBA").save(png)
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
        json.dumps(manifest.model_dump(mode="json")),
        encoding="utf-8",
    )

    assert "NON_OPAQUE_BACKGROUND" in {
        item.code for item in Fe8DialogueBackgroundSource240x160().validate(package)
    }


def test_target_rejects_hash_mismatch_and_extra_files(tmp_path: Path) -> None:
    package = tmp_path / "package"
    _write_package(package)
    payload = json.loads((package / "phantom_city.manifest.json").read_text("utf-8"))
    payload["png_sha256"] = "0" * 64
    (package / "phantom_city.manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    (package / "extra.bin").write_bytes(b"x")

    codes = {item.code for item in Fe8DialogueBackgroundSource240x160().validate(package)}
    assert {"BACKGROUND_HASH_MISMATCH", "UNEXPECTED_BACKGROUND_PACKAGE_ENTRY"} <= codes
```

Also cover corrupt PNG, missing manifest, unsafe/mismatched name, malformed metadata,
opaque RGBA, and indexed P packages.

- [ ] **Step 3: Run the focused tests and confirm they fail**

Run:

```powershell
pytest -q tests/dialogue_background/test_spec.py
```

Expected: failures because the I/O helpers and target spec are absent.

- [ ] **Step 4: Implement deterministic PNG helpers**

Add to `src/fecreator/imaging/io.py`:

```python
def load_opaque_png_rgb(
    path: Path,
    budget: ResourceBudget | None = None,
) -> tuple[np.ndarray, str]:
    actual_budget = budget or ResourceBudget()
    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                raise ValueError("image must be a PNG")
            if image.mode not in {"RGB", "RGBA", "P"}:
                raise ValueError(f"unsupported PNG mode: {image.mode}")
            width, height = image.size
            _check_pixel_budget(width, height, actual_budget)
            image.load()
            rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
            if bool(np.any(rgba[:, :, 3] != 255)):
                raise ValueError("PNG contains non-opaque pixels")
            return np.asarray(image.convert("RGB"), dtype=np.uint8).copy(), image.mode
    except ImageBudgetError:
        raise
    except (OSError, ValueError) as exc:
        raise ValueError(f"invalid opaque PNG: {path.name}") from exc


def _stored_zlib(payload: bytes) -> bytes:
    encoded = bytearray(b"\x78\x01")
    offset = 0
    while offset < len(payload):
        chunk = payload[offset : offset + 65535]
        offset += len(chunk)
        encoded.append(1 if offset == len(payload) else 0)
        encoded.extend(struct.pack("<H", len(chunk)))
        encoded.extend(struct.pack("<H", len(chunk) ^ 0xFFFF))
        encoded.extend(chunk)
    encoded.extend(struct.pack(">I", zlib.adler32(payload) & 0xFFFFFFFF))
    return bytes(encoded)


def save_canonical_rgb_png(path: Path, rgb: np.ndarray) -> None:
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.dtype(np.uint8):
        raise ValueError("rgb must be a uint8 (H, W, 3) array")
    height, width = rgb.shape[:2]
    raw = bytearray()
    for row in rgb:
        raw.append(0)
        raw.extend(row.tobytes())
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = (
        _PNG_SIG
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", _stored_zlib(bytes(raw)))
        + _png_chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_png(path, lambda tmp: Path(tmp).write_bytes(png))
```

- [ ] **Step 5: Implement target validation**

Create `validation.py` with constants `WIDTH = 240`, `HEIGHT = 160` and a
`validate_package()` function that:

```python
def validate_package(package_dir: Path) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if not package_dir.is_dir():
        return [error("MISSING_BACKGROUND_PACKAGE", "package directory does not exist")]

    entries = sorted(package_dir.iterdir(), key=lambda path: path.name)
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            diagnostics.append(
                error(
                    "UNSAFE_BACKGROUND_PACKAGE_ENTRY",
                    "package entries must be regular files",
                    where=entry.name,
                )
            )
    pngs = [entry for entry in entries if entry.suffix.casefold() == ".png"]
    manifests = [entry for entry in entries if entry.name.endswith(".manifest.json")]
    expected = {path.name for path in (*pngs, *manifests)}
    for entry in entries:
        if entry.name not in expected:
            diagnostics.append(
                error(
                    "UNEXPECTED_BACKGROUND_PACKAGE_ENTRY",
                    "dialogue background packages contain only PNG and manifest files",
                    where=entry.name,
                )
            )
    if len(pngs) != 1:
        diagnostics.append(error("MISSING_BACKGROUND_PNG", "package must contain one PNG"))
    if len(manifests) != 1:
        diagnostics.append(
            error("MISSING_BACKGROUND_MANIFEST", "package must contain one manifest")
        )
    if len(pngs) != 1 or len(manifests) != 1:
        return diagnostics

    png_path = pngs[0]
    manifest_path = manifests[0]
    try:
        manifest = DialogueBackgroundPackageManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        diagnostics.append(
            error(
                "INVALID_BACKGROUND_MANIFEST",
                "dialogue background manifest is malformed",
                where=manifest_path.name,
            )
        )
        return diagnostics

    if png_path.name != f"{manifest.name}.png" or manifest_path.name != (
        f"{manifest.name}.manifest.json"
    ):
        diagnostics.append(
            error(
                "BACKGROUND_NAME_MISMATCH",
                "package filenames must match manifest.name",
                where=manifest_path.name,
            )
        )
    try:
        rgb, _mode = load_opaque_png_rgb(png_path)
    except (ImageBudgetError, ValueError):
        diagnostics.append(
            error(
                "INVALID_BACKGROUND_PNG",
                "background must be a supported opaque PNG",
                where=png_path.name,
            )
        )
        return diagnostics
    if rgb.shape != (HEIGHT, WIDTH, 3):
        diagnostics.append(
            error(
                "INVALID_BACKGROUND_DIMENSIONS",
                f"background must be exactly {WIDTH}x{HEIGHT}",
                where=png_path.name,
            )
        )
    if sha256_file(png_path) != manifest.png_sha256:
        diagnostics.append(
            error(
                "BACKGROUND_HASH_MISMATCH",
                "manifest PNG hash does not match the package image",
                where=png_path.name,
            )
        )
    return diagnostics
```

Map the opacity-specific `ValueError` to `NON_OPAQUE_BACKGROUND` by inspecting it
inside a small helper rather than exposing Pillow errors.

Create `spec.py`:

```python
class Fe8DialogueBackgroundSource240x160:
    id = "fe8-dialogue-background-source-240x160"

    def validate(self, package_dir: Path) -> list[Diagnostic]:
        return validate_package(package_dir)
```

Register it idempotently in `src/fecreator/specs/__init__.py`.

- [ ] **Step 6: Run target and existing spec tests**

Run:

```powershell
pytest -q tests/dialogue_background/test_spec.py tests/specs
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit deterministic target support**

```powershell
git add src/fecreator/imaging/io.py src/fecreator/specs tests/dialogue_background/test_spec.py tests/specs
git commit -m "feat: validate dialogue background packages" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: Extract asset-neutral review and final publication

**Files:**
- Create: `src/fecreator/assets/candidate.py`
- Create: `src/fecreator/assets/reviewed.py`
- Create: `src/fecreator/assets/publication.py`
- Modify: `src/fecreator/assets/base.py`
- Modify: `src/fecreator/assets/portrait/candidate.py`
- Modify: `src/fecreator/assets/portrait/plugin.py`
- Delete: `src/fecreator/assets/portrait/publication.py`
- Modify: `src/fecreator/app.py`
- Modify: `tests/portrait/test_build_e2e.py`
- Modify: `tests/portrait/test_build_concurrency.py`
- Modify: `tests/app/test_app.py`

**Interfaces:**
- Produces: `CandidatePublication`.
- Produces: `ReviewedAssetPlugin[PreparedT]`.
- Produces: `finalize_candidate(data_root, job, candidate, approval) -> JobResult`.
- Changes: `AssetPlugin.finalize()` becomes required.
- Preserves: portrait build state transitions, locks, rollback order, candidate bytes, and final package bytes.

- [ ] **Step 1: Add a failing facade-dispatch test**

In `tests/app/test_app.py`, register a temporary plugin whose `finalize()` records
its arguments, create a job for that plugin, seed a candidate and approval, and assert
`FeCreatorApp.finalize_job()` invokes the plugin rather than importing portrait code.
The test double must implement:

```python
def finalize(
    self,
    *,
    data_root: Path,
    job: Job,
    candidate: CandidateSnapshot,
    approval: ApprovalRecord,
) -> JobResult:
    self.finalized = (data_root, job.id, candidate.job_id, approval.actor)
    return JobResult(job_id=job.id, ok=True)
```

- [ ] **Step 2: Capture the existing portrait package hash**

Add a regression assertion to `tests/portrait/test_build_e2e.py` after a fake
`text_to_portrait` build:

```python
assert sha256_file(ctx.workspace / "candidate" / "package" / "hero.png") == (
    "7f90e17b62494767ad47a7cf4ab0d5cb8ae4e3b859c9ac09b775d4e989d4b163"
)
assert sha256_file(ctx.workspace / "candidate" / "package" / "hero.pal") == (
    "e81a04260b01b1293d81b34c148c771a5215c54ebb74be1377c944d434a5fbc1"
)
```

Obtain the two literal hashes by running the existing test fixture once before
moving code. Store the literal values in the test; do not recompute the expected
value from the implementation.

- [ ] **Step 3: Run the focused tests and confirm facade dispatch fails**

Run:

```powershell
pytest -q tests/app/test_app.py tests/portrait/test_build_e2e.py -k "finalize or package_hash"
```

Expected: the new dispatch test fails because `FeCreatorApp` imports portrait
publication directly; the existing portrait hash probe passes before refactoring.

- [ ] **Step 4: Extract candidate publication**

Move `CandidatePublication`, `publish_candidate_atomically()`,
`rollback_candidate_publication()`, and their tree cleanup helper unchanged from
`assets/portrait/candidate.py` into `assets/candidate.py`. Update portrait candidate
assembly to import:

```python
from fecreator.assets.candidate import CandidatePublication
```

The concrete class remains:

```python
@dataclass
class CandidatePublication:
    snapshot: CandidateSnapshot
    lineage: LineageNode
    staged_root: Path
    candidate_published: bool = field(init=False, default=False)
    lineage_published: bool = field(init=False, default=False)

    def publish(self, workspace: Path) -> None:
        publish_candidate_atomically(workspace, self.snapshot, self.lineage, self.staged_root)
        self.candidate_published = True
        self.lineage_published = True

    def rollback(self, workspace: Path) -> None:
        rollback_candidate_publication(
            workspace,
            self.lineage.asset_id,
            self.staged_root,
            candidate_published=self.candidate_published,
            lineage_published=self.lineage_published,
        )
```

- [ ] **Step 5: Extract the reviewed-plugin base**

Create `assets/reviewed.py` by moving the following existing `PortraitPlugin`
methods without behavioral changes:

```text
build
_build_lease
_claim_build
_run_provider
_stage_candidate
_publish_candidate
_fail
_reference_pack
_load_job
_assert_manifest_supported
_mark_job_failed_if_possible
_transition_job
_transition_steps
```

Define the subclass hooks exactly as:

```python
PreparedT = TypeVar("PreparedT")


class AssetWorkflowFailure(Exception):
    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        super().__init__(
            ", ".join(f"{diagnostic.code}: {diagnostic.message}" for diagnostic in diagnostics)
        )
        self.diagnostics = diagnostics


class CandidateValidationError(Exception):
    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        super().__init__("candidate package validation failed")
        self.diagnostics = diagnostics


class ReviewedAssetPlugin(Generic[PreparedT]):
    id: str
    target_spec: str
    workflows: frozenset[str]

    def _prepare(
        self,
        manifest: Manifest,
        pack: ReferencePack | None,
        provider: Provider,
        workspace: Path,
    ) -> PreparedT:
        raise NotImplementedError

    def _prepare_candidate(
        self,
        *,
        ctx: PipelineContext,
        manifest: Manifest,
        prepared: PreparedT,
        reference_pack: ReferencePack | None,
        parent_candidate_id: str | None,
    ) -> CandidatePublication:
        raise NotImplementedError

    def finalize(
        self,
        *,
        data_root: Path,
        job: Job,
        candidate: CandidateSnapshot,
        approval: ApprovalRecord,
    ) -> JobResult:
        return finalize_candidate(
            data_root=data_root,
            job=job,
            candidate=candidate,
            approval=approval,
        )
```

Change `_assert_manifest_supported()` to compare `manifest.asset_type`,
`manifest.target_spec`, and `manifest.workflow` against the three class attributes.

Make portrait `WorkflowFailure` inherit from `AssetWorkflowFailure`, import
`CandidateValidationError` from `assets.reviewed`, and reduce `PortraitPlugin` to
its capability, source-plan, `_prepare()`, and `_prepare_candidate()` hooks:

```python
class PortraitPlugin(ReviewedAssetPlugin[PreparedPortrait]):
    id = "portrait"
    target_spec = "fe-gba-portrait-standard"
    workflows = WORKFLOWS

    def _prepare_candidate(self, **kwargs: object) -> CandidatePublication:
        return prepare_candidate(**kwargs)
```

Use a fully typed explicit signature instead of `**kwargs` in the actual file.

- [ ] **Step 6: Extract generic final publication**

Move the current contents of `assets/portrait/publication.py` to
`assets/publication.py`. Replace the hard-coded portrait validator with:

```python
spec = cast(TargetSpec, SPEC_REGISTRY.get(job.manifest.target_spec))
diagnostics = tuple(spec.validate(candidate_package))
```

Keep staging paths, copy behavior, report construction, lineage export, bundle
construction, rollback flags, cleanup order, and state transitions unchanged.

Update `AssetPlugin` with the exact `finalize()` signature above. Change
`FeCreatorApp.finalize_job()` to:

```python
plugin = cast(AssetPlugin, ASSET_REGISTRY.get(job.manifest.asset_type))
return plugin.finalize(
    data_root=self._settings.data_root,
    job=job,
    candidate=candidate,
    approval=approval,
)
```

Update the rollback monkeypatch in `test_build_e2e.py` to import
`fecreator.assets.publication`.

- [ ] **Step 7: Run portrait lifecycle tests**

Run:

```powershell
pytest -q tests/app/test_app.py tests/portrait/test_build_e2e.py tests/portrait/test_build_concurrency.py
```

Expected: all selected tests pass and the portrait package hashes remain unchanged.

- [ ] **Step 8: Commit shared orchestration**

```powershell
git add src/fecreator/assets src/fecreator/app.py tests/app tests/portrait
git commit -m "refactor: share reviewed asset publication" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 4: Implement dialogue-background workflows and candidate packaging

**Files:**
- Create: `src/fecreator/assets/dialogue_background/__init__.py`
- Create: `src/fecreator/assets/dialogue_background/manifest.py`
- Create: `src/fecreator/assets/dialogue_background/prompt_plan.py`
- Create: `src/fecreator/assets/dialogue_background/workflows.py`
- Create: `src/fecreator/assets/dialogue_background/candidate.py`
- Create: `src/fecreator/assets/dialogue_background/plugin.py`
- Modify: `src/fecreator/assets/__init__.py`
- Modify: `src/fecreator/contracts/lineage.py`
- Modify: `src/fecreator/providers/manual.py`
- Create: `tests/dialogue_background/test_workflows.py`
- Create: `tests/dialogue_background/test_build_e2e.py`
- Modify: `tests/providers/test_manual.py`

**Interfaces:**
- Produces: `DialogueBackgroundPlugin`.
- Produces: `PreparedDialogueBackground`.
- Produces: `prepare_text_to_dialogue_background()`,
  `prepare_concept_to_dialogue_background()`, and
  `prepare_masked_variant()`.
- Produces: deterministic candidate package artifacts with roles `background` and
  `manifest`.

- [ ] **Step 1: Write failing capability and source-plan tests**

Create `tests/dialogue_background/test_workflows.py` with:

```python
def _metadata() -> AssetMetadata:
    return AssetMetadata(
        name="phantom_city",
        purpose="Original phantom city",
        source=SourceIdentity(kind="prompt", id="bg/phantom-city", revision="1"),
        license_note="Original repository fixture.",
        source_note="Generated from an original prompt.",
    )


def _manifest(workflow: str = "text_to_dialogue_background") -> Manifest:
    return Manifest(
        asset_type="dialogue_background",
        target_spec="fe8-dialogue-background-source-240x160",
        workflow=workflow,
        provider="fake",
        metadata=_metadata(),
        sources=(SourceSpec(kind="text", ref="phantom city"),),
    )


def test_plugin_declares_required_capabilities() -> None:
    plugin = DialogueBackgroundPlugin()

    assert plugin.required_capabilities("text_to_dialogue_background") == {
        Capability.TEXT_TO_IMAGE
    }
    assert plugin.required_capabilities("concept_to_dialogue_background") == {
        Capability.IMAGE_TO_IMAGE
    }
    assert plugin.required_capabilities("masked_variant") == {Capability.MASKED_EDIT}


def test_source_plan_documents_opaque_240x160_contract() -> None:
    plan = DialogueBackgroundPlugin().plan_sources(_manifest(), None)

    assert plan.expected_filenames == ("phantom_city.png",)
    assert "240x160" in plan.background_contract
    assert "opaque" in plan.background_contract
    assert plan.forbidden_colors == ()
```

- [ ] **Step 2: Write failing build and determinism tests**

Create `tests/dialogue_background/test_build_e2e.py`:

```python
def test_fake_text_workflow_builds_reviewable_package(data_root: Path) -> None:
    app = FeCreatorApp(Settings(data_root=data_root))
    manifest = Manifest(
        asset_type="dialogue_background",
        target_spec="fe8-dialogue-background-source-240x160",
        workflow="text_to_dialogue_background",
        provider="fake",
        metadata=_metadata(),
        sources=(SourceSpec(kind="text", ref="phantom city"),),
        params={"width": 240, "height": 160},
    )
    job = app.create_job(manifest)

    result = app.build(job.id)

    assert result.ok is True
    assert app.get_job(job.id).state is JobState.WAITING_FOR_REVIEW
    package = data_root / "jobs" / job.id / "candidate" / "package"
    assert Fe8DialogueBackgroundSource240x160().validate(package) == []
    assert {path.name for path in package.iterdir()} == {
        "phantom_city.png",
        "phantom_city.manifest.json",
    }


def test_identical_inputs_produce_identical_candidate_package_bytes(data_root: Path) -> None:
    app = FeCreatorApp(Settings(data_root=data_root))
    first = app.create_job(_fake_manifest())
    second = app.create_job(_fake_manifest())

    assert app.build(first.id).ok is True
    assert app.build(second.id).ok is True

    first_package = data_root / "jobs" / first.id / "candidate" / "package"
    second_package = data_root / "jobs" / second.id / "candidate" / "package"
    for filename in ("phantom_city.png", "phantom_city.manifest.json"):
        assert (first_package / filename).read_bytes() == (second_package / filename).read_bytes()
```

Add concept tests for missing concept input and capability refusal. Add masked-variant
tests that seed an approved package and parent lineage, apply a binary mask, assert
pixels outside the mask are unchanged, and assert protected-region changes fail.

- [ ] **Step 3: Write failing manual-provider sidecar test**

Add to `tests/providers/test_manual.py`:

```python
def test_manual_provider_ignores_supported_package_sidecars(tmp_path: Path) -> None:
    submitted = tmp_path / "submitted"
    submitted.mkdir()
    save_png(submitted / "background.png", np.zeros((160, 240, 3), dtype=np.uint8))
    (submitted / "background.manifest.json").write_text("{}", encoding="utf-8")
    (submitted / "background.pal").write_text("JASC-PAL\n0100\n0\n", encoding="ascii")

    response = ManualProvider().generate(GenRequest(workflow="masked_variant"), tmp_path)

    assert response.ok is True
    assert [artifact.path for artifact in response.artifacts] == ["submitted/background.png"]
```

- [ ] **Step 4: Run focused tests and confirm they fail**

Run:

```powershell
pytest -q tests/dialogue_background/test_workflows.py tests/dialogue_background/test_build_e2e.py tests/providers/test_manual.py
```

Expected: failures because the plugin and workflow modules do not exist and sidecars
are rejected.

- [ ] **Step 5: Implement capability and prompt modules**

In `manifest.py` define:

```python
WORKFLOWS = frozenset(
    {"text_to_dialogue_background", "concept_to_dialogue_background", "masked_variant"}
)
REQUIRED_CAPS = {
    "text_to_dialogue_background": {Capability.TEXT_TO_IMAGE},
    "concept_to_dialogue_background": {Capability.IMAGE_TO_IMAGE},
    "masked_variant": {Capability.MASKED_EDIT},
}
PREFERRED_CAPS = {
    "text_to_dialogue_background": {Capability.SEED_CONTROL, Capability.SIZE_CONTROL},
    "concept_to_dialogue_background": {
        Capability.MULTI_REFERENCE,
        Capability.STYLE_REFERENCE,
        Capability.SIZE_CONTROL,
    },
    "masked_variant": {Capability.BACKGROUND_CONTROL, Capability.SIZE_CONTROL},
}
```

In `prompt_plan.py`, build one deterministic prompt:

```python
def build_prompt(manifest: Manifest, pack: ReferencePack | None) -> str:
    text = " ".join(source.ref for source in manifest.sources if source.kind == "text")
    subject = text or cast(AssetMetadata, manifest.metadata).purpose
    forbidden = (
        f"; preserve: {', '.join(pack.forbidden_changes)}"
        if pack and pack.forbidden_changes
        else ""
    )
    return (
        f"{subject}{forbidden}; Fire Emblem 8 dialogue background source; "
        "240x160 composition; no text, logos, portrait frames, or characters; "
        "keep critical focal detail out of the lower 48 pixels"
    )
```

Return a `SourcePlan` with expected filename `<metadata.name>.png`, no expressions,
no forbidden colors, and source/license notes in `SubmissionSchema`.

- [ ] **Step 6: Implement workflow preparation**

Define:

```python
@dataclass(frozen=True)
class PreparedDialogueBackground:
    rgb: np.ndarray
    operation: Operation
    provider_model: str | None
    prompt: str | None
    seed: int | None
    diagnostics: tuple[Diagnostic, ...]
    inputs: tuple[Artifact, ...]
    parents: tuple[str, ...] = ()
    mask: str | None = None
    protected_regions: tuple[Region, ...] = ()
    metrics: Mapping[str, float] = field(
        default_factory=lambda: {"width": 240.0, "height": 160.0}
    )
```

Implement the three functions with these exact capability and input rules:

```python
def prepare_text_to_dialogue_background(
    manifest: Manifest,
    pack: ReferencePack | None,
    provider: Provider,
    workspace: Path,
) -> PreparedDialogueBackground:
    require_capabilities(provider, {Capability.TEXT_TO_IMAGE})
    references = concept_art_artifacts(pack) if pack else ()
    return _generate(
        manifest,
        pack,
        provider,
        workspace,
        operation=Operation.CREATE_DIALOGUE_BACKGROUND,
        references=references,
    )


def prepare_concept_to_dialogue_background(
    manifest: Manifest,
    pack: ReferencePack | None,
    provider: Provider,
    workspace: Path,
) -> PreparedDialogueBackground:
    references = _concept_inputs(manifest, pack, workspace)
    if not references:
        raise WorkflowInputError(
            (error("WORKFLOW_INPUT_MISSING", "concept workflow requires concept art"),)
        )
    require_capabilities(provider, {Capability.IMAGE_TO_IMAGE})
    return _generate(
        manifest,
        pack,
        provider,
        workspace,
        operation=Operation.IMPORT_DIALOGUE_BACKGROUND_CONCEPT,
        references=references,
    )


def prepare_masked_variant(
    manifest: Manifest,
    pack: ReferencePack | None,
    provider: Provider,
    workspace: Path,
) -> PreparedDialogueBackground:
    approved = _load_approved_background(workspace, manifest)
    mask, mask_artifact = _load_bool_mask(workspace, cast(EditSpec, manifest.edit).mask_path)
    require_capabilities(provider, {Capability.MASKED_EDIT})
    response = provider.generate(
        GenRequest(
            workflow=manifest.workflow,
            prompt=build_prompt(manifest, pack),
            references=(approved.png_artifact,),
            mask=mask_artifact,
            protected_regions=cast(EditSpec, manifest.edit).protected_regions,
            params=manifest.params,
        ),
        workspace,
    )
    edited = _load_selected_background(response, workspace, cast(AssetMetadata, manifest.metadata).name)
    result, diagnostics = build_variant(
        approved.rgb,
        edited,
        mask,
        cast(EditSpec, manifest.edit).protected_regions,
    )
    if has_errors(diagnostics):
        raise WorkflowFailure(tuple(response.diagnostics) + tuple(diagnostics))
    return PreparedDialogueBackground(
        rgb=result,
        operation=Operation.VARIANT_MASKED_EDIT,
        provider_model=response.model,
        prompt=build_prompt(manifest, pack),
        seed=response.seed,
        diagnostics=tuple(response.diagnostics) + tuple(diagnostics),
        inputs=(approved.png_artifact, approved.manifest_artifact, mask_artifact),
        parents=(cast(str, manifest.parent_asset_id),),
        mask=cast(EditSpec, manifest.edit).mask_path,
        protected_regions=cast(EditSpec, manifest.edit).protected_regions,
    )
```

Use `safe_join`, single-filename normalization, actual SHA-256 checks, and
`load_opaque_png_rgb()` for every submitted/provider PNG. `_load_selected_background`
must prefer roles in this order: metadata name, `background`, `variant`, `neutral`;
if none match, accept only one image artifact.

The shared generator has this exact signature:

```python
def _generate(
    manifest: Manifest,
    pack: ReferencePack | None,
    provider: Provider,
    workspace: Path,
    *,
    operation: Operation,
    references: tuple[Artifact, ...],
) -> PreparedDialogueBackground:
    prompt = build_prompt(manifest, pack)
    response = provider.generate(
        GenRequest(
            workflow=manifest.workflow,
            prompt=prompt,
            references=references,
            params=manifest.params,
        ),
        workspace,
    )
    metadata = cast(AssetMetadata, manifest.metadata)
    rgb = _load_selected_background(response, workspace, metadata.name)
    return PreparedDialogueBackground(
        rgb=rgb,
        operation=operation,
        provider_model=response.model,
        prompt=prompt,
        seed=response.seed,
        diagnostics=tuple(response.diagnostics),
        inputs=references,
    )
```

- [ ] **Step 7: Implement deterministic candidate packaging**

In `candidate.py`, compute the input hash:

```python
def _input_hash(manifest: Manifest, inputs: tuple[Artifact, ...]) -> str:
    payload = {
        "manifest": manifest.model_dump(mode="json"),
        "inputs": [
            artifact.model_dump(mode="json")
            for artifact in sorted(
                inputs,
                key=lambda item: (item.role, item.path, item.sha256, item.media_type),
            )
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(canonical.encode("utf-8"))
```

Write `<name>.png` using `save_canonical_rgb_png()`, then write
`<name>.manifest.json` with `write_json_atomic()` and:

```python
DialogueBackgroundPackageManifest(
    name=metadata.name,
    purpose=metadata.purpose,
    provider=manifest.provider,
    model=prepared.provider_model,
    prompt=prepared.prompt,
    reference_pack=reference_pack.id if reference_pack else None,
    reference_pack_rev=reference_pack.revision if reference_pack else None,
    source=DialogueBackgroundSourceRecord(
        kind=metadata.source.kind,
        id=metadata.source.id,
        revision=metadata.source.revision,
        input_sha256=_input_hash(manifest, prepared.inputs),
    ),
    png_sha256=sha256_file(png_path),
    license_note=metadata.license_note,
    source_note=metadata.source_note,
    requested_downstream_profile=metadata.requested_downstream_profile,
)
```

Validate the staged package with `Fe8DialogueBackgroundSource240x160`, create
artifacts with `candidate/package/<name>.png` and
`candidate/package/<name>.manifest.json`, create `<job>-candidate` lineage, and
return the shared `CandidatePublication`.

Add `CREATE_DIALOGUE_BACKGROUND` and
`IMPORT_DIALOGUE_BACKGROUND_CONCEPT` to `Operation`.

- [ ] **Step 8: Implement and register the plugin**

Define:

```python
class DialogueBackgroundPlugin(ReviewedAssetPlugin[PreparedDialogueBackground]):
    id = "dialogue_background"
    target_spec = "fe8-dialogue-background-source-240x160"
    workflows = WORKFLOWS

    def required_capabilities(self, workflow: str) -> set[Capability]:
        return required_capabilities(workflow)

    def preferred_capabilities(self, workflow: str) -> set[Capability]:
        return preferred_capabilities(workflow)

    def plan_sources(self, manifest: Manifest, pack: ReferencePack | None) -> SourcePlan:
        return prompt_plan.plan_sources(manifest, pack)

    def _prepare(
        self,
        manifest: Manifest,
        pack: ReferencePack | None,
        provider: Provider,
        workspace: Path,
    ) -> PreparedDialogueBackground:
        if manifest.workflow == "text_to_dialogue_background":
            return prepare_text_to_dialogue_background(manifest, pack, provider, workspace)
        if manifest.workflow == "concept_to_dialogue_background":
            return prepare_concept_to_dialogue_background(manifest, pack, provider, workspace)
        return prepare_masked_variant(manifest, pack, provider, workspace)

    def _prepare_candidate(
        self,
        *,
        ctx: PipelineContext,
        manifest: Manifest,
        prepared: PreparedDialogueBackground,
        reference_pack: ReferencePack | None,
        parent_candidate_id: str | None,
    ) -> CandidatePublication:
        return prepare_candidate(
            ctx=ctx,
            manifest=manifest,
            prepared=prepared,
            reference_pack=reference_pack,
            parent_candidate_id=parent_candidate_id,
        )
```

Register it idempotently in `assets/__init__.py`.

Change `ManualProvider.generate()` to skip only filenames ending in `.manifest.json`
or `.pal`; retain failure for every other unsupported regular file.

- [ ] **Step 9: Run workflow and portrait regression tests**

Run:

```powershell
pytest -q tests/dialogue_background tests/providers/test_manual.py tests/portrait
```

Expected: all selected tests pass.

- [ ] **Step 10: Commit the asset plugin**

```powershell
git add src/fecreator/assets src/fecreator/contracts/lineage.py src/fecreator/providers/manual.py tests/dialogue_background tests/providers
git commit -m "feat: build dialogue background candidates" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 5: Make reproducibility bundles target-aware

**Files:**
- Modify: `src/fecreator/reporting/bundle.py`
- Modify: `tests/reporting/test_bundle.py`
- Modify: `tests/portrait/test_build_e2e.py`
- Modify: `tests/dialogue_background/test_build_e2e.py`

**Interfaces:**
- Preserves: portrait `compat.json` structure and FEBuilder roundtrip.
- Produces: dialogue-background source-package hash evidence and verification.
- Produces: explicit downstream adapter status `not_run`.

- [ ] **Step 1: Write failing background-bundle tests**

Add to `tests/reporting/test_bundle.py`:

```python
@pytest.fixture
def completed_background_workspace(
    data_root: Path,
) -> tuple[Job, Path]:
    app = FeCreatorApp(Settings(data_root=data_root))
    job = app.create_job(_background_manifest())
    assert app.build(job.id).ok is True
    app.approve_review(job.id, "reviewer")
    assert app.finalize_job(job.id).ok is True
    return app.get_job(job.id), data_root / "jobs" / job.id


def test_dialogue_background_bundle_records_source_hash_evidence(
    completed_background_workspace: tuple[Job, Path],
    tmp_path: Path,
) -> None:
    job, workspace = completed_background_workspace

    bundle = build_bundle(job, workspace, tmp_path / "bundle")
    compat = json.loads((bundle / "compat.json").read_text("utf-8"))

    assert compat == {
        "algorithm": "sha256",
        "external_adapter": {
            "profile": "fe8-dialogue-background-feimg2",
            "status": "not_run",
        },
        "package_files": {
            "phantom_city.manifest.json": sha256_file(
                workspace / "package" / "phantom_city.manifest.json"
            ),
            "phantom_city.png": sha256_file(workspace / "package" / "phantom_city.png"),
        },
        "source": "deterministic_dialogue_background_source_package",
        "status": "passed",
    }
    assert verify_bundle(bundle) == []


def test_dialogue_background_bundle_rejects_compat_hash_tampering(
    completed_background_workspace: tuple[Job, Path],
    tmp_path: Path,
) -> None:
    job, workspace = completed_background_workspace
    bundle = build_bundle(job, workspace, tmp_path / "bundle")
    compat = json.loads((bundle / "compat.json").read_text("utf-8"))
    compat["package_files"]["phantom_city.png"] = "0" * 64
    (bundle / "compat.json").write_text(json.dumps(compat), encoding="utf-8")
    _refresh_declared_hash(bundle, "compat.json")

    assert "BUNDLE_COMPAT_EVIDENCE_MISMATCH" in {
        item.code for item in verify_bundle(bundle)
    }
```

Add a portrait regression asserting the existing portrait `compat.json` still has
`source == "deterministic_febuilder_compatible_roundtrip"` and unchanged keys.

- [ ] **Step 2: Run focused bundle tests and confirm they fail**

Run:

```powershell
pytest -q tests/reporting/test_bundle.py -k "dialogue_background or compatibility"
```

Expected: dialogue-background bundle construction fails in portrait roundtrip decoding.

- [ ] **Step 3: Add the background evidence model and writer**

In `bundle.py`, add:

```python
class _ExternalBackgroundAdapter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["not_run", "passed", "failed"]
    profile: Literal["fe8-dialogue-background-feimg2"] | None = None


class _DialogueBackgroundCompatEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["deterministic_dialogue_background_source_package"]
    status: Literal["passed"]
    algorithm: Literal["sha256"]
    package_files: dict[str, str]
    external_adapter: _ExternalBackgroundAdapter
```

Build evidence with:

```python
def _dialogue_background_compat_report(
    package_files: list[Path],
    package_dir: Path,
    profile: str | None,
) -> JsonObject:
    return {
        "source": "deterministic_dialogue_background_source_package",
        "status": "passed",
        "algorithm": "sha256",
        "package_files": {
            path.relative_to(package_dir).as_posix(): sha256_file(path)
            for path in package_files
        },
        "external_adapter": {"status": "not_run", "profile": profile},
    }
```

In `build_bundle()`, preserve the existing portrait branch exactly. For the new
target spec, reject a non-`None` `febuilder_cli` because the existing command is a
portrait validator, parse the package manifest to get the requested profile, and
write `_dialogue_background_compat_report()`.

- [ ] **Step 4: Dispatch bundle verification by manifest target**

Validate `manifest.json` before `compat.json`, then:

```python
if manifest.target_spec == "fe-gba-portrait-standard":
    compat = _validate_portrait_compat_file(bundle_dir, diagnostics, missing_files)
else:
    compat = _validate_dialogue_background_compat_file(
        bundle_dir,
        diagnostics,
        missing_files,
    )
```

After package hashes are calculated, compare background evidence to the actual
`package/` files:

```python
expected = {
    path.removeprefix("package/"): digest
    for path, digest in actual_package_hashes.items()
}
if compat.package_files != expected:
    diagnostics.append(
        error(
            "BUNDLE_COMPAT_EVIDENCE_MISMATCH",
            "compat.json package hashes do not describe the bundled package",
            where="compat.json",
        )
    )
if compat.external_adapter.status == "failed":
    diagnostics.append(
        error(
            "BUNDLE_EXTERNAL_ADAPTER_FAILURE",
            "configured downstream compatibility adapter failed",
            where="compat.json",
        )
    )
```

- [ ] **Step 5: Run bundle and end-to-end finalization tests**

Run:

```powershell
pytest -q tests/reporting/test_bundle.py tests/portrait/test_build_e2e.py tests/dialogue_background/test_build_e2e.py
```

Expected: all selected tests pass; background finalization produces package, report,
lineage, and a verified bundle.

- [ ] **Step 6: Commit target-aware bundles**

```powershell
git add src/fecreator/reporting/bundle.py tests/reporting tests/portrait tests/dialogue_background
git commit -m "feat: bundle dialogue background sources" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 6: Prove CLI, HTTP, MCP, review, lineage, reports, and bundles

**Files:**
- Modify: `tests/integration/test_interface_equivalence.py`
- Modify: `tests/interfaces/test_cli_json.py`
- Modify: `tests/interfaces/test_http_api.py`
- Modify: `tests/interfaces/test_mcp_server.py`
- Modify: `tests/contracts/test_contract_freeze.py`

**Interfaces:**
- Consumes only existing CLI commands, HTTP routes, MCP tools, and `FeCreatorApp`.
- Produces acceptance evidence for an opaque truecolor fixture with more than 128 colors.

- [ ] **Step 1: Add one reusable truecolor fixture helper**

In `tests/dialogue_background/conftest.py`, create:

```python
@pytest.fixture
def truecolor_background_sources(tmp_path: Path) -> Path:
    sources = tmp_path / "sources"
    sources.mkdir()
    y, x = np.indices((160, 240), dtype=np.uint16)
    rgb = np.stack(
        (x % 256, y % 256, (x * 17 + y * 29) % 256),
        axis=2,
    ).astype(np.uint8)
    Image.fromarray(rgb, "RGB").save(sources / "phantom_city.png")
    return sources
```

Use a manifest with provider `manual`, workflow `text_to_dialogue_background`, and
the metadata from Task 1.

- [ ] **Step 2: Add a failing CLI completion flow**

Drive the existing JSON CLI handlers:

```python
create -> job plan-sources -> job submit-sources -> job build
-> job approve -> job finalize -> job artifact -> job report -> job bundle
```

Assert exit code zero, `waiting_for_review` before approval, `completed` after
finalization, both final package artifacts readable, and the bundle contains a
`not_run` downstream adapter.

- [ ] **Step 3: Add a failing MCP completion flow**

Call the existing handlers from `make_handlers(app)`:

```python
create_job
submit_sources
build_asset
approve_review
finalize_job
read_job_artifact
get_job_report
list_bundle_entries
```

Assert every result has `isError is False`, the artifact hashes match disk, and the
manifest literals survive structured-content serialization.

- [ ] **Step 4: Add a failing HTTP completion flow**

Use `TestClient(create_api(app))` and the existing routes to create the job, upload
the truecolor PNG, build, approve, finalize, read artifacts, read report, and list
bundle entries. Assert status codes, state transitions, and package names.

- [ ] **Step 5: Run interface tests**

Run:

```powershell
pytest -q tests/integration/test_interface_equivalence.py tests/interfaces/test_cli_json.py tests/interfaces/test_http_api.py tests/interfaces/test_mcp_server.py
```

Expected before any fixes: failures reveal any remaining portrait assumptions in
serialization, route handling, tool input schemas, or finalization. Fix only those
shared assumptions; do not add dialogue-specific interface branches.

- [ ] **Step 6: Update the frozen interface inventory**

Keep route, command, and tool name inventories unchanged. Update only registry,
manifest literal, schema, operation, and workflow capability assertions:

```python
assert app.list_assets() == ["dialogue_background", "portrait"]
assert app.list_specs() == [
    "fe-gba-portrait-standard",
    "fe8-dialogue-background-source-240x160",
]
```

- [ ] **Step 7: Run interface and freeze tests**

Run:

```powershell
pytest -q tests/interfaces tests/integration/test_interface_equivalence.py tests/contracts/test_contract_freeze.py
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit interface acceptance coverage**

```powershell
git add tests/integration tests/interfaces tests/contracts/test_contract_freeze.py
git commit -m "test: prove dialogue background interfaces" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 7: Synchronize TypeScript types, docs, and public fixtures

**Files:**
- Modify: `web/src/api/types.ts`
- Modify: `web/src/api/types.contract.test.ts`
- Modify: `web/src/demo/demoClient.ts`
- Modify: `web/src/demo/demoClient.test.ts`
- Modify: `docs/product-statement.md`
- Modify: `docs/v1-contract.md`
- Modify: `docs/febuilder-interop.md`
- Add from branch: `docs/feature-requests/fe8-dialogue-background/*`

**Interfaces:**
- Produces: TypeScript mirrors of the additive Python contracts.
- Preserves: portrait-only deterministic demo behavior.
- Documents: source/downstream boundary and public example evidence.

- [ ] **Step 1: Write failing TypeScript contract assertions**

Update `web/src/api/types.contract.test.ts`:

```typescript
expectTypeOf<Manifest["asset_type"]>().toEqualTypeOf<
  "portrait" | "dialogue_background"
>();
expectTypeOf<Manifest["target_spec"]>().toEqualTypeOf<
  "fe-gba-portrait-standard" | "fe8-dialogue-background-source-240x160"
>();
expectTypeOf<Workflow>().toEqualTypeOf<
  | "text_to_portrait"
  | "concept_to_portrait"
  | "expression_refine"
  | "masked_variant"
  | "text_to_dialogue_background"
  | "concept_to_dialogue_background"
>();
expectTypeOf<SourceKind>().toEqualTypeOf<
  "text" | "concept_art" | "approved_portrait" | "approved_dialogue_background"
>();
```

Add exact shape assertions for `SourceIdentity`, `AssetMetadata`, and
`DialogueBackgroundPackageManifest`.

- [ ] **Step 2: Run the TypeScript contract test and confirm it fails**

Run:

```powershell
npm run -w @laqieer/fecreator-web test -- src/api/types.contract.test.ts
```

Expected: compile-time assertion failures.

- [ ] **Step 3: Update TypeScript mirrors**

Add:

```typescript
export type AssetType = "portrait" | "dialogue_background";
export type TargetSpec =
  | "fe-gba-portrait-standard"
  | "fe8-dialogue-background-source-240x160";
export type SourceKind =
  | "text"
  | "concept_art"
  | "approved_portrait"
  | "approved_dialogue_background";

export interface SourceIdentity {
  kind: string;
  id: string;
  revision: string;
}

export interface AssetMetadata {
  name: string;
  purpose: string;
  source: SourceIdentity;
  license_note: string;
  source_note: string;
  requested_downstream_profile: "fe8-dialogue-background-feimg2" | null;
}

export interface DialogueBackgroundSourceRecord {
  kind: string;
  id: string;
  revision: string;
  input_sha256: string;
}

export interface DialogueBackgroundPackageManifest {
  version: "1.0";
  contract_version: "1.0";
  asset_type: "dialogue_background";
  asset_type_version: "1.0";
  target_spec: "fe8-dialogue-background-source-240x160";
  target_spec_version: "1.0";
  name: string;
  purpose: string;
  width: 240;
  height: 160;
  opaque: true;
  provider: string;
  model: string | null;
  prompt: string | null;
  reference_pack: string | null;
  reference_pack_rev: number | null;
  source: DialogueBackgroundSourceRecord;
  png_sha256: string;
  license_note: string;
  source_note: string;
  requested_downstream_profile: "fe8-dialogue-background-feimg2" | null;
}
```

Extend `Workflow`, change `Manifest.asset_type` and `target_spec` to the aliases,
and add `metadata: AssetMetadata | null`.

Add the package manifest interface with the exact Python fields and literals.

Keep `ManifestControls` portrait-only. Update demo validation so it still explicitly
rejects `dialogue_background` with the existing offline-demo error path.

- [ ] **Step 4: Import public fixture commits**

Cherry-pick the four fixture-only commits:

```powershell
git cherry-pick c92371c 03eb56c 178d5e1 3d9cf4c
```

Confirm the diff adds only:

```text
docs/feature-requests/fe8-dialogue-background/
```

- [ ] **Step 5: Update product and compatibility docs**

Change `docs/product-statement.md` so v1 includes:

```markdown
- Asset plugins: `portrait`, `dialogue_background`.
- Target specs: `fe-gba-portrait-standard`,
  `fe8-dialogue-background-source-240x160`.
- Dialogue backgrounds stop at deterministic opaque 240x160 source packages;
  FE8 color reduction, palette banks, TSA conversion, and ROM integration are downstream.
```

Update `docs/v1-contract.md` tables for every new literal, model, schema, registry,
workflow capability, operation, and target-spec rule.

Update `docs/febuilder-interop.md` with the exact downstream command from issue #2
and state that FECreator does not duplicate `DecreaseColorCore` or validate palette
banks/TSA at the source stage.

- [ ] **Step 6: Run web and documentation contract checks**

Run:

```powershell
npm run -w @laqieer/fecreator-web typecheck
npm run -w @laqieer/fecreator-web lint
npm run -w @laqieer/fecreator-web test -- src/api/types.contract.test.ts src/demo/demoClient.test.ts
pytest -q tests/contracts/test_schemas.py tests/contracts/test_contract_freeze.py
```

Expected: all selected checks pass.

- [ ] **Step 7: Commit synchronized public surfaces**

```powershell
git add web/src docs schemas
git commit -m "docs: publish dialogue background contract" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 8: Run full verification and complete issue #2

**Files:**
- Modify only files required to fix failures caused by this feature.
- Do not change unrelated pre-existing behavior.

**Interfaces:**
- Produces: a pushed branch, merged pull request, green required checks, and closed issue #2.

- [ ] **Step 1: Run Python static checks**

```powershell
ruff check .
ruff format --check .
mypy src
```

Expected: all commands exit zero.

- [ ] **Step 2: Run the full Python test suite**

```powershell
pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Run all web checks**

```powershell
npm run -w @laqieer/fecreator-web typecheck
npm run -w @laqieer/fecreator-web lint
npm run -w @laqieer/fecreator-web test
```

Expected: all commands exit zero.

- [ ] **Step 4: Run browser end-to-end tests**

```powershell
npm run -w @laqieer/fecreator-web test:e2e
```

Expected: all Playwright flows pass; portrait local/demo behavior is unchanged.

- [ ] **Step 5: Build distributable artifacts**

```powershell
npm run -w @laqieer/fecreator-web build
python -m build
npm run -w @laqieer/fecreator-web build:demo
```

Expected: local web build, Python sdist/wheel, and Pages demo build succeed.

- [ ] **Step 6: Review the complete diff**

Run:

```powershell
git status --short
git --no-pager diff origin/main...HEAD --stat
git --no-pager diff origin/main...HEAD --check
```

Expected: no uncommitted changes, no whitespace errors, and only issue #2 files.

- [ ] **Step 7: Push and open the completing pull request**

```powershell
git push -u origin feat/issue-2-dialogue-background
gh pr create --repo laqieer/FECreator --base main --head feat/issue-2-dialogue-background --title "Add FE8 dialogue background source assets" --body "Closes #2"
```

- [ ] **Step 8: Wait for and inspect required checks**

```powershell
$prNumber = gh pr view --repo laqieer/FECreator --json number --jq .number
gh pr checks --repo laqieer/FECreator --watch $prNumber
```

Expected: every required check passes. Fix feature-caused failures in focused commits,
push, and repeat until green.

- [ ] **Step 9: Merge and verify issue closure**

```powershell
$prNumber = gh pr view --repo laqieer/FECreator --json number --jq .number
gh pr merge --repo laqieer/FECreator --squash --delete-branch $prNumber
gh issue view 2 --repo laqieer/FECreator --json state,closedAt,url
```

Expected: the pull request is merged and issue #2 reports `CLOSED`.
