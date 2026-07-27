# FECreator

Local-first, agent-neutral, provider-neutral Fire Emblem **portrait** creation
workbench with deterministic imaging, immutable jobs/lineage, human review, and a
`fe-gba-portrait-standard` export compatible with FEBuilderGBA (file-based, ROM-free).

See `docs/product-statement.md` for scope and `docs/architecture.md` for the module map.
FEBuilderGBA compatibility evidence levels (mandatory deterministic proof, optional
CLI validation, opt-in local ROM checks) are documented in
[`docs/febuilder-interop.md`](docs/febuilder-interop.md).

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
