# GitHub Pages demo

The FECreator web workspace builds in two explicit modes.

| Mode  | Env var                     | Vite base     | API client       | Job events              | Packaged into `_web` for FastAPI |
| ----- | --------------------------- | ------------- | ---------------- | ----------------------- | -------------------------------- |
| Local | (unset)                     | `/`           | `httpClient()`   | real WebSocket          | yes                              |
| Demo  | `VITE_FE_CREATOR_MODE=demo` | `/FECreator/` | `demoClient()`   | in-memory timer source  | published to Pages               |

## URL

<https://laqieer.github.io/FECreator/>

## What the demo is

A static, deterministic preview composed at the entry point (`web/src/main.tsx` →
`createComposition(appMode())`). A persistent, accessible banner states that the
page uses sample data. Sample content is synthetic and repository-owned
(`web/src/demo/fixtures.ts`). The in-memory registry and job controls expose both
`portrait` and `dialogue_background`, including deterministic synthetic candidate
and package artifacts for their supported workflows.

## Limitations

- Runs entirely in the browser; there is no FastAPI backend, provider, or file access.
- Makes **no** `fetch`, `WebSocket`, upload, or File System Access calls.
- It cannot generate, validate, upload, or save real assets.
- Does not persist anything; reloading the page resets all in-memory state.
- Embeds no backend URL, credential, token, signed URL, or private reference.

## Build the demo locally

```bash
npm ci
npm run -w @laqieer/fecreator-web build:demo
```

Output lands in `src/fecreator/_web` with asset URLs under `/FECreator/`. To rebuild
the packaged local app (root-relative assets), run `npm run -w @laqieer/fecreator-web build`.

## Deployment

`.github/workflows/ci.yml` runs a `deploy-pages` job that only executes on pushes to
`main`, after the `python`, `web`, and `package` jobs pass. It builds with demo mode
enabled, uploads `src/fecreator/_web` with `actions/upload-pages-artifact`, and deploys
with `actions/deploy-pages` to the `github-pages` environment. Pull requests run every
build and test check but never deploy.
