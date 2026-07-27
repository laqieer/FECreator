# Interfaces

Every interface stays thin and calls the same `FeCreatorApp` facade. The exact
frozen v1 operation inventory (and the compatibility policy that governs
changing it) is in [`v1-contract.md`](v1-contract.md); this page documents how
each adapter behaves.

## JSON CLI

- `fecreator --version`
- `fecreator list-assets`
- `fecreator list-specs`
- `fecreator list-providers`
- `fecreator job create --manifest <path>`
- `fecreator job status <id>`
- `fecreator job list`
- `fecreator job candidate <id>`
- `fecreator job approvals <id>`
- `fecreator job plan-sources <id>`
- `fecreator job validate <id>`
- `fecreator job artifact <id> <package-relative-path>`
- `fecreator job report <id>`
- `fecreator job bundle <id>`
- `fecreator job bundle-file <id> <bundle-relative-path>`
- `fecreator job approve <id> --actor <actor>`
- `fecreator job reject <id> --actor <actor> --reason <reason>`
- `fecreator job finalize <id>`
- `fecreator job retry <id> --actor <actor>`
- `fecreator job cancel <id>`
- `fecreator references list`
- `fecreator references history <pack-id>`
- `fecreator lineage get <asset-id>`
- `fecreator lineage ancestors <asset-id>`
- `fecreator lineage children <asset-id>`
- `fecreator plan-sources --job <id> --out <dir>`
- `fecreator submit-sources --job <id> --sources <dir>`
- `fecreator build --job <id>`
- `fecreator validate --spec <id> --path <dir>`
- `fecreator serve`

Facade routing:

- `list-assets` → `FeCreatorApp.list_assets()`
- `list-specs` → `FeCreatorApp.list_specs()`
- `list-providers` → `FeCreatorApp.list_providers()`
- `job create` → `FeCreatorApp.create_job()`
- `job status` → `FeCreatorApp.get_job()`
- `job list`, `candidate`, and `approvals` → `FeCreatorApp.list_jobs()`,
  `get_job_candidate()`, and `list_approval_decisions()`
- review actions → `FeCreatorApp.approve_review()`, `reject_review()`,
  `finalize_job()`, `retry_job()`, and `cancel()`
- final-output reads → `FeCreatorApp.validate_job()`, `read_job_artifact()`,
  `get_job_report()`, `list_bundle_entries()`, and `read_bundle_file()`
- reference and lineage commands → `FeCreatorApp.list_reference_packs()`,
  `list_reference_history()`, `get_lineage()`, `list_lineage_ancestors()`, and
  `list_lineage_children()`
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

The parser and dispatch table live in `fecreator.interfaces.cli_json` so the JSON
commands stay separate from `serve`, which is handled in `fecreator.cli` and is the
only non-JSON command.

## Local server

`fecreator serve` (also reachable as `python -m fecreator serve`) starts the local
workbench: it builds one `FeCreatorApp` from `Settings`, mounts `create_api()` — which
includes the WebSocket route and the packaged web assets — and hands the application to
Uvicorn on `Settings.host` and `Settings.port` (`FECREATOR_HOST`, default `127.0.0.1`,
and `FECREATOR_PORT`, default `8765`). The launcher refuses to start when
`FECREATOR_DATA_ROOT` is unset and when the configured host is not a loopback address,
so the workbench is never published on a public interface. Both failures write a
message to stderr and exit `2`. When the packaged assets are missing, the root route
returns the deterministic 503 explanation from `fecreator.interfaces.static` instead of
a broken page.

Browser end-to-end flows in `web/e2e` drive this launcher: the local project builds the
web app, starts `fecreator serve` on an isolated loopback port with its own temporary
`FECREATOR_DATA_ROOT`, and exercises create → provider build → queue selection → review
→ approve/reject → finalize → validate → lineage/report/bundle against the real API and
the deterministic `fake` provider. The demo project serves the `/FECreator/` static
build and asserts that no `/api` request, WebSocket, upload, or other non-static call is
made.

## HTTP API

`fecreator.interfaces.http_api.create_api()` exposes the GUI-facing HTTP facade:

- `GET /api/assets` → `FeCreatorApp.list_assets()`
- `GET /api/specs` → `FeCreatorApp.list_specs()`
- `GET /api/providers` → `FeCreatorApp.list_providers()`
- `POST /api/jobs` → `FeCreatorApp.create_job()`
- `GET /api/jobs` → `FeCreatorApp.list_jobs()`
- `GET /api/jobs/{job_id}` → `FeCreatorApp.get_job()`
- `GET /api/jobs/{job_id}/candidate` → `FeCreatorApp.get_job_candidate()`
- `GET /api/jobs/{job_id}/approvals` → `FeCreatorApp.list_approval_decisions()`
- `POST /api/jobs/{job_id}/plan-sources` → `FeCreatorApp.plan_job_sources()`
- `POST /api/jobs/{job_id}/sources` → `FeCreatorApp.submit_sources()`
- `POST /api/jobs/{job_id}/validate` → `FeCreatorApp.validate_job()`
- `GET /api/jobs/{job_id}/artifacts/{path}` → `FeCreatorApp.read_job_artifact()`
- `GET /api/jobs/{job_id}/report` → `FeCreatorApp.get_job_report()`
- `GET /api/jobs/{job_id}/bundle` and `/bundle/{path}` →
  `FeCreatorApp.list_bundle_entries()` and `read_bundle_file()`
- `POST /api/jobs/{job_id}/approve`, `/reject`, `/finalize`, `/retry`, and
  `/cancel` → review lifecycle facade actions
- `POST /api/validate` → `FeCreatorApp.validate()`
- `GET /api/references` and `/api/references/{pack_id}/history` → reference reads
- `GET /api/lineage/{asset_id}`, `/ancestors`, and `/children` → lineage reads

The HTTP adapter validates request envelopes, normalizes path/id inputs, converts
expected failures into deterministic diagnostic responses, and otherwise leaves job,
validation, approval, and lineage orchestration inside `FeCreatorApp` and the domain
layers behind it. Multipart source uploads are bounded twice: an ASGI request-body
limiter caps the raw multipart request at 33 MiB before Starlette buffers any part, so
chunked, missing, or understated `Content-Length` bodies cannot exceed it, and the
route then streams each part into an application-owned unique staging directory with
an 8 MiB per-file and 32 MiB total budget. Upload names are rejected when they are
unsafe, duplicate, case-colliding, Windows reserved device names, or end with a dot or
space, staging is resolved with `safe_join()`, and staging is removed before the
response. Artifact reads serve only `package/` and `candidate/package/` files;
`job.json`, `manifest.json`, event and approval records, reports, and bundle internals
have dedicated sanitized endpoints and are never returned as raw artifact bytes.
Artifact and bundle paths must be POSIX-relative, workspace-contained regular files;
backslash-separated paths, symlinks, and reparse points are refused. Reference reads
map corrupt or invalid stored pack ids to structured `CORRUPT_REFERENCE_PACK`
diagnostics instead of a bare 500.

Two store failures are mapped once at each adapter's boundary rather than in
every handler, because every action that touches a job routes through the same
store: `LockTimeoutError` becomes `STORE_LOCK_TIMEOUT` and `JobCorruptionError`
becomes `CORRUPT_JOB` (both HTTP `409`, CLI exit `2`, MCP `isError`). The
corruption diagnostic reports the offending job id from the exception's
structured metadata; neither ever echoes the exception text, which quotes
absolute store paths. See `docs/v1-contract.md` §10 for the recovery procedure.

## MCP server

`fecreator.interfaces.mcp_server.build_mcp()` registers these deterministic MCP tools:

- `list_assets` → `FeCreatorApp.list_assets()`
- `list_specs` → `FeCreatorApp.list_specs()`
- `list_providers` → `FeCreatorApp.list_providers()`
- `list_jobs` → `FeCreatorApp.list_jobs()`
- `create_job` → `FeCreatorApp.create_job()`
- `get_job` → `FeCreatorApp.get_job()`
- `get_job_candidate` and `list_approval_decisions` → candidate/review reads
- `plan_sources` → `FeCreatorApp.plan_sources()`
- `plan_job_sources` → `FeCreatorApp.plan_job_sources()`
- `submit_sources` → `FeCreatorApp.submit_sources()`
- `build_asset` → `FeCreatorApp.build()`
- `validate_asset` → `FeCreatorApp.validate()`
- `validate_job`, `read_job_artifact`, `get_job_report`, `list_bundle_entries`, and
  `read_bundle_file` → final-output reads
- `list_reference_packs`, `list_reference_history`, `get_lineage`,
  `list_lineage_ancestors`, and `list_lineage_children` → immutable history reads
- `approve_stage` → `FeCreatorApp.approve()`
- `reject_stage` → `FeCreatorApp.reject()`
- `approve_review`, `reject_review`, `finalize_job`, and `retry_job` → review lifecycle
- `cancel_job` → `FeCreatorApp.cancel()`

FastMCP publishes the exact `Manifest` input schema for `create_job` while leaving
manifest validation inside the handler, so malformed payloads return the standard
redacted `INVALID_MANIFEST` diagnostic instead of a pre-handler FastMCP/Pydantic
`ToolError`, even when callers send string or list manifest values. Every tool also
publishes typed `outputSchema` metadata with exact success/error alternatives: every
branch requires the `ok` discriminator, success payloads also require their
tool-specific fields, and expected/domain failures are structured MCP errors with
`isError=true` plus redacted `{"ok": false, "diagnostics": [...]}` content instead of
raw tracebacks or absolute paths. The MCP layer does not add image logic or bypass
validation, approvals, lineage, or job lookup safeguards; it only normalizes ids,
validates manifest input, sanitizes payloads, and forwards to `FeCreatorApp`.
Artifact and bundle file payloads use deterministic base64 envelopes; `content_base64`
is an explicitly opaque transport field that is never redacted, while every other
string in the payload — including diagnostic text and paths — is still sanitized.
Report and diagnostic payloads are sanitized before they are returned.

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
