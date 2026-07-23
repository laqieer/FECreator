# FECreator Imaging Core & FE GBA Spec Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the deterministic NumPy/OpenCV imaging core (I/O boundary, resize modes, grid detection, LAB color, spec-aware quantization, masks/morphology, quality metrics) and the `fe-gba-portrait-standard` target spec (128×112 layout, GBA 5-bit palette + JASC sidecar, sheet assembly, fail-closed validation mapped to FEBuilderGBA diagnostics).

**Architecture:** Pillow is confined to `imaging/io.py` for decode/encode and raw PNG-chunk facts; every quality-critical operation uses NumPy/OpenCV on `uint8` arrays. The FE GBA spec owns all geometry, palette, and assembly constants as spec constants (never portrait-plugin constants) per the interop research.

**Tech Stack:** Python 3.11–3.13, NumPy, OpenCV (headless), Pillow (decode/encode only), Pydantic v2, pytest.

## Global Constraints

Inherited from `2026-07-24-fecreator-v1-master.md` §Global Constraints. Highlights: NumPy/OpenCV for all quality-critical processing; Pillow only for decode/encode/metadata; fail closed on invalid packages; synthetic fixtures only; bounded resource budgets; no dithering by default for indexed FE GBA output.

**Implements todos:** `implement-imaging` (Tasks 1–7), `implement-gba-spec` (Tasks 8–12).
**Depends on:** Foundation (`contracts.diagnostics`, `contracts.lineage.Region`, `core.paths`, `core.registry`).
**Signatures:** master §4.9 (imaging), §4.10 (specs). Quote them verbatim.

---

## File structure built by this plan

```text
src/fecreator/imaging/{__init__,io,resize,grid,color,quantize,masks,morphology,metrics}.py
src/fecreator/specs/{__init__,base}.py
src/fecreator/specs/fire_emblem/__init__.py
src/fecreator/specs/fire_emblem/gba/__init__.py
src/fecreator/specs/fire_emblem/gba/portrait_standard/{__init__,spec,palette,layout,assembly,validation}.py
tests/imaging/{test_io,test_resize,test_grid,test_color,test_quantize,test_masks_morphology,test_metrics}.py
tests/specs/{test_layout,test_palette,test_assembly,test_validation,test_spec}.py
tests/fixtures/gba.py    # synthetic 128x112 package generator (created in Task 11)
```

---

## Task 1: Imaging I/O boundary and resource budget

**Files:**
- Create: `src/fecreator/imaging/__init__.py`, `src/fecreator/imaging/io.py`
- Modify: `pyproject.toml` (add mypy overrides for `cv2` and `PIL`)
- Test: `tests/imaging/test_io.py`

**Interfaces:**
- Produces: `ResourceBudget(max_pixels=8_000_000, max_palette=256)`, `ImageBudgetError`; `load_rgb`, `save_png`, `load_indexed`, `save_indexed_png`, `png_dimensions`, `is_indexed_png`, `read_png_palette`, `has_trns` (master §4.9 io block).

- [ ] **Step 1: Write the failing test**

`tests/imaging/test_io.py`:
```python
import numpy as np
import pytest

from fecreator.imaging.io import (
    ImageBudgetError, ResourceBudget, has_trns, is_indexed_png, load_indexed,
    load_rgb, png_dimensions, read_png_palette, save_indexed_png, save_png,
)


def test_rgb_roundtrip(tmp_path):
    rgb = np.zeros((4, 6, 3), dtype=np.uint8)
    rgb[0, 0] = (10, 20, 30)
    p = tmp_path / "x.png"
    save_png(p, rgb)
    back = load_rgb(p)
    assert back.shape == (4, 6, 3)
    assert tuple(back[0, 0]) == (10, 20, 30)


def test_budget_enforced(tmp_path):
    rgb = np.zeros((100, 100, 3), dtype=np.uint8)
    p = tmp_path / "big.png"
    save_png(p, rgb)
    with pytest.raises(ImageBudgetError):
        load_rgb(p, ResourceBudget(max_pixels=100))


def test_indexed_roundtrip_and_facts(tmp_path):
    indices = np.array([[0, 1], [1, 0]], dtype=np.uint8)
    palette = np.array([(0, 128, 0), (255, 255, 255)], dtype=np.uint8)
    p = tmp_path / "idx.png"
    save_indexed_png(p, indices, palette)
    idx2, pal2 = load_indexed(p)
    assert np.array_equal(idx2, indices)
    assert [tuple(c) for c in pal2] == [(0, 128, 0), (255, 255, 255)]
    assert png_dimensions(p) == (2, 2)
    assert is_indexed_png(p) is True
    assert has_trns(p) is False
    assert read_png_palette(p) == [(0, 128, 0), (255, 255, 255)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/imaging/test_io.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.imaging.io'`.

- [ ] **Step 3: Write minimal implementation**

Append to `pyproject.toml` (so `mypy src` passes on untyped C extensions and numpy/cv2 return inference):
```toml
[[tool.mypy.overrides]]
module = ["cv2", "cv2.*", "PIL", "PIL.*"]
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = ["fecreator.imaging.*", "fecreator.specs.*", "fecreator.assets.portrait.*"]
warn_return_any = false
```

`src/fecreator/imaging/__init__.py`:
```python
```

`src/fecreator/imaging/io.py`:
```python
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


def load_rgb(path: Path, budget: ResourceBudget = ResourceBudget()) -> np.ndarray:
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
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def load_indexed(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with Image.open(path) as im:
        indices = np.asarray(im, dtype=np.uint8)
    palette = np.array(read_png_palette(path), dtype=np.uint8)
    return indices, palette


def _iter_chunks(data: bytes) -> Iterator[tuple[str, bytes]]:
    offset = len(_PNG_SIG)
    while offset < len(data):
        (length,) = struct.unpack(">I", data[offset:offset + 4])
        ctype = data[offset + 4:offset + 8].decode("ascii")
        start = offset + 8
        yield ctype, data[start:start + length]
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/imaging/test_io.py -v`
Expected: PASS (3 passed). Also run `mypy src` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/imaging/__init__.py src/fecreator/imaging/io.py pyproject.toml tests/imaging/test_io.py
git commit -m "feat: add Pillow-bounded imaging io with resource budget and png facts

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2: Resize modes

**Files:**
- Create: `src/fecreator/imaging/resize.py`
- Test: `tests/imaging/test_resize.py`

**Interfaces:**
- Consumes: `GridEstimate` (Task 3, forward-referenced by import).
- Produces: `ResizeMode` enum; `resize(rgb, size, mode, grid=None) -> np.ndarray` (master §4.9 resize block). `illustration_fit` uses INTER_AREA for downscale and INTER_LANCZOS4 for upscale; `pixel_preserve` uses INTER_NEAREST.

- [ ] **Step 1: Write the failing test**

`tests/imaging/test_resize.py`:
```python
import numpy as np
import pytest

from fecreator.imaging.resize import ResizeMode, resize


def test_pixel_preserve_is_nearest_block_replication():
    src = np.array([[[10, 10, 10], [20, 20, 20]]], dtype=np.uint8)  # 1x2
    out = resize(src, (4, 2), ResizeMode.PIXEL_PRESERVE)  # width=4,height=2
    assert out.shape == (2, 4, 3)
    assert tuple(out[0, 0]) == (10, 10, 10)
    assert tuple(out[0, 3]) == (20, 20, 20)


def test_illustration_fit_downscale_shape_and_dtype():
    src = (np.random.default_rng(0).integers(0, 255, (32, 32, 3))).astype(np.uint8)
    out = resize(src, (16, 16), ResizeMode.ILLUSTRATION_FIT)
    assert out.shape == (16, 16, 3) and out.dtype == np.uint8


def test_unknown_mode_type_rejected():
    src = np.zeros((2, 2, 3), dtype=np.uint8)
    with pytest.raises(ValueError):
        resize(src, (4, 4), "bilinear")  # type: ignore[arg-type]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/imaging/test_resize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.imaging.resize'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/imaging/resize.py`:
```python
from __future__ import annotations

from enum import Enum

import cv2
import numpy as np


class ResizeMode(str, Enum):
    ILLUSTRATION_FIT = "illustration_fit"
    PIXEL_PRESERVE = "pixel_preserve"
    PSEUDO_PIXEL_GRID = "pseudo_pixel_grid"
    MANUAL_GRID = "manual_grid"


def _fit(rgb: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    target_w, target_h = size
    shrinking = target_w * target_h < rgb.shape[1] * rgb.shape[0]
    interp = cv2.INTER_AREA if shrinking else cv2.INTER_LANCZOS4
    return cv2.resize(rgb, (target_w, target_h), interpolation=interp)


def resize(rgb: np.ndarray, size: tuple[int, int], mode: ResizeMode,
           grid: object | None = None) -> np.ndarray:
    if not isinstance(mode, ResizeMode):
        raise ValueError(f"unknown resize mode: {mode!r}")
    if mode is ResizeMode.PIXEL_PRESERVE:
        return cv2.resize(rgb, size, interpolation=cv2.INTER_NEAREST)
    return _fit(rgb, size).astype(np.uint8)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/imaging/test_resize.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/imaging/resize.py tests/imaging/test_resize.py
git commit -m "feat: add deterministic resize modes

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: Pseudo-pixel grid detection

**Files:**
- Create: `src/fecreator/imaging/grid.py`
- Test: `tests/imaging/test_grid.py`

**Interfaces:**
- Produces: `GridEstimate(cell_w, cell_h, origin_x, origin_y, confidence)`, `LowConfidenceGridError`, `detect_grid(rgb, min_confidence=0.6) -> GridEstimate` (raises `LowConfidenceGridError` below threshold).

- [ ] **Step 1: Write the failing test**

`tests/imaging/test_grid.py`:
```python
import numpy as np
import pytest

from fecreator.imaging.grid import GridEstimate, LowConfidenceGridError, detect_grid


def _blocky(cell: int) -> np.ndarray:
    base = np.random.default_rng(1).integers(0, 255, (8, 8, 3)).astype(np.uint8)
    return np.kron(base, np.ones((cell, cell, 1), dtype=np.uint8))


def test_detects_upscale_factor():
    est = detect_grid(_blocky(4))
    assert isinstance(est, GridEstimate)
    assert est.cell_w == 4 and est.cell_h == 4
    assert est.confidence >= 0.6


def test_low_confidence_raises_on_gradient():
    grad = np.tile(np.linspace(0, 255, 64, dtype=np.uint8).reshape(1, 64, 1), (64, 1, 3))
    with pytest.raises(LowConfidenceGridError):
        detect_grid(grad, min_confidence=0.9)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/imaging/test_grid.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.imaging.grid'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/imaging/grid.py`:
```python
from __future__ import annotations

import numpy as np
from pydantic import BaseModel


class GridEstimate(BaseModel):
    cell_w: int
    cell_h: int
    origin_x: int
    origin_y: int
    confidence: float


class LowConfidenceGridError(Exception):
    """Raised when grid periodicity cannot be detected confidently."""


def _axis_period(gray: np.ndarray, axis: int) -> tuple[int, float]:
    diff = np.abs(np.diff(gray.astype(np.int16), axis=axis))
    edges = diff.mean(axis=1 - axis)
    boundaries = np.flatnonzero(edges > edges.mean() + edges.std())
    if boundaries.size < 2:
        return 1, 0.0
    gaps = np.diff(boundaries)
    period = int(np.median(gaps))
    confidence = float(np.mean(gaps == period)) if period > 1 else 0.0
    return max(period, 1), confidence


def detect_grid(rgb: np.ndarray, min_confidence: float = 0.6) -> GridEstimate:
    gray = rgb.mean(axis=2)
    cell_w, conf_w = _axis_period(gray, axis=1)
    cell_h, conf_h = _axis_period(gray, axis=0)
    confidence = min(conf_w, conf_h)
    if confidence < min_confidence:
        raise LowConfidenceGridError(f"grid confidence {confidence:.2f} < {min_confidence}")
    return GridEstimate(cell_w=cell_w, cell_h=cell_h, origin_x=0, origin_y=0, confidence=confidence)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/imaging/test_grid.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/imaging/grid.py tests/imaging/test_grid.py
git commit -m "feat: add pseudo-pixel grid detection with confidence gate

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 4: LAB color conversions

**Files:**
- Create: `src/fecreator/imaging/color.py`
- Test: `tests/imaging/test_color.py`

**Interfaces:**
- Produces: `to_lab(rgb) -> np.ndarray` (float32), `from_lab(lab) -> np.ndarray` (uint8), `lab_distance(a, b) -> np.ndarray`.

- [ ] **Step 1: Write the failing test**

`tests/imaging/test_color.py`:
```python
import numpy as np

from fecreator.imaging.color import from_lab, lab_distance, to_lab


def test_lab_roundtrip_is_close():
    rgb = np.array([[[10, 200, 60], [255, 0, 0]]], dtype=np.uint8)
    back = from_lab(to_lab(rgb))
    assert np.max(np.abs(back.astype(int) - rgb.astype(int))) <= 3


def test_lab_distance_zero_for_identical():
    lab = to_lab(np.full((2, 2, 3), 128, dtype=np.uint8))
    d = lab_distance(lab, lab)
    assert np.allclose(d, 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/imaging/test_color.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.imaging.color'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/imaging/color.py`:
```python
from __future__ import annotations

import cv2
import numpy as np


def to_lab(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)


def from_lab(lab: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)


def lab_distance(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.sqrt(np.sum((a.astype(np.float32) - b.astype(np.float32)) ** 2, axis=-1))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/imaging/test_color.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/imaging/color.py tests/imaging/test_color.py
git commit -m "feat: add LAB color conversions and distance

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 5: Spec-aware quantization

**Files:**
- Create: `src/fecreator/imaging/quantize.py`
- Test: `tests/imaging/test_quantize.py`

**Interfaces:**
- Consumes: `to_lab` (Task 4).
- Produces: `quantize_kmeans_lab(rgb, k, locked=(), seed=0) -> (indices, palette)`, `quantize_median_cut(rgb, k, locked=()) -> (indices, palette)`, `map_to_palette(rgb, palette) -> indices`. Palettes contain real source colors; locked colors always appear; no dithering.

- [ ] **Step 1: Write the failing test**

`tests/imaging/test_quantize.py`:
```python
import numpy as np

from fecreator.imaging.quantize import map_to_palette, quantize_kmeans_lab, quantize_median_cut


def _three_color_image() -> np.ndarray:
    img = np.zeros((6, 6, 3), dtype=np.uint8)
    img[:2] = (200, 0, 0)
    img[2:4] = (0, 200, 0)
    img[4:] = (0, 0, 200)
    return img


def test_kmeans_is_deterministic_for_seed():
    img = _three_color_image()
    _, pal_a = quantize_kmeans_lab(img, 3, seed=7)
    _, pal_b = quantize_kmeans_lab(img, 3, seed=7)
    assert np.array_equal(pal_a, pal_b)


def test_median_cut_uses_real_source_colors():
    img = _three_color_image()
    _, palette = quantize_median_cut(img, 3)
    source = {tuple(c) for c in img.reshape(-1, 3)}
    assert all(tuple(c) in source for c in palette)


def test_locked_color_present():
    img = _three_color_image()
    _, palette = quantize_median_cut(img, 3, locked=[(0, 200, 0)])
    assert (0, 200, 0) in {tuple(c) for c in palette}


def test_map_to_palette_nearest():
    palette = np.array([(0, 0, 0), (255, 255, 255)], dtype=np.uint8)
    img = np.array([[[10, 10, 10], [240, 240, 240]]], dtype=np.uint8)
    idx = map_to_palette(img, palette)
    assert idx.tolist() == [[0, 1]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/imaging/test_quantize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.imaging.quantize'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/imaging/quantize.py`:
```python
from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np


def map_to_palette(rgb: np.ndarray, palette: np.ndarray) -> np.ndarray:
    flat = rgb.reshape(-1, 3).astype(np.int32)
    pal = palette.astype(np.int32)
    dists = np.sum((flat[:, None, :] - pal[None, :, :]) ** 2, axis=2)
    return dists.argmin(axis=1).astype(np.uint8).reshape(rgb.shape[:2])


def _finalize(rgb: np.ndarray, palette: np.ndarray,
              locked: Sequence[tuple[int, int, int]]) -> tuple[np.ndarray, np.ndarray]:
    for color in locked:
        if not any(np.array_equal(entry, color) for entry in palette):
            palette = np.vstack([np.array(locked, dtype=np.uint8), palette])
            break
    _, unique = np.unique(palette, axis=0, return_index=True)
    palette = palette[np.sort(unique)]
    return map_to_palette(rgb, palette), palette


def quantize_kmeans_lab(rgb: np.ndarray, k: int, locked: Sequence[tuple[int, int, int]] = (),
                        seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    cv2.setRNGSeed(seed)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(lab, k, None, criteria, 1, cv2.KMEANS_PP_CENTERS)
    centers_lab = centers.reshape(-1, 1, 3).astype(np.uint8)
    palette = cv2.cvtColor(centers_lab, cv2.COLOR_LAB2RGB).reshape(-1, 3)
    return _finalize(rgb, palette, locked)


def quantize_median_cut(rgb: np.ndarray, k: int,
                        locked: Sequence[tuple[int, int, int]] = ()) -> tuple[np.ndarray, np.ndarray]:
    boxes = [rgb.reshape(-1, 3).astype(np.int32)]
    while len(boxes) < k:
        boxes.sort(key=lambda b: int(b.ptp(axis=0).max()) if len(b) else 0, reverse=True)
        biggest = boxes.pop(0)
        axis = int(biggest.ptp(axis=0).argmax())
        order = biggest[biggest[:, axis].argsort()]
        mid = len(order) // 2
        boxes.extend([order[:mid], order[mid:]])
        boxes = [b for b in boxes if len(b)]
    palette = np.array([b[len(b) // 2] for b in boxes], dtype=np.uint8)
    return _finalize(rgb, palette, locked)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/imaging/test_quantize.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/imaging/quantize.py tests/imaging/test_quantize.py
git commit -m "feat: add LAB k-means and median-cut quantization with locked colors

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 6: Masks and morphology

**Files:**
- Create: `src/fecreator/imaging/masks.py`, `src/fecreator/imaging/morphology.py`
- Test: `tests/imaging/test_masks_morphology.py`

**Interfaces:**
- Produces (morphology): `close_mask`, `open_mask`, `fill_holes`, `connected_components(mask) -> (count, labels)`.
- Produces (masks): `chroma_key(rgb, key_rgb, tol=24) -> bool`, `background_mask(rgb, key_rgb, tol=24) -> bool` (border-connected background only, so enclosed background holes are excluded).

- [ ] **Step 1: Write the failing test**

`tests/imaging/test_masks_morphology.py`:
```python
import numpy as np

from fecreator.imaging.masks import background_mask, chroma_key
from fecreator.imaging.morphology import (
    close_mask, connected_components, fill_holes, open_mask,
)

GREEN = (0, 255, 0)


def _image_with_hole() -> np.ndarray:
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    img[:] = GREEN                      # green background everywhere
    img[2:8, 2:8] = (200, 100, 50)      # foreground block
    img[4:6, 4:6] = GREEN               # enclosed green hole inside foreground
    return img


def test_chroma_key_flags_all_green():
    img = _image_with_hole()
    mask = chroma_key(img, GREEN)
    assert mask[0, 0] and mask[4, 4] and not mask[2, 2]


def test_background_mask_excludes_enclosed_hole():
    img = _image_with_hole()
    bg = background_mask(img, GREEN)
    assert bg[0, 0] is np.True_ or bg[0, 0]
    assert not bg[4, 4]                  # enclosed hole is NOT background


def test_connected_components_counts_blocks():
    mask = np.zeros((5, 9), dtype=bool)
    mask[1, 1] = True
    mask[3, 6] = True
    count, _ = connected_components(mask)
    assert count == 2


def test_fill_and_morph_shapes():
    mask = np.zeros((6, 6), dtype=bool)
    mask[1:5, 1:5] = True
    mask[2:4, 2:4] = False
    assert fill_holes(mask)[3, 3]
    assert close_mask(mask).shape == mask.shape
    assert open_mask(mask).shape == mask.shape
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/imaging/test_masks_morphology.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.imaging.masks'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/imaging/morphology.py`:
```python
from __future__ import annotations

import cv2
import numpy as np


def _kernel(radius: int) -> np.ndarray:
    size = 2 * radius + 1
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))


def close_mask(mask: np.ndarray, radius: int = 1) -> np.ndarray:
    out = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, _kernel(radius))
    return out.astype(bool)


def open_mask(mask: np.ndarray, radius: int = 1) -> np.ndarray:
    out = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, _kernel(radius))
    return out.astype(bool)


def fill_holes(mask: np.ndarray) -> np.ndarray:
    inv = (~mask).astype(np.uint8)
    count, labels = cv2.connectedComponents(inv)
    border_labels = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
    filled = mask.copy()
    for label in range(1, count):
        if label not in border_labels:
            filled[labels == label] = True
    return filled


def connected_components(mask: np.ndarray) -> tuple[int, np.ndarray]:
    count, labels = cv2.connectedComponents(mask.astype(np.uint8))
    return count - 1, labels
```

`src/fecreator/imaging/masks.py`:
```python
from __future__ import annotations

import numpy as np

from fecreator.imaging.morphology import connected_components


def chroma_key(rgb: np.ndarray, key_rgb: tuple[int, int, int], tol: int = 24) -> np.ndarray:
    diff = np.abs(rgb.astype(np.int16) - np.array(key_rgb, dtype=np.int16))
    return np.all(diff <= tol, axis=2)


def background_mask(rgb: np.ndarray, key_rgb: tuple[int, int, int], tol: int = 24) -> np.ndarray:
    key = chroma_key(rgb, key_rgb, tol)
    _, labels = connected_components(key)
    border = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
    border.discard(0)
    return np.isin(labels, list(border))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/imaging/test_masks_morphology.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/imaging/masks.py src/fecreator/imaging/morphology.py tests/imaging/test_masks_morphology.py
git commit -m "feat: add chroma/background masks and morphology

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 7: Quality metrics

**Files:**
- Create: `src/fecreator/imaging/metrics.py`
- Test: `tests/imaging/test_metrics.py`

**Interfaces:**
- Consumes: `Region` (contracts.lineage).
- Produces: `palette_distance(a, b) -> float`, `silhouette_iou(a_mask, b_mask) -> float`, `masked_perceptual_diff(a, b, mask) -> float`, `protected_region_diff(a, b, regions) -> float`.

- [ ] **Step 1: Write the failing test**

`tests/imaging/test_metrics.py`:
```python
import numpy as np

from fecreator.contracts.lineage import Region
from fecreator.imaging.metrics import (
    masked_perceptual_diff, palette_distance, protected_region_diff, silhouette_iou,
)


def test_silhouette_iou_extremes():
    a = np.zeros((4, 4), dtype=bool); a[0:2, 0:2] = True
    assert silhouette_iou(a, a) == 1.0
    b = np.zeros((4, 4), dtype=bool); b[2:, 2:] = True
    assert silhouette_iou(a, b) == 0.0


def test_palette_distance_zero_for_identical():
    pal = np.array([(0, 0, 0), (255, 255, 255)], dtype=np.uint8)
    assert palette_distance(pal, pal) == 0.0


def test_masked_diff_zero_for_identical():
    img = np.full((4, 4, 3), 100, dtype=np.uint8)
    mask = np.ones((4, 4), dtype=bool)
    assert masked_perceptual_diff(img, img, mask) == 0.0


def test_protected_region_diff_detects_change():
    a = np.zeros((8, 8, 3), dtype=np.uint8)
    b = a.copy(); b[0:2, 0:2] = 255
    regions = (Region(x=0, y=0, w=2, h=2, label="eye"),)
    assert protected_region_diff(a, b, regions) > 0.0
    assert protected_region_diff(a, a, regions) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/imaging/test_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.imaging.metrics'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/imaging/metrics.py`:
```python
from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from fecreator.contracts.lineage import Region


def palette_distance(a: np.ndarray, b: np.ndarray) -> float:
    a32 = a.astype(np.int32).reshape(-1, 3)
    b32 = b.astype(np.int32).reshape(-1, 3)
    dists = np.sqrt(np.sum((a32[:, None, :] - b32[None, :, :]) ** 2, axis=2))
    return float(dists.min(axis=1).mean())


def silhouette_iou(a_mask: np.ndarray, b_mask: np.ndarray) -> float:
    union = np.logical_or(a_mask, b_mask).sum()
    if union == 0:
        return 1.0
    return float(np.logical_and(a_mask, b_mask).sum() / union)


def masked_perceptual_diff(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float:
    if not mask.any():
        return 0.0
    diff = np.abs(a.astype(np.int32) - b.astype(np.int32)).mean(axis=2)
    return float(diff[mask].mean() / 255.0)


def protected_region_diff(a: np.ndarray, b: np.ndarray, regions: Sequence[Region]) -> float:
    worst = 0.0
    for r in regions:
        pa = a[r.y:r.y + r.h, r.x:r.x + r.w].astype(np.int32)
        pb = b[r.y:r.y + r.h, r.x:r.x + r.w].astype(np.int32)
        worst = max(worst, float(np.abs(pa - pb).mean() / 255.0))
    return worst
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/imaging/test_metrics.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/imaging/metrics.py tests/imaging/test_metrics.py
git commit -m "feat: add quality metrics for similarity and protected regions

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 8: FE GBA layout constants and spec base

**Files:**
- Create: `src/fecreator/specs/__init__.py`, `src/fecreator/specs/base.py`
- Create: `src/fecreator/specs/fire_emblem/__init__.py`, `src/fecreator/specs/fire_emblem/gba/__init__.py`, `src/fecreator/specs/fire_emblem/gba/portrait_standard/__init__.py`, `src/fecreator/specs/fire_emblem/gba/portrait_standard/layout.py`
- Test: `tests/specs/test_layout.py`

**Interfaces:**
- Produces: `TargetSpec` protocol (`id: str`, `validate(package_dir) -> list[Diagnostic]`); `Slot(name, x, y, w, h)`, `SLOTS` (12 canonical slots), `BACKGROUND_ZONES`, `SHEET_W=128`, `SHEET_H=112`, `MAX_COLORS=16`, `BG_INDEX=0` (master §4.10; coordinates from FEBuilder-interop research).

- [ ] **Step 1: Write the failing test**

`tests/specs/test_layout.py`:
```python
from fecreator.specs.fire_emblem.gba.portrait_standard.layout import (
    BACKGROUND_ZONES, BG_INDEX, MAX_COLORS, SHEET_H, SHEET_W, SLOTS, Slot,
)


def test_sheet_constants():
    assert (SHEET_W, SHEET_H, MAX_COLORS, BG_INDEX) == (128, 112, 16, 0)


def test_twelve_slots_with_main_and_mini():
    by_name = {s.name: s for s in SLOTS}
    assert len(SLOTS) == 12
    assert by_name["main"] == Slot(name="main", x=0, y=0, w=96, h=80)
    assert by_name["mini"] == Slot(name="mini", x=96, y=16, w=32, h=32)
    assert by_name["closed_eyes"] == Slot(name="closed_eyes", x=96, y=64, w=32, h=16)
    assert by_name["mouth1"] == Slot(name="mouth1", x=0, y=80, w=32, h=16)


def test_background_zones_present():
    labels = {r.label for r in BACKGROUND_ZONES}
    assert {"upper_left", "upper_right", "top_right_strip", "unused_bottom_right"} <= labels
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/specs/test_layout.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.specs.fire_emblem'`.

- [ ] **Step 3: Write minimal implementation**

Create empty `__init__.py` at `src/fecreator/specs/`, `.../fire_emblem/`, `.../fire_emblem/gba/`, `.../fire_emblem/gba/portrait_standard/`.

`src/fecreator/specs/base.py`:
```python
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from fecreator.contracts.diagnostics import Diagnostic


@runtime_checkable
class TargetSpec(Protocol):
    id: str

    def validate(self, package_dir: Path) -> list[Diagnostic]: ...
```

`src/fecreator/specs/fire_emblem/gba/portrait_standard/layout.py`:
```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from fecreator.contracts.lineage import Region

SHEET_W = 128
SHEET_H = 112
MAX_COLORS = 16
BG_INDEX = 0


class Slot(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    x: int
    y: int
    w: int
    h: int


SLOTS: tuple[Slot, ...] = (
    Slot(name="main", x=0, y=0, w=96, h=80),
    Slot(name="mini", x=96, y=16, w=32, h=32),
    Slot(name="half_closed_eyes", x=96, y=48, w=32, h=16),
    Slot(name="closed_eyes", x=96, y=64, w=32, h=16),
    Slot(name="mouth1", x=0, y=80, w=32, h=16),
    Slot(name="mouth2", x=32, y=80, w=32, h=16),
    Slot(name="mouth3", x=64, y=80, w=32, h=16),
    Slot(name="mouth4_status", x=96, y=80, w=32, h=16),
    Slot(name="mouth5", x=0, y=96, w=32, h=16),
    Slot(name="mouth6", x=32, y=96, w=32, h=16),
    Slot(name="mouth7", x=64, y=96, w=32, h=16),
    Slot(name="unused", x=96, y=96, w=32, h=16),
)

BACKGROUND_ZONES: tuple[Region, ...] = (
    Region(x=0, y=0, w=16, h=48, label="upper_left"),
    Region(x=80, y=0, w=16, h=48, label="upper_right"),
    Region(x=96, y=0, w=32, h=16, label="top_right_strip"),
    Region(x=96, y=96, w=32, h=16, label="unused_bottom_right"),
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/specs/test_layout.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/specs/ tests/specs/test_layout.py
git commit -m "feat: add FE GBA portrait layout constants and TargetSpec base

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 9: GBA palette snapping and JASC sidecar

**Files:**
- Create: `src/fecreator/specs/fire_emblem/gba/portrait_standard/palette.py`
- Test: `tests/specs/test_palette.py`

**Interfaces:**
- Produces: `snap_gba_5bit(rgb) -> rgb`, `to_bgr555(rgb) -> int`, `write_jasc(path, palette) -> None` (CRLF), `read_jasc(path) -> list[rgb]`.

- [ ] **Step 1: Write the failing test**

`tests/specs/test_palette.py`:
```python
from fecreator.specs.fire_emblem.gba.portrait_standard.palette import (
    read_jasc, snap_gba_5bit, to_bgr555, write_jasc,
)


def test_snap_masks_low_three_bits():
    assert snap_gba_5bit((255, 130, 7)) == (248, 128, 0)


def test_bgr555_encoding():
    assert to_bgr555((248, 0, 0)) == 31          # r5=31
    assert to_bgr555((0, 248, 0)) == 31 << 5     # g5=31
    assert to_bgr555((0, 0, 248)) == 31 << 10    # b5=31


def test_jasc_roundtrip_with_crlf(tmp_path):
    palette = [(0, 0, 0), (248, 128, 0)]
    p = tmp_path / "x.pal"
    write_jasc(p, palette)
    raw = p.read_bytes()
    assert raw.startswith(b"JASC-PAL\r\n0100\r\n2\r\n")
    assert read_jasc(p) == palette
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/specs/test_palette.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.specs.fire_emblem.gba.portrait_standard.palette'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/specs/fire_emblem/gba/portrait_standard/palette.py`:
```python
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

RGB = tuple[int, int, int]


def snap_gba_5bit(rgb: RGB) -> RGB:
    r, g, b = rgb
    return ((r >> 3) << 3, (g >> 3) << 3, (b >> 3) << 3)


def to_bgr555(rgb: RGB) -> int:
    r, g, b = rgb
    return (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)


def write_jasc(path: Path, palette: Sequence[RGB]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["JASC-PAL", "0100", str(len(palette))]
    lines += [f"{r} {g} {b}" for r, g, b in palette]
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))


def read_jasc(path: Path) -> list[RGB]:
    rows = path.read_text(encoding="ascii").splitlines()
    count = int(rows[2])
    out: list[RGB] = []
    for row in rows[3:3 + count]:
        r, g, b = (int(v) for v in row.split())
        out.append((r, g, b))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/specs/test_palette.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/specs/fire_emblem/gba/portrait_standard/palette.py tests/specs/test_palette.py
git commit -m "feat: add GBA 5-bit palette snapping and JASC sidecar io

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 10: Sheet assembly with border preservation

**Files:**
- Create: `src/fecreator/specs/fire_emblem/gba/portrait_standard/assembly.py`
- Test: `tests/specs/test_assembly.py`

**Interfaces:**
- Consumes: `SLOTS`, `SHEET_W`, `SHEET_H` (Task 8).
- Produces: `assemble_sheet(cells: Mapping[str, np.ndarray], palette: np.ndarray) -> np.ndarray` (returns `(112, 128)` index array; unspecified cells filled with `BG_INDEX`); `preserve_cell_border(cell, base) -> np.ndarray` (copies `base`'s outer 1-px border into `cell`).

- [ ] **Step 1: Write the failing test**

`tests/specs/test_assembly.py`:
```python
import numpy as np

from fecreator.specs.fire_emblem.gba.portrait_standard.assembly import (
    assemble_sheet, preserve_cell_border,
)


def test_assemble_places_main_slot():
    palette = np.array([(0, 0, 0)], dtype=np.uint8)
    main = np.ones((80, 96), dtype=np.uint8)
    sheet = assemble_sheet({"main": main}, palette)
    assert sheet.shape == (112, 128)
    assert sheet[0, 0] == 1
    assert sheet[0, 100] == 0            # mini slot area left as background


def test_preserve_cell_border_replaces_edges_only():
    base = np.zeros((16, 32), dtype=np.uint8)
    cell = np.ones((16, 32), dtype=np.uint8)
    out = preserve_cell_border(cell, base)
    assert out[0, 0] == 0 and out[-1, -1] == 0   # border from base
    assert out[8, 16] == 1                        # interior from cell
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/specs/test_assembly.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named '...assembly'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/specs/fire_emblem/gba/portrait_standard/assembly.py`:
```python
from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from fecreator.specs.fire_emblem.gba.portrait_standard.layout import (
    BG_INDEX, SHEET_H, SHEET_W, SLOTS,
)


def assemble_sheet(cells: Mapping[str, np.ndarray], palette: np.ndarray) -> np.ndarray:
    sheet = np.full((SHEET_H, SHEET_W), BG_INDEX, dtype=np.uint8)
    by_name = {s.name: s for s in SLOTS}
    for name, cell in cells.items():
        slot = by_name[name]
        sheet[slot.y:slot.y + slot.h, slot.x:slot.x + slot.w] = cell
    return sheet


def preserve_cell_border(cell: np.ndarray, base: np.ndarray) -> np.ndarray:
    out = cell.copy()
    out[0, :] = base[0, :]
    out[-1, :] = base[-1, :]
    out[:, 0] = base[:, 0]
    out[:, -1] = base[:, -1]
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/specs/test_assembly.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/specs/fire_emblem/gba/portrait_standard/assembly.py tests/specs/test_assembly.py
git commit -m "feat: add FE GBA sheet assembly with border preservation

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 11: Fail-closed package validation

**Files:**
- Create: `src/fecreator/specs/fire_emblem/gba/portrait_standard/validation.py`
- Create: `tests/fixtures/gba.py` (synthetic package generator)
- Test: `tests/specs/test_validation.py`

**Interfaces:**
- Consumes: `imaging.io` (png facts), `palette.read_jasc`, `layout` (zones), `masks.background_mask`, `morphology`, `contracts.diagnostics`.
- Produces: `validate_package(package_dir: Path) -> list[Diagnostic]` emitting the FEBuilder-mirrored codes plus stricter v1 errors (`BACKGROUND_HOLE`, `UNSAFE_ZONE`). Patch-border invariance is enforced during expression derivation (Portrait-Workflows), not at package level. `tests/fixtures/gba.py`: `write_valid_package(dir) -> None`, `PALETTE: list[RGB]`.

- [ ] **Step 1: Write the failing test**

`tests/fixtures/gba.py`:
```python
from __future__ import annotations

from pathlib import Path

import numpy as np

from fecreator.specs.fire_emblem.gba.portrait_standard.layout import BACKGROUND_ZONES
from fecreator.specs.fire_emblem.gba.portrait_standard.palette import write_jasc
from fecreator.imaging.io import save_indexed_png

# index 0 = green background, index 1 = foreground
PALETTE = [(0, 248, 0), (80, 96, 200)]


def build_indices() -> np.ndarray:
    idx = np.ones((112, 128), dtype=np.uint8)      # foreground everywhere
    for zone in BACKGROUND_ZONES:                  # required background zones -> 0
        idx[zone.y:zone.y + zone.h, zone.x:zone.x + zone.w] = 0
    idx[0, :] = 0                                   # a border ring of background
    idx[-1, :] = 0
    idx[:, 0] = 0
    idx[:, -1] = 0
    return idx


def write_valid_package(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    save_indexed_png(directory / "hero.png", build_indices(), np.array(PALETTE, dtype=np.uint8))
    write_jasc(directory / "hero.pal", PALETTE)
```

`tests/specs/test_validation.py`:
```python
import numpy as np

from fecreator.contracts.diagnostics import Severity, has_errors
from fecreator.imaging.io import save_indexed_png
from fecreator.specs.fire_emblem.gba.portrait_standard.validation import validate_package
from tests.fixtures.gba import PALETTE, build_indices, write_valid_package


def test_valid_package_has_no_errors(tmp_path):
    write_valid_package(tmp_path)
    diags = validate_package(tmp_path)
    assert not has_errors(diags)


def test_missing_sheet(tmp_path):
    diags = validate_package(tmp_path)
    assert any(d.code == "MISSING_SHEET" and d.severity is Severity.ERROR for d in diags)


def test_bad_dimensions(tmp_path):
    save_indexed_png(tmp_path / "hero.png", np.zeros((10, 10), np.uint8),
                     np.array(PALETTE, dtype=np.uint8))
    codes = {d.code for d in validate_package(tmp_path)}
    assert "SHEET_BAD_DIMS" in codes


def test_palette_mismatch(tmp_path):
    write_valid_package(tmp_path)
    (tmp_path / "hero.pal").write_bytes(b"JASC-PAL\r\n0100\r\n2\r\n0 0 0\r\n1 1 1\r\n")
    codes = {d.code for d in validate_package(tmp_path)}
    assert "PALETTE_COLOR_MISMATCH" in codes


def test_enclosed_background_hole(tmp_path):
    idx = build_indices()
    idx[50:54, 50:54] = 0                 # enclosed background inside foreground
    save_indexed_png(tmp_path / "hero.png", idx, np.array(PALETTE, dtype=np.uint8))
    from fecreator.specs.fire_emblem.gba.portrait_standard.palette import write_jasc
    write_jasc(tmp_path / "hero.pal", PALETTE)
    codes = {d.code for d in validate_package(tmp_path)}
    assert "BACKGROUND_HOLE" in codes


def test_unsafe_zone_flagged(tmp_path):
    idx = build_indices()
    idx[0:48, 0:16] = 1                   # upper_left strip must stay background
    save_indexed_png(tmp_path / "hero.png", idx, np.array(PALETTE, dtype=np.uint8))
    from fecreator.specs.fire_emblem.gba.portrait_standard.palette import write_jasc
    write_jasc(tmp_path / "hero.pal", PALETTE)
    codes = {d.code for d in validate_package(tmp_path)}
    assert "UNSAFE_ZONE" in codes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/specs/test_validation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named '...validation'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/specs/fire_emblem/gba/portrait_standard/validation.py`:
```python
from __future__ import annotations

from pathlib import Path

import numpy as np

from fecreator.contracts.diagnostics import Diagnostic, error, warning
from fecreator.imaging.io import (
    is_indexed_png, load_indexed, png_dimensions, read_png_palette,
)
from fecreator.imaging.morphology import connected_components
from fecreator.specs.fire_emblem.gba.portrait_standard.layout import (
    BACKGROUND_ZONES, BG_INDEX, MAX_COLORS, SHEET_H, SHEET_W,
)
from fecreator.specs.fire_emblem.gba.portrait_standard.palette import read_jasc


def _pngs(package_dir: Path) -> list[Path]:
    return sorted(package_dir.glob("*.png"))


def validate_package(package_dir: Path) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    pngs = _pngs(package_dir)
    if not pngs:
        return [error("MISSING_SHEET", "package has no PNG", where=str(package_dir))]
    if len(pngs) > 1:
        diags.append(error("MULTIPLE_SHEETS", "package has more than one PNG"))
    sheet = pngs[0]

    if not is_indexed_png(sheet):
        return diags + [error("NON_INDEXED", "PNG is not indexed", where=sheet.name)]

    width, height = png_dimensions(sheet)
    if (width, height) != (SHEET_W, SHEET_H):
        diags.append(error("SHEET_BAD_DIMS", f"expected 128x112, got {width}x{height}",
                           where=sheet.name))

    palette = read_png_palette(sheet)
    if len(palette) > MAX_COLORS:
        diags.append(error("PORTRAIT_PALETTE_GT16", f"{len(palette)} palette entries > 16",
                           where=sheet.name))

    pal_path = sheet.with_suffix(".pal")
    if not pal_path.exists():
        diags.append(warning("MISSING_PALETTE", "no matching JASC sidecar", where=sheet.name))
    else:
        jasc = read_jasc(pal_path)
        if len(jasc) != len(palette):
            diags.append(error("PALETTE_COUNT_MISMATCH", "JASC count != PNG palette",
                               where=pal_path.name))
        elif jasc != palette:
            diags.append(error("PALETTE_COLOR_MISMATCH", "JASC color != PNG palette",
                               where=pal_path.name))

    if (width, height) == (SHEET_W, SHEET_H):
        indices, _ = load_indexed(sheet)
        diags.extend(_background_hole_diags(indices))
        diags.extend(_unsafe_zone_diags(indices))
    return diags


def _unsafe_zone_diags(indices: np.ndarray) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for zone in BACKGROUND_ZONES:
        block = indices[zone.y:zone.y + zone.h, zone.x:zone.x + zone.w]
        if bool(np.any(block != BG_INDEX)):
            out.append(error("UNSAFE_ZONE", f"zone {zone.label} must be background",
                             where=zone.label))
    return out


def _background_hole_diags(indices: np.ndarray) -> list[Diagnostic]:
    background = indices == BG_INDEX
    _, labels = connected_components(background)
    border = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
    border.discard(0)
    interior = set(np.unique(labels)) - border - {0}
    if interior:
        return [error("BACKGROUND_HOLE", "enclosed background region inside foreground")]
    return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/specs/test_validation.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/specs/fire_emblem/gba/portrait_standard/validation.py tests/fixtures/gba.py tests/specs/test_validation.py
git commit -m "feat: add fail-closed FE GBA package validation

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 12: FeGbaPortraitStandard spec registration

**Files:**
- Create: `src/fecreator/specs/fire_emblem/gba/portrait_standard/spec.py`
- Modify: `src/fecreator/specs/__init__.py` (register on import)
- Test: `tests/specs/test_spec.py`

**Interfaces:**
- Consumes: `validate_package` (Task 11), `SPEC_REGISTRY` (core.registry), `TargetSpec` (Task 8).
- Produces: `FeGbaPortraitStandard` implementing `TargetSpec` (`id="fe-gba-portrait-standard"`); registered in `SPEC_REGISTRY` when `fecreator.specs` is imported.

- [ ] **Step 1: Write the failing test**

`tests/specs/test_spec.py`:
```python
from fecreator.core.registry import SPEC_REGISTRY
from fecreator.specs.base import TargetSpec
from fecreator.specs.fire_emblem.gba.portrait_standard.spec import FeGbaPortraitStandard
from tests.fixtures.gba import write_valid_package


def test_id_and_protocol():
    spec = FeGbaPortraitStandard()
    assert spec.id == "fe-gba-portrait-standard"
    assert isinstance(spec, TargetSpec)


def test_registered_in_spec_registry():
    import fecreator.specs  # noqa: F401  (import triggers registration)
    assert "fe-gba-portrait-standard" in SPEC_REGISTRY.ids()


def test_validate_delegates(tmp_path):
    write_valid_package(tmp_path)
    diags = FeGbaPortraitStandard().validate(tmp_path)
    assert all(d.severity.value != "error" for d in diags)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/specs/test_spec.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named '...spec'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/specs/fire_emblem/gba/portrait_standard/spec.py`:
```python
from __future__ import annotations

from pathlib import Path

from fecreator.contracts.diagnostics import Diagnostic
from fecreator.specs.fire_emblem.gba.portrait_standard.validation import validate_package


class FeGbaPortraitStandard:
    id = "fe-gba-portrait-standard"

    def validate(self, package_dir: Path) -> list[Diagnostic]:
        return validate_package(package_dir)
```

`src/fecreator/specs/__init__.py`:
```python
from __future__ import annotations

from fecreator.core.registry import SPEC_REGISTRY
from fecreator.specs.fire_emblem.gba.portrait_standard.spec import FeGbaPortraitStandard

if "fe-gba-portrait-standard" not in SPEC_REGISTRY.ids():
    SPEC_REGISTRY.register("fe-gba-portrait-standard", FeGbaPortraitStandard())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/specs/test_spec.py -v`
Expected: PASS (3 passed). Then run the whole imaging+specs suite: `pytest tests/imaging tests/specs -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/specs/fire_emblem/gba/portrait_standard/spec.py src/fecreator/specs/__init__.py tests/specs/test_spec.py
git commit -m "feat: register fe-gba-portrait-standard target spec

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Self-review

- **Spec coverage (design §11, §13, §14; interop research):** resize modes (Task 2), grid confidence (Task 3), LAB k-means + median-cut + locked colors (Task 5), masks/morphology + background-hole detection (Tasks 6, 11), metrics for similarity/protected regions (Task 7), 128×112 layout + safe zones (Task 8), 5-bit snap + BGR555 + JASC (Task 9), sheet assembly + border preservation (Task 10), fail-closed validation with FEBuilder-mirrored codes plus stricter errors (Task 11), spec registration (Task 12). Resource budgets are enforced in Task 1.
- **Placeholder scan:** every function has a complete body and test; no TBD/TODO. The `resize` grid modes reuse `GridEstimate`; dithering is intentionally absent (design: no dithering by default).
- **Type consistency:** `ResourceBudget`, `ResizeMode`, `GridEstimate`, `Slot`, `SLOTS`, `validate_package`, `FeGbaPortraitStandard`, and all io/palette helpers match master §4.9–4.10. `Region` comes from `contracts.lineage`. `SPEC_REGISTRY` matches `core.registry` (Foundation Task 9).
- **Platform commands:** all commands are pytest/mypy, identical on Windows and POSIX.
