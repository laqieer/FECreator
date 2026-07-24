# Interfaces

All interfaces call `FeCreatorApp`. The MCP tool `build_asset` maps to `app.build`,
`validate_asset` to `app.validate`, `approve_stage`/`reject_stage` to `app.approve`/`app.reject`,
`cancel_job` to `app.cancel`, and job inspection uses `app.get_job` + `app.events`.

## CLI
`fecreator list-assets | list-specs | list-providers`
`fecreator job create --manifest <path>` · `fecreator job status <id>`
`fecreator validate --spec <id> --path <dir>` (exit 2 on validation errors)
`fecreator serve` launches the localhost web app.
