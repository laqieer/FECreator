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
