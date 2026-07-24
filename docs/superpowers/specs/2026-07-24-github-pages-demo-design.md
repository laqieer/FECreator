# GitHub Pages Demo Design

## Goal

Deploy a safe, deterministic FECreator web demo to:

`https://laqieer.github.io/FECreator/`

GitHub Pages hosts static files only. It does not host the FastAPI backend, run
providers, access local files, or perform real asset generation.

## Build modes

The web workspace has two explicit build modes:

1. **Local application**
   - Default Vite base path: `/`.
   - Uses the real HTTP and WebSocket clients.
   - Is packaged into `src/fecreator/_web` for FastAPI.

2. **GitHub Pages demo**
   - Vite base path: `/FECreator/`.
   - Enabled only by a build-time demo-mode environment variable.
   - Uses deterministic in-browser data and simulated job events.
   - Makes no HTTP, WebSocket, provider, upload, or filesystem calls.

The demo build must display a persistent, accessible banner stating that it
uses sample data and cannot generate, validate, upload, or save real assets.

## Components

### Demo API client

Add a demo implementation of the existing `ApiClient` interface. It owns an
in-memory, deterministic collection of:

- registered asset/spec/provider identifiers
- sample manifests and jobs
- validation examples

Creating or loading a job changes only this in-memory state. Reloading the page
resets the demo.

### Demo event source

The job-events hook selects its event source through an injected abstraction:

- local mode uses the real WebSocket
- demo mode emits a deterministic sequence of sample events

The demo source follows the same connection-state and cleanup contract as the
real source. It must not instantiate a browser `WebSocket`.

### Application composition

The application entry point reads the build-time demo flag and composes either:

- `httpClient()` plus the real WebSocket source, or
- `demoClient()` plus the demo event source

Components remain unaware of the deployment environment.

## Data flow

```text
GitHub Pages build
        |
        v
demo-mode application composition
        |
        +--> in-memory ApiClient
        |
        +--> deterministic event source
        |
        v
existing review-workbench components
```

No demo action leaves the browser. No data is persisted across reloads.

## CI deployment

Extend the existing `CI` workflow with a `deploy-pages` job.

The job:

1. Runs only for pushes to `main`.
2. Depends on successful Python, web, and package jobs.
3. Uses Node 22 and `npm ci`.
4. Builds with demo mode enabled and Vite base `/FECreator/`.
5. Uploads `src/fecreator/_web` with `actions/upload-pages-artifact`.
6. Deploys with `actions/deploy-pages` to the `github-pages` environment.

Workflow permissions are least-privilege:

- `contents: read`
- `pages: write`
- `id-token: write`

Pull requests run all build and test checks but never deploy.

## Error handling

- Demo client methods reject invalid IDs and malformed manifests explicitly.
- Demo event failures use the same visible error state as real WebSocket
  failures.
- Missing or malformed demo fixtures fail tests/build; they do not trigger a
  fallback to the real network client.
- The Pages build must never infer an API URL from the browser location.

## Security and privacy

- No backend URL, credential, token, signed URL, or private reference is
  embedded.
- Demo mode does not call `fetch`, instantiate `WebSocket`, use browser file
  APIs, or upload data.
- Sample content is synthetic and repository-owned.
- The banner prevents users from mistaking the demo for a functioning hosted
  generation service.

## Testing

Add tests that prove:

- demo mode shows the banner
- demo registries/jobs are deterministic
- job creation and selection work entirely in memory
- the simulated timeline reaches a terminal sample state
- `fetch` and `WebSocket` are never called in demo mode
- malformed demo inputs fail closed
- the normal local application still composes the real clients
- the Pages build emits asset URLs beneath `/FECreator/`
- the normal package build continues to emit root-relative assets
- CI deployment is gated on successful test/package jobs and cannot run on pull
  requests

## Non-goals

- Hosting FastAPI or providers
- Connecting the public HTTPS page to a localhost HTTP server
- Adding remote API/CORS support
- Persisting demo data
- Publishing generated assets
- Replacing the local application
