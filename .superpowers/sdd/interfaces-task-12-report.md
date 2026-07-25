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
