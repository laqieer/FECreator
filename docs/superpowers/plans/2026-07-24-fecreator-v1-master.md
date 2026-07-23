# FECreator v1 Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This master plan is an index; execute the focused sub-plans it references.

**Goal:** Build FECreator v1 — a local-first, agent-neutral, provider-neutral Fire Emblem portrait creation workbench with deterministic imaging, immutable jobs/lineage, human review, and a `fe-gba-portrait-standard` export that passes ROM-free FEBuilderGBA interoperability.

**Architecture:** One Python package (`fecreator`) exposes a single application service (`FeCreatorApp`) that every interface (JSON CLI, FastAPI HTTP, WebSocket, MCP server, thin agent skills) calls. The service composes registries (assets, specs, providers), persistent immutable jobs/workspaces, a deterministic NumPy/OpenCV imaging core, a portrait asset plugin, and the `fe-gba-portrait-standard` target spec. A private React/Vite web workspace bound to `127.0.0.1` is the human review UI, shipped as static assets inside the Python distribution.

**Tech Stack:** Python 3.11–3.13, FastAPI, Uvicorn, Pydantic v2, NumPy, OpenCV (headless), Pillow (decode/encode only), official MCP SDK; TypeScript, React 19, Vite 8, Konva/react-konva, Vitest, Playwright.

## Global Constraints

These apply to **every task in every sub-plan** and are copied verbatim from the approved design.

- **Localhost only:** the web/API server binds `127.0.0.1` by default; no public tunnel in v1.
- **V1 scope only:** asset plugin `portrait` and target spec `fe-gba-portrait-standard` only. No unit icons, map sprites, battle sprites, multi-frame weapon insertion, LoRA training, other FE platforms, or full pixel-editor tooling.
- **Immutable jobs/revisions:** accepted sources, approved stages, exports, and lineage are immutable; changes require an explicit new revision. Preserve originals; back up before any user-approved overwrite/export.
- **Fail closed:** missing capabilities, invalid job states, validation failures, and path escapes all fail; there is no silent downgrade or silent acceptance.
- **No shell execution:** the external `command` provider and any external CLI probe execute an argv list with `shell=False`; never through a shell.
- **No credentials in manifests/bundles:** provider tokens/signed URLs stay in environment variables, OS keyring, or provider config; they are redacted from diagnostics and never written to job manifests or bundles.
- **Imaging engine policy:** NumPy/OpenCV perform all quality-critical processing (resize, masking, quantization, morphology, metrics). Pillow is used **only** for image decode/encode/metadata. No preemptive Numba/Rust.
- **No Electron/Tauri/Rust in v1:** the native model is a local FastAPI server + system-browser React app + one launcher command.
- **No GitHub Releases** and **no ROM in CI:** distribution is via the Python package; automated CI stops at ROM-free FEBuilderGBA checks. ROM-required checks are opt-in local acceptance only.
- **Fixtures:** synthetic/original fixtures only. Do not copy FEBuilderGBA or `sprite-workshop` source; reimplement documented algorithms/formats.

---

## 1. Naming (locked)

| Surface | Name |
| --- | --- |
| GitHub repository | `laqieer/FECreator` |
| Python distribution / import / CLI | `fecreator` |
| npm root workspace (private) | `@laqieer/fecreator` |
| npm web workspace (private) | `@laqieer/fecreator-web` |

Both `package.json` manifests set `"private": true`. The frontend ships as static assets inside the Python wheel; there is no public npm release.

## 2. Pinned toolchain and dependencies

Conservative, current-compatible ranges (verified against PyPI/npm on 2026-07-24). Pin these exactly in the manifests created by the Foundation plan.

### Python (`pyproject.toml`)

- `requires-python = ">=3.11,<3.14"`; CI matrix runs **3.11** and **3.12**.
- Runtime dependencies:
  - `fastapi>=0.115,<0.140`
  - `uvicorn[standard]>=0.30,<0.52`
  - `pydantic>=2.9,<3`
  - `numpy>=2.1,<3`
  - `opencv-python-headless>=4.10,<5.1`
  - `Pillow>=11.0,<13`
  - `mcp>=1.10,<2`
- Dev dependencies (`[project.optional-dependencies].dev`, installed with `pip install -e ".[dev]"`):
  - `pytest>=8.2,<10`
  - `pytest-asyncio>=0.24,<2`
  - `pytest-cov>=5,<8`
  - `httpx>=0.27,<0.29`
  - `mypy>=1.13,<3`
  - `ruff>=0.11,<0.16`

Build backend: `hatchling>=1.25,<2` (`[build-system] requires = ["hatchling>=1.25,<2"]`, `build-backend = "hatchling.build"`).

### Node / web (`web/package.json`)

- `engines.node = ">=20.19 <25"`; CI uses **Node 22.x**.
- dependencies: `react@^19.2.7`, `react-dom@^19.2.7`, `konva@^10.3.0`, `react-konva@^19.2.5`, `@tanstack/react-query@^5.101.0`.
- devDependencies: `@types/react@^19.2.0`, `@types/react-dom@^19.2.0`, `typescript@~5.9.0`, `vite@^8.1.0`, `@vitejs/plugin-react@^6.0.0`, `vitest@^4.1.0`, `@vitest/coverage-v8@^4.1.0`, `jsdom@^29.1.0`, `@testing-library/react@^16.3.0`, `@testing-library/jest-dom@^6.9.0`, `@testing-library/user-event@^14.6.0`, `@playwright/test@^1.61.0`, `eslint@^10.7.0`, `typescript-eslint@^8.40.0`, `prettier@^3.4.0`.

**Canvas library decision (design left this open):** use **Konva + react-konva**. Rationale: mature React bindings, imperative pixel/layer control for the mask and protected-region editors, and testable via `react-konva`'s node tree under jsdom. This is locked for v1; PixiJS/Fabric are not used.

## 3. Full repository file tree

Every path below has exactly one responsibility. Sub-plans create these files; this master plan is the authoritative map. Paths marked *(skeleton in Foundation)* are created minimally in Foundation and completed by the named plan.

```text
FECreator/
  pyproject.toml                         # Python distribution metadata + pinned deps (Foundation)
  package.json                           # @laqieer/fecreator private root workspace (Foundation)
  package-lock.json                      # generated lockfile (Foundation)
  .gitignore                             # ignore build/venv/node_modules/data (Foundation)
  .ruff.toml                             # ruff lint/format config (Foundation)
  README.md                              # product statement + boundaries (Foundation)
  .github/workflows/ci.yml               # full CI pipeline (Foundation; extended in Integration)
  docs/
    product-statement.md                 # what FECreator is/ is not (Foundation)
    architecture.md                      # runtime architecture + module map (Foundation)
    interfaces.md                        # CLI/MCP/HTTP/skills reference (Providers-Interfaces)
    febuilder-interop.md                 # ROM-free + ROM-required interop guide (Web-Skills-Integration)
    superpowers/plans/                   # these plan documents
  schemas/                               # exported JSON Schemas for public contracts (Foundation)
    manifest.schema.json
    result.schema.json
    diagnostics.schema.json
    lineage.schema.json
    capabilities.schema.json
  src/fecreator/
    __init__.py                          # package version constant (Foundation)
    app.py                               # FeCreatorApp facade wiring registries+stores (Providers-Interfaces)
    cli.py                               # console-script entry: `--version` (minimal in Foundation); full dispatch + `serve` launcher (Providers-Interfaces)
    core/
      __init__.py
      config.py                          # Settings (127.0.0.1 bind, data_root) (Foundation)
      paths.py                           # safe_join / path containment (Foundation)
      hashing.py                         # sha256 + canonical content hashing (Foundation)
      clock.py                           # utc_now_iso timestamp source (Foundation)
      atomicio.py                        # atomic json write + read helpers (Jobs-Lineage)
      redaction.py                       # secret pattern + redact()/contains_secret_key() (Providers-Interfaces)
      registry.py                        # generic Registry + 3 global registries (Foundation)
      compatibility.py                   # contract/spec/provider version negotiation (Foundation)
      pipeline.py                        # PipelineStep protocol + Pipeline runner (Foundation)
    contracts/
      __init__.py
      capabilities.py                    # Capability enum + CapabilitySet (Foundation)
      manifest.py                        # frozen Manifest + SourceSpec + EditSpec (Foundation)
      result.py                          # Artifact / StageResult / JobResult (Foundation)
      diagnostics.py                     # Severity + Diagnostic + helpers (Foundation)
      lineage.py                         # Operation / Region / LineageNode (Foundation)
    jobs/
      __init__.py
      model.py                           # JobState enum + transitions + Job/JobEvent (Jobs-Lineage)
      store.py                           # atomic immutable JobStore (Jobs-Lineage)
      service.py                         # JobService transitions/resume/cancel (Jobs-Lineage)
      events.py                          # append-only event log (Jobs-Lineage)
      approvals.py                       # immutable approval/rejection records (Jobs-Lineage)
    references/
      __init__.py
      model.py                           # versioned ReferencePack (Jobs-Lineage)
      store.py                           # immutable ReferencePackStore (Jobs-Lineage)
    lineage/
      __init__.py
      store.py                           # DAG LineageStore (add/ancestors/children) (Jobs-Lineage)
    imaging/
      __init__.py
      io.py                              # Pillow decode/encode boundary + ResourceBudget (Imaging-GBA)
      resize.py                          # ResizeMode + resize() (Imaging-GBA)
      grid.py                            # pseudo-pixel grid detection + confidence (Imaging-GBA)
      color.py                           # LAB conversions + color distance (Imaging-GBA)
      quantize.py                        # LAB k-means + weighted median-cut + locked colors (Imaging-GBA)
      masks.py                           # background/chroma-key masks (Imaging-GBA)
      morphology.py                      # erode/dilate/close/open/fill_holes/components (Imaging-GBA)
      metrics.py                         # palette distance / silhouette IoU / masked diff (Imaging-GBA)
    specs/
      __init__.py
      base.py                            # TargetSpec protocol (Imaging-GBA)
      fire_emblem/gba/portrait_standard/
        __init__.py
        spec.py                          # FeGbaPortraitStandard registration (Imaging-GBA)
        palette.py                       # 5-bit snap / BGR555 / JASC read+write (Imaging-GBA)
        layout.py                        # 128x112 slots + background zones (Imaging-GBA)
        assembly.py                      # sheet compositing + border preservation (Imaging-GBA)
        validation.py                    # fail-closed package validation + diagnostics (Imaging-GBA)
    providers/
      __init__.py
      base.py                            # Provider protocol + GenRequest/GenResponse (Providers-Interfaces)
      manual.py                          # human/agent-submitted sources (Providers-Interfaces)
      fake.py                            # deterministic test provider (Providers-Interfaces)
      mcp_client.py                      # configured image-gen MCP client (Providers-Interfaces)
      command.py                         # external argv provider, shell=False JSON stdio (Providers-Interfaces)
    reporting/
      __init__.py
      json_report.py                     # machine-readable job report (Providers-Interfaces)
      bundle.py                          # reproducibility bundle + FEBuilder compat report (Providers-Interfaces)
    assets/
      __init__.py                        # registers portrait plugin on import (Portrait-Workflows)
      base.py                            # AssetPlugin protocol + SourcePlan/PromptPlan (Providers-Interfaces)
      portrait/
        __init__.py
        plugin.py                        # PortraitPlugin implementing AssetPlugin (Portrait-Workflows)
        manifest.py                      # workflow constants + capability maps + params (Portrait-Workflows)
        prompt_plan.py                   # prompt/source planning + plan-sources (Portrait-Workflows)
        references.py                    # map reference roles onto ReferencePack (Portrait-Workflows)
        alignment.py                     # face crop/align to 96x80 content (Portrait-Workflows)
        expressions.py                   # expression frame derivation (Portrait-Workflows)
        variants.py                      # masked variant (festival hat) workflow (Portrait-Workflows)
        review.py                        # review gates + similarity thresholds (Portrait-Workflows)
    interfaces/
      __init__.py
      cli_json.py                        # argparse -> JSON stdout command table (Providers-Interfaces)
      http_api.py                        # FastAPI app factory create_api() (Providers-Interfaces)
      websocket.py                       # job progress WebSocket (Providers-Interfaces)
      mcp_server.py                      # MCP tool surface over FeCreatorApp (Providers-Interfaces)
      static.py                          # mount built web assets (Providers-Interfaces)
    interop/
      __init__.py
      febuilder_cli.py                   # optional ROM-free FEBuilderGBA CLI probe, shell=False (Web-Skills-Integration)
  web/
    package.json                         # @laqieer/fecreator-web private workspace (Foundation skeleton; Web plan)
    tsconfig.json                        # TS config (Foundation skeleton)
    vite.config.ts                       # Vite + plugin-react + vitest config (Foundation skeleton)
    playwright.config.ts                 # Playwright smoke config (Web-Skills-Integration)
    index.html                           # app entry (Foundation skeleton)
    src/
      main.tsx                           # React root render (Foundation skeleton)
      app/App.tsx                        # shell + routing (Web-Skills-Integration)
      api/client.ts                      # typed HTTP+WS client for FeCreatorApp (Web-Skills-Integration)
      api/types.ts                       # TS mirror of contracts (Web-Skills-Integration)
      components/                        # shared presentational components (Web-Skills-Integration)
      jobs/JobTimeline.tsx               # job timeline + live progress (Web-Skills-Integration)
      references/ReferenceBoard.tsx      # reference pack board + manifest editor (Web-Skills-Integration)
      canvas/MaskEditor.tsx              # Konva mask + protected-region editor (Web-Skills-Integration)
      palette/PalettePreview.tsx         # palette + native-size preview (Web-Skills-Integration)
      review/ReviewGallery.tsx           # comparison gallery + crop overlay + approve/reject (Web-Skills-Integration)
      lineage/LineageView.tsx            # lineage + variants graph (Web-Skills-Integration)
    e2e/                                 # Playwright specs (Web-Skills-Integration)
  skills/fecreator/
    SKILL.md                             # thin agent skill entry (Web-Skills-Integration)
    references/                          # capability-gap + workflow reference docs (Web-Skills-Integration)
    agents/                              # per-workflow agent instructions (Web-Skills-Integration)
  tests/                                 # pytest suite mirrors src/ (all plans)
    conftest.py                          # shared fixtures + tmp data_root (Foundation)
    fixtures/                            # synthetic generators only (all plans)
```

## 4. Shared interface catalog (authoritative signatures)

This catalog is the single source of truth for cross-plan types. Sub-plans restate the slice they build in their per-task **Interfaces** blocks; those must match the names and signatures here exactly. All models are Pydantic v2 `BaseModel`; public contract models set `model_config = ConfigDict(frozen=True)`.

### 4.1 `fecreator.contracts.capabilities`

```python
class Capability(str, Enum):
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"
    MULTI_REFERENCE = "multi_reference"
    MASKED_EDIT = "masked_edit"
    SESSION_REFINEMENT = "session_refinement"
    POSE_CONTROL = "pose_control"
    LINEART_CONTROL = "lineart_control"
    IDENTITY_EMBEDDING = "identity_embedding"
    STYLE_REFERENCE = "style_reference"
    SEED_CONTROL = "seed_control"
    SIZE_CONTROL = "size_control"
    BACKGROUND_CONTROL = "background_control"
    ASYNCHRONOUS_JOBS = "asynchronous_jobs"

class CapabilitySet(BaseModel):  # frozen
    capabilities: frozenset[Capability]
    def supports(self, required: set[Capability]) -> bool: ...
    def missing(self, required: set[Capability]) -> set[Capability]: ...
```

### 4.2 `fecreator.contracts.diagnostics`

```python
class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

class Diagnostic(BaseModel):  # frozen
    code: str
    severity: Severity
    message: str
    where: str | None = None
    data: dict[str, str | int | float | bool] | None = None

def error(code: str, message: str, *, where: str | None = None,
          data: dict[str, str | int | float | bool] | None = None) -> Diagnostic: ...
def warning(code: str, message: str, *, where: str | None = None, data=None) -> Diagnostic: ...
def has_errors(diags: Sequence[Diagnostic]) -> bool: ...
```

### 4.3 `fecreator.contracts.result`

```python
class Artifact(BaseModel):  # frozen
    role: str
    path: str                 # workspace-relative POSIX path
    sha256: str
    media_type: str

class StageResult(BaseModel):  # frozen
    stage: str
    ok: bool
    artifacts: tuple[Artifact, ...] = ()
    metrics: dict[str, float] = {}
    diagnostics: tuple[Diagnostic, ...] = ()

class JobResult(BaseModel):  # frozen
    job_id: str
    ok: bool
    artifacts: tuple[Artifact, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    lineage_id: str | None = None
```

### 4.4 `fecreator.contracts.manifest`

```python
class SourceSpec(BaseModel):  # frozen
    kind: Literal["text", "concept_art", "approved_portrait"]
    ref: str                  # text body or workspace-relative artifact path

class Region(BaseModel):  # frozen  (re-exported from lineage)
    x: int; y: int; w: int; h: int; label: str

class EditSpec(BaseModel):  # frozen
    mask_path: str
    protected_regions: tuple[Region, ...] = ()

class Manifest(BaseModel):  # frozen
    version: Literal["1.0"] = "1.0"
    asset_type: str           # "portrait"
    target_spec: str          # "fe-gba-portrait-standard"
    workflow: str             # "text_to_portrait" | "concept_to_portrait" | "expression_refine" | "masked_variant"
    provider: str             # provider id
    character_ref_pack: str | None = None
    sources: tuple[SourceSpec, ...] = ()
    edit: EditSpec | None = None
    params: dict[str, str | int | float | bool] = {}
    def content_hash(self) -> str: ...     # delegates to core.hashing.content_hash
```

### 4.5 `fecreator.contracts.lineage`

```python
class Operation(str, Enum):
    IMPORT_CONCEPT = "import_concept"
    CREATE_NEUTRAL = "create_neutral"
    REFINE_EXPRESSION = "refine_expression"
    VARIANT_MASKED_EDIT = "variant_masked_edit"
    EXPORT_SPEC = "export_spec"

class LineageNode(BaseModel):  # frozen
    asset_id: str
    operation: Operation
    parents: tuple[str, ...] = ()
    provider: str | None = None
    model: str | None = None
    prompt: str | None = None
    reference_pack: str | None = None
    reference_pack_rev: int | None = None
    seed: int | None = None
    params: dict[str, str | int | float | bool] = {}
    mask: str | None = None
    protected_regions: tuple[Region, ...] = ()
    metrics: dict[str, float] = {}
    approved_by: str | None = None
    output_hashes: tuple[str, ...] = ()
    created_at: str           # ISO-8601 UTC
```

### 4.5.1 `fecreator.core.clock`

```python
def utc_now_iso() -> str: ...   # ISO-8601 UTC, injectable in tests; used for all created_at fields
```

### 4.6 `fecreator.core`

```python
# paths.py
class PathEscapeError(Exception): ...
def safe_join(root: Path, *parts: str) -> Path: ...   # raises PathEscapeError on escape
def is_contained(root: Path, target: Path) -> bool: ...

# hashing.py
def sha256_bytes(data: bytes) -> str: ...
def sha256_file(path: Path) -> str: ...
def content_hash(model: BaseModel) -> str: ...        # sha256 of canonical JSON

# registry.py
class UnknownIdError(KeyError): ...
class Registry(Generic[T]):
    def register(self, id: str, value: T) -> None: ...
    def get(self, id: str) -> T: ...                  # raises UnknownIdError
    def ids(self) -> list[str]: ...
ASSET_REGISTRY: Registry[AssetPlugin]
SPEC_REGISTRY: Registry[TargetSpec]
PROVIDER_REGISTRY: Registry[Provider]

# compatibility.py
class UnsupportedVersionError(Exception): ...
SUPPORTED_CONTRACT_VERSIONS: frozenset[str] = frozenset({"1.0"})
def check_supported(kind: str, version: str) -> None: ...   # raises UnsupportedVersionError

# config.py
class Settings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    data_root: Path
    allow_remote_upload: bool = False
def get_settings(env: Mapping[str, str] | None = None) -> Settings: ...  # FECREATOR_* env prefix

# pipeline.py
class PipelineContext(BaseModel):     # not frozen; carries job_id, workspace root, cancel flag
    job_id: str
    workspace: Path
    cancelled: bool = False
class PipelineStep(Protocol):
    name: str
    def run(self, ctx: PipelineContext) -> StageResult: ...
class Pipeline:
    def run(self, steps: Sequence[PipelineStep], ctx: PipelineContext) -> tuple[StageResult, ...]: ...
```

### 4.7 `fecreator.jobs`

```python
# model.py
class JobState(str, Enum):
    CREATED="created"; PLANNING="planning"; WAITING_FOR_PROVIDER="waiting_for_provider"
    WAITING_FOR_SOURCES="waiting_for_sources"; PROCESSING="processing"
    WAITING_FOR_REVIEW="waiting_for_review"; VALIDATING="validating"
    COMPLETED="completed"; FAILED="failed"; CANCELLED="cancelled"
ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]]
class Job(BaseModel):
    id: str; state: JobState; manifest: Manifest
    revision: int; created_at: str; updated_at: str
class JobEvent(BaseModel):  # frozen
    seq: int; at: str; kind: str; message: str
    data: dict[str, str | int | float | bool] = {}

# store.py
class JobStore:
    def __init__(self, root: Path) -> None: ...
    def create(self, manifest: Manifest) -> Job: ...
    def load(self, job_id: str) -> Job: ...
    def save(self, job: Job) -> None: ...        # atomic temp+rename; frozen manifest snapshot
    def list_jobs(self) -> list[str]: ...

# service.py
class InvalidTransitionError(Exception): ...
class JobService:
    def __init__(self, store: JobStore, events: EventLog) -> None: ...
    def create_job(self, manifest: Manifest) -> Job: ...
    def transition(self, job_id: str, to: JobState) -> Job: ...   # raises InvalidTransitionError
    def cancel(self, job_id: str) -> Job: ...
    def resume(self, job_id: str) -> Job: ...

# events.py
class EventLog:
    def __init__(self, root: Path) -> None: ...
    def append(self, job_id: str, kind: str, message: str, data: dict | None = None) -> JobEvent: ...
    def read(self, job_id: str) -> list[JobEvent]: ...

# approvals.py
class ApprovalError(Exception): ...
class ApprovalRecord(BaseModel):  # frozen
    job_id: str; stage: str; decision: Literal["approved", "rejected"]
    actor: str; reason: str | None; at: str
class ApprovalStore:
    def __init__(self, root: Path) -> None: ...
    def approve(self, job_id: str, stage: str, actor: str) -> ApprovalRecord: ...
    def reject(self, job_id: str, stage: str, actor: str, reason: str) -> ApprovalRecord: ...
    def decisions(self, job_id: str) -> list[ApprovalRecord]: ...   # append-only; re-decide raises ApprovalError
```

### 4.8 `fecreator.references` and `fecreator.lineage`

```python
# references/model.py
class ReferencePack(BaseModel):  # frozen
    id: str; revision: int
    concept_art: tuple[Artifact, ...] = ()
    swatches: tuple[str, ...] = ()          # hex colors
    forbidden_changes: tuple[str, ...] = ()
    provenance: str = ""
    rights: str = ""
# references/store.py
class ReferencePackStore:
    def __init__(self, root: Path) -> None: ...
    def create(self, pack: ReferencePack) -> ReferencePack: ...       # revision forced to 1
    def new_revision(self, pack_id: str, **changes) -> ReferencePack: ...  # immutable prior revisions
    def get(self, pack_id: str, revision: int) -> ReferencePack: ...
    def latest(self, pack_id: str) -> ReferencePack: ...

# lineage/store.py
class CycleError(Exception): ...
class LineageStore:
    def __init__(self, root: Path) -> None: ...
    def add(self, node: LineageNode) -> None: ...        # raises CycleError on back-edge
    def get(self, asset_id: str) -> LineageNode: ...
    def ancestors(self, asset_id: str) -> list[LineageNode]: ...
    def children(self, asset_id: str) -> list[LineageNode]: ...
```

### 4.9 `fecreator.imaging`

Arrays are `numpy.ndarray`, `dtype=uint8`. RGB images have shape `(H, W, 3)`; indexed images are `(H, W)` index arrays plus an `(N, 3)` palette.

```python
# io.py
class ResourceBudget(BaseModel):
    max_pixels: int = 8_000_000
    max_palette: int = 256
class ImageBudgetError(Exception): ...
def load_rgb(path: Path, budget: ResourceBudget = ResourceBudget()) -> np.ndarray: ...
def save_png(path: Path, rgb: np.ndarray) -> None: ...
def load_indexed(path: Path) -> tuple[np.ndarray, np.ndarray]: ...
def save_indexed_png(path: Path, indices: np.ndarray, palette: np.ndarray) -> None: ...  # no tRNS
def png_dimensions(path: Path) -> tuple[int, int]: ...        # (width, height) from IHDR
def is_indexed_png(path: Path) -> bool: ...                   # PNG color type 3
def read_png_palette(path: Path) -> list[tuple[int, int, int]]: ...   # exact PLTE entries
def has_trns(path: Path) -> bool: ...                         # detects a tRNS chunk

# resize.py
class ResizeMode(str, Enum):
    ILLUSTRATION_FIT="illustration_fit"; PIXEL_PRESERVE="pixel_preserve"
    PSEUDO_PIXEL_GRID="pseudo_pixel_grid"; MANUAL_GRID="manual_grid"
def resize(rgb: np.ndarray, size: tuple[int, int], mode: ResizeMode,
           grid: "GridEstimate | None" = None) -> np.ndarray: ...

# grid.py
class GridEstimate(BaseModel):
    cell_w: int; cell_h: int; origin_x: int; origin_y: int; confidence: float
class LowConfidenceGridError(Exception): ...
def detect_grid(rgb: np.ndarray, min_confidence: float = 0.6) -> GridEstimate: ...

# color.py
def to_lab(rgb: np.ndarray) -> np.ndarray: ...
def from_lab(lab: np.ndarray) -> np.ndarray: ...
def lab_distance(a: np.ndarray, b: np.ndarray) -> np.ndarray: ...

# quantize.py
def quantize_kmeans_lab(rgb: np.ndarray, k: int, locked: Sequence[tuple[int,int,int]] = (),
                        seed: int = 0) -> tuple[np.ndarray, np.ndarray]: ...   # (indices, palette)
def quantize_median_cut(rgb: np.ndarray, k: int,
                        locked: Sequence[tuple[int,int,int]] = ()) -> tuple[np.ndarray, np.ndarray]: ...
def map_to_palette(rgb: np.ndarray, palette: np.ndarray) -> np.ndarray: ...   # (indices)

# masks.py
def background_mask(rgb: np.ndarray, key_rgb: tuple[int,int,int], tol: int = 24) -> np.ndarray: ...  # bool
def chroma_key(rgb: np.ndarray, key_rgb: tuple[int,int,int], tol: int = 24) -> np.ndarray: ...

# morphology.py
def close_mask(mask: np.ndarray, radius: int = 1) -> np.ndarray: ...
def open_mask(mask: np.ndarray, radius: int = 1) -> np.ndarray: ...
def fill_holes(mask: np.ndarray) -> np.ndarray: ...
def connected_components(mask: np.ndarray) -> tuple[int, np.ndarray]: ...

# metrics.py
def palette_distance(a: np.ndarray, b: np.ndarray) -> float: ...
def silhouette_iou(a_mask: np.ndarray, b_mask: np.ndarray) -> float: ...
def masked_perceptual_diff(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float: ...
def protected_region_diff(a: np.ndarray, b: np.ndarray, regions: Sequence[Region]) -> float: ...
```

### 4.10 `fecreator.specs`

```python
# base.py
class TargetSpec(Protocol):
    id: str
    def validate(self, package_dir: Path) -> list[Diagnostic]: ...

# fire_emblem/gba/portrait_standard/layout.py
class Slot(BaseModel):
    name: str; x: int; y: int; w: int; h: int
SLOTS: tuple[Slot, ...]                    # 12 canonical slots
BACKGROUND_ZONES: tuple[Region, ...]       # must remain index 0
SHEET_W: int = 128; SHEET_H: int = 112; MAX_COLORS: int = 16; BG_INDEX: int = 0

# palette.py
def snap_gba_5bit(rgb: tuple[int,int,int]) -> tuple[int,int,int]: ...   # (c>>3)<<3
def to_bgr555(rgb: tuple[int,int,int]) -> int: ...                      # r5 | g5<<5 | b5<<10
def write_jasc(path: Path, palette: Sequence[tuple[int,int,int]]) -> None: ...  # CRLF
def read_jasc(path: Path) -> list[tuple[int,int,int]]: ...

# assembly.py
def assemble_sheet(cells: Mapping[str, np.ndarray], palette: np.ndarray) -> np.ndarray: ...  # (112,128) indices
def preserve_cell_border(cell: np.ndarray, base: np.ndarray) -> np.ndarray: ...

# validation.py  (diagnostic codes mirror FEBuilderGBA; stricter fail-closed)
def validate_package(package_dir: Path) -> list[Diagnostic]: ...
# spec.py
class FeGbaPortraitStandard:   # implements TargetSpec
    id = "fe-gba-portrait-standard"
    def validate(self, package_dir: Path) -> list[Diagnostic]: ...
```

FEBuilderGBA validator diagnostic codes reproduced by `validation.py` (see FEBuilder-interop research): `MISSING_SHEET`, `MULTIPLE_SHEETS`, `BAD_PNG`, `NON_INDEXED`, `SHEET_TOO_SMALL`, `INCOMPLETE_PACKAGE`, `PALETTE_COUNT_MISMATCH`, `PALETTE_COLOR_MISMATCH`, `SHEET_BAD_DIMS`, `PORTRAIT_PALETTE_GT16`, `MISSING_PALETTE`, `EXTRA_PALETTE`. FECreator v1 export additionally **fails** (ERROR) on non-`128x112` dims, >16 palette, missing sidecar, enclosed background holes (`BACKGROUND_HOLE`), and unsafe/non-background safe zones (`UNSAFE_ZONE`). Patch-border invariance is enforced during expression derivation (portrait plugin), not at package level.

### 4.11 `fecreator.providers`

```python
# base.py
class GenRequest(BaseModel):  # frozen
    workflow: str
    prompt: str | None = None
    references: tuple[Artifact, ...] = ()
    mask: Artifact | None = None
    protected_regions: tuple[Region, ...] = ()
    seed: int | None = None
    params: dict[str, str | int | float | bool] = {}
class GenResponse(BaseModel):  # frozen
    ok: bool
    artifacts: tuple[Artifact, ...] = ()
    model: str | None = None
    seed: int | None = None
    diagnostics: tuple[Diagnostic, ...] = ()
class ProviderRefusal(Exception): ...
class Provider(Protocol):
    id: str
    capabilities: CapabilitySet
    def generate(self, request: GenRequest, workspace: Path) -> GenResponse: ...
def require_capabilities(provider: Provider, required: set[Capability]) -> None: ...  # raises ProviderRefusal
```

### 4.12 `fecreator.reporting`

```python
# json_report.py
def build_report(job: Job, results: Sequence[StageResult],
                 lineage: Sequence[LineageNode]) -> dict[str, object]: ...
def write_report(path: Path, report: Mapping[str, object]) -> None: ...

# bundle.py
class BundleError(Exception): ...
def build_bundle(job: Job, workspace: Path, out_dir: Path) -> Path: ...   # returns bundle dir; no credentials
def verify_bundle(bundle_dir: Path) -> list[Diagnostic]: ...
def febuilder_compat_report(diags: Sequence[Diagnostic]) -> dict[str, object]: ...
# credential safety uses fecreator.core.redaction.contains_secret_key to reject secret-bearing keys
```

### 4.12.1 `fecreator.core.redaction`

```python
SECRET_PATTERN: re.Pattern[str]          # token|key|secret|authorization|bearer|password|sig=
def redact(text: str) -> str: ...        # replaces secret-looking substrings with "***"
def contains_secret_key(key: str) -> bool: ...   # True if a mapping key names a credential
```

### 4.13 `fecreator.assets`

```python
# base.py
class SourcePlan(BaseModel):  # frozen
    prompts: tuple[str, ...]
    reference_roles: dict[str, str]        # role -> description
    expected_filenames: tuple[str, ...]
    required_expressions: tuple[str, ...]
    background_contract: str
    forbidden_colors: tuple[str, ...]
    submission_schema: dict[str, object]
class PromptPlan(BaseModel):  # frozen
    neutral_prompt: str
    expression_prompts: dict[str, str]
class AssetPlugin(Protocol):
    id: str
    def required_capabilities(self, workflow: str) -> set[Capability]: ...
    def preferred_capabilities(self, workflow: str) -> set[Capability]: ...
    def plan_sources(self, manifest: Manifest, pack: ReferencePack | None) -> SourcePlan: ...
    def build(self, ctx: PipelineContext, manifest: Manifest) -> JobResult: ...
```

### 4.14 `fecreator.app`

```python
class FeCreatorApp:
    def __init__(self, settings: Settings) -> None: ...
    def list_assets(self) -> list[str]: ...
    def list_specs(self) -> list[str]: ...
    def list_providers(self) -> list[str]: ...
    def create_job(self, manifest: Manifest) -> Job: ...
    def get_job(self, job_id: str) -> Job: ...
    def plan_sources(self, job_id: str, out_dir: Path) -> SourcePlan: ...
    def submit_sources(self, job_id: str, sources_dir: Path) -> Job: ...
    def build(self, job_id: str) -> JobResult: ...
    def validate(self, spec_id: str, package_dir: Path) -> list[Diagnostic]: ...
    def approve(self, job_id: str, stage: str, actor: str) -> ApprovalRecord: ...
    def reject(self, job_id: str, stage: str, actor: str, reason: str) -> ApprovalRecord: ...
    def cancel(self, job_id: str) -> Job: ...
    def events(self, job_id: str) -> list[JobEvent]: ...   # used by CLI inspect + WebSocket
```

## 5. Sub-plan index and execution order

Execute in dependency order. Each plan produces working, independently testable software and ends green.

| Order | Plan file | Implements todos | Depends on |
| --- | --- | --- | --- |
| 1 | `2026-07-24-fecreator-foundation.md` | bootstrap-repository, define-contracts | — |
| 2 | `2026-07-24-fecreator-jobs-lineage.md` | implement-jobs, implement-lineage | Foundation |
| 3 | `2026-07-24-fecreator-imaging-gba.md` | implement-imaging, implement-gba-spec | Foundation |
| 4 | `2026-07-24-fecreator-providers-interfaces.md` | implement-providers, implement-cli-mcp, implement-reports | Foundation, Jobs-Lineage, Imaging-GBA |
| 5 | `2026-07-24-fecreator-portrait-workflows.md` | implement-portrait | Foundation, Jobs-Lineage, Imaging-GBA, Providers-Interfaces |
| 6 | `2026-07-24-fecreator-web-skills-integration.md` | implement-web, implement-skills, integration-validation, febuilder-validation, stabilize-v1 | all above |

Plans 2 and 3 are independent of each other and MAY run in parallel after Foundation.

### Todo coverage matrix

| Todo id | Covered by |
| --- | --- |
| `bootstrap-repository` | Foundation Tasks 1–4, 10, 12 (scaffold/core-infra/pipeline/CI), and Web-Skills-Integration Task 13 (merge/green CI) |
| `define-contracts` | Foundation Tasks 5–9, 11 (contracts, registries, schema export) |
| `implement-jobs` | Jobs-Lineage Tasks 1–6 |
| `implement-lineage` | Jobs-Lineage Tasks 7–8 |
| `implement-imaging` | Imaging-GBA Tasks 1–7 |
| `implement-gba-spec` | Imaging-GBA Tasks 8–12 |
| `implement-providers` | Providers-Interfaces Tasks 1–5 |
| `implement-reports` | Providers-Interfaces Tasks 6–7 |
| `implement-cli-mcp` | Providers-Interfaces Tasks 8–12 |
| `implement-portrait` | Portrait-Workflows Tasks 1–9 |
| `implement-web` | Web-Skills-Integration Tasks 1–7 |
| `implement-skills` | Web-Skills-Integration Task 8 |
| `integration-validation` | Web-Skills-Integration Tasks 9–10 |
| `febuilder-validation` | Web-Skills-Integration Tasks 11–12 |
| `stabilize-v1` | Web-Skills-Integration Task 13 |

## 6. CI overview (`.github/workflows/ci.yml`)

Foundation creates the pipeline; later plans only add test files it already runs. Jobs:

1. **python** (matrix 3.11, 3.12 on `ubuntu-latest` and `windows-latest`): `pip install -e ".[dev]"`; then `ruff check .`, `ruff format --check .`, `mypy src`, `pytest -q`. Security/path tests are ordinary pytest tests under `tests/core/` and `tests/security/`, so they run here.
2. **web** (Node 22 on `ubuntu-latest`): `npm ci`; `npm run -w @laqieer/fecreator-web typecheck`; `npm run -w @laqieer/fecreator-web lint`; `npm run -w @laqieer/fecreator-web test`; `npm run -w @laqieer/fecreator-web build`.
3. **e2e** (Node 22 on `ubuntu-latest`): build web, start `fecreator serve` bound to `127.0.0.1`, run Playwright browser smoke + interaction specs.
4. **package** (`ubuntu-latest`): `python -m build` (sdist+wheel), then `twine check dist/*`.
5. **febuilder-interop** (`ubuntu-latest`): run ROM-free `FEBuilderGBA.CLI --validate-asset/--roundtrip-asset` against a synthetic package **only if** a `FEBUILDER_CLI` binary is provided; otherwise the step is a no-op success. **Never** depends on a ROM.

Windows vs POSIX command differences appear per task; CI runs the POSIX form except the python job's `windows-latest` matrix leg.

## 7. Conventions for every task

- **TDD:** write the failing test, run it, see it fail for the stated reason, write the minimal code, run it, see it pass, commit.
- **DRY / YAGNI:** reuse the catalog types; do not build capabilities beyond v1 scope.
- **Small commits:** one commit per task (Conventional Commits: `feat:`, `test:`, `chore:`, `docs:`, `ci:`).
- **Fixtures:** synthetic only, generated in code under `tests/fixtures/`. No copyrighted art, no ROM, no copied third-party source.
- **Platform commands:** where a command differs, tasks give a **PowerShell (Windows)** line and a **bash (POSIX)** line. Python/pytest/npm invocations are identical cross-platform and are given once.
- **Commit trailer:** append `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` to every commit message.

### Environment bootstrap (run once before Task 1 of Foundation)

PowerShell (Windows):
```powershell
cd C:\Projects\FECreator
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

bash (POSIX):
```bash
cd ~/FECreator
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

## 8. Self-review summary

This master plan and its six sub-plans were checked against the approved architecture design, the name-availability decision, and the FEBuilderGBA interoperability research:

- **Spec coverage:** every design section (scope, architecture, layout, stack, interfaces, jobs, reference packs/lineage, provider model, source handoff, imaging, portrait workflows, quality gates, FE GBA contract, security, testing, distribution, sequence) maps to at least one task via §5's coverage matrix.
- **No placeholders:** the canvas library and all dependency versions are decided here; no TBD/TODO remains.
- **Type consistency:** §4 is the single signature source; sub-plan Interfaces blocks quote it verbatim.
- **Constraints preserved:** §Global Constraints restates all v1 commitments and is inherited by every task.
