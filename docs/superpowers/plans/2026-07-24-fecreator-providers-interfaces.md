# FECreator Providers, Reporting & Interfaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the four provider bridges (`manual`, `fake`, `command`, `mcp-client`) with fail-closed capability checks and credential redaction, the JSON report + reproducibility bundle (with FEBuilder compatibility mapping and no-credential guarantees), and the four agent/human interfaces (JSON CLI, FastAPI HTTP, WebSocket, MCP server) that all call one `FeCreatorApp` facade.

**Architecture:** Providers self-register into `PROVIDER_REGISTRY` on import; each declares a `CapabilitySet`, and `require_capabilities` refuses missing required capabilities with no silent downgrade. The external `command` provider runs an argv list with `shell=False`. All interfaces are thin: they translate transport payloads to `FeCreatorApp` calls and back, holding zero image-processing logic.

**Tech Stack:** Python 3.11–3.13, FastAPI + Uvicorn, Starlette WebSockets, official MCP SDK (`mcp.server.fastmcp`), stdlib `argparse`/`subprocess`, Pydantic v2, pytest + httpx TestClient.

## Global Constraints

Inherited from `2026-07-24-fecreator-v1-master.md` §Global Constraints. Highlights: bind `127.0.0.1`; fail closed on missing capabilities; no shell in the command provider; no credentials in manifests or bundles (redacted); interfaces contain no processing logic.

**Implements todos:** `implement-providers` (Tasks 1–5), `implement-reports` (Tasks 6–7), `implement-cli-mcp` (Tasks 8–12).
**Depends on:** Foundation, Jobs-Lineage, Imaging-GBA.
**Signatures:** master §4.11 (providers), §4.12 (reporting), §4.12.1 (redaction), §4.13 (assets base), §4.14 (app). Quote verbatim.

---

## File structure built by this plan

```text
src/fecreator/providers/{__init__,base,manual,fake,command,mcp_client}.py
src/fecreator/core/redaction.py
src/fecreator/reporting/{__init__,json_report,bundle}.py
src/fecreator/assets/{__init__,base}.py
src/fecreator/app.py
src/fecreator/cli.py                     # expanded from Foundation minimal
src/fecreator/interfaces/{__init__,cli_json,http_api,websocket,mcp_server,static}.py
docs/interfaces.md
tests/providers/{test_base,test_manual,test_fake,test_command,test_mcp_client}.py
tests/reporting/{test_json_report,test_bundle}.py
tests/app/test_app.py
tests/interfaces/{test_cli_json,test_http_api,test_websocket,test_mcp_server}.py
```

---

## Task 1: Provider base contract and capability refusal

**Files:**
- Create: `src/fecreator/providers/__init__.py` (empty for now), `src/fecreator/providers/base.py`
- Test: `tests/providers/test_base.py`

**Interfaces:**
- Consumes: `Capability`, `CapabilitySet` (contracts.capabilities); `Artifact`, `Diagnostic`, `Region`.
- Produces: `GenRequest`, `GenResponse`, `ProviderRefusal`, `Provider` protocol, `require_capabilities(provider, required)` (master §4.11).

- [ ] **Step 1: Write the failing test**

`tests/providers/test_base.py`:
```python
import pytest

from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.providers.base import (
    GenRequest, GenResponse, Provider, ProviderRefusal, require_capabilities,
)


class _P:
    id = "p"
    capabilities = CapabilitySet(capabilities=frozenset({Capability.TEXT_TO_IMAGE}))

    def generate(self, request, workspace):
        return GenResponse(ok=True)


def test_protocol_isinstance():
    assert isinstance(_P(), Provider)


def test_require_capabilities_passes():
    require_capabilities(_P(), {Capability.TEXT_TO_IMAGE})


def test_require_capabilities_refuses_missing():
    with pytest.raises(ProviderRefusal) as exc:
        require_capabilities(_P(), {Capability.MASKED_EDIT})
    assert "masked_edit" in str(exc.value)


def test_gen_request_defaults():
    req = GenRequest(workflow="text_to_portrait", prompt="knight")
    assert req.references == () and req.seed is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/providers/test_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.providers.base'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/providers/__init__.py`:
```python
```

`src/fecreator/providers/base.py`:
```python
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.contracts.diagnostics import Diagnostic
from fecreator.contracts.lineage import Region
from fecreator.contracts.result import Artifact

Params = dict[str, str | int | float | bool]


class GenRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    workflow: str
    prompt: str | None = None
    references: tuple[Artifact, ...] = ()
    mask: Artifact | None = None
    protected_regions: tuple[Region, ...] = ()
    seed: int | None = None
    params: Params = {}


class GenResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    ok: bool
    artifacts: tuple[Artifact, ...] = ()
    model: str | None = None
    seed: int | None = None
    diagnostics: tuple[Diagnostic, ...] = ()


class ProviderRefusal(Exception):
    """Raised when a provider lacks a required capability (fail closed)."""


@runtime_checkable
class Provider(Protocol):
    id: str
    capabilities: CapabilitySet

    def generate(self, request: GenRequest, workspace: Path) -> GenResponse: ...


def require_capabilities(provider: Provider, required: set[Capability]) -> None:
    missing = provider.capabilities.missing(required)
    if missing:
        names = ", ".join(sorted(c.value for c in missing))
        raise ProviderRefusal(f"provider {provider.id} missing capabilities: {names}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/providers/test_base.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/providers/__init__.py src/fecreator/providers/base.py tests/providers/test_base.py
git commit -m "feat: add provider contract with fail-closed capability refusal

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2: Manual provider

**Files:**
- Create: `src/fecreator/providers/manual.py`
- Test: `tests/providers/test_manual.py`

**Interfaces:**
- Produces: `ManualProvider` (`id="manual"`, capabilities `{TEXT_TO_IMAGE, IMAGE_TO_IMAGE, MULTI_REFERENCE, MASKED_EDIT}`). `generate(request, workspace)` returns `GenResponse` referencing files under `workspace/submitted/` as artifacts (a human/agent placed them there).

- [ ] **Step 1: Write the failing test**

`tests/providers/test_manual.py`:
```python
from fecreator.contracts.capabilities import Capability
from fecreator.providers.base import GenRequest
from fecreator.providers.manual import ManualProvider


def test_capabilities_include_masked_edit():
    assert Capability.MASKED_EDIT in ManualProvider().capabilities.capabilities


def test_generate_picks_up_submitted_files(tmp_path):
    submitted = tmp_path / "submitted"
    submitted.mkdir()
    (submitted / "neutral.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    resp = ManualProvider().generate(GenRequest(workflow="text_to_portrait"), tmp_path)
    assert resp.ok
    assert [a.role for a in resp.artifacts] == ["neutral"]
    assert resp.artifacts[0].path == "submitted/neutral.png"


def test_generate_empty_is_not_ok(tmp_path):
    resp = ManualProvider().generate(GenRequest(workflow="text_to_portrait"), tmp_path)
    assert resp.ok is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/providers/test_manual.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.providers.manual'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/providers/manual.py`:
```python
from __future__ import annotations

from pathlib import Path

from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.contracts.result import Artifact
from fecreator.core.hashing import sha256_file
from fecreator.providers.base import GenRequest, GenResponse


class ManualProvider:
    id = "manual"
    capabilities = CapabilitySet(capabilities=frozenset({
        Capability.TEXT_TO_IMAGE, Capability.IMAGE_TO_IMAGE,
        Capability.MULTI_REFERENCE, Capability.MASKED_EDIT,
    }))

    def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
        submitted = workspace / "submitted"
        files = sorted(submitted.glob("*")) if submitted.exists() else []
        artifacts = tuple(
            Artifact(role=f.stem, path=f"submitted/{f.name}", sha256=sha256_file(f),
                     media_type="image/png")
            for f in files if f.is_file()
        )
        return GenResponse(ok=bool(artifacts), artifacts=artifacts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/providers/test_manual.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/providers/manual.py tests/providers/test_manual.py
git commit -m "feat: add manual provider for human/agent-submitted sources

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: Fake provider (deterministic)

**Files:**
- Create: `src/fecreator/providers/fake.py`
- Test: `tests/providers/test_fake.py`

**Interfaces:**
- Consumes: `imaging.io.save_png`, `core.hashing.sha256_file`.
- Produces: `FakeProvider` (`id="fake"`, broad capabilities). `generate` writes a deterministic solid-color PNG under `workspace/generated/neutral.png` (color derived from prompt hash), returns its `Artifact`. Same prompt+workspace → identical sha256.

- [ ] **Step 1: Write the failing test**

`tests/providers/test_fake.py`:
```python
from fecreator.providers.base import GenRequest
from fecreator.providers.fake import FakeProvider


def test_generate_is_deterministic(tmp_path):
    req = GenRequest(workflow="text_to_portrait", prompt="brave knight",
                     params={"width": 96, "height": 80})
    a = FakeProvider().generate(req, tmp_path / "a")
    b = FakeProvider().generate(req, tmp_path / "b")
    assert a.ok and a.artifacts[0].sha256 == b.artifacts[0].sha256


def test_different_prompt_differs(tmp_path):
    p1 = FakeProvider().generate(GenRequest(workflow="w", prompt="a"), tmp_path / "1")
    p2 = FakeProvider().generate(GenRequest(workflow="w", prompt="b"), tmp_path / "2")
    assert p1.artifacts[0].sha256 != p2.artifacts[0].sha256
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/providers/test_fake.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.providers.fake'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/providers/fake.py`:
```python
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.contracts.result import Artifact
from fecreator.core.hashing import sha256_file
from fecreator.imaging.io import save_png
from fecreator.providers.base import GenRequest, GenResponse


class FakeProvider:
    id = "fake"
    capabilities = CapabilitySet(capabilities=frozenset(Capability))

    def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
        digest = hashlib.sha256((request.prompt or "").encode("utf-8")).digest()
        color = (digest[0], digest[1], digest[2])
        width = int(request.params.get("width", 96))
        height = int(request.params.get("height", 80))
        rgb = np.zeros((height, width, 3), dtype=np.uint8)
        rgb[:, :] = color
        out = workspace / "generated" / "neutral.png"
        save_png(out, rgb)
        artifact = Artifact(role="neutral", path="generated/neutral.png",
                            sha256=sha256_file(out), media_type="image/png")
        return GenResponse(ok=True, artifacts=(artifact,), model="fake-1", seed=request.seed or 0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/providers/test_fake.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/providers/fake.py tests/providers/test_fake.py
git commit -m "feat: add deterministic fake provider

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 4: External command provider (no shell) and redaction

**Files:**
- Create: `src/fecreator/core/redaction.py`, `src/fecreator/providers/command.py`
- Test: `tests/core/test_redaction.py`, `tests/providers/test_command.py`

**Interfaces:**
- Produces (redaction): `SECRET_PATTERN`, `redact(text) -> str`, `contains_secret_key(key) -> bool` (master §4.12.1).
- Produces (command): `CommandProvider(argv: list[str], capabilities: CapabilitySet, id="command")`. `generate` runs `subprocess.run(argv, input=<json>, capture_output=True, text=True, shell=False, timeout=...)`, parses stdout JSON, fills `sha256` for each returned artifact from `workspace`, redacts stderr in diagnostics.

- [ ] **Step 1: Write the failing test**

`tests/core/test_redaction.py`:
```python
from fecreator.core.redaction import contains_secret_key, redact


def test_redact_masks_tokens():
    assert "***" in redact("authorization: Bearer sk-abc123")
    assert "sk-abc123" not in redact("token=sk-abc123")


def test_contains_secret_key():
    assert contains_secret_key("api_key") is True
    assert contains_secret_key("authorization") is True
    assert contains_secret_key("width") is False
```

`tests/providers/test_command.py`:
```python
import sys

import numpy as np

from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.imaging.io import save_png
from fecreator.providers.base import GenRequest
from fecreator.providers.command import CommandProvider

SCRIPT = '''
import json, sys, numpy as np
from pathlib import Path
from PIL import Image
req = json.load(sys.stdin)
ws = Path(req["workspace"])
(ws / "generated").mkdir(parents=True, exist_ok=True)
Image.fromarray(np.zeros((4, 4, 3), dtype=np.uint8), "RGB").save(ws / "generated" / "n.png")
print(json.dumps({"ok": True, "model": "ext-1",
    "artifacts": [{"role": "neutral", "path": "generated/n.png", "media_type": "image/png"}]}))
'''


def test_command_provider_runs_without_shell(tmp_path):
    script = tmp_path / "gen.py"
    script.write_text(SCRIPT)
    provider = CommandProvider(argv=[sys.executable, str(script)],
                               capabilities=CapabilitySet(capabilities=frozenset({Capability.TEXT_TO_IMAGE})))
    resp = provider.generate(GenRequest(workflow="text_to_portrait", prompt="x"), tmp_path)
    assert resp.ok and resp.model == "ext-1"
    assert len(resp.artifacts[0].sha256) == 64
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_redaction.py tests/providers/test_command.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.core.redaction'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/core/redaction.py`:
```python
from __future__ import annotations

import re

SECRET_PATTERN = re.compile(
    r"(?i)(authorization|bearer|token|api[_-]?key|secret|password|sig)\s*[:=]\s*\S+"
)
_SECRET_KEY = re.compile(r"(?i)(authorization|bearer|token|api[_-]?key|secret|password|credential)")


def redact(text: str) -> str:
    return SECRET_PATTERN.sub(lambda m: f"{m.group(1)}=***", text)


def contains_secret_key(key: str) -> bool:
    return _SECRET_KEY.search(key) is not None
```

`src/fecreator/providers/command.py`:
```python
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fecreator.contracts.capabilities import CapabilitySet
from fecreator.contracts.diagnostics import Diagnostic, warning
from fecreator.contracts.result import Artifact
from fecreator.core.hashing import sha256_file
from fecreator.core.redaction import redact
from fecreator.providers.base import GenRequest, GenResponse


class CommandProvider:
    id = "command"

    def __init__(self, argv: list[str], capabilities: CapabilitySet, timeout: float = 120.0) -> None:
        self._argv = argv
        self.capabilities = capabilities
        self._timeout = timeout

    def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
        payload = {"version": "1.0", "workspace": str(workspace),
                   "request": request.model_dump(mode="json")}
        proc = subprocess.run(  # noqa: S603 - argv list, shell=False, no user shell string
            self._argv, input=json.dumps(payload), capture_output=True, text=True,
            shell=False, timeout=self._timeout,
        )
        diagnostics: tuple[Diagnostic, ...] = ()
        if proc.stderr.strip():
            diagnostics = (warning("PROVIDER_STDERR", redact(proc.stderr.strip())),)
        if proc.returncode != 0:
            return GenResponse(ok=False, diagnostics=diagnostics)
        data = json.loads(proc.stdout)
        artifacts = tuple(
            Artifact(role=a["role"], path=a["path"], media_type=a["media_type"],
                     sha256=sha256_file(workspace / a["path"]))
            for a in data.get("artifacts", [])
        )
        return GenResponse(ok=bool(data.get("ok")), artifacts=artifacts,
                           model=data.get("model"), diagnostics=diagnostics)
```

Add to `.ruff.toml` `[lint]` an ignore for the audited subprocess call, or annotate as shown; ensure `ruff check .` passes.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_redaction.py tests/providers/test_command.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/core/redaction.py src/fecreator/providers/command.py tests/core/test_redaction.py tests/providers/test_command.py
git commit -m "feat: add no-shell command provider with credential redaction

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 5: MCP-client provider and registry finalization

**Files:**
- Create: `src/fecreator/providers/mcp_client.py`
- Modify: `src/fecreator/providers/__init__.py` (register all four)
- Test: `tests/providers/test_mcp_client.py`

**Interfaces:**
- Produces: `McpTransport` protocol (`call_tool(name, args) -> dict`), `McpClientProvider(transport, capabilities, tool_map, id="mcp-client")`; `generate` maps a `GenRequest` to a tool call, writes returned base64/paths as artifacts. `providers/__init__.py` registers `manual`, `fake`, `command` (a default no-op argv is not registered; `command`/`mcp-client` register a not-configured sentinel that refuses until configured). Registry ids after import: `{"manual", "fake", "command", "mcp-client"}`.

- [ ] **Step 1: Write the failing test**

`tests/providers/test_mcp_client.py`:
```python
from pathlib import Path

from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.core.registry import PROVIDER_REGISTRY
from fecreator.providers.base import GenRequest
from fecreator.providers.mcp_client import McpClientProvider


class _FakeTransport:
    def call_tool(self, name, args):
        (Path(args["workspace"]) / "generated").mkdir(parents=True, exist_ok=True)
        out = Path(args["workspace"]) / "generated" / "n.png"
        out.write_bytes(b"\x89PNG\r\n\x1a\n")
        return {"ok": True, "artifacts": [{"role": "neutral", "path": "generated/n.png",
                                           "media_type": "image/png"}]}


def test_generate_maps_tool_call(tmp_path):
    provider = McpClientProvider(
        transport=_FakeTransport(),
        capabilities=CapabilitySet(capabilities=frozenset({Capability.TEXT_TO_IMAGE})),
        tool_map={"text_to_portrait": "generate_image"},
    )
    resp = provider.generate(GenRequest(workflow="text_to_portrait", prompt="x"), tmp_path)
    assert resp.ok and resp.artifacts[0].role == "neutral"


def test_all_providers_registered():
    import fecreator.providers  # noqa: F401
    assert set(PROVIDER_REGISTRY.ids()) >= {"manual", "fake", "command", "mcp-client"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/providers/test_mcp_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.providers.mcp_client'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/providers/mcp_client.py`:
```python
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from fecreator.contracts.capabilities import CapabilitySet
from fecreator.contracts.result import Artifact
from fecreator.core.hashing import sha256_file
from fecreator.providers.base import GenRequest, GenResponse, ProviderRefusal


class McpTransport(Protocol):
    def call_tool(self, name: str, args: dict[str, object]) -> dict[str, object]: ...


class McpClientProvider:
    id = "mcp-client"

    def __init__(self, transport: McpTransport | None, capabilities: CapabilitySet,
                 tool_map: dict[str, str]) -> None:
        self._transport = transport
        self.capabilities = capabilities
        self._tool_map = tool_map

    def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
        if self._transport is None:
            raise ProviderRefusal("mcp-client is not configured")
        tool = self._tool_map[request.workflow]
        data = self._transport.call_tool(tool, {"workspace": str(workspace),
                                                 "prompt": request.prompt or ""})
        artifacts = tuple(
            Artifact(role=str(a["role"]), path=str(a["path"]), media_type=str(a["media_type"]),
                     sha256=sha256_file(workspace / str(a["path"])))
            for a in data.get("artifacts", [])  # type: ignore[union-attr]
        )
        return GenResponse(ok=bool(data.get("ok")), artifacts=artifacts, model="mcp-client")
```

`src/fecreator/providers/__init__.py`:
```python
from __future__ import annotations

from fecreator.contracts.capabilities import CapabilitySet
from fecreator.core.registry import PROVIDER_REGISTRY
from fecreator.providers.command import CommandProvider
from fecreator.providers.fake import FakeProvider
from fecreator.providers.manual import ManualProvider
from fecreator.providers.mcp_client import McpClientProvider

_UNCONFIGURED = CapabilitySet(capabilities=frozenset())


def _register(provider_id: str, provider: object) -> None:
    if provider_id not in PROVIDER_REGISTRY.ids():
        PROVIDER_REGISTRY.register(provider_id, provider)


_register("manual", ManualProvider())
_register("fake", FakeProvider())
_register("command", CommandProvider(argv=[], capabilities=_UNCONFIGURED))
_register("mcp-client", McpClientProvider(transport=None, capabilities=_UNCONFIGURED, tool_map={}))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/providers/test_mcp_client.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/providers/mcp_client.py src/fecreator/providers/__init__.py tests/providers/test_mcp_client.py
git commit -m "feat: add mcp-client provider and register all provider bridges

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 6: JSON report

**Files:**
- Create: `src/fecreator/reporting/__init__.py`, `src/fecreator/reporting/json_report.py`
- Test: `tests/reporting/test_json_report.py`

**Interfaces:**
- Consumes: `Job`, `StageResult`, `LineageNode`.
- Produces: `build_report(job, results, lineage) -> dict`, `write_report(path, report) -> None`.

- [ ] **Step 1: Write the failing test**

`tests/reporting/test_json_report.py`:
```python
from fecreator.contracts.lineage import LineageNode, Operation
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.contracts.result import StageResult
from fecreator.jobs.model import Job, JobState
from fecreator.reporting.json_report import build_report, write_report


def _job():
    m = Manifest(asset_type="portrait", target_spec="fe-gba-portrait-standard",
                 workflow="text_to_portrait", provider="fake",
                 sources=(SourceSpec(kind="text", ref="hero"),))
    return Job(id="j1", state=JobState.COMPLETED, manifest=m, revision=1,
               created_at="t", updated_at="t")


def test_build_report_shape():
    report = build_report(_job(), [StageResult(stage="export", ok=True)],
                          [LineageNode(asset_id="a", operation=Operation.EXPORT_SPEC, created_at="t")])
    assert report["job_id"] == "j1"
    assert report["manifest"]["provider"] == "fake"
    assert report["stages"][0]["stage"] == "export"
    assert report["lineage"][0]["asset_id"] == "a"


def test_write_report(tmp_path):
    report = build_report(_job(), [], [])
    write_report(tmp_path / "r.json", report)
    assert (tmp_path / "r.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/reporting/test_json_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.reporting.json_report'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/reporting/__init__.py`:
```python
```

`src/fecreator/reporting/json_report.py`:
```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from fecreator.contracts.lineage import LineageNode
from fecreator.contracts.result import StageResult
from fecreator.core.atomicio import write_json_atomic
from fecreator.jobs.model import Job


def build_report(job: Job, results: Sequence[StageResult],
                 lineage: Sequence[LineageNode]) -> dict[str, object]:
    return {
        "job_id": job.id,
        "state": job.state.value,
        "manifest": job.manifest.model_dump(mode="json"),
        "manifest_hash": job.manifest.content_hash(),
        "stages": [r.model_dump(mode="json") for r in results],
        "lineage": [n.model_dump(mode="json") for n in lineage],
    }


def write_report(path: Path, report: Mapping[str, object]) -> None:
    write_json_atomic(path, dict(report))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/reporting/test_json_report.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/reporting/__init__.py src/fecreator/reporting/json_report.py tests/reporting/test_json_report.py
git commit -m "feat: add json job report builder

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 7: Reproducibility bundle and FEBuilder compat report

**Files:**
- Create: `src/fecreator/reporting/bundle.py`
- Test: `tests/reporting/test_bundle.py`

**Interfaces:**
- Consumes: `Job`, `core.hashing.sha256_file`, `core.redaction.contains_secret_key`, `core.atomicio`.
- Produces: `BundleError`; `build_bundle(job, workspace, out_dir) -> Path` (copies the package + writes `manifest.json`, `report.json`, `hashes.json`; refuses any manifest param whose key names a credential); `verify_bundle(bundle_dir) -> list[Diagnostic]`; `febuilder_compat_report(diags) -> dict`.

- [ ] **Step 1: Write the failing test**

`tests/reporting/test_bundle.py`:
```python
import numpy as np
import pytest

from fecreator.contracts.diagnostics import error, warning
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.imaging.io import save_indexed_png
from fecreator.jobs.model import Job, JobState
from fecreator.reporting.bundle import (
    BundleError, build_bundle, febuilder_compat_report, verify_bundle,
)


def _job(params=None):
    m = Manifest(asset_type="portrait", target_spec="fe-gba-portrait-standard",
                 workflow="text_to_portrait", provider="fake",
                 sources=(SourceSpec(kind="text", ref="hero"),), params=params or {})
    return Job(id="j1", state=JobState.COMPLETED, manifest=m, revision=1,
               created_at="t", updated_at="t")


def _workspace(tmp_path):
    pkg = tmp_path / "package"
    pkg.mkdir()
    save_indexed_png(pkg / "hero.png", np.zeros((2, 2), np.uint8),
                     np.array([(0, 0, 0)], dtype=np.uint8))
    return tmp_path


def test_build_bundle_has_no_credentials(tmp_path):
    bundle = build_bundle(_job(), _workspace(tmp_path), tmp_path / "out")
    assert (bundle / "manifest.json").exists()
    assert (bundle / "hashes.json").exists()
    assert (bundle / "package" / "hero.png").exists()


def test_bundle_refuses_secret_param(tmp_path):
    with pytest.raises(BundleError):
        build_bundle(_job({"api_key": "sk-xyz"}), _workspace(tmp_path), tmp_path / "out")


def test_verify_bundle_ok(tmp_path):
    bundle = build_bundle(_job(), _workspace(tmp_path), tmp_path / "out")
    assert verify_bundle(bundle) == []


def test_febuilder_compat_report_maps_codes():
    report = febuilder_compat_report([error("SHEET_BAD_DIMS", "x"), warning("MISSING_PALETTE", "y")])
    assert report["errors"] == 1 and report["warnings"] == 1
    assert "SHEET_BAD_DIMS" in report["codes"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/reporting/test_bundle.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.reporting.bundle'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/reporting/bundle.py`:
```python
from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path

from fecreator.contracts.diagnostics import Diagnostic, Severity, error
from fecreator.core.atomicio import write_json_atomic
from fecreator.core.hashing import sha256_file
from fecreator.core.redaction import contains_secret_key
from fecreator.jobs.model import Job


class BundleError(Exception):
    """Raised when a bundle would contain credentials or is malformed."""


def build_bundle(job: Job, workspace: Path, out_dir: Path) -> Path:
    for key in job.manifest.params:
        if contains_secret_key(key):
            raise BundleError(f"manifest param names a credential: {key}")
    out_dir.mkdir(parents=True, exist_ok=True)
    package_src = workspace / "package"
    package_dst = out_dir / "package"
    if package_src.exists():
        shutil.copytree(package_src, package_dst, dirs_exist_ok=True)
    write_json_atomic(out_dir / "manifest.json", job.manifest.model_dump(mode="json"))
    hashes = {p.name: sha256_file(p) for p in sorted(package_dst.glob("*"))} if package_dst.exists() else {}
    write_json_atomic(out_dir / "hashes.json", hashes)
    write_json_atomic(out_dir / "report.json", {"job_id": job.id, "state": job.state.value})
    return out_dir


def verify_bundle(bundle_dir: Path) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    for required in ("manifest.json", "hashes.json", "report.json"):
        if not (bundle_dir / required).exists():
            diags.append(error("BUNDLE_MISSING_FILE", f"missing {required}", where=required))
    return diags


def febuilder_compat_report(diags: Sequence[Diagnostic]) -> dict[str, object]:
    return {
        "errors": sum(1 for d in diags if d.severity is Severity.ERROR),
        "warnings": sum(1 for d in diags if d.severity is Severity.WARNING),
        "codes": sorted({d.code for d in diags}),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/reporting/test_bundle.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/reporting/bundle.py tests/reporting/test_bundle.py
git commit -m "feat: add reproducibility bundle with no-credential guarantee

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 8: Asset plugin base and FeCreatorApp facade

**Files:**
- Create: `src/fecreator/assets/__init__.py`, `src/fecreator/assets/base.py`, `src/fecreator/app.py`
- Test: `tests/app/test_app.py`

**Interfaces:**
- Produces (assets.base): `SourcePlan`, `PromptPlan`, `AssetPlugin` protocol (master §4.13).
- Produces (app): `FeCreatorApp` (master §4.14). Resolves plugins/providers/specs from the three registries; imports `fecreator.providers` and `fecreator.specs` to populate them.

- [ ] **Step 1: Write the failing test**

`tests/app/test_app.py`:
```python
from pathlib import Path

from fecreator.app import FeCreatorApp
from fecreator.assets.base import AssetPlugin, PromptPlan, SourcePlan
from fecreator.contracts.capabilities import Capability
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.contracts.result import JobResult
from fecreator.core.config import Settings
from fecreator.core.pipeline import PipelineContext
from fecreator.core.registry import ASSET_REGISTRY


class _StubPortrait:
    id = "portrait"

    def required_capabilities(self, workflow: str) -> set[Capability]:
        return {Capability.TEXT_TO_IMAGE}

    def preferred_capabilities(self, workflow: str) -> set[Capability]:
        return set()

    def plan_sources(self, manifest, pack) -> SourcePlan:
        return SourcePlan(prompts=("hero",), reference_roles={}, expected_filenames=("neutral.png",),
                          required_expressions=("neutral",), background_contract="green",
                          forbidden_colors=(), submission_schema={})

    def build(self, ctx: PipelineContext, manifest) -> JobResult:
        return JobResult(job_id=ctx.job_id, ok=True)


def _app(tmp_path) -> FeCreatorApp:
    if "portrait" not in ASSET_REGISTRY.ids():
        ASSET_REGISTRY.register("portrait", _StubPortrait())
    return FeCreatorApp(Settings(data_root=tmp_path))


def _manifest():
    return Manifest(asset_type="portrait", target_spec="fe-gba-portrait-standard",
                    workflow="text_to_portrait", provider="fake",
                    sources=(SourceSpec(kind="text", ref="hero"),))


def test_lists_include_registered(tmp_path):
    app = _app(tmp_path)
    assert "fake" in app.list_providers()
    assert "fe-gba-portrait-standard" in app.list_specs()
    assert "portrait" in app.list_assets()


def test_create_get_and_stub_build(tmp_path):
    app = _app(tmp_path)
    job = app.create_job(_manifest())
    assert app.get_job(job.id).id == job.id
    assert app.build(job.id).ok


def test_plan_sources_writes_file(tmp_path):
    app = _app(tmp_path)
    job = app.create_job(_manifest())
    plan = app.plan_sources(job.id, tmp_path / "plan")
    assert "neutral.png" in plan.expected_filenames
    assert (tmp_path / "plan" / "source_plan.json").exists()


def test_validate_uses_spec(tmp_path):
    app = _app(tmp_path)
    diags = app.validate("fe-gba-portrait-standard", tmp_path)  # empty dir -> MISSING_SHEET
    assert any(d.code == "MISSING_SHEET" for d in diags)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/app/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.app'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/assets/__init__.py`:
```python
```

`src/fecreator/assets/base.py`:
```python
from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from fecreator.contracts.capabilities import Capability
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import JobResult
from fecreator.core.pipeline import PipelineContext
from fecreator.references.model import ReferencePack


class SourcePlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    prompts: tuple[str, ...]
    reference_roles: dict[str, str]
    expected_filenames: tuple[str, ...]
    required_expressions: tuple[str, ...]
    background_contract: str
    forbidden_colors: tuple[str, ...]
    submission_schema: dict[str, object]


class PromptPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    neutral_prompt: str
    expression_prompts: dict[str, str]


@runtime_checkable
class AssetPlugin(Protocol):
    id: str

    def required_capabilities(self, workflow: str) -> set[Capability]: ...
    def preferred_capabilities(self, workflow: str) -> set[Capability]: ...
    def plan_sources(self, manifest: Manifest, pack: ReferencePack | None) -> SourcePlan: ...
    def build(self, ctx: PipelineContext, manifest: Manifest) -> JobResult: ...
```

`src/fecreator/app.py`:
```python
from __future__ import annotations

import shutil
from pathlib import Path
from typing import cast

import fecreator.assets  # noqa: F401  registers the portrait plugin on import
import fecreator.providers  # noqa: F401  registers provider bridges
import fecreator.specs  # noqa: F401  registers target specs
from fecreator.assets.base import AssetPlugin, SourcePlan
from fecreator.contracts.diagnostics import Diagnostic
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import JobResult
from fecreator.core.atomicio import write_json_atomic
from fecreator.core.config import Settings
from fecreator.core.paths import safe_join
from fecreator.core.pipeline import PipelineContext
from fecreator.core.registry import ASSET_REGISTRY, PROVIDER_REGISTRY, SPEC_REGISTRY
from fecreator.jobs.approvals import ApprovalRecord, ApprovalStore
from fecreator.jobs.events import EventLog
from fecreator.jobs.model import Job, JobEvent
from fecreator.jobs.service import JobService
from fecreator.jobs.store import JobStore
from fecreator.references.store import ReferencePackStore
from fecreator.specs.base import TargetSpec


class FeCreatorApp:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        root = settings.data_root
        self._jobs = JobStore(root)
        self._events = EventLog(root)
        self._service = JobService(self._jobs, self._events)
        self._approvals = ApprovalStore(root)
        self._refs = ReferencePackStore(root)

    def list_assets(self) -> list[str]:
        return sorted(ASSET_REGISTRY.ids())

    def list_specs(self) -> list[str]:
        return sorted(SPEC_REGISTRY.ids())

    def list_providers(self) -> list[str]:
        return sorted(PROVIDER_REGISTRY.ids())

    def create_job(self, manifest: Manifest) -> Job:
        return self._service.create_job(manifest)

    def get_job(self, job_id: str) -> Job:
        return self._jobs.load(job_id)

    def cancel(self, job_id: str) -> Job:
        return self._service.cancel(job_id)

    def approve(self, job_id: str, stage: str, actor: str) -> ApprovalRecord:
        return self._approvals.approve(job_id, stage, actor)

    def reject(self, job_id: str, stage: str, actor: str, reason: str) -> ApprovalRecord:
        return self._approvals.reject(job_id, stage, actor, reason)

    def events(self, job_id: str) -> list[JobEvent]:
        return self._events.read(job_id)

    def validate(self, spec_id: str, package_dir: Path) -> list[Diagnostic]:
        return cast(TargetSpec, SPEC_REGISTRY.get(spec_id)).validate(package_dir)

    def plan_sources(self, job_id: str, out_dir: Path) -> SourcePlan:
        job = self._jobs.load(job_id)
        plugin = cast(AssetPlugin, ASSET_REGISTRY.get(job.manifest.asset_type))
        pack = self._refs.latest(job.manifest.character_ref_pack) if job.manifest.character_ref_pack else None
        plan = plugin.plan_sources(job.manifest, pack)
        out_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(out_dir / "source_plan.json", plan.model_dump(mode="json"))
        return plan

    def submit_sources(self, job_id: str, sources_dir: Path) -> Job:
        job = self._jobs.load(job_id)
        dest = safe_join(self._settings.data_root, "jobs", job_id, "submitted")
        dest.mkdir(parents=True, exist_ok=True)
        for item in sorted(Path(sources_dir).glob("*")):
            if item.is_file():
                shutil.copy2(item, dest / item.name)
        self._events.append(job_id, "sources_submitted", f"from {sources_dir}")
        return job

    def build(self, job_id: str) -> JobResult:
        job = self._jobs.load(job_id)
        plugin = cast(AssetPlugin, ASSET_REGISTRY.get(job.manifest.asset_type))
        workspace = safe_join(self._settings.data_root, "jobs", job_id)
        ctx = PipelineContext(job_id=job_id, workspace=workspace)
        return plugin.build(ctx, job.manifest)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/app/test_app.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/assets/__init__.py src/fecreator/assets/base.py src/fecreator/app.py tests/app/test_app.py
git commit -m "feat: add asset plugin base and FeCreatorApp facade

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 9: JSON CLI

**Files:**
- Create: `src/fecreator/interfaces/__init__.py`, `src/fecreator/interfaces/cli_json.py`, `docs/interfaces.md`
- Modify: `src/fecreator/cli.py` (dispatch to `cli_json` + keep `--version`)
- Test: `tests/interfaces/test_cli_json.py`

**Interfaces:**
- Consumes: `FeCreatorApp` (Task 8).
- Produces: `build_parser() -> argparse.ArgumentParser`; `run(app, argv, out) -> int` writing JSON to `out`. Commands: `list-assets`, `list-specs`, `list-providers`, `job create --manifest <path>`, `job status <id>`, `validate --spec <id> --path <dir>`.

- [ ] **Step 1: Write the failing test**

`tests/interfaces/test_cli_json.py`:
```python
import io
import json

from fecreator.app import FeCreatorApp
from fecreator.core.config import Settings
from fecreator.interfaces.cli_json import run


def _app(tmp_path):
    return FeCreatorApp(Settings(data_root=tmp_path))


def test_list_specs_json(tmp_path):
    out = io.StringIO()
    rc = run(_app(tmp_path), ["list-specs"], out)
    assert rc == 0
    assert "fe-gba-portrait-standard" in json.loads(out.getvalue())


def test_validate_missing_sheet(tmp_path):
    out = io.StringIO()
    rc = run(_app(tmp_path), ["validate", "--spec", "fe-gba-portrait-standard",
                              "--path", str(tmp_path)], out)
    codes = {d["code"] for d in json.loads(out.getvalue())}
    assert rc == 2 and "MISSING_SHEET" in codes


def test_job_create_and_status(tmp_path):
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({
        "asset_type": "portrait", "target_spec": "fe-gba-portrait-standard",
        "workflow": "text_to_portrait", "provider": "fake",
        "sources": [{"kind": "text", "ref": "hero"}]}))
    out = io.StringIO()
    run(_app(tmp_path), ["job", "create", "--manifest", str(manifest)], out)
    job_id = json.loads(out.getvalue())["id"]
    out2 = io.StringIO()
    run(_app(tmp_path), ["job", "status", job_id], out2)
    assert json.loads(out2.getvalue())["state"] == "created"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/interfaces/test_cli_json.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.interfaces.cli_json'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/interfaces/__init__.py`:
```python
```

`src/fecreator/interfaces/cli_json.py`:
```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TextIO

from fecreator.app import FeCreatorApp
from fecreator.contracts.diagnostics import has_errors
from fecreator.contracts.manifest import Manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fecreator")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list-assets")
    sub.add_parser("list-specs")
    sub.add_parser("list-providers")
    validate = sub.add_parser("validate")
    validate.add_argument("--spec", required=True)
    validate.add_argument("--path", required=True)
    job = sub.add_parser("job")
    job_sub = job.add_subparsers(dest="job_command", required=True)
    create = job_sub.add_parser("create")
    create.add_argument("--manifest", required=True)
    status = job_sub.add_parser("status")
    status.add_argument("job_id")
    return parser


def run(app: FeCreatorApp, argv: list[str], out: TextIO) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "list-assets":
        json.dump(app.list_assets(), out)
    elif args.command == "list-specs":
        json.dump(app.list_specs(), out)
    elif args.command == "list-providers":
        json.dump(app.list_providers(), out)
    elif args.command == "validate":
        diags = app.validate(args.spec, Path(args.path))
        json.dump([d.model_dump(mode="json") for d in diags], out)
        return 2 if has_errors(diags) else 0
    elif args.command == "job" and args.job_command == "create":
        manifest = Manifest.model_validate_json(Path(args.manifest).read_text())
        json.dump(app.create_job(manifest).model_dump(mode="json"), out)
    elif args.command == "job" and args.job_command == "status":
        json.dump(app.get_job(args.job_id).model_dump(mode="json"), out)
    return 0
```

`src/fecreator/cli.py` (replace Foundation minimal):
```python
from __future__ import annotations

import sys

from fecreator import __version__
from fecreator.app import FeCreatorApp
from fecreator.core.config import get_settings
from fecreator.interfaces import cli_json


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--version":
        print(f"fecreator {__version__}")
        return 0
    app = FeCreatorApp(get_settings())
    rc = cli_json.run(app, argv, sys.stdout)
    sys.stdout.write("\n")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
```

`docs/interfaces.md`:
```markdown
# Interfaces

All interfaces call `FeCreatorApp`. The MCP tool `build_asset` maps to `app.build`,
`validate_asset` to `app.validate`, `approve_stage`/`reject_stage` to `app.approve`/`app.reject`,
`cancel_job` to `app.cancel`, and job inspection uses `app.get_job` + `app.events`.

## CLI
`fecreator list-assets | list-specs | list-providers`
`fecreator job create --manifest <path>` · `fecreator job status <id>`
`fecreator validate --spec <id> --path <dir>` (exit 2 on validation errors)
`fecreator serve` launches the localhost web app.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/interfaces/test_cli_json.py -v`
Expected: PASS (3 passed). Also confirm `python -m fecreator.cli --version` still prints the version.

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/interfaces/__init__.py src/fecreator/interfaces/cli_json.py src/fecreator/cli.py docs/interfaces.md tests/interfaces/test_cli_json.py
git commit -m "feat: add json cli dispatch over FeCreatorApp

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 10: FastAPI HTTP API and static mount

**Files:**
- Create: `src/fecreator/interfaces/http_api.py`, `src/fecreator/interfaces/static.py`
- Test: `tests/interfaces/test_http_api.py`

**Interfaces:**
- Consumes: `FeCreatorApp`.
- Produces: `create_api(app: FeCreatorApp) -> FastAPI` with `GET /api/assets`, `/api/specs`, `/api/providers`, `POST /api/jobs`, `GET /api/jobs/{id}`, `POST /api/validate`; `web_dir() -> Path | None` and `mount_static(api) -> None`.

- [ ] **Step 1: Write the failing test**

`tests/interfaces/test_http_api.py`:
```python
from fastapi.testclient import TestClient

from fecreator.app import FeCreatorApp
from fecreator.core.config import Settings
from fecreator.interfaces.http_api import create_api


def _client(tmp_path):
    return TestClient(create_api(FeCreatorApp(Settings(data_root=tmp_path))))


def test_specs_endpoint(tmp_path):
    resp = _client(tmp_path).get("/api/specs")
    assert resp.status_code == 200
    assert "fe-gba-portrait-standard" in resp.json()


def test_create_and_get_job(tmp_path):
    client = _client(tmp_path)
    body = {"asset_type": "portrait", "target_spec": "fe-gba-portrait-standard",
            "workflow": "text_to_portrait", "provider": "fake",
            "sources": [{"kind": "text", "ref": "hero"}]}
    created = client.post("/api/jobs", json=body).json()
    fetched = client.get(f"/api/jobs/{created['id']}")
    assert fetched.status_code == 200 and fetched.json()["state"] == "created"


def test_get_missing_job_is_404(tmp_path):
    assert _client(tmp_path).get("/api/jobs/nope").status_code == 404


def test_validate_endpoint_reports_missing_sheet(tmp_path):
    resp = _client(tmp_path).post(
        "/api/validate", json={"spec_id": "fe-gba-portrait-standard", "package_dir": str(tmp_path)})
    assert resp.status_code == 200
    assert any(d["code"] == "MISSING_SHEET" for d in resp.json())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/interfaces/test_http_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.interfaces.http_api'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/interfaces/static.py`:
```python
from __future__ import annotations

from importlib import resources
from pathlib import Path


def web_dir() -> Path | None:
    try:
        target = resources.files("fecreator") / "_web"
    except ModuleNotFoundError:
        return None
    path = Path(str(target))
    return path if path.is_dir() else None
```

`src/fecreator/interfaces/http_api.py`:
```python
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from fecreator.app import FeCreatorApp
from fecreator.contracts.manifest import Manifest
from fecreator.interfaces.static import web_dir


class ValidateRequest(BaseModel):
    spec_id: str
    package_dir: str


def create_api(app: FeCreatorApp) -> FastAPI:
    api = FastAPI(title="FECreator")

    @api.get("/api/assets")
    def list_assets() -> list[str]:
        return app.list_assets()

    @api.get("/api/specs")
    def list_specs() -> list[str]:
        return app.list_specs()

    @api.get("/api/providers")
    def list_providers() -> list[str]:
        return app.list_providers()

    @api.post("/api/jobs")
    def create_job(manifest: Manifest) -> dict[str, object]:
        return app.create_job(manifest).model_dump(mode="json")

    @api.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, object]:
        try:
            return app.get_job(job_id).model_dump(mode="json")
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc

    @api.post("/api/validate")
    def validate(request: ValidateRequest) -> list[dict[str, object]]:
        diags = app.validate(request.spec_id, Path(request.package_dir))
        return [d.model_dump(mode="json") for d in diags]

    mount_static(api)
    return api


def mount_static(api: FastAPI) -> None:
    directory = web_dir()
    if directory is not None:
        api.mount("/", StaticFiles(directory=str(directory), html=True), name="web")
```

Note: `JobStore.load` raises `FileNotFoundError` when `job.json` is absent; the 404 handler relies on that. Confirm during Step 4.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/interfaces/test_http_api.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/interfaces/http_api.py src/fecreator/interfaces/static.py tests/interfaces/test_http_api.py
git commit -m "feat: add FastAPI http api and static web mount

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 11: WebSocket job progress

**Files:**
- Modify: `src/fecreator/interfaces/http_api.py` (register the WS route)
- Create: `src/fecreator/interfaces/websocket.py`
- Test: `tests/interfaces/test_websocket.py`

**Interfaces:**
- Consumes: `FeCreatorApp.events`.
- Produces: `register_ws(api: FastAPI, app: FeCreatorApp) -> None` adding `GET /ws/jobs/{id}` that sends a JSON snapshot of the job's events then closes.

- [ ] **Step 1: Write the failing test**

`tests/interfaces/test_websocket.py`:
```python
from fastapi.testclient import TestClient

from fecreator.app import FeCreatorApp
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.core.config import Settings
from fecreator.interfaces.http_api import create_api


def test_ws_streams_event_snapshot(tmp_path):
    app = FeCreatorApp(Settings(data_root=tmp_path))
    job = app.create_job(Manifest(asset_type="portrait", target_spec="fe-gba-portrait-standard",
                                   workflow="text_to_portrait", provider="fake",
                                   sources=(SourceSpec(kind="text", ref="hero"),)))
    client = TestClient(create_api(app))
    with client.websocket_connect(f"/ws/jobs/{job.id}") as ws:
        message = ws.receive_json()
    assert message["job_id"] == job.id
    assert any(e["kind"] == "created" for e in message["events"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/interfaces/test_websocket.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.interfaces.websocket'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/interfaces/websocket.py`:
```python
from __future__ import annotations

from fastapi import FastAPI, WebSocket

from fecreator.app import FeCreatorApp


def register_ws(api: FastAPI, app: FeCreatorApp) -> None:
    @api.websocket("/ws/jobs/{job_id}")
    async def job_events(websocket: WebSocket, job_id: str) -> None:
        await websocket.accept()
        events = [e.model_dump(mode="json") for e in app.events(job_id)]
        await websocket.send_json({"job_id": job_id, "events": events})
        await websocket.close()
```

Add to `http_api.create_api`, immediately before `mount_static(api)`:
```python
    from fecreator.interfaces.websocket import register_ws
    register_ws(api, app)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/interfaces/test_websocket.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/interfaces/websocket.py src/fecreator/interfaces/http_api.py tests/interfaces/test_websocket.py
git commit -m "feat: add websocket job event snapshot endpoint

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 12: MCP server tool surface

**Files:**
- Create: `src/fecreator/interfaces/mcp_server.py`
- Test: `tests/interfaces/test_mcp_server.py`

**Interfaces:**
- Consumes: `FeCreatorApp`, `mcp.server.fastmcp.FastMCP`.
- Produces: `TOOL_NAMES: list[str]` (12 tools), `make_handlers(app) -> dict[str, Callable]`, `build_mcp(app) -> FastMCP`. Handlers are thin wrappers over `FeCreatorApp`; the MCP layer holds no image logic.

- [ ] **Step 1: Write the failing test**

`tests/interfaces/test_mcp_server.py`:
```python
from fecreator.app import FeCreatorApp
from fecreator.core.config import Settings
from fecreator.interfaces.mcp_server import TOOL_NAMES, build_mcp, make_handlers


def _app(tmp_path):
    return FeCreatorApp(Settings(data_root=tmp_path))


def test_tool_names_match_design():
    assert set(TOOL_NAMES) == {
        "list_assets", "list_specs", "list_providers", "create_job", "get_job",
        "plan_sources", "submit_sources", "build_asset", "validate_asset",
        "approve_stage", "reject_stage", "cancel_job",
    }


def test_handlers_cover_all_tools(tmp_path):
    handlers = make_handlers(_app(tmp_path))
    assert set(handlers) == set(TOOL_NAMES)


def test_list_specs_handler_matches_app(tmp_path):
    app = _app(tmp_path)
    assert make_handlers(app)["list_specs"]() == app.list_specs()


def test_build_mcp_returns_server(tmp_path):
    server = build_mcp(_app(tmp_path))
    assert server is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/interfaces/test_mcp_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.interfaces.mcp_server'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/interfaces/mcp_server.py`:
```python
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from fecreator.app import FeCreatorApp
from fecreator.contracts.manifest import Manifest

TOOL_NAMES: list[str] = [
    "list_assets", "list_specs", "list_providers", "create_job", "get_job",
    "plan_sources", "submit_sources", "build_asset", "validate_asset",
    "approve_stage", "reject_stage", "cancel_job",
]


def make_handlers(app: FeCreatorApp) -> dict[str, Callable[..., object]]:
    return {
        "list_assets": lambda: app.list_assets(),
        "list_specs": lambda: app.list_specs(),
        "list_providers": lambda: app.list_providers(),
        "create_job": lambda manifest: app.create_job(Manifest.model_validate(manifest)).model_dump(mode="json"),
        "get_job": lambda job_id: app.get_job(job_id).model_dump(mode="json"),
        "plan_sources": lambda job_id, out_dir: app.plan_sources(job_id, Path(out_dir)).model_dump(mode="json"),
        "submit_sources": lambda job_id, sources_dir: app.submit_sources(job_id, Path(sources_dir)).model_dump(mode="json"),
        "build_asset": lambda job_id: app.build(job_id).model_dump(mode="json"),
        "validate_asset": lambda spec_id, path: [d.model_dump(mode="json") for d in app.validate(spec_id, Path(path))],
        "approve_stage": lambda job_id, stage, actor: app.approve(job_id, stage, actor).model_dump(mode="json"),
        "reject_stage": lambda job_id, stage, actor, reason: app.reject(job_id, stage, actor, reason).model_dump(mode="json"),
        "cancel_job": lambda job_id: app.cancel(job_id).model_dump(mode="json"),
    }


def build_mcp(app: FeCreatorApp) -> FastMCP:
    server = FastMCP("fecreator")
    for name, handler in make_handlers(app).items():
        server.tool(name=name)(handler)
    return server
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/interfaces/test_mcp_server.py -v`
Expected: PASS (4 passed). Then run the whole suite: `pytest -q` → all pass; `mypy src` → PASS; `ruff check .` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/interfaces/mcp_server.py tests/interfaces/test_mcp_server.py
git commit -m "feat: add MCP tool surface mapping to FeCreatorApp

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Self-review

- **Spec coverage (design §6, §9, §10, §15, §17):** four provider bridges with capability refusal (Tasks 1–5), no-shell command provider + redaction (Task 4), JSON report + reproducibility bundle + FEBuilder compat report + no-credential guarantee (Tasks 6–7), one `FeCreatorApp` facade (Task 8), and CLI/HTTP/WS/MCP interfaces that all call it (Tasks 9–12). CLI/MCP result equivalence is enforced because both call the same app methods; the design→MCP tool mapping is documented in `docs/interfaces.md`.
- **Placeholder scan:** no TBD/TODO; `command`/`mcp-client` register an explicitly unconfigured sentinel that refuses until configured (fail closed), not a placeholder.
- **Type consistency:** `Provider`, `GenRequest/GenResponse`, `AssetPlugin`, `SourcePlan/PromptPlan`, `FeCreatorApp` methods, and reporting/redaction signatures match master §4.11–4.14. `create_api`/`build_mcp`/`run` signatures are reused by the Web-Skills-Integration e2e and serve launcher.
- **Platform commands:** all commands are pytest/mypy/ruff, identical on Windows and POSIX; the `serve` launcher's platform-specific browser open is specified in Web-Skills-Integration.
