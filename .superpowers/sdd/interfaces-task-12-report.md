# Interfaces Task 12 Report

Status: done

Summary:
- Added `src/fecreator/interfaces/mcp_server.py` with the 12-task MCP tool surface over `FeCreatorApp` using the official `FastMCP` SDK.
- Registered deterministic tool names for listing assets/specs/providers plus job creation, lookup, source planning/submission, build, validation, approvals, rejection, and cancellation.
- Kept handlers thin: they normalize/verify job ids, validate manifest payloads, sanitize JSON output, and forward into `FeCreatorApp` without adding image logic.
- Expected/domain failures now return structured `{ "ok": false, "diagnostics": [...] }` payloads with redacted details instead of raw tracebacks.
- Documented the MCP mappings and failure contract in `docs/interfaces.md`.

Verification:
- `.venv\Scripts\python.exe -m pytest tests\interfaces\test_mcp_server.py tests\app\test_app.py -v`
- `.venv\Scripts\python.exe -m ruff check .`
- `.venv\Scripts\python.exe -m ruff format --check .`
- `.venv\Scripts\python.exe -m mypy src`

Concerns:
- The MCP layer now enforces job existence before `approve_stage` and `reject_stage`; the underlying `FeCreatorApp.approve()` / `reject()` methods still do not enforce that invariant for non-MCP callers.

---

## 2026-07-25 blocking-review follow-up

Status: done

Summary:
- Switched the FastMCP tool registration to official structured-output patterns using
  typed `CallToolResult` annotations instead of `structured_output=False`.
- Changed `create_job` to expose the exact `Manifest` schema through FastMCP rather
  than an open-ended `dict[str, object]`.
- Added typed output envelopes for all 12 tools so `outputSchema` is published for
  each tool and remains directly testable through `build_mcp()` / `make_handlers()`.
- Converted expected MCP domain failures into structured redacted MCP errors with
  `isError=true`, including regressions for missing reference packs, build failures,
  and unknown specs without raw absolute-path leakage.
- Kept the interface layer thin: handlers still normalize ids, sanitize payloads, and
  forward to `FeCreatorApp` without adding domain/image logic.

Verification:
- Red: `.venv\Scripts\python.exe -m pytest tests\interfaces\test_mcp_server.py -q`
- Green: `.venv\Scripts\python.exe -m pytest tests\interfaces\test_mcp_server.py -q`
- Final tests: `.venv\Scripts\python.exe -m pytest tests\interfaces tests\app\test_app.py -q`
- Final lint: `.venv\Scripts\python.exe -m ruff check .`
- Final format: `.venv\Scripts\python.exe -m ruff format --check .`
- Final typing: `.venv\Scripts\python.exe -m mypy src`

Concerns:
- `tests\interfaces tests\app\test_app.py` still emits the pre-existing FastAPI /
  Starlette deprecation warning about `starlette.testclient`; no new warnings were
  introduced by the MCP changes.

---

## 2026-07-25 remaining-schema follow-up

Status: done

Summary:
- Kept the 12 MCP tool names and thin `FeCreatorApp` facade routing unchanged.
- Switched `create_job` to accept a handler-owned manifest dict while overriding the
  published FastMCP `inputSchema` to the exact `Manifest` JSON schema, so malformed
  payloads now return structured redacted `INVALID_MANIFEST` results instead of
  pre-handler `ToolError` validation dumps.
- Replaced nullable payload envelopes with exact output alternatives: each success
  shape now has its required payload field (`job`, `source_plan`, `job_result`,
  `approval`, or `diagnostics`) and all handled failures share `ok: false` plus
  `diagnostics`.
- Added regression coverage for invalid `create_job` payloads, exact schema exposure,
  and every output-schema family exposed by `list_tools()`.

Verification:
- Red: `.venv\Scripts\python.exe -m pytest -q tests\interfaces\test_mcp_server.py`
- Green: `.venv\Scripts\python.exe -m pytest -q tests\interfaces\test_mcp_server.py`
- Final tests: `.venv\Scripts\python.exe -m pytest -q tests\interfaces tests\app`
- Final lint: `.venv\Scripts\python.exe -m ruff check .`
- Final format: `.venv\Scripts\python.exe -m ruff format --check .`
- Final typing: `.venv\Scripts\python.exe -m mypy src`

Concerns:
- The remaining verification scope still inherits the existing FastAPI / Starlette
  `starlette.testclient` deprecation warning; the MCP schema/error follow-up does not
  add new warnings or known open failures.

---

## 2026-07-25 final-review follow-up

Status: done

Summary:
- Changed the `create_job` handler input annotation from `dict[str, object]` to
  `object` while keeping the published FastMCP `Manifest` schema exact, so raw JSON
  string/list manifest values now reach `Manifest.model_validate()` and return the
  redacted `INVALID_MANIFEST` envelope instead of a leaked FastMCP `ToolError`.
- Added `call_tool()` regressions for string path-like and list manifest inputs to
  prove the structured error path stays redacted and never exposes `input_value`.
- Removed success-envelope defaults from every `ok: Literal[True]` discriminator and
  instantiated them explicitly so published JSON Schema now requires `ok` on every
  success/error branch while still requiring the success payload field.
- Updated the interface documentation to reflect the exact `create_job` manifest
  behavior and the required `ok` discriminators in all MCP tool envelopes.

Verification:
- Red: `.venv\Scripts\python.exe -m pytest -q tests\interfaces\test_mcp_server.py`
- Green: `.venv\Scripts\python.exe -m pytest -q tests\interfaces\test_mcp_server.py`
- Final tests: `.venv\Scripts\python.exe -m pytest -q tests\interfaces tests\app`
- Final lint: `.venv\Scripts\python.exe -m ruff check .`
- Final format: `.venv\Scripts\python.exe -m ruff format --check .`
- Final typing: `.venv\Scripts\python.exe -m mypy src`

Concerns:
- Final verification still emits the pre-existing FastAPI / Starlette
  `starlette.testclient` deprecation warning; this follow-up does not add new warnings
  or open issues.
