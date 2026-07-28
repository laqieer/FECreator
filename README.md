# FECreator

Local-first, agent-neutral, provider-neutral Fire Emblem **portrait** creation
workbench with deterministic imaging, immutable jobs/lineage, human review, and a
`fe-gba-portrait-standard` export compatible with FEBuilderGBA (file-based, ROM-free).

See `docs/product-statement.md` for scope and `docs/architecture.md` for the module map.
The frozen v1 public surface — contracts, HTTP routes, CLI commands, MCP tools,
capability semantics, and the compatibility policy — is in
[`docs/v1-contract.md`](docs/v1-contract.md).
FEBuilderGBA compatibility evidence levels (mandatory deterministic proof, optional
CLI validation, opt-in local ROM checks) are documented in
[`docs/febuilder-interop.md`](docs/febuilder-interop.md).

## Getting started

Supported runtimes are Python 3.11-3.13 and Node.js 20.19-24. Install the
published Python package from [PyPI](https://pypi.org/project/fecreator/):

```powershell
python -m pip install fecreator==0.1.0
```

For development, run everything from the repository root.

```powershell
python -m pip install -e ".[dev]"
npm ci
pre-commit install
```

Build the web bundle before packaging or serving; the generated
`src/fecreator/_web` directory is ignored and must never be committed.

```powershell
# Local app: root-relative assets, written into src/fecreator/_web
npm run -w @laqieer/fecreator-web build
python -m build

# GitHub Pages demo: assets use the /FECreator/ base path
npm run -w @laqieer/fecreator-web build:demo
```

Run the local workbench (loopback only, `FECREATOR_DATA_ROOT` required):

```powershell
$env:FECREATOR_DATA_ROOT = "$PWD\data"
fecreator serve
```

## Checks

```powershell
# Python
ruff check .
ruff format --check .
mypy src
pytest -q

# Web
npm run -w @laqieer/fecreator-web typecheck
npm run -w @laqieer/fecreator-web lint
npm run -w @laqieer/fecreator-web test

# Browser end-to-end flows (builds the local and demo bundles first)
npx playwright install chromium
npm run -w @laqieer/fecreator-web test:e2e
```

Set `FECREATOR_PYTHON` when the interpreter that has FECreator installed is not
`python`; a path containing spaces is quoted automatically, and an already quoted
value is accepted as-is.

CI runs `python`, `web`, `browser`, `package`, `febuilder-interop`, and
`secret-scan` on every push and pull request. The GitHub Pages deployment is
limited to successful `main` pushes and depends on all six. The optional external
FEBuilder-compatible check runs only when the `FEBUILDER_CLI` repository variable
is set; no gate ever requires a ROM.

## Releasing

Releases go to [PyPI](https://pypi.org/project/fecreator/) through Trusted
Publishing (OIDC); no PyPI API token exists in this repository. Pushing a
`v*.*.*` tag builds the distributions in an
unprivileged job that checks out `refs/tags/<tag>`, then publishes them from a
separate `pypi` environment job that a required reviewer must approve and that
only `v*.*.*` tags may deploy to. A manual re-run is dispatched on the tag
itself (`gh workflow run publish.yml --ref v0.1.0`).
See [`docs/pypi-publishing.md`](docs/pypi-publishing.md) for the trust boundary,
the exact pending-publisher fields, and the required environment protection.

## Live demo

A static, sample-data demo is published to GitHub Pages:

**<https://laqieer.github.io/FECreator/>**

The demo runs entirely in the browser with built-in synthetic data. It **cannot**
generate, validate, upload, or save real assets, makes no HTTP or WebSocket calls,
and resets whenever the page is reloaded. See
[`docs/github-pages-demo.md`](docs/github-pages-demo.md) for build modes and
limitations.

## Security

Secrets are guarded by layered scanning: a local
[`ggshield`](https://github.com/GitGuardian/ggshield) pre-commit hook, a
`secret-scan` CI job on pushes and internal PRs, and the GitGuardian GitHub App
for fork PRs and full history. Test fixtures that need credential *shapes* are
assembled at runtime (never stored as literals), and a regression test blocks
any literal JWT/AWS-key from re-entering the tree.

See [`docs/security.md`](docs/security.md) for the incident classification, the
required dashboard action, fork-PR limitations, and setup commands
(`gh secret set GITGUARDIAN_API_KEY --repo laqieer/FECreator`, `pre-commit
install`).
