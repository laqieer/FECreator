# FECreator repository instructions

FECreator is a local-first, provider-neutral workbench for creating Fire Emblem GBA
portraits. Keep changes within the portrait-focused v1 scope in
`docs/product-statement.md`; this is not a ROM editor or a hosted generation service.

## Build, test, and lint commands

Run commands from the repository root. Supported runtimes are Python 3.11-3.13 and
Node.js 20.19-24.

```powershell
# Install Python and JavaScript dependencies
python -m pip install -e ".[dev]"
npm ci

# Install the local GitGuardian pre-commit hook
pre-commit install

# Python checks used by CI
ruff check .
ruff format --check .
mypy src
pytest -q

# One Python test
pytest -q tests/core/test_pipeline.py::test_pipeline_stops_after_failure

# Web checks used by CI
npm run -w @laqieer/fecreator-web typecheck
npm run -w @laqieer/fecreator-web lint
npm run -w @laqieer/fecreator-web test

# One Vitest test
npm run -w @laqieer/fecreator-web test -- src/config/base.test.ts -t "demo mode resolves the project pages base path"
```

Maintainers configure the CI scanner with
`gh secret set GITGUARDIAN_API_KEY --repo laqieer/FECreator`; the command prompts for
the value securely. Keep the key only in the environment or GitHub Actions secrets.

Build the web app before building the Python distribution:

```powershell
# Local app: root-relative assets, written into src/fecreator/_web
npm run -w @laqieer/fecreator-web build
python -m build

# GitHub Pages demo: assets use the /FECreator/ base path
npm run -w @laqieer/fecreator-web build:demo
```

`hatch_build.py` deliberately rejects non-editable Python builds when
`src/fecreator/_web/index.html` is missing. The generated `_web` directory is ignored
and should not be committed. The root `package-lock.json` is authoritative for the npm
workspace.

## High-level architecture

- `src/fecreator/contracts` defines the Pydantic v2 wire/domain models.
  `schemas/*.schema.json` are committed exports of selected public contracts, while
  `web/src/api/types.ts` is the TypeScript mirror used by the UI.
- `src/fecreator/core`, `jobs`, `lineage`, and `references` provide local persistence:
  path containment, hashing, atomic writes, cross-platform sidecar locks, optimistic
  job revisions, append-only event/approval records, and immutable lineage/reference
  revisions.
- `src/fecreator/imaging` contains deterministic NumPy/OpenCV processing. Pillow is
  kept at image decode/encode and PNG metadata boundaries. The portrait asset workflow
  lives under `assets/portrait`; the concrete `fe-gba-portrait-standard` layout,
  palette, assembly, and fail-closed validation live under
  `specs/fire_emblem/gba/portrait_standard`.
- Providers implement the protocol in `providers/base.py`. Built-ins cover manual
  submission, deterministic fake output, versioned JSON over an external command, and
  a configured MCP transport. Reporting code creates redacted machine-readable output
  and reproducibility bundles.
- The accepted architecture keeps CLI/HTTP/WebSocket/MCP adapters thin and routes them
  through one application/job service; image processing and validation belong in the
  domain layers, not interface adapters. `docs/superpowers/plans/` records design and
  implementation intent and can be ahead of `main`, so verify planned paths against
  current source and tests.
- The React entry point selects `appMode()` and injects an `ApiClient` plus
  `JobEventSource` through `createComposition()`. Local mode uses HTTP and WebSocket
  adapters. Demo mode uses deterministic in-memory fixtures and timers and must make no
  fetch, WebSocket, upload, persistence, or filesystem calls.
- Python tests mirror package areas under `tests/`. Web tests are colocated as
  `*.test.ts`/`*.test.tsx`; shared component setup is in `web/src/test/util.tsx`.

## Repository-specific conventions

- Public contract/value models normally use
  `ConfigDict(extra="forbid", frozen=True)`, tuples instead of mutable lists, and
  `freeze_mapping()` for mapping fields. Serialize persisted or transported models
  with `model_dump(mode="json")` and validate input with `model_validate()`.
- When a Python public contract changes, regenerate `schemas/` with
  `export_schemas(Path("schemas"))`, update `web/src/api/types.ts` when the UI consumes
  it, and run `tests/contracts/test_schemas.py` plus
  `web/src/api/types.contract.test.ts`.
- Do not bypass `safe_join()`, storage-ID normalization, atomic I/O helpers, or store
  locks when writing job, lineage, reference, event, or approval data. Store corruption,
  stale revisions, invalid transitions, budget overruns, and unsafe paths fail loudly;
  do not turn them into success-shaped fallbacks.
- Registries reject duplicate IDs. Built-in provider and target-spec modules use
  guarded import-time registration, so preserve idempotent imports when adding a
  built-in implementation.
- Provider workflows declare required capabilities and refuse missing capabilities
  instead of silently downgrading. External command execution stays `shell=False`,
  receives versioned JSON on stdin, uses the allowlisted environment, bounds/redacts
  diagnostics, and accepts artifacts only from the job workspace. Apply the same path,
  size, and redaction rules to MCP responses.
- FE GBA package validation is intentionally strict: canonical output is one opaque
  128x112 indexed PNG, at most 16 GBA-snapped colors with background at index 0, and a
  matching same-basename JASC palette. Contract violations are errors, not warnings.
- Keep demo/local behavior separated at the composition boundary. Changes to demo mode
  must remain deterministic and offline; changes to Vite base-path logic must preserve
  `/` for local builds and `/FECreator/` for demo builds.
- Do not add literal JWT- or AWS-key-shaped fixtures. Construct synthetic credential
  shapes at runtime through `tests/fixtures/synthetic_secrets.py`; the regression test
  scans tracked text files. Preserve CI's all-branch `push` trigger for secret scanning
  and keep Pages deployment gated to successful `main` builds.
- Python uses Ruff with a 100-character line limit and strict mypy for `src`. The web
  workspace uses strict TypeScript and ESLint; Prettier is installed but is not a CI
  command.
