# Interfaces

Every interface stays thin and calls the same `FeCreatorApp` facade.

## JSON CLI

- `fecreator --version`
- `fecreator list-assets`
- `fecreator list-specs`
- `fecreator list-providers`
- `fecreator job create --manifest <path>`
- `fecreator job status <id>`
- `fecreator validate --spec <id> --path <dir>`

Facade routing:

- `list-assets` → `FeCreatorApp.list_assets()`
- `list-specs` → `FeCreatorApp.list_specs()`
- `list-providers` → `FeCreatorApp.list_providers()`
- `job create` → `FeCreatorApp.create_job()`
- `job status` → `FeCreatorApp.get_job()`
- `validate` → `FeCreatorApp.validate()`

JSON commands write one compact JSON document to stdout followed by a single newline
from `fecreator.cli`. `validate` exits with status `2` when any returned diagnostic
has severity `error`, and expected manifest/lookup failures also emit compact JSON
diagnostics and exit `2`; the other commands exit `0` on success. Long options are not
abbreviated anywhere in the parser tree. `--version` and parser help do not require
runtime settings; command execution requires `FECREATOR_DATA_ROOT`.

The parser and dispatch table live in `fecreator.interfaces.cli_json` so later tasks
can extend the CLI with `plan-sources`, `submit-sources`, `build`, and `serve`
without moving application logic out of `FeCreatorApp`.

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
`ToolError`. All 12 tools also publish typed `outputSchema` metadata with exact
success/error alternatives: success payloads require their tool-specific fields
(`asset_ids`, `job`, `source_plan`, `job_result`, `approval`, or `diagnostics`), while
expected/domain failures are structured MCP errors with `isError=true` and redacted
`{"ok": false, "diagnostics": [...]}` content instead of raw tracebacks or absolute
paths. The MCP layer does not add image logic or bypass validation, approvals,
lineage, or job lookup safeguards; it only normalizes ids, validates manifest input,
sanitizes payloads, and forwards to `FeCreatorApp`.
