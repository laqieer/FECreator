# Interfaces

All interfaces call `FeCreatorApp`. No imaging or business logic lives in the interface layer.

## CLI (JSON stdout only)

```
fecreator list-assets | list-specs | list-providers
fecreator job create --manifest <path>
fecreator job status <id> | cancel <id> | resume <id>
fecreator plan-sources <id>
fecreator submit-sources <id> --from <dir>   # trusted-local; not via HTTP/MCP
fecreator generate <id>
fecreator build <id>
fecreator inspect <id>
fecreator validate --spec <id> --path <dir>  # trusted-local; not via HTTP/MCP
fecreator approve <id> --stage <s> --actor <a>
fecreator reject  <id> --stage <s> --actor <a> --reason <r>
fecreator serve [--host 127.0.0.1] [--port N]
```

Exit codes: 0 success; 2 validation-errors; 3 invalid-state; 4 not-found; 5 internal-error.
Errors are JSON on stderr; success payloads are JSON on stdout.

## HTTP API

All endpoints accept / return JSON. Domain errors map to 400/404/409/422; unexpected errors
return `{"detail": "internal error"}` with 500.

```
GET  /api/assets | /api/specs | /api/providers
POST /api/jobs                              → creates job
GET  /api/jobs/{id}                         → job state
GET  /api/jobs/{id}/inspect                 → detailed info
POST /api/jobs/{id}/plan-sources
POST /api/jobs/{id}/generate
POST /api/jobs/{id}/build
POST /api/jobs/{id}/validate  body: {"spec_id":"…"}
POST /api/jobs/{id}/approve   body: {"stage":"…","actor":"…"}
POST /api/jobs/{id}/reject    body: {"stage":"…","actor":"…","reason":"…"}
POST /api/jobs/{id}/cancel
WS   /ws/jobs/{id}            → incremental event stream until terminal state
```

No arbitrary `package_dir` paths accepted via HTTP.

## MCP (14 tools)

`list_assets`, `list_specs`, `list_providers`, `create_job`, `get_job`,
`plan_sources`, `submit_sources`, `generate_asset`, `build_asset`, `validate_asset`,
`inspect_asset`, `approve_stage`, `reject_stage`, `cancel_job`.

All tools use the same `FeCreatorApp` methods as the CLI/HTTP layer.
Errors are returned as `{"error": "<CODE>", "message": "…"}` dicts, not raised.
No raw server paths, secrets, or tracebacks are exposed.
