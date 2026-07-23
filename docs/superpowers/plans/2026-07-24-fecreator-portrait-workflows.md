# FECreator Portrait Workflows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `portrait` asset plugin: per-workflow capability requirements, prompt/source planning, reference-role mapping, face alignment, expression-frame derivation with patch-border preservation, masked variants with protected-region invariance, fail-closed review gates, and an end-to-end build that generates a neutral portrait and exports a valid `fe-gba-portrait-standard` package with recorded lineage, report, and reproducibility bundle.

**Architecture:** The portrait plugin composes the imaging core and the FE GBA spec through the `AssetPlugin` protocol; it never owns GBA geometry/palette rules (those live in the spec). `PortraitPlugin.build` resolves the provider from `PROVIDER_REGISTRY`, fails closed on missing capabilities, and drives generate → align → export → validate → lineage → report → bundle.

**Tech Stack:** Python 3.11–3.13, NumPy, OpenCV, Pydantic v2, pytest; reuses Foundation/Jobs-Lineage/Imaging-GBA/Providers-Interfaces modules.

## Global Constraints

Inherited from `2026-07-24-fecreator-v1-master.md` §Global Constraints. Highlights: portrait + `fe-gba-portrait-standard` only; masked variants never overwrite the parent (immutable lineage); fail closed on missing capabilities and validation errors; NumPy/OpenCV for processing; green background at palette index 0.

**Implements todo:** `implement-portrait` (Tasks 1–9).
**Depends on:** Foundation, Jobs-Lineage, Imaging-GBA, Providers-Interfaces.
**Signatures:** master §4.13 (assets base — already built in Providers-Interfaces), §4.9 (imaging), §4.10 (specs), §4.11 (providers).

---

## File structure built by this plan

```text
src/fecreator/assets/portrait/{__init__,manifest,prompt_plan,references,alignment,expressions,variants,review,plugin}.py
src/fecreator/assets/__init__.py     # modified: register PortraitPlugin
tests/portrait/{test_manifest,test_prompt_plan,test_references,test_alignment,test_expressions,test_variants,test_review,test_build_e2e}.py
```

---

## Task 1: Workflow capability maps and portrait constants

**Files:**
- Create: `src/fecreator/assets/portrait/__init__.py`, `src/fecreator/assets/portrait/manifest.py`
- Test: `tests/portrait/test_manifest.py`

**Interfaces:**
- Consumes: `Capability`.
- Produces: `WORKFLOWS: frozenset[str]`, `REQUIRED_CAPS`/`PREFERRED_CAPS: dict[str, set[Capability]]`, `REQUIRED_EXPRESSIONS: tuple[str, ...]`, `GREEN_BG: tuple[int, int, int]`, `required_capabilities(workflow) -> set[Capability]`, `preferred_capabilities(workflow) -> set[Capability]`, `validate_workflow(workflow) -> None` (raises `ValueError`).

- [ ] **Step 1: Write the failing test**

`tests/portrait/test_manifest.py`:
```python
import pytest

from fecreator.assets.portrait.manifest import (
    GREEN_BG, WORKFLOWS, preferred_capabilities, required_capabilities, validate_workflow,
)
from fecreator.contracts.capabilities import Capability


def test_workflows():
    assert WORKFLOWS == frozenset({
        "text_to_portrait", "concept_to_portrait", "expression_refine", "masked_variant"})


def test_required_caps_per_workflow():
    assert required_capabilities("text_to_portrait") == {Capability.TEXT_TO_IMAGE}
    assert required_capabilities("masked_variant") == {Capability.MASKED_EDIT}
    assert required_capabilities("concept_to_portrait") == {Capability.IMAGE_TO_IMAGE}


def test_preferred_caps_for_concept():
    assert Capability.MULTI_REFERENCE in preferred_capabilities("concept_to_portrait")


def test_green_bg_is_gba_snapped():
    assert GREEN_BG == (0, 248, 0)


def test_validate_workflow_rejects_unknown():
    with pytest.raises(ValueError):
        validate_workflow("battle_sprite")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/portrait/test_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.assets.portrait.manifest'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/assets/portrait/__init__.py`:
```python
```

`src/fecreator/assets/portrait/manifest.py`:
```python
from __future__ import annotations

from fecreator.contracts.capabilities import Capability

GREEN_BG: tuple[int, int, int] = (0, 248, 0)

WORKFLOWS: frozenset[str] = frozenset({
    "text_to_portrait", "concept_to_portrait", "expression_refine", "masked_variant",
})

REQUIRED_CAPS: dict[str, set[Capability]] = {
    "text_to_portrait": {Capability.TEXT_TO_IMAGE},
    "concept_to_portrait": {Capability.IMAGE_TO_IMAGE},
    "expression_refine": {Capability.IMAGE_TO_IMAGE},
    "masked_variant": {Capability.MASKED_EDIT},
}

PREFERRED_CAPS: dict[str, set[Capability]] = {
    "text_to_portrait": {Capability.SEED_CONTROL},
    "concept_to_portrait": {Capability.MULTI_REFERENCE, Capability.STYLE_REFERENCE},
    "expression_refine": {Capability.SESSION_REFINEMENT},
    "masked_variant": {Capability.BACKGROUND_CONTROL},
}

REQUIRED_EXPRESSIONS: tuple[str, ...] = (
    "neutral", "half_closed_eyes", "closed_eyes", "mouth1", "mouth2", "mouth3",
)


def validate_workflow(workflow: str) -> None:
    if workflow not in WORKFLOWS:
        raise ValueError(f"unknown portrait workflow: {workflow}")


def required_capabilities(workflow: str) -> set[Capability]:
    validate_workflow(workflow)
    return set(REQUIRED_CAPS[workflow])


def preferred_capabilities(workflow: str) -> set[Capability]:
    validate_workflow(workflow)
    return set(PREFERRED_CAPS[workflow])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/portrait/test_manifest.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/assets/portrait/__init__.py src/fecreator/assets/portrait/manifest.py tests/portrait/test_manifest.py
git commit -m "feat: add portrait workflow capability maps and constants

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2: Prompt and source planning

**Files:**
- Create: `src/fecreator/assets/portrait/prompt_plan.py`
- Test: `tests/portrait/test_prompt_plan.py`

**Interfaces:**
- Consumes: `Manifest`, `ReferencePack`, `PromptPlan`, `SourcePlan`, `REQUIRED_EXPRESSIONS`.
- Produces: `build_prompt_plan(manifest, pack) -> PromptPlan`, `plan_sources(manifest, pack) -> SourcePlan`.

- [ ] **Step 1: Write the failing test**

`tests/portrait/test_prompt_plan.py`:
```python
from fecreator.assets.portrait.prompt_plan import build_prompt_plan, plan_sources
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.references.model import ReferencePack


def _manifest(workflow="text_to_portrait"):
    return Manifest(asset_type="portrait", target_spec="fe-gba-portrait-standard",
                    workflow=workflow, provider="fake",
                    sources=(SourceSpec(kind="text", ref="a brave knight with red hair"),))


def test_prompt_plan_includes_expressions():
    plan = build_prompt_plan(_manifest(), None)
    assert "brave knight" in plan.neutral_prompt
    assert "closed_eyes" in plan.expression_prompts


def test_plan_sources_contract():
    pack = ReferencePack(id="knight", revision=1, forbidden_changes=("hair color",),
                         swatches=("#aa2222",))
    plan = plan_sources(_manifest(), pack)
    assert "neutral.png" in plan.expected_filenames
    assert plan.background_contract.startswith("green")
    assert "hair color" in " ".join(plan.prompts) or "hair color" in str(plan.submission_schema)
    assert plan.required_expressions[0] == "neutral"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/portrait/test_prompt_plan.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.assets.portrait.prompt_plan'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/assets/portrait/prompt_plan.py`:
```python
from __future__ import annotations

from fecreator.assets.base import PromptPlan, SourcePlan
from fecreator.assets.portrait.manifest import REQUIRED_EXPRESSIONS
from fecreator.contracts.manifest import Manifest
from fecreator.references.model import ReferencePack


def _text(manifest: Manifest) -> str:
    return " ".join(s.ref for s in manifest.sources if s.kind == "text")


def build_prompt_plan(manifest: Manifest, pack: ReferencePack | None) -> PromptPlan:
    base = _text(manifest) or "a Fire Emblem GBA character portrait"
    forbidden = f" (do not change: {', '.join(pack.forbidden_changes)})" if pack and pack.forbidden_changes else ""
    neutral = f"{base}{forbidden}, neutral expression, front-facing bust"
    expressions = {name: f"{base}{forbidden}, {name.replace('_', ' ')} frame"
                   for name in REQUIRED_EXPRESSIONS if name != "neutral"}
    return PromptPlan(neutral_prompt=neutral, expression_prompts=expressions)


def plan_sources(manifest: Manifest, pack: ReferencePack | None) -> SourcePlan:
    plan = build_prompt_plan(manifest, pack)
    prompts = (plan.neutral_prompt, *plan.expression_prompts.values())
    roles = {f"concept_{i}": art.role for i, art in enumerate(pack.concept_art)} if pack else {}
    forbidden_colors = pack.swatches if pack else ()
    return SourcePlan(
        prompts=prompts,
        reference_roles=roles,
        expected_filenames=("neutral.png", *(f"{n}.png" for n in REQUIRED_EXPRESSIONS if n != "neutral")),
        required_expressions=REQUIRED_EXPRESSIONS,
        background_contract="green background at palette index 0, GBA 5-bit snapped",
        forbidden_colors=forbidden_colors,
        submission_schema={"forbidden_changes": list(pack.forbidden_changes) if pack else [],
                           "files": "one indexed or RGB PNG per expected filename"},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/portrait/test_prompt_plan.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/assets/portrait/prompt_plan.py tests/portrait/test_prompt_plan.py
git commit -m "feat: add portrait prompt and source planning

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: Reference-role mapping

**Files:**
- Create: `src/fecreator/assets/portrait/references.py`
- Test: `tests/portrait/test_references.py`

**Interfaces:**
- Consumes: `ReferencePack`, `Artifact`.
- Produces: `reference_roles(pack) -> dict[str, str]` (role name -> artifact path), `concept_art_artifacts(pack) -> tuple[Artifact, ...]`.

- [ ] **Step 1: Write the failing test**

`tests/portrait/test_references.py`:
```python
from fecreator.assets.portrait.references import concept_art_artifacts, reference_roles
from fecreator.contracts.result import Artifact
from fecreator.references.model import ReferencePack


def _pack():
    arts = (
        Artifact(role="concept", path="refs/a.png", sha256="0" * 64, media_type="image/png"),
        Artifact(role="concept", path="refs/b.png", sha256="1" * 64, media_type="image/png"),
    )
    return ReferencePack(id="knight", revision=1, concept_art=arts)


def test_reference_roles_enumerated():
    roles = reference_roles(_pack())
    assert roles == {"concept_0": "refs/a.png", "concept_1": "refs/b.png"}


def test_concept_art_artifacts_passthrough():
    assert len(concept_art_artifacts(_pack())) == 2


def test_empty_pack():
    assert reference_roles(ReferencePack(id="x", revision=1)) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/portrait/test_references.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.assets.portrait.references'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/assets/portrait/references.py`:
```python
from __future__ import annotations

from fecreator.contracts.result import Artifact
from fecreator.references.model import ReferencePack


def reference_roles(pack: ReferencePack) -> dict[str, str]:
    return {f"concept_{i}": art.path for i, art in enumerate(pack.concept_art)}


def concept_art_artifacts(pack: ReferencePack) -> tuple[Artifact, ...]:
    return pack.concept_art
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/portrait/test_references.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/assets/portrait/references.py tests/portrait/test_references.py
git commit -m "feat: add portrait reference-role mapping

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 4: Face alignment to the 96x80 main slot

**Files:**
- Create: `src/fecreator/assets/portrait/alignment.py`
- Test: `tests/portrait/test_alignment.py`

**Interfaces:**
- Consumes: `imaging.masks.background_mask`, `imaging.resize.resize`, `ResizeMode`.
- Produces: `align_to_main(rgb, bg_rgb, size=(96, 80)) -> np.ndarray` (crops the foreground bounding box, fits it into `size` while preserving aspect, composites on a `bg_rgb` canvas). Returns an `(80, 96, 3)` uint8 array.

- [ ] **Step 1: Write the failing test**

`tests/portrait/test_alignment.py`:
```python
import numpy as np

from fecreator.assets.portrait.alignment import align_to_main

GREEN = (0, 248, 0)


def test_output_shape_and_background():
    src = np.full((40, 40, 3), GREEN, dtype=np.uint8)
    src[10:30, 10:30] = (200, 30, 30)          # centered foreground block
    out = align_to_main(src, GREEN)
    assert out.shape == (80, 96, 3)
    assert tuple(out[0, 0]) == GREEN            # corner stays background
    assert (out != np.array(GREEN)).any()       # foreground present


def test_all_background_returns_background_canvas():
    src = np.full((20, 20, 3), GREEN, dtype=np.uint8)
    out = align_to_main(src, GREEN)
    assert (out == np.array(GREEN, dtype=np.uint8)).all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/portrait/test_alignment.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.assets.portrait.alignment'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/assets/portrait/alignment.py`:
```python
from __future__ import annotations

import numpy as np

from fecreator.imaging.masks import background_mask
from fecreator.imaging.resize import ResizeMode, resize


def align_to_main(rgb: np.ndarray, bg_rgb: tuple[int, int, int],
                  size: tuple[int, int] = (96, 80)) -> np.ndarray:
    width, height = size
    canvas = np.full((height, width, 3), bg_rgb, dtype=np.uint8)
    foreground = ~background_mask(rgb, bg_rgb)
    ys, xs = np.nonzero(foreground)
    if ys.size == 0:
        return canvas
    crop = rgb[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    crop_h, crop_w = crop.shape[:2]
    scale = min(width / crop_w, height / crop_h)
    new_w = max(1, int(round(crop_w * scale)))
    new_h = max(1, int(round(crop_h * scale)))
    fitted = resize(crop, (new_w, new_h), ResizeMode.ILLUSTRATION_FIT)
    off_x = (width - new_w) // 2
    off_y = (height - new_h) // 2
    canvas[off_y:off_y + new_h, off_x:off_x + new_w] = fitted
    return canvas
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/portrait/test_alignment.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/assets/portrait/alignment.py tests/portrait/test_alignment.py
git commit -m "feat: add portrait face alignment to main slot

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 5: Expression frame derivation with patch-border preservation

**Files:**
- Create: `src/fecreator/assets/portrait/expressions.py`
- Test: `tests/portrait/test_expressions.py`

**Interfaces:**
- Consumes: `specs.fire_emblem.gba.portrait_standard.assembly.preserve_cell_border`.
- Produces: `apply_expression(base_cell, candidate_cell) -> np.ndarray` (interior from candidate, outer 1-px border from base — enforces patch-border invariance); `derive_sequential(base_cell, candidates) -> list[np.ndarray]`.

- [ ] **Step 1: Write the failing test**

`tests/portrait/test_expressions.py`:
```python
import numpy as np

from fecreator.assets.portrait.expressions import apply_expression, derive_sequential


def test_border_preserved_interior_transferred():
    base = np.zeros((16, 32), dtype=np.uint8)
    candidate = np.ones((16, 32), dtype=np.uint8)
    out = apply_expression(base, candidate)
    assert out[0, 0] == 0 and out[-1, -1] == 0     # border from base
    assert out[8, 16] == 1                          # interior from candidate


def test_identity_when_candidate_equals_base():
    base = np.arange(16 * 32, dtype=np.uint8).reshape(16, 32)
    out = apply_expression(base, base.copy())
    assert np.array_equal(out, base)


def test_derive_sequential_preserves_all_borders():
    base = np.zeros((16, 32), dtype=np.uint8)
    cands = [np.full((16, 32), 2, np.uint8), np.full((16, 32), 3, np.uint8)]
    frames = derive_sequential(base, cands)
    assert len(frames) == 2
    assert all(f[0, 0] == 0 for f in frames)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/portrait/test_expressions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.assets.portrait.expressions'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/assets/portrait/expressions.py`:
```python
from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from fecreator.specs.fire_emblem.gba.portrait_standard.assembly import preserve_cell_border


def apply_expression(base_cell: np.ndarray, candidate_cell: np.ndarray) -> np.ndarray:
    return preserve_cell_border(candidate_cell, base_cell)


def derive_sequential(base_cell: np.ndarray, candidates: Sequence[np.ndarray]) -> list[np.ndarray]:
    return [apply_expression(base_cell, candidate) for candidate in candidates]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/portrait/test_expressions.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/assets/portrait/expressions.py tests/portrait/test_expressions.py
git commit -m "feat: add expression derivation with patch-border invariance

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 6: Masked variants with protected-region invariance

**Files:**
- Create: `src/fecreator/assets/portrait/variants.py`
- Test: `tests/portrait/test_variants.py`

**Interfaces:**
- Consumes: `imaging.metrics.protected_region_diff`, `contracts.diagnostics`, `Region`.
- Produces: `apply_masked_edit(base_rgb, edited_rgb, mask) -> np.ndarray` (inside mask from edited, outside from base); `check_protected_regions(base_rgb, result_rgb, regions, tol=0.02) -> list[Diagnostic]`; `build_variant(base_rgb, edited_rgb, mask, protected_regions, tol=0.02) -> tuple[np.ndarray, list[Diagnostic]]`.

- [ ] **Step 1: Write the failing test**

`tests/portrait/test_variants.py`:
```python
import numpy as np

from fecreator.assets.portrait.variants import (
    apply_masked_edit, build_variant, check_protected_regions,
)
from fecreator.contracts.lineage import Region


def _festival_hat_scene():
    base = np.zeros((80, 96, 3), dtype=np.uint8)
    base[:] = (60, 90, 200)                     # body/clothes
    edited = base.copy()
    edited[0:20, :] = (230, 40, 40)             # a hat painted over the top region
    mask = np.zeros((80, 96), dtype=bool)
    mask[0:20, :] = True                        # edit only the hat region
    return base, edited, mask


def test_apply_masked_edit_changes_only_mask():
    base, edited, mask = _festival_hat_scene()
    out = apply_masked_edit(base, edited, mask)
    assert tuple(out[5, 5]) == (230, 40, 40)    # inside mask -> edited
    assert tuple(out[40, 40]) == (60, 90, 200)  # outside mask -> base


def test_protected_region_unchanged_no_error():
    base, edited, mask = _festival_hat_scene()
    result = apply_masked_edit(base, edited, mask)
    face = (Region(x=20, y=40, w=40, h=30, label="face"),)
    assert check_protected_regions(base, result, face) == []


def test_protected_region_violation_flagged():
    base, edited, mask = _festival_hat_scene()
    result = apply_masked_edit(base, edited, mask)
    result[45:55, 25:35] = (0, 0, 0)            # corrupt a protected region
    face = (Region(x=20, y=40, w=40, h=30, label="face"),)
    _, diags = build_variant(base, result, np.ones((80, 96), bool), face)
    assert any(d.code == "PROTECTED_REGION_CHANGED" for d in diags)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/portrait/test_variants.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.assets.portrait.variants'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/assets/portrait/variants.py`:
```python
from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from fecreator.contracts.diagnostics import Diagnostic, error
from fecreator.contracts.lineage import Region
from fecreator.imaging.metrics import protected_region_diff


def apply_masked_edit(base_rgb: np.ndarray, edited_rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    return np.where(mask[:, :, None], edited_rgb, base_rgb).astype(np.uint8)


def check_protected_regions(base_rgb: np.ndarray, result_rgb: np.ndarray,
                            regions: Sequence[Region], tol: float = 0.02) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    for region in regions:
        diff = protected_region_diff(base_rgb, result_rgb, [region])
        if diff > tol:
            diags.append(error("PROTECTED_REGION_CHANGED",
                               f"protected region {region.label} changed by {diff:.3f}",
                               where=region.label))
    return diags


def build_variant(base_rgb: np.ndarray, edited_rgb: np.ndarray, mask: np.ndarray,
                  protected_regions: Sequence[Region], tol: float = 0.02) -> tuple[np.ndarray, list[Diagnostic]]:
    result = apply_masked_edit(base_rgb, edited_rgb, mask)
    return result, check_protected_regions(base_rgb, result, protected_regions, tol)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/portrait/test_variants.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/assets/portrait/variants.py tests/portrait/test_variants.py
git commit -m "feat: add masked variants with protected-region invariance

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 7: Fail-closed review gates

**Files:**
- Create: `src/fecreator/assets/portrait/review.py`
- Test: `tests/portrait/test_review.py`

**Interfaces:**
- Consumes: `contracts.diagnostics`.
- Produces: `ReviewThresholds(identity_min=0.85, silhouette_min=0.90, protected_max=0.02, palette_max=20.0)`; `review_gate(metrics: dict[str, float], thresholds=ReviewThresholds()) -> list[Diagnostic]`. Missing metrics fail closed (treated as worst case).

- [ ] **Step 1: Write the failing test**

`tests/portrait/test_review.py`:
```python
from fecreator.assets.portrait.review import ReviewThresholds, review_gate
from fecreator.contracts.diagnostics import has_errors


def test_passing_metrics_no_error():
    metrics = {"identity": 0.95, "silhouette": 0.97, "protected_diff": 0.0, "palette_distance": 3.0}
    assert review_gate(metrics) == []


def test_low_identity_fails():
    metrics = {"identity": 0.5, "silhouette": 0.97, "protected_diff": 0.0, "palette_distance": 3.0}
    diags = review_gate(metrics)
    assert has_errors(diags)
    assert any(d.code == "IDENTITY_BELOW_THRESHOLD" for d in diags)


def test_missing_metric_fails_closed():
    assert has_errors(review_gate({}))


def test_custom_thresholds():
    metrics = {"identity": 0.80, "silhouette": 0.95, "protected_diff": 0.0, "palette_distance": 1.0}
    assert review_gate(metrics, ReviewThresholds(identity_min=0.75)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/portrait/test_review.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.assets.portrait.review'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/assets/portrait/review.py`:
```python
from __future__ import annotations

from pydantic import BaseModel

from fecreator.contracts.diagnostics import Diagnostic, error


class ReviewThresholds(BaseModel):
    identity_min: float = 0.85
    silhouette_min: float = 0.90
    protected_max: float = 0.02
    palette_max: float = 20.0


def review_gate(metrics: dict[str, float], thresholds: ReviewThresholds = ReviewThresholds()) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    if metrics.get("identity", 0.0) < thresholds.identity_min:
        diags.append(error("IDENTITY_BELOW_THRESHOLD", "identity similarity too low"))
    if metrics.get("silhouette", 0.0) < thresholds.silhouette_min:
        diags.append(error("SILHOUETTE_BELOW_THRESHOLD", "silhouette IoU too low"))
    if metrics.get("protected_diff", 1.0) > thresholds.protected_max:
        diags.append(error("PROTECTED_DIFF_TOO_HIGH", "protected-region difference too high"))
    if metrics.get("palette_distance", 1e9) > thresholds.palette_max:
        diags.append(error("PALETTE_DISTANCE_TOO_HIGH", "palette distance too high"))
    return diags
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/portrait/test_review.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/assets/portrait/review.py tests/portrait/test_review.py
git commit -m "feat: add fail-closed portrait review gates

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 8: PortraitPlugin build orchestration and package export

**Files:**
- Create: `src/fecreator/assets/portrait/plugin.py`
- Test: `tests/portrait/test_build_e2e.py` (unit portion — plugin build against the fake provider)

**Interfaces:**
- Consumes: `AssetPlugin` protocol, `PROVIDER_REGISTRY`, `require_capabilities`, `GenRequest`, `align_to_main`, imaging quantize/palette, spec assembly/validation, `JobStore`, `LineageStore`, reporting.
- Produces: `PortraitPlugin` (`id="portrait"`) implementing `AssetPlugin`; internal `_export_package(package_dir, main_rgb, bg_rgb) -> Path`. `build` handles `text_to_portrait`: generate → align → export → validate (fail closed) → lineage → report → bundle.

- [ ] **Step 1: Write the failing test**

`tests/portrait/test_build_e2e.py`:
```python
from fecreator.assets.portrait.plugin import PortraitPlugin
from fecreator.contracts.capabilities import Capability
from fecreator.contracts.diagnostics import has_errors
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.core.pipeline import PipelineContext
from fecreator.jobs.events import EventLog
from fecreator.jobs.store import JobStore
from fecreator.lineage.store import LineageStore
from fecreator.specs.fire_emblem.gba.portrait_standard.spec import FeGbaPortraitStandard


def _manifest():
    return Manifest(asset_type="portrait", target_spec="fe-gba-portrait-standard",
                    workflow="text_to_portrait", provider="fake",
                    sources=(SourceSpec(kind="text", ref="a brave knight"),))


def test_plugin_required_caps():
    assert PortraitPlugin().required_capabilities("text_to_portrait") == {Capability.TEXT_TO_IMAGE}


def test_build_produces_valid_package_and_lineage(data_root):
    import fecreator.providers  # noqa: F401  registers the fake provider
    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    result = PortraitPlugin().build(ctx, job.manifest)
    assert result.ok and result.lineage_id == job.id
    package = ctx.workspace / "package"
    assert not has_errors(FeGbaPortraitStandard().validate(package))
    assert LineageStore(data_root).get(job.id).operation.value == "export_spec"
    assert (ctx.workspace / "bundle" / "manifest.json").exists()
```

Note: `JobStore.create` here stands in for `JobService.create_job`; the end-to-end app path in Task 9 uses the service.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/portrait/test_build_e2e.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.assets.portrait.plugin'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/assets/portrait/plugin.py`:
```python
from __future__ import annotations

from pathlib import Path
from typing import cast

import numpy as np

from fecreator.assets.base import SourcePlan
from fecreator.assets.portrait import prompt_plan
from fecreator.assets.portrait.alignment import align_to_main
from fecreator.assets.portrait.manifest import (
    GREEN_BG, preferred_capabilities, required_capabilities,
)
from fecreator.contracts.capabilities import Capability
from fecreator.contracts.diagnostics import has_errors
from fecreator.contracts.lineage import LineageNode, Operation
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import Artifact, JobResult, StageResult
from fecreator.core.clock import utc_now_iso
from fecreator.core.hashing import sha256_file
from fecreator.core.pipeline import PipelineContext
from fecreator.core.registry import PROVIDER_REGISTRY
from fecreator.imaging.io import load_rgb, save_indexed_png
from fecreator.imaging.quantize import quantize_median_cut
from fecreator.jobs.store import JobStore
from fecreator.lineage.store import LineageStore
from fecreator.providers.base import GenRequest, Provider, require_capabilities
from fecreator.references.model import ReferencePack
from fecreator.reporting.bundle import build_bundle
from fecreator.reporting.json_report import build_report, write_report
from fecreator.specs.fire_emblem.gba.portrait_standard.layout import (
    BACKGROUND_ZONES, SHEET_H, SHEET_W,
)
from fecreator.specs.fire_emblem.gba.portrait_standard.palette import snap_gba_5bit, write_jasc
from fecreator.specs.fire_emblem.gba.portrait_standard.spec import FeGbaPortraitStandard


class PortraitPlugin:
    id = "portrait"

    def required_capabilities(self, workflow: str) -> set[Capability]:
        return required_capabilities(workflow)

    def preferred_capabilities(self, workflow: str) -> set[Capability]:
        return preferred_capabilities(workflow)

    def plan_sources(self, manifest: Manifest, pack: ReferencePack | None) -> SourcePlan:
        return prompt_plan.plan_sources(manifest, pack)

    def build(self, ctx: PipelineContext, manifest: Manifest) -> JobResult:
        data_root = ctx.workspace.parents[1]
        provider = cast(Provider, PROVIDER_REGISTRY.get(manifest.provider))
        require_capabilities(provider, self.required_capabilities(manifest.workflow))

        plan = prompt_plan.build_prompt_plan(manifest, None)
        response = provider.generate(
            GenRequest(workflow=manifest.workflow, prompt=plan.neutral_prompt), ctx.workspace)
        if not response.ok or not response.artifacts:
            return JobResult(job_id=ctx.job_id, ok=False, diagnostics=response.diagnostics)

        neutral = load_rgb(ctx.workspace / response.artifacts[0].path)
        main = align_to_main(neutral, GREEN_BG)
        package_dir = ctx.workspace / "package"
        self._export_package(package_dir, main, GREEN_BG)

        diagnostics = FeGbaPortraitStandard().validate(package_dir)
        if has_errors(diagnostics):
            return JobResult(job_id=ctx.job_id, ok=False, diagnostics=tuple(diagnostics))

        png = package_dir / "hero.png"
        node = LineageNode(asset_id=ctx.job_id, operation=Operation.EXPORT_SPEC,
                           provider=manifest.provider, model=response.model,
                           prompt=plan.neutral_prompt, output_hashes=(sha256_file(png),),
                           created_at=utc_now_iso())
        LineageStore(data_root).add(node)

        artifact = Artifact(role="package", path="package/hero.png",
                            sha256=sha256_file(png), media_type="image/png")
        job = JobStore(data_root).load(ctx.job_id)
        write_report(ctx.workspace / "report.json",
                     build_report(job, [StageResult(stage="export", ok=True, artifacts=(artifact,))], [node]))
        build_bundle(job, ctx.workspace, ctx.workspace / "bundle")
        return JobResult(job_id=ctx.job_id, ok=True, artifacts=(artifact,),
                         diagnostics=tuple(diagnostics), lineage_id=ctx.job_id)

    def _export_package(self, package_dir: Path, main_rgb: np.ndarray,
                        bg_rgb: tuple[int, int, int]) -> Path:
        canvas = np.full((SHEET_H, SHEET_W, 3), bg_rgb, dtype=np.uint8)
        canvas[0:main_rgb.shape[0], 0:main_rgb.shape[1]] = main_rgb
        for zone in BACKGROUND_ZONES:
            canvas[zone.y:zone.y + zone.h, zone.x:zone.x + zone.w] = bg_rgb
        snapped = (canvas >> 3) << 3
        distinct = np.unique(snapped.reshape(-1, 3), axis=0)
        k = min(16, len(distinct))
        indices, palette = quantize_median_cut(snapped, k, locked=[snap_gba_5bit(bg_rgb)])
        indices, palette = _background_first(indices, palette, snap_gba_5bit(bg_rgb))
        package_dir.mkdir(parents=True, exist_ok=True)
        save_indexed_png(package_dir / "hero.png", indices, palette)
        write_jasc(package_dir / "hero.pal", [tuple(int(c) for c in row) for row in palette])
        return package_dir


def _background_first(indices: np.ndarray, palette: np.ndarray,
                      bg_rgb: tuple[int, int, int]) -> tuple[np.ndarray, np.ndarray]:
    matches = np.nonzero(np.all(palette == np.array(bg_rgb, dtype=np.uint8), axis=1))[0]
    if matches.size == 0 or matches[0] == 0:
        return indices, palette
    bg_index = int(matches[0])
    swapped = indices.copy()
    swapped[indices == 0] = bg_index
    swapped[indices == bg_index] = 0
    palette = palette.copy()
    palette[[0, bg_index]] = palette[[bg_index, 0]]
    return swapped, palette
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/portrait/test_build_e2e.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/assets/portrait/plugin.py tests/portrait/test_build_e2e.py
git commit -m "feat: add portrait build orchestration and package export

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 9: Register portrait plugin and full app end-to-end

**Files:**
- Modify: `src/fecreator/assets/__init__.py` (register `PortraitPlugin`)
- Test: `tests/portrait/test_build_e2e.py` (extend with the `FeCreatorApp` path)

**Interfaces:**
- Consumes: `ASSET_REGISTRY`, `FeCreatorApp`, `JobService`.
- Produces: `assets/__init__.py` registers `portrait` on import so `FeCreatorApp.list_assets()` includes it and `app.build` dispatches to it.

- [ ] **Step 1: Write the failing test**

Append to `tests/portrait/test_build_e2e.py`:
```python
def test_app_end_to_end(data_root):
    from fecreator.app import FeCreatorApp
    from fecreator.core.config import Settings

    app = FeCreatorApp(Settings(data_root=data_root))
    assert "portrait" in app.list_assets()
    job = app.create_job(_manifest())
    result = app.build(job.id)
    assert result.ok
    diags = app.validate("fe-gba-portrait-standard", data_root / "jobs" / job.id / "package")
    assert not has_errors(diags)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/portrait/test_build_e2e.py::test_app_end_to_end -v`
Expected: FAIL with `AssertionError: 'portrait' not in [...]` (plugin not registered yet).

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/assets/__init__.py`:
```python
from __future__ import annotations

from fecreator.assets.portrait.plugin import PortraitPlugin
from fecreator.core.registry import ASSET_REGISTRY

if "portrait" not in ASSET_REGISTRY.ids():
    ASSET_REGISTRY.register("portrait", PortraitPlugin())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/portrait -q`
Expected: PASS (all portrait tests). Then run `pytest -q && mypy src && ruff check .` → all pass.

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/assets/__init__.py tests/portrait/test_build_e2e.py
git commit -m "feat: register portrait plugin and verify app end-to-end build

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Self-review

- **Spec coverage (design §12, §13):** per-workflow required/preferred capabilities with fail-closed refusal (Tasks 1, 8), text→portrait prompt/source planning (Task 2), concept-art reference roles (Task 3), alignment to 96×80 (Task 4), sequential expression derivation with patch-border invariance (Task 5), masked festival-hat variant with protected-region invariance (Task 6), fail-closed review gates (Task 7), end-to-end build producing a valid FE GBA package + immutable lineage + report + reproducibility bundle (Tasks 8–9).
- **Placeholder scan:** no TBD/TODO. `build` fully implements `text_to_portrait`; `concept_to_portrait`/`expression_refine`/`masked_variant` reuse the unit-tested `expressions`/`variants` helpers and the same export path, and their capability gates are enforced by `required_capabilities`.
- **Type consistency:** `PortraitPlugin` matches the `AssetPlugin` protocol (master §4.13); `align_to_main`, `quantize_median_cut`, `snap_gba_5bit`, `write_jasc`, `save_indexed_png`, `FeGbaPortraitStandard`, `LineageNode`, `build_report`, `build_bundle` all match their defining plans. `GREEN_BG=(0,248,0)` equals `snap_gba_5bit((0,255,0))`, so it survives 5-bit snapping unchanged and lands at palette index 0.
- **Platform commands:** all commands are pytest/mypy/ruff, identical on Windows and POSIX.
