# FECreator Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold the `fecreator` Python distribution and private React/Vite web workspace, stand up green cross-platform CI, and define the immutable v1 contracts, registries, versioning, hashing, path-safety, and pipeline primitives every other subsystem builds on.

**Architecture:** A `src/`-layout Python package plus an `web/` npm workspace inside one repo. Contracts are frozen Pydantic v2 models with exported JSON Schemas. Core utilities (config, path containment, hashing, registries, version negotiation, pipeline) are dependency-light and fully unit-tested. No product logic yet — this plan delivers the substrate.

**Tech Stack:** Python 3.11–3.13, Pydantic v2, hatchling; TypeScript 5.9, React 19, Vite 8, Vitest; ruff, mypy, pytest.

## Global Constraints

Inherited from `2026-07-24-fecreator-v1-master.md` §Global Constraints. Task-relevant highlights: bind `127.0.0.1`; fail closed on path escape and unsupported versions; immutable/frozen contracts; no credentials in manifests; synthetic fixtures only; no Electron/Tauri/Rust.

**Implements todos:** `bootstrap-repository` (Tasks 1–4, 10, 12), `define-contracts` (Tasks 5–9, 11).

**Signatures:** All types quoted below come from master §4 (authoritative catalog). Do not invent alternatives.

---

## File structure built by this plan

```text
pyproject.toml  package.json  package-lock.json  .gitignore  .ruff.toml  README.md
.github/workflows/ci.yml
docs/product-statement.md  docs/architecture.md
schemas/{manifest,result,diagnostics,lineage,capabilities}.schema.json
src/fecreator/__init__.py  src/fecreator/cli.py
src/fecreator/core/{__init__,config,paths,hashing,clock,registry,compatibility,pipeline}.py
src/fecreator/contracts/{__init__,capabilities,diagnostics,result,lineage,manifest}.py
web/{package.json,tsconfig.json,vite.config.ts,index.html}
web/src/main.tsx  web/src/app/smoke.test.ts
tests/conftest.py
tests/core/{test_config,test_paths,test_hashing,test_registry,test_compatibility,test_pipeline}.py
tests/contracts/{test_capabilities,test_diagnostics,test_result,test_lineage,test_manifest,test_schemas}.py
tests/security/test_path_containment.py
```

Run the master's **Environment bootstrap** once before Task 1.

---

## Task 1: Repository scaffold, package metadata, and web workspace

**Files:**
- Create: `pyproject.toml`, `package.json`, `.gitignore`, `.ruff.toml`, `README.md`, `docs/product-statement.md`, `docs/architecture.md`
- Create: `src/fecreator/__init__.py`, `src/fecreator/cli.py`, `tests/conftest.py`
- Create: `web/package.json`, `web/tsconfig.json`, `web/vite.config.ts`, `web/index.html`, `web/src/main.tsx`, `web/src/app/smoke.test.ts`
- Test: `tests/test_package.py`

**Interfaces:**
- Consumes: nothing.
- Produces: importable package `fecreator` with `fecreator.__version__: str`; console script `fecreator` calling `fecreator.cli.main`; private npm workspaces `@laqieer/fecreator` (root) and `@laqieer/fecreator-web`.

- [ ] **Step 1: Write the failing test**

`tests/test_package.py`:
```python
import subprocess
import sys

import fecreator


def test_version_is_semver():
    parts = fecreator.__version__.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts)


def test_cli_version_matches_package():
    out = subprocess.run(
        [sys.executable, "-m", "fecreator.cli", "--version"],
        capture_output=True, text=True, check=True,
    )
    assert fecreator.__version__ in out.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_package.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator'`.

- [ ] **Step 3: Write minimal implementation**

`pyproject.toml`:
```toml
[build-system]
requires = ["hatchling>=1.25,<2"]
build-backend = "hatchling.build"

[project]
name = "fecreator"
version = "0.1.0"
description = "Local-first Fire Emblem portrait creation workbench"
readme = "README.md"
requires-python = ">=3.11,<3.14"
license = { text = "MIT" }
authors = [{ name = "laqieer" }]
dependencies = [
  "fastapi>=0.115,<0.140",
  "uvicorn[standard]>=0.30,<0.52",
  "pydantic>=2.9,<3",
  "numpy>=2.1,<3",
  "opencv-python-headless>=4.10,<5.1",
  "Pillow>=11.0,<13",
  "mcp>=1.10,<2",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2,<10",
  "pytest-asyncio>=0.24,<2",
  "pytest-cov>=5,<8",
  "httpx>=0.27,<0.29",
  "mypy>=1.13,<3",
  "ruff>=0.11,<0.16",
]

[project.scripts]
fecreator = "fecreator.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/fecreator"]
artifacts = ["src/fecreator/_web/**"]

[tool.pytest.ini_options]
addopts = "-q"
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.11"
strict = true
files = ["src"]
```

`.ruff.toml`:
```toml
line-length = 100
target-version = "py311"

[lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
```

`.gitignore`:
```text
.venv/
__pycache__/
*.egg-info/
dist/
build/
node_modules/
src/fecreator/_web/
.pytest_cache/
.mypy_cache/
.ruff_cache/
data/
```

`src/fecreator/__init__.py`:
```python
__version__ = "0.1.0"
```

`src/fecreator/cli.py` (minimal; expanded in Providers-Interfaces):
```python
from __future__ import annotations

import argparse

from fecreator import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fecreator")
    parser.add_argument("--version", action="version", version=f"fecreator {__version__}")
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`README.md`:
```markdown
# FECreator

Local-first, agent-neutral, provider-neutral Fire Emblem **portrait** creation
workbench with deterministic imaging, immutable jobs/lineage, human review, and a
`fe-gba-portrait-standard` export compatible with FEBuilderGBA (file-based, ROM-free).

See `docs/product-statement.md` for scope and `docs/architecture.md` for the module map.
```

`docs/product-statement.md`:
```markdown
# Product statement

FECreator **is** a local-first workbench that turns text or concept art into
Fire Emblem GBA portraits through deterministic processing and human review.

FECreator **is not** a ROM editor, ROM builder, FEBuilderGBA replacement, hosted
image-generation service, or generic non-Fire-Emblem asset tool.

## v1 scope
- Asset plugin: `portrait`. Target spec: `fe-gba-portrait-standard`.
- Interfaces: JSON CLI, FastAPI HTTP, WebSocket, MCP server, thin agent skills.
- Providers: `manual`, `fake`, `mcp-client`, `command`.
- Deferred: unit icons, map sprites, battle sprites, weapon frames, LoRA, other platforms.
```

`docs/architecture.md`:
```markdown
# Architecture

Every interface calls one `FeCreatorApp` service, which composes registries
(assets/specs/providers), immutable jobs/workspaces, a NumPy/OpenCV imaging core,
the portrait plugin, and the `fe-gba-portrait-standard` spec. The React/Vite web
app (bound to 127.0.0.1) is the human review UI, shipped as static assets in the wheel.

Module map: see the file tree in `docs/superpowers/plans/2026-07-24-fecreator-v1-master.md` §3.
```

`tests/conftest.py`:
```python
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    return root
```

Root `package.json`:
```json
{
  "name": "@laqieer/fecreator",
  "version": "0.1.0",
  "private": true,
  "workspaces": ["web"]
}
```

`web/package.json`:
```json
{
  "name": "@laqieer/fecreator-web",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "engines": { "node": ">=20.19 <25" },
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "typecheck": "tsc --noEmit",
    "lint": "eslint .",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^19.2.7",
    "react-dom": "^19.2.7",
    "konva": "^10.3.0",
    "react-konva": "^19.2.5",
    "@tanstack/react-query": "^5.101.0"
  },
  "devDependencies": {
    "@types/react": "^19.2.0",
    "@types/react-dom": "^19.2.0",
    "typescript": "~5.9.0",
    "vite": "^8.1.0",
    "@vitejs/plugin-react": "^6.0.0",
    "vitest": "^4.1.0",
    "@vitest/coverage-v8": "^4.1.0",
    "jsdom": "^29.1.0",
    "@testing-library/react": "^16.3.0",
    "@testing-library/jest-dom": "^6.9.0",
    "@testing-library/user-event": "^14.6.0",
    "@playwright/test": "^1.61.0",
    "eslint": "^10.7.0",
    "typescript-eslint": "^8.40.0",
    "prettier": "^3.4.0"
  }
}
```

`web/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"]
}
```

`web/vite.config.ts`:
```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: { outDir: "../src/fecreator/_web", emptyOutDir: true },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
```

`web/index.html`:
```html
<!doctype html>
<html lang="en">
  <head><meta charset="UTF-8" /><title>FECreator</title></head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`web/src/main.tsx`:
```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

export function App() {
  return <h1>FECreator</h1>;
}

const el = document.getElementById("root");
if (el) createRoot(el).render(<StrictMode><App /></StrictMode>);
```

`web/src/app/smoke.test.ts`:
```ts
import { expect, test } from "vitest";
import { App } from "../main";

test("App is defined", () => {
  expect(typeof App).toBe("function");
});
```

- [ ] **Step 4: Install and run tests to verify they pass**

PowerShell (Windows):
```powershell
python -m pip install -e ".[dev]"
npm install
```
bash (POSIX):
```bash
python -m pip install -e ".[dev]"
npm install
```
Then (identical cross-platform):
```
pytest tests/test_package.py -v
npm run -w @laqieer/fecreator-web test
npm run -w @laqieer/fecreator-web build
```
Expected: pytest PASS (2 passed); vitest PASS (1 passed); vite build writes `src/fecreator/_web/` (the wheel embeds it as `fecreator/_web`). `npm install` created `package-lock.json`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml package.json package-lock.json .gitignore .ruff.toml README.md docs src web tests
git commit -m "chore: scaffold fecreator package and web workspace

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2: Settings and localhost binding

**Files:**
- Create: `src/fecreator/core/__init__.py`, `src/fecreator/core/config.py`
- Test: `tests/core/test_config.py`

**Interfaces:**
- Produces: `Settings(host="127.0.0.1", port=8765, data_root: Path, allow_remote_upload=False)`; `get_settings(env: Mapping[str, str] | None = None) -> Settings` reading `FECREATOR_*`.

- [ ] **Step 1: Write the failing test**

`tests/core/test_config.py`:
```python
from pathlib import Path

from fecreator.core.config import Settings, get_settings


def test_defaults_bind_localhost(tmp_path):
    s = get_settings({"FECREATOR_DATA_ROOT": str(tmp_path)})
    assert s.host == "127.0.0.1"
    assert s.port == 8765
    assert s.allow_remote_upload is False
    assert s.data_root == tmp_path


def test_env_overrides(tmp_path):
    s = get_settings({
        "FECREATOR_DATA_ROOT": str(tmp_path),
        "FECREATOR_PORT": "9000",
        "FECREATOR_ALLOW_REMOTE_UPLOAD": "true",
    })
    assert s.port == 9000
    assert s.allow_remote_upload is True


def test_data_root_required():
    import pytest
    with pytest.raises(KeyError):
        get_settings({})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.core.config'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/core/__init__.py`:
```python
```

`src/fecreator/core/config.py`:
```python
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    data_root: Path
    allow_remote_upload: bool = False


def get_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    if "FECREATOR_DATA_ROOT" not in env:
        raise KeyError("FECREATOR_DATA_ROOT is required")
    return Settings(
        host=env.get("FECREATOR_HOST", "127.0.0.1"),
        port=int(env.get("FECREATOR_PORT", "8765")),
        data_root=Path(env["FECREATOR_DATA_ROOT"]),
        allow_remote_upload=env.get("FECREATOR_ALLOW_REMOTE_UPLOAD", "false").lower() == "true",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_config.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/core/__init__.py src/fecreator/core/config.py tests/core/test_config.py
git commit -m "feat: add Settings with localhost-default binding

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: Path containment (security)

**Files:**
- Create: `src/fecreator/core/paths.py`
- Test: `tests/core/test_paths.py`, `tests/security/test_path_containment.py`

**Interfaces:**
- Produces: `PathEscapeError`; `safe_join(root: Path, *parts: str) -> Path` (raises on escape); `is_contained(root: Path, target: Path) -> bool`.

- [ ] **Step 1: Write the failing test**

`tests/core/test_paths.py`:
```python
from pathlib import Path

import pytest

from fecreator.core.paths import PathEscapeError, is_contained, safe_join


def test_safe_join_ok(tmp_path):
    p = safe_join(tmp_path, "jobs", "abc", "manifest.json")
    assert is_contained(tmp_path, p)
    assert p.name == "manifest.json"


def test_safe_join_rejects_parent_escape(tmp_path):
    with pytest.raises(PathEscapeError):
        safe_join(tmp_path, "..", "etc", "passwd")


def test_safe_join_rejects_absolute(tmp_path):
    with pytest.raises(PathEscapeError):
        safe_join(tmp_path, "/abs/path")


def test_is_contained_false_for_sibling(tmp_path):
    sibling = tmp_path.parent / "other"
    assert is_contained(tmp_path, sibling) is False
```

`tests/security/test_path_containment.py`:
```python
from pathlib import Path

import pytest

from fecreator.core.paths import PathEscapeError, safe_join


@pytest.mark.parametrize("evil", ["../secret", "a/../../secret", "sub/../../..", "C:/Windows"])
def test_workspace_paths_cannot_escape(tmp_path, evil):
    with pytest.raises(PathEscapeError):
        safe_join(tmp_path, *evil.split("/"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_paths.py tests/security/test_path_containment.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.core.paths'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/core/paths.py`:
```python
from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath


class PathEscapeError(Exception):
    """Raised when a path would resolve outside its workspace root."""


def _has_absolute_part(parts: tuple[str, ...]) -> bool:
    for part in parts:
        if PurePosixPath(part).is_absolute() or PureWindowsPath(part).is_absolute():
            return True
        if len(part) >= 2 and part[1] == ":":
            return True
    return False


def safe_join(root: Path, *parts: str) -> Path:
    if _has_absolute_part(parts):
        raise PathEscapeError(f"absolute segment not allowed: {parts!r}")
    root = root.resolve()
    candidate = (root.joinpath(*parts)).resolve()
    if not is_contained(root, candidate):
        raise PathEscapeError(f"{candidate} escapes {root}")
    return candidate


def is_contained(root: Path, target: Path) -> bool:
    root = root.resolve()
    target = target.resolve()
    return root == target or root in target.parents
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_paths.py tests/security/test_path_containment.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/core/paths.py tests/core/test_paths.py tests/security/test_path_containment.py
git commit -m "feat: add fail-closed workspace path containment

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 4: Hashing and clock

**Files:**
- Create: `src/fecreator/core/hashing.py`, `src/fecreator/core/clock.py`
- Test: `tests/core/test_hashing.py`

**Interfaces:**
- Produces: `sha256_bytes(data) -> str`, `sha256_file(path) -> str`, `content_hash(model: BaseModel) -> str`; `utc_now_iso() -> str`.

- [ ] **Step 1: Write the failing test**

`tests/core/test_hashing.py`:
```python
from pydantic import BaseModel

from fecreator.core.clock import utc_now_iso
from fecreator.core.hashing import content_hash, sha256_bytes, sha256_file


class _M(BaseModel):
    a: int
    b: str


def test_sha256_bytes_known_vector():
    assert sha256_bytes(b"") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_sha256_file_matches_bytes(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc")
    assert sha256_file(p) == sha256_bytes(b"abc")


def test_content_hash_is_field_order_independent():
    assert content_hash(_M(a=1, b="x")) == content_hash(_M(b="x", a=1))


def test_utc_now_iso_has_utc_suffix():
    assert utc_now_iso().endswith("+00:00") or utc_now_iso().endswith("Z")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_hashing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.core.hashing'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/core/hashing.py`:
```python
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def content_hash(model: BaseModel) -> str:
    payload = model.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(canonical.encode("utf-8"))
```

`src/fecreator/core/clock.py`:
```python
from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_hashing.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/core/hashing.py src/fecreator/core/clock.py tests/core/test_hashing.py
git commit -m "feat: add sha256 and canonical content hashing plus utc clock

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 5: Capability contract

**Files:**
- Create: `src/fecreator/contracts/__init__.py`, `src/fecreator/contracts/capabilities.py`
- Test: `tests/contracts/test_capabilities.py`

**Interfaces:**
- Produces: `Capability` enum (13 members per master §4.1); `CapabilitySet(capabilities: frozenset[Capability])` with `supports(required) -> bool`, `missing(required) -> set[Capability]`.

- [ ] **Step 1: Write the failing test**

`tests/contracts/test_capabilities.py`:
```python
from fecreator.contracts.capabilities import Capability, CapabilitySet


def test_thirteen_capabilities():
    assert len(list(Capability)) == 13
    assert Capability.MASKED_EDIT.value == "masked_edit"


def test_supports_and_missing():
    cs = CapabilitySet(capabilities=frozenset({Capability.TEXT_TO_IMAGE}))
    assert cs.supports({Capability.TEXT_TO_IMAGE}) is True
    assert cs.supports({Capability.MASKED_EDIT}) is False
    assert cs.missing({Capability.TEXT_TO_IMAGE, Capability.MASKED_EDIT}) == {Capability.MASKED_EDIT}


def test_frozen():
    import pytest
    from pydantic import ValidationError

    cs = CapabilitySet(capabilities=frozenset())
    with pytest.raises((ValidationError, TypeError)):
        cs.capabilities = frozenset({Capability.SEED_CONTROL})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/contracts/test_capabilities.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.contracts.capabilities'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/contracts/__init__.py`:
```python
```

`src/fecreator/contracts/capabilities.py`:
```python
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


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


class CapabilitySet(BaseModel):
    model_config = ConfigDict(frozen=True)
    capabilities: frozenset[Capability]

    def supports(self, required: set[Capability]) -> bool:
        return required.issubset(self.capabilities)

    def missing(self, required: set[Capability]) -> set[Capability]:
        return set(required) - set(self.capabilities)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/contracts/test_capabilities.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/contracts/__init__.py src/fecreator/contracts/capabilities.py tests/contracts/test_capabilities.py
git commit -m "feat: add capability contract with fail-closed set checks

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 6: Diagnostics and result contracts

**Files:**
- Create: `src/fecreator/contracts/diagnostics.py`, `src/fecreator/contracts/result.py`
- Test: `tests/contracts/test_diagnostics.py`, `tests/contracts/test_result.py`

**Interfaces:**
- Produces: `Severity`, `Diagnostic`, `error()`, `warning()`, `has_errors()`; `Artifact`, `StageResult`, `JobResult` (master §4.2–4.3).

- [ ] **Step 1: Write the failing test**

`tests/contracts/test_diagnostics.py`:
```python
from fecreator.contracts.diagnostics import Diagnostic, Severity, error, has_errors, warning


def test_error_helper_sets_severity():
    d = error("BAD", "boom", where="file.png")
    assert d.severity is Severity.ERROR
    assert d.code == "BAD" and d.where == "file.png"


def test_has_errors():
    diags = [warning("W", "w"), error("E", "e")]
    assert has_errors(diags) is True
    assert has_errors([warning("W", "w")]) is False
```

`tests/contracts/test_result.py`:
```python
from fecreator.contracts.result import Artifact, JobResult, StageResult


def test_artifact_and_stage_result():
    a = Artifact(role="export", path="out/x.png", sha256="0" * 64, media_type="image/png")
    sr = StageResult(stage="export", ok=True, artifacts=(a,))
    assert sr.artifacts[0].path == "out/x.png"


def test_job_result_defaults():
    jr = JobResult(job_id="j1", ok=False)
    assert jr.artifacts == () and jr.lineage_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/contracts/test_diagnostics.py tests/contracts/test_result.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.contracts.diagnostics'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/contracts/diagnostics.py`:
```python
from __future__ import annotations

from collections.abc import Sequence
from enum import Enum

from pydantic import BaseModel, ConfigDict

DiagData = dict[str, str | int | float | bool]


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Diagnostic(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: str
    severity: Severity
    message: str
    where: str | None = None
    data: DiagData | None = None


def error(code: str, message: str, *, where: str | None = None, data: DiagData | None = None) -> Diagnostic:
    return Diagnostic(code=code, severity=Severity.ERROR, message=message, where=where, data=data)


def warning(code: str, message: str, *, where: str | None = None, data: DiagData | None = None) -> Diagnostic:
    return Diagnostic(code=code, severity=Severity.WARNING, message=message, where=where, data=data)


def has_errors(diags: Sequence[Diagnostic]) -> bool:
    return any(d.severity is Severity.ERROR for d in diags)
```

`src/fecreator/contracts/result.py`:
```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from fecreator.contracts.diagnostics import Diagnostic


class Artifact(BaseModel):
    model_config = ConfigDict(frozen=True)
    role: str
    path: str
    sha256: str
    media_type: str


class StageResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    stage: str
    ok: bool
    artifacts: tuple[Artifact, ...] = ()
    metrics: dict[str, float] = {}
    diagnostics: tuple[Diagnostic, ...] = ()


class JobResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    job_id: str
    ok: bool
    artifacts: tuple[Artifact, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    lineage_id: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/contracts/test_diagnostics.py tests/contracts/test_result.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/contracts/diagnostics.py src/fecreator/contracts/result.py tests/contracts/test_diagnostics.py tests/contracts/test_result.py
git commit -m "feat: add diagnostics and result contracts

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 7: Lineage contract (defines Region)

**Files:**
- Create: `src/fecreator/contracts/lineage.py`
- Test: `tests/contracts/test_lineage.py`

**Interfaces:**
- Produces: `Region`, `Operation`, `LineageNode` (master §4.5). `Region` is canonically defined here and imported by `manifest.py` (Task 8).

- [ ] **Step 1: Write the failing test**

`tests/contracts/test_lineage.py`:
```python
from fecreator.contracts.lineage import LineageNode, Operation, Region


def test_region_fields():
    r = Region(x=0, y=0, w=96, h=80, label="face")
    assert (r.x, r.y, r.w, r.h, r.label) == (0, 0, 96, 80, "face")


def test_lineage_node_immutable_and_defaults():
    import pytest
    from pydantic import ValidationError

    n = LineageNode(asset_id="a1", operation=Operation.CREATE_NEUTRAL, created_at="2026-07-24T00:00:00+00:00")
    assert n.parents == ()
    with pytest.raises((ValidationError, TypeError)):
        n.asset_id = "a2"


def test_operation_values():
    assert Operation.VARIANT_MASKED_EDIT.value == "variant_masked_edit"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/contracts/test_lineage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.contracts.lineage'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/contracts/lineage.py`:
```python
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

Params = dict[str, str | int | float | bool]


class Region(BaseModel):
    model_config = ConfigDict(frozen=True)
    x: int
    y: int
    w: int
    h: int
    label: str


class Operation(str, Enum):
    IMPORT_CONCEPT = "import_concept"
    CREATE_NEUTRAL = "create_neutral"
    REFINE_EXPRESSION = "refine_expression"
    VARIANT_MASKED_EDIT = "variant_masked_edit"
    EXPORT_SPEC = "export_spec"


class LineageNode(BaseModel):
    model_config = ConfigDict(frozen=True)
    asset_id: str
    operation: Operation
    parents: tuple[str, ...] = ()
    provider: str | None = None
    model: str | None = None
    prompt: str | None = None
    reference_pack: str | None = None
    reference_pack_rev: int | None = None
    seed: int | None = None
    params: Params = {}
    mask: str | None = None
    protected_regions: tuple[Region, ...] = ()
    metrics: dict[str, float] = {}
    approved_by: str | None = None
    output_hashes: tuple[str, ...] = ()
    created_at: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/contracts/test_lineage.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/contracts/lineage.py tests/contracts/test_lineage.py
git commit -m "feat: add lineage contract and Region geometry

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 8: Manifest contract

**Files:**
- Create: `src/fecreator/contracts/manifest.py`
- Test: `tests/contracts/test_manifest.py`

**Interfaces:**
- Consumes: `Region` from `fecreator.contracts.lineage`; `content_hash` from `fecreator.core.hashing`.
- Produces: `SourceSpec`, `EditSpec`, `Manifest` with `content_hash() -> str` (master §4.4).

- [ ] **Step 1: Write the failing test**

`tests/contracts/test_manifest.py`:
```python
import pytest
from pydantic import ValidationError

from fecreator.contracts.lineage import Region
from fecreator.contracts.manifest import EditSpec, Manifest, SourceSpec


def _manifest() -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="fake",
        sources=(SourceSpec(kind="text", ref="a brave knight"),),
    )


def test_manifest_defaults_and_hash_stable():
    m = _manifest()
    assert m.version == "1.0"
    assert m.content_hash() == _manifest().content_hash()
    assert len(m.content_hash()) == 64


def test_manifest_is_frozen():
    m = _manifest()
    with pytest.raises((ValidationError, TypeError)):
        m.provider = "openai"


def test_edit_spec_regions():
    e = EditSpec(mask_path="mask.png", protected_regions=(Region(x=0, y=0, w=96, h=80, label="face"),))
    assert e.protected_regions[0].label == "face"


def test_invalid_source_kind_rejected():
    with pytest.raises(ValidationError):
        SourceSpec(kind="video", ref="x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/contracts/test_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.contracts.manifest'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/contracts/manifest.py`:
```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from fecreator.contracts.lineage import Params, Region
from fecreator.core.hashing import content_hash


class SourceSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["text", "concept_art", "approved_portrait"]
    ref: str


class EditSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    mask_path: str
    protected_regions: tuple[Region, ...] = ()


class Manifest(BaseModel):
    model_config = ConfigDict(frozen=True)
    version: Literal["1.0"] = "1.0"
    asset_type: str
    target_spec: str
    workflow: str
    provider: str
    character_ref_pack: str | None = None
    sources: tuple[SourceSpec, ...] = ()
    edit: EditSpec | None = None
    params: Params = {}

    def content_hash(self) -> str:
        return content_hash(self)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/contracts/test_manifest.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/contracts/manifest.py tests/contracts/test_manifest.py
git commit -m "feat: add frozen Manifest contract with content hashing

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 9: Registries and version negotiation

**Files:**
- Create: `src/fecreator/core/registry.py`, `src/fecreator/core/compatibility.py`
- Test: `tests/core/test_registry.py`, `tests/core/test_compatibility.py`

**Interfaces:**
- Produces: `Registry[T]` (`register`/`get`/`ids`), `UnknownIdError`, and the three global registries `ASSET_REGISTRY`, `SPEC_REGISTRY`, `PROVIDER_REGISTRY` (typed `Registry[object]` in v1; concrete plugin types register into them). `check_supported(kind, version)`, `UnsupportedVersionError`, `SUPPORTED_CONTRACT_VERSIONS`.

- [ ] **Step 1: Write the failing test**

`tests/core/test_registry.py`:
```python
import pytest

from fecreator.core.registry import Registry, UnknownIdError


def test_register_get_ids():
    r: Registry[int] = Registry()
    r.register("a", 1)
    r.register("b", 2)
    assert r.get("a") == 1
    assert sorted(r.ids()) == ["a", "b"]


def test_unknown_id_raises():
    r: Registry[int] = Registry()
    with pytest.raises(UnknownIdError):
        r.get("missing")


def test_duplicate_registration_raises():
    r: Registry[int] = Registry()
    r.register("a", 1)
    with pytest.raises(ValueError):
        r.register("a", 2)
```

`tests/core/test_compatibility.py`:
```python
import pytest

from fecreator.core.compatibility import (
    SUPPORTED_CONTRACT_VERSIONS,
    UnsupportedVersionError,
    check_supported,
)


def test_supported_passes():
    assert "1.0" in SUPPORTED_CONTRACT_VERSIONS
    check_supported("manifest", "1.0")


def test_unsupported_raises():
    with pytest.raises(UnsupportedVersionError):
        check_supported("manifest", "2.0")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_registry.py tests/core/test_compatibility.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.core.registry'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/core/registry.py`:
```python
from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class UnknownIdError(KeyError):
    """Raised when a registry id is not registered."""


class Registry(Generic[T]):
    def __init__(self) -> None:
        self._items: dict[str, T] = {}

    def register(self, id: str, value: T) -> None:
        if id in self._items:
            raise ValueError(f"id already registered: {id}")
        self._items[id] = value

    def get(self, id: str) -> T:
        try:
            return self._items[id]
        except KeyError as exc:
            raise UnknownIdError(id) from exc

    def ids(self) -> list[str]:
        return list(self._items)


ASSET_REGISTRY: Registry[object] = Registry()
SPEC_REGISTRY: Registry[object] = Registry()
PROVIDER_REGISTRY: Registry[object] = Registry()
```

`src/fecreator/core/compatibility.py`:
```python
from __future__ import annotations

SUPPORTED_CONTRACT_VERSIONS: frozenset[str] = frozenset({"1.0"})


class UnsupportedVersionError(Exception):
    """Raised when a contract/spec/provider version is not supported."""


def check_supported(kind: str, version: str) -> None:
    if version not in SUPPORTED_CONTRACT_VERSIONS:
        raise UnsupportedVersionError(f"{kind} version {version} is not supported")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_registry.py tests/core/test_compatibility.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/core/registry.py src/fecreator/core/compatibility.py tests/core/test_registry.py tests/core/test_compatibility.py
git commit -m "feat: add registries and contract version negotiation

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 10: Pipeline primitives

**Files:**
- Create: `src/fecreator/core/pipeline.py`
- Test: `tests/core/test_pipeline.py`

**Interfaces:**
- Consumes: `StageResult` from `fecreator.contracts.result`.
- Produces: `PipelineContext(job_id, workspace, cancelled=False)`, `PipelineStep` protocol (`name: str`, `run(ctx) -> StageResult`), `Pipeline.run(steps, ctx) -> tuple[StageResult, ...]` (stops appending after a cancelled context or a failing stage).

- [ ] **Step 1: Write the failing test**

`tests/core/test_pipeline.py`:
```python
from pathlib import Path

from fecreator.contracts.result import StageResult
from fecreator.core.pipeline import Pipeline, PipelineContext


class _Step:
    def __init__(self, name: str, ok: bool = True) -> None:
        self.name = name
        self._ok = ok

    def run(self, ctx: PipelineContext) -> StageResult:
        return StageResult(stage=self.name, ok=self._ok)


def test_pipeline_runs_all_steps(tmp_path: Path):
    ctx = PipelineContext(job_id="j1", workspace=tmp_path)
    results = Pipeline().run([_Step("a"), _Step("b")], ctx)
    assert [r.stage for r in results] == ["a", "b"]


def test_pipeline_stops_after_failure(tmp_path: Path):
    ctx = PipelineContext(job_id="j1", workspace=tmp_path)
    results = Pipeline().run([_Step("a", ok=False), _Step("b")], ctx)
    assert [r.stage for r in results] == ["a"]


def test_pipeline_respects_cancellation(tmp_path: Path):
    ctx = PipelineContext(job_id="j1", workspace=tmp_path, cancelled=True)
    results = Pipeline().run([_Step("a")], ctx)
    assert results == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.core.pipeline'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/core/pipeline.py`:
```python
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from fecreator.contracts.result import StageResult


class PipelineContext(BaseModel):
    job_id: str
    workspace: Path
    cancelled: bool = False


@runtime_checkable
class PipelineStep(Protocol):
    name: str

    def run(self, ctx: PipelineContext) -> StageResult: ...


class Pipeline:
    def run(self, steps: Sequence[PipelineStep], ctx: PipelineContext) -> tuple[StageResult, ...]:
        results: list[StageResult] = []
        for step in steps:
            if ctx.cancelled:
                break
            result = step.run(ctx)
            results.append(result)
            if not result.ok:
                break
        return tuple(results)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_pipeline.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/core/pipeline.py tests/core/test_pipeline.py
git commit -m "feat: add pipeline step protocol and fail-closed runner

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 11: JSON Schema export for public contracts

**Files:**
- Create: `src/fecreator/contracts/schemas.py`
- Create (generated, committed): `schemas/{manifest,result,diagnostics,lineage,capabilities}.schema.json`
- Test: `tests/contracts/test_schemas.py`

**Interfaces:**
- Produces: `export_schemas(out_dir: Path) -> list[Path]` writing one `<name>.schema.json` per public contract; `SCHEMA_MODELS: dict[str, type[BaseModel]]`.

- [ ] **Step 1: Write the failing test**

`tests/contracts/test_schemas.py`:
```python
import json
from pathlib import Path

from fecreator.contracts.schemas import SCHEMA_MODELS, export_schemas

REPO_SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


def test_export_writes_all_models(tmp_path):
    written = export_schemas(tmp_path)
    assert {p.name for p in written} == {f"{n}.schema.json" for n in SCHEMA_MODELS}


def test_committed_schemas_are_up_to_date(tmp_path):
    export_schemas(tmp_path)
    for name in SCHEMA_MODELS:
        fresh = json.loads((tmp_path / f"{name}.schema.json").read_text())
        committed = json.loads((REPO_SCHEMAS / f"{name}.schema.json").read_text())
        assert fresh == committed, f"{name}.schema.json is stale; regenerate"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/contracts/test_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.contracts.schemas'`.

- [ ] **Step 3: Write minimal implementation and generate files**

`src/fecreator/contracts/schemas.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from fecreator.contracts.capabilities import CapabilitySet
from fecreator.contracts.diagnostics import Diagnostic
from fecreator.contracts.lineage import LineageNode
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import JobResult

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "manifest": Manifest,
    "result": JobResult,
    "diagnostics": Diagnostic,
    "lineage": LineageNode,
    "capabilities": CapabilitySet,
}


def export_schemas(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in SCHEMA_MODELS.items():
        path = out_dir / f"{name}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n")
        written.append(path)
    return written
```

Generate the committed copies (run from repo root):
```
python -c "from pathlib import Path; from fecreator.contracts.schemas import export_schemas; export_schemas(Path('schemas'))"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/contracts/test_schemas.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/contracts/schemas.py schemas/
git commit -m "feat: export JSON schemas for public contracts

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 12: Cross-platform CI pipeline

**Files:**
- Create: `.github/workflows/ci.yml`
- Test: local dry run of each job's commands (no new test file; CI config is validated by running its steps).

**Interfaces:**
- Consumes: all tasks above (package installs, tests, build).
- Produces: CI jobs `python`, `web`, `package` (jobs `e2e` and `febuilder-interop` are added in Web-Skills-Integration Tasks 10 and 11).

- [ ] **Step 1: Write the failing check**

Verify no workflow exists yet.
PowerShell (Windows): `Test-Path .github/workflows/ci.yml` → expected `False`.
bash (POSIX): `test -f .github/workflows/ci.yml && echo yes || echo no` → expected `no`.

- [ ] **Step 2: Confirm the gap**

Run the intended commands locally to confirm they pass before encoding them:
```
ruff check .
ruff format --check .
mypy src
pytest -q
npm ci
npm run -w @laqieer/fecreator-web typecheck
npm run -w @laqieer/fecreator-web lint
npm run -w @laqieer/fecreator-web test
npm run -w @laqieer/fecreator-web build
```
Expected before writing config: all pass locally (this is the acceptance the CI encodes). If `ruff format --check` fails, run `ruff format .` and re-commit affected files.

- [ ] **Step 3: Write the workflow**

`.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  python:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        python-version: ["3.11", "3.12"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: python -m pip install --upgrade pip
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: ruff format --check .
      - run: mypy src
      - run: pytest -q

  web:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
      - run: npm ci
      - run: npm run -w @laqieer/fecreator-web typecheck
      - run: npm run -w @laqieer/fecreator-web lint
      - run: npm run -w @laqieer/fecreator-web test
      - run: npm run -w @laqieer/fecreator-web build

  package:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
      - run: npm ci
      - run: npm run -w @laqieer/fecreator-web build
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install build twine
      - run: python -m build
      - run: twine check dist/*
```

Add an ESLint flat config so `npm run lint` works. `web/eslint.config.js`:
```js
import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.recommended,
  { ignores: ["dist/"] },
);
```
Add `@eslint/js` to `web/package.json` devDependencies at `^10.0.1` and re-run `npm install`. `^10.0.1` is the verified available 10.x floor; `^10.7.0` is not published.

- [ ] **Step 4: Verify locally**

Run every command from Step 2 again plus `python -m build && twine check dist/*` (after `pip install build twine`).
Expected: all PASS; `dist/` contains a wheel whose `fecreator/_web/` holds the built frontend.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml web/eslint.config.js web/package.json package-lock.json
git commit -m "ci: add cross-platform python/web/package pipeline

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Self-review

- **Spec coverage:** repository scaffold, pinned deps (master §2), naming (master §1), contracts (capabilities/diagnostics/result/lineage/manifest), registries, version negotiation, hashing, path-safety, pipeline, JSON schemas, and CI (python/web/package) are each a task. `e2e` and `febuilder-interop` CI jobs are explicitly deferred to Web-Skills-Integration (noted in Task 12).
- **Placeholder scan:** every code/test block is complete; the only intentionally empty files are `__init__.py` package markers.
- **Type consistency:** all signatures quote master §4; `Region` is defined once (Task 7) and imported by `manifest.py` (Task 8); `content_hash` is defined once (Task 4) and reused by `Manifest` (Task 8).
- **Platform commands:** venv activation (master §7), path-containment env, and CI-config existence checks give Windows + POSIX forms; pytest/npm commands are identical cross-platform.
