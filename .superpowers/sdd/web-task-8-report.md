# Web Task 8 Report

Status: done

Summary:
- Added `skills/fecreator/SKILL.md` as a thin FECreator orchestration skill with valid
  frontmatter, discovery-oriented description, portrait-v1 guardrails, and exact CLI/MCP
  surface references.
- Added `skills/fecreator/references/capability-gaps.md` to document the current JSON CLI
  limits plus provider capability requirements without inventing missing commands.
- Added `skills/fecreator/agents/portrait-neutral.md` with a manifest skeleton and a
  neutral-portrait flow that gathers intent, builds manifests, uses real tools, and keeps
  review, validation, and lineage in the loop.
- Added `tests/integration/test_skills.py` to lock the skill shape: required files,
  valid frontmatter, real CLI examples parsed from `build_parser()`, real MCP tool names
  checked against `TOOL_NAMES`, and explicit portrait-v1 guardrails.

Verification:
- Red: `.venv\Scripts\python.exe -m pytest tests\integration\test_skills.py -q`
- Green: `.venv\Scripts\python.exe -m pytest tests\integration\test_skills.py -q`
- Final tests: `.venv\Scripts\python.exe -m pytest tests\integration\test_skills.py tests\interfaces\test_cli_json.py tests\interfaces\test_mcp_server.py -q`
- Final lint: `.venv\Scripts\python.exe -m ruff check tests\integration\test_skills.py`
- Final format: `.venv\Scripts\python.exe -m ruff format --check tests\integration\test_skills.py`
- Final typing: `.venv\Scripts\python.exe -m mypy src`

Concerns:
- The JSON CLI still intentionally exposes only discovery, job-create/status, and
  validation commands. The new skill explains that full source planning, submission,
  build, approval, rejection, and cancellation must go through MCP until the CLI grows.

---

## 2026-07-25 documentation findings follow-up

Status: done

Summary:
- Clarified that `submit_sources` is only for manual-provider or explicit source-handoff
  flows, not the generic next step after `plan_sources` for generating providers.
- Removed the misleading automatic `build_asset` → `validate_asset` sequence from the
  skill docs and documented that `build_asset` already performs fail-closed target
  validation while `validate_asset` is for a known package directory.
- Strengthened `tests/integration/test_skills.py` to lock the submit/handoff guidance
  and the build-versus-standalone-validation distinction across the skill and interface
  docs.

Verification:
- Red: `.venv\Scripts\python.exe -m pytest tests\integration\test_skills.py -q`
- Green: `.venv\Scripts\python.exe -m pytest tests\integration\test_skills.py -q`
- Final tests: `.venv\Scripts\python.exe -m pytest tests\integration\test_skills.py tests\interfaces\test_cli_json.py tests\interfaces\test_mcp_server.py tests\app\test_app.py::test_submit_sources_copies_files_and_records_event tests\app\test_app.py::test_build_validate_approvals_cancel_and_events -q`
- Final lint: `.venv\Scripts\python.exe -m ruff check tests\integration\test_skills.py`
- Final format: `.venv\Scripts\python.exe -m ruff format --check tests\integration\test_skills.py`

Concerns:
- The JSON CLI still intentionally stops at discovery, job create/status, and
  standalone validation. Manual file handoff, job builds, approvals, and cancellation
  remain MCP-only flows for now.
