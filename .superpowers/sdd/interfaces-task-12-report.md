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
