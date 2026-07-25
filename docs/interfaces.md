# Interfaces

Every interface stays thin and calls the same `FeCreatorApp` facade.

## JSON CLI

- `fecreator --version`
- `fecreator list-assets`
- `fecreator list-specs`
- `fecreator list-providers`
- `fecreator job create --manifest <path>`
- `fecreator job status <id>`
- `fecreator plan-sources --job <id> --out <dir>`
- `fecreator submit-sources --job <id> --sources <dir>`
- `fecreator build --job <id>`
- `fecreator validate --spec <id> --path <dir>`

Facade routing:

- `list-assets` → `FeCreatorApp.list_assets()`
- `list-specs` → `FeCreatorApp.list_specs()`
- `list-providers` → `FeCreatorApp.list_providers()`
- `job create` → `FeCreatorApp.create_job()`
- `job status` → `FeCreatorApp.get_job()`
- `plan-sources` → `FeCreatorApp.plan_sources()`
- `submit-sources` → `FeCreatorApp.submit_sources()`
- `build` → `FeCreatorApp.build()`
- `validate` → `FeCreatorApp.validate()`

JSON commands write one compact JSON document to stdout followed by a single newline
from `fecreator.cli`. `validate` exits with status `2` when any returned diagnostic
has severity `error`; `build` also exits `2` when the returned `JobResult.ok` is
`false`. Expected manifest, lookup, source-handoff, and build failures emit compact
JSON diagnostics and exit `2`; the other commands exit `0` on success. Long options are
not abbreviated anywhere in the parser tree. `--version` and parser help do not require
runtime settings; command execution requires `FECREATOR_DATA_ROOT`.

The parser and dispatch table live in `fecreator.interfaces.cli_json` so later tasks
can extend the CLI with `serve` without moving application logic out of
`FeCreatorApp`.

## HTTP API

`fecreator.interfaces.http_api.create_api()` exposes the GUI-facing HTTP facade:

- `GET /api/assets` → `FeCreatorApp.list_assets()`
- `GET /api/specs` → `FeCreatorApp.list_specs()`
- `GET /api/providers` → `FeCreatorApp.list_providers()`
- `POST /api/jobs` → `FeCreatorApp.create_job()`
- `GET /api/jobs/{job_id}` → `FeCreatorApp.get_job()`
- `POST /api/validate` → `FeCreatorApp.validate()`

The HTTP adapter validates request envelopes, normalizes path/id inputs, converts
expected failures into deterministic diagnostic responses, and otherwise leaves job,
validation, approval, and lineage orchestration inside `FeCreatorApp` and the domain
layers behind it.

## MCP server

`fecreator.interfaces.mcp_server.build_mcp()` registers these deterministic MCP tools:

- `list_assets` → `FeCreatorApp.list_assets()`
- `list_specs` → `FeCreatorApp.list_specs()`
- `list_providers` → `FeCreatorApp.list_providers()`
- `create_job` → `FeCreatorApp.create_job()`
- `get_job` → `FeCreatorApp.get_job()`
- `plan_sources` → `FeCreatorApp.plan_sources()`
- `submit_sources` → `FeCreatorApp.submit_sources()`
- `build_asset` → `FeCreatorApp.build()`
- `validate_asset` → `FeCreatorApp.validate()`
- `approve_stage` → `FeCreatorApp.approve()`
- `reject_stage` → `FeCreatorApp.reject()`
- `cancel_job` → `FeCreatorApp.cancel()`

FastMCP publishes the exact `Manifest` input schema for `create_job` while leaving
manifest validation inside the handler, so malformed payloads return the standard
redacted `INVALID_MANIFEST` diagnostic instead of a pre-handler FastMCP/Pydantic
`ToolError`, even when callers send string or list manifest values. All 12 tools also
publish typed `outputSchema` metadata with exact success/error alternatives: every
branch requires the `ok` discriminator, success payloads also require their
tool-specific fields (`asset_ids`, `job`, `source_plan`, `job_result`, `approval`, or
`diagnostics`), and expected/domain failures are structured MCP errors with
`isError=true` plus redacted `{"ok": false, "diagnostics": [...]}` content instead of
raw tracebacks or absolute paths. The MCP layer does not add image logic or bypass
validation, approvals, lineage, or job lookup safeguards; it only normalizes ids,
validates manifest input, sanitizes payloads, and forwards to `FeCreatorApp`.

submit_sources is the explicit source-handoff tool for manual/agent-owned files, not a
required step for providers that generate their own intermediates. For manual-provider
workflows, create the job with provider `manual` before `plan_sources` or
`submit_sources`; callers cannot rewrite an existing job manifest to flip it into
manual mode after creation. build_asset already runs target-spec validation for the job
result, and validate_asset remains available for standalone validation of an existing
package directory when the caller already knows its path. Repeated builds surface the
same redacted `BUILD_ASSET_FAILED` diagnostic envelope as the CLI instead of bubbling a
raw `InvalidTransitionError`, and the manual source-handoff equivalence tests exercise
`plan_sources`, `submit_sources`, and `build_asset` through MCP without seeding state
through the CLI.
