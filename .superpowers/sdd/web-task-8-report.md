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
