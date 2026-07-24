# FECreator

Local-first, agent-neutral, provider-neutral Fire Emblem **portrait** creation
workbench with deterministic imaging, immutable jobs/lineage, human review, and a
`fe-gba-portrait-standard` export compatible with FEBuilderGBA (file-based, ROM-free).

See `docs/product-statement.md` for scope and `docs/architecture.md` for the module map.

## Live demo

A static, sample-data demo is published to GitHub Pages:

**<https://laqieer.github.io/FECreator/>**

The demo runs entirely in the browser with built-in synthetic data. It **cannot**
generate, validate, upload, or save real assets, makes no HTTP or WebSocket calls,
and resets whenever the page is reloaded. See
[`docs/github-pages-demo.md`](docs/github-pages-demo.md) for build modes and
limitations.
