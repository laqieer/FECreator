# GitHub Pages Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a safe, deterministic, network-free FECreator web demo to `https://laqieer.github.io/FECreator/` while keeping the packaged local FastAPI app unchanged.

**Architecture:** A build-time typed mode flag (`VITE_FE_CREATOR_MODE`) selects one of two compositions at the entry point: the local app wires the real `httpClient()` plus a WebSocket job-event source; the demo wires an in-memory `demoClient()` plus a timer-driven event source that never touches `fetch` or `WebSocket`. The event source becomes an injected abstraction so `useJobEvents` no longer constructs a `WebSocket` directly. Vite's `base` is `/FECreator/` for the demo build and `/` for the local build. CI gains a `deploy-pages` job that runs only on `main` pushes after all build/test jobs pass.

**Tech Stack:** TypeScript 5.9, React 19, Vite 8 (`--mode`/`loadEnv`), Vitest + Testing Library, Python 3.11–3.13 / pytest + PyYAML (already bundled by `uvicorn[standard]`), GitHub Actions Pages actions.

## Global Constraints

- **Demo is fail-closed and network-free:** demo mode must never call `fetch`, instantiate `WebSocket`, use browser File APIs, upload, or persist. No backend URL, credential, token, signed URL, or private reference may be embedded. (spec §Security and privacy)
- **Two explicit build modes only:** local base `/`; demo base `/FECreator/`; demo enabled solely by the build-time env var `VITE_FE_CREATOR_MODE=demo`. Any other/absent value resolves to local. (spec §Build modes)
- **Both builds write to the same `outDir` `../src/fecreator/_web`** and both must emit an `index.html`, so the Hatch `_web` guard (`hatch_build.py`) keeps passing. (pyproject.toml `[tool.hatch.build.hooks.custom]`, hatch_build.py)
- **Do not weaken the frozen `ApiClient` contract:** `demoClient()` implements `listAssets/listSpecs/listProviders/createJob/getJob/validate` exactly. (web/src/api/client.ts)
- **No new build/test tools or dependencies.** Reuse Vite, Vitest, pytest, PyYAML, and the GitHub-published Pages actions.
- **Least-privilege CI:** the Pages job uses `contents: read`, `pages: write`, `id-token: write`; pull requests run all checks but never deploy. (spec §CI deployment)
- **Node 22 + `npm ci` in CI; frontend workspace is `@laqieer/fecreator-web`.** (.github/workflows/ci.yml)
- **Deterministic, synthetic, repository-owned sample data; reset on reload.** (spec §Components, §Data flow)

---

## File map built by this plan

```text
web/.env.demo                                   # NEW: VITE_FE_CREATOR_MODE=demo (loaded only by --mode demo)
web/vite.config.ts                              # MODIFY: config fn -> base from resolveBase(loadEnv(...))
web/package.json                                # MODIFY: add "build:demo" script
web/src/vite-env.d.ts                           # NEW: vite/client + typed ImportMetaEnv.VITE_FE_CREATOR_MODE
web/src/config/constants.ts                     # NEW: mode/base constants + AppMode type
web/src/config/base.ts                          # NEW: resolveBase(env) (imported by vite.config.ts)
web/src/config/base.test.ts                     # NEW
web/src/config/mode.ts                          # NEW: appMode(), isDemo() (reads import.meta.env)
web/src/config/mode.test.ts                     # NEW
web/src/demo/fixtures.ts                         # NEW: deterministic registries/manifest/jobs/diagnostics/timeline
web/src/demo/demoClient.ts                       # NEW: demoClient(): ApiClient + assertValidManifest
web/src/demo/demoClient.test.ts                  # NEW
web/src/jobs/eventSource.ts                      # NEW: JobEventConnection + JobEventSource interfaces
web/src/jobs/webSocketEventSource.ts             # NEW: webSocketJobEventSource(baseUrl?)
web/src/jobs/webSocketEventSource.test.tsx       # NEW
web/src/jobs/eventSourceContext.tsx              # NEW: JobEventSourceProvider + useJobEventSource()
web/src/jobs/useJobEvents.ts                     # MODIFY: consume injected source; drop baseUrl param
web/src/jobs/useJobEvents.test.tsx               # MODIFY: wrap Probe in JobEventSourceProvider
web/src/demo/demoJobEventSource.ts               # NEW: timer-driven demo source (no WebSocket)
web/src/demo/demoJobEventSource.test.tsx         # NEW
web/src/demo/DemoBanner.tsx                       # NEW: persistent accessible demo banner
web/src/demo/DemoBanner.test.tsx                  # NEW
web/src/app/composition.ts                        # NEW: createComposition(mode) -> {client,eventSource,demo}
web/src/app/composition.test.ts                   # NEW
web/src/app/AppRoot.tsx                            # NEW: providers + optional banner + <App/>
web/src/app/AppRoot.test.tsx                      # NEW: banner + zero-network demo + local composition
web/src/test/util.tsx                             # MODIFY: renderWithProviders provides a JobEventSource
web/src/main.tsx                                  # MODIFY: createComposition(appMode()) + AppRoot
.github/workflows/ci.yml                          # MODIFY: top-level permissions + web asset check + deploy-pages
tests/test_ci_pages_workflow.py                   # NEW: static gate checks for the deploy-pages job
README.md                                         # MODIFY: Live demo section
docs/github-pages-demo.md                         # NEW: demo docs, limitations, URL
```

**App.tsx is intentionally NOT modified:** it already calls `useJobEvents(selectedJobId)` with no base URL and remains unaware of the deployment environment (spec §Application composition).

---

## Task 1: Build-time mode/config abstraction and Vite base

**Files:**
- Create: `web/src/config/constants.ts`, `web/src/config/base.ts`, `web/src/config/mode.ts`, `web/src/vite-env.d.ts`, `web/.env.demo`
- Modify: `web/vite.config.ts`, `web/package.json`
- Test: `web/src/config/base.test.ts`, `web/src/config/mode.test.ts`

**Interfaces:**
- Produces (`constants.ts`): `DEMO_MODE = "demo"`, `LOCAL_MODE = "local"`, `DEMO_BASE_PATH = "/FECreator/"`, `LOCAL_BASE_PATH = "/"`, `type AppMode = "local" | "demo"`.
- Produces (`base.ts`): `resolveBase(env: Record<string, string | undefined>): string` — returns `DEMO_BASE_PATH` iff `env.VITE_FE_CREATOR_MODE === DEMO_MODE`, else `LOCAL_BASE_PATH`. Consumed by `vite.config.ts` and Task 6's CI asset check (indirectly, via the built base).
- Produces (`mode.ts`): `appMode(): AppMode`, `isDemo(): boolean` (read `import.meta.env.VITE_FE_CREATOR_MODE`). Consumed by Tasks 5.
- Produces (`web/.env.demo`): sets `VITE_FE_CREATOR_MODE=demo`, loaded only under `vite build --mode demo`.

- [ ] **Step 1: Write the failing tests**

`web/src/config/base.test.ts`:
```ts
import { expect, test } from "vitest";
import { resolveBase } from "./base";

test("demo mode resolves the project pages base path", () => {
  expect(resolveBase({ VITE_FE_CREATOR_MODE: "demo" })).toBe("/FECreator/");
});

test("missing mode resolves the root base path", () => {
  expect(resolveBase({})).toBe("/");
});

test("any non-demo value fails closed to the root base path", () => {
  expect(resolveBase({ VITE_FE_CREATOR_MODE: "local" })).toBe("/");
  expect(resolveBase({ VITE_FE_CREATOR_MODE: "DEMO" })).toBe("/");
  expect(resolveBase({ VITE_FE_CREATOR_MODE: "" })).toBe("/");
});
```

`web/src/config/mode.test.ts`:
```ts
import { afterEach, expect, test, vi } from "vitest";
import { appMode, isDemo } from "./mode";

afterEach(() => {
  vi.unstubAllEnvs();
});

test("the demo environment variable selects demo mode", () => {
  vi.stubEnv("VITE_FE_CREATOR_MODE", "demo");
  expect(appMode()).toBe("demo");
  expect(isDemo()).toBe(true);
});

test("an empty environment variable fails closed to local mode", () => {
  vi.stubEnv("VITE_FE_CREATOR_MODE", "");
  expect(appMode()).toBe("local");
  expect(isDemo()).toBe(false);
});

test("an unrecognized value fails closed to local mode", () => {
  vi.stubEnv("VITE_FE_CREATOR_MODE", "production");
  expect(appMode()).toBe("local");
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm run -w @laqieer/fecreator-web test -- config`
Expected: FAIL — cannot resolve `./base` / `./mode`.

- [ ] **Step 3: Write the minimal implementation**

`web/src/config/constants.ts`:
```ts
export const LOCAL_MODE = "local" as const;
export const DEMO_MODE = "demo" as const;
export const LOCAL_BASE_PATH = "/";
export const DEMO_BASE_PATH = "/FECreator/";

export type AppMode = typeof LOCAL_MODE | typeof DEMO_MODE;
```

`web/src/config/base.ts`:
```ts
import { DEMO_BASE_PATH, DEMO_MODE, LOCAL_BASE_PATH } from "./constants";

export function resolveBase(env: Record<string, string | undefined>): string {
  return env.VITE_FE_CREATOR_MODE === DEMO_MODE ? DEMO_BASE_PATH : LOCAL_BASE_PATH;
}
```

`web/src/config/mode.ts`:
```ts
import { DEMO_MODE, LOCAL_MODE, type AppMode } from "./constants";

export function appMode(): AppMode {
  return import.meta.env.VITE_FE_CREATOR_MODE === DEMO_MODE ? DEMO_MODE : LOCAL_MODE;
}

export function isDemo(): boolean {
  return appMode() === DEMO_MODE;
}
```

`web/src/vite-env.d.ts`:
```ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_FE_CREATOR_MODE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
```

`web/.env.demo`:
```dotenv
VITE_FE_CREATOR_MODE=demo
```

Modify `web/vite.config.ts` to a config function that derives `base` from the env (single source of truth with the client runtime):
```ts
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { resolveBase } from "./src/config/base";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd());
  return {
    base: resolveBase(env),
    plugins: [react()],
    build: {
      outDir: "../src/fecreator/_web",
      emptyOutDir: true,
    },
    test: {
      environment: "jsdom",
      globals: true,
    },
  };
});
```

Add the demo build script to `web/package.json` (`scripts` block), keeping the existing `build`:
```json
    "build": "vite build",
    "build:demo": "vite build --mode demo",
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm run -w @laqieer/fecreator-web test -- config`
Expected: PASS (2 files, 6 tests).

- [ ] **Step 5: Verify both builds resolve the correct base end-to-end**

Run (PowerShell or bash):
```
npm run -w @laqieer/fecreator-web build
npm run -w @laqieer/fecreator-web build:demo
```
Expected: both succeed and write `src/fecreator/_web/index.html`. Confirm the base wiring:
```
# after build:demo
node -e "const h=require('fs').readFileSync('src/fecreator/_web/index.html','utf8'); if(!h.includes('/FECreator/assets/')) throw new Error('demo base missing'); console.log('demo base OK')"
# after re-running the local build
npm run -w @laqieer/fecreator-web build
node -e "const h=require('fs').readFileSync('src/fecreator/_web/index.html','utf8'); if(h.includes('/FECreator/')) throw new Error('unexpected demo base'); console.log('local base OK')"
```
Expected: prints `demo base OK` then `local base OK`.

- [ ] **Step 6: Commit**

```bash
git add web/src/config web/src/vite-env.d.ts web/.env.demo web/vite.config.ts web/package.json
git commit -m "feat(web): add typed build mode flag and demo Vite base

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Co-authored-by: laqieer <laqieer@126.com>"
```

---

## Task 2: `DemoApiClient` with deterministic in-memory data

**Files:**
- Create: `web/src/demo/fixtures.ts`, `web/src/demo/demoClient.ts`
- Test: `web/src/demo/demoClient.test.ts`

**Interfaces:**
- Consumes: `ApiClient` (web/src/api/client.ts), `Manifest`/`Job`/`Diagnostic`/`JobEvent` (web/src/api/types.ts).
- Produces (`fixtures.ts`): `DEMO_CREATED_AT: string`, `demoAssets/demoSpecs/demoProviders: readonly string[]`, `demoManifest: Manifest`, `demoJobsSeed: readonly Job[]`, `demoDiagnostics: readonly Diagnostic[]`, `demoTimeline: readonly JobEvent[]`. `demoTimeline` and `demoProviders` are consumed by Task 4 and Task 2 respectively.
- Produces (`demoClient.ts`): `assertValidManifest(manifest: Manifest): void` (throws on invalid) and `demoClient(): ApiClient`.

- [ ] **Step 1: Write the failing test**

`web/src/demo/demoClient.test.ts`:
```ts
import { expect, test } from "vitest";
import { demoClient } from "./demoClient";
import type { Manifest } from "../api/types";

const validManifest: Manifest = {
  version: "1.0",
  asset_type: "portrait",
  target_spec: "fe-gba-portrait-standard",
  workflow: "text_to_portrait",
  provider: "fake",
};

test("registries are deterministic and match the frozen v1 surface", async () => {
  const client = demoClient();
  expect(await client.listAssets()).toEqual(["portrait"]);
  expect(await client.listSpecs()).toEqual(["fe-gba-portrait-standard"]);
  expect(await client.listProviders()).toEqual(["fake"]);
});

test("creating a job stores it in memory with a deterministic id", async () => {
  const client = demoClient();
  const job = await client.createJob(validManifest);
  expect(job.id).toBe("demo-job-1");
  expect(job.state).toBe("created");
  expect(await client.getJob("demo-job-1")).toEqual(job);
});

test("a fresh client resets in-memory state (reload semantics)", async () => {
  const first = demoClient();
  await first.createJob(validManifest);
  const second = demoClient();
  await expect(second.getJob("demo-job-1")).rejects.toThrow("Demo job demo-job-1 does not exist.");
});

test("getJob rejects unknown ids", async () => {
  await expect(demoClient().getJob("nope")).rejects.toThrow("Demo job nope does not exist.");
});

test("createJob fails closed on an unregistered provider", async () => {
  const client = demoClient();
  const malformed: Manifest = { ...validManifest, provider: "unregistered" };
  await expect(client.createJob(malformed)).rejects.toThrow("Demo manifest provider is not registered.");
});

test("createJob fails closed on a malformed target spec", async () => {
  const client = demoClient();
  const malformed = { ...validManifest, target_spec: "other" } as unknown as Manifest;
  await expect(client.createJob(malformed)).rejects.toThrow(
    "Demo manifest target_spec must be fe-gba-portrait-standard.",
  );
});

test("validate rejects unregistered specs and returns deterministic diagnostics", async () => {
  const client = demoClient();
  await expect(client.validate("wrong", "pkg")).rejects.toThrow("Demo spec wrong is not registered.");
  const diagnostics = await client.validate("fe-gba-portrait-standard", "pkg");
  expect(diagnostics).toHaveLength(1);
  expect(diagnostics[0]?.code).toBe("portrait.palette.count");
});

test("a preseeded sample job is available and completed", async () => {
  const job = await demoClient().getJob("demo-portrait-neutral");
  expect(job.state).toBe("completed");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm run -w @laqieer/fecreator-web test -- demoClient`
Expected: FAIL — cannot resolve `./demoClient`.

- [ ] **Step 3: Write the minimal implementation**

`web/src/demo/fixtures.ts`:
```ts
import type { Diagnostic, Job, JobEvent, Manifest } from "../api/types";

export const DEMO_CREATED_AT = "2026-07-24T00:00:00+00:00";

export const demoAssets: readonly string[] = ["portrait"];
export const demoSpecs: readonly string[] = ["fe-gba-portrait-standard"];
export const demoProviders: readonly string[] = ["fake"];

export const demoManifest: Manifest = {
  version: "1.0",
  asset_type: "portrait",
  target_spec: "fe-gba-portrait-standard",
  workflow: "text_to_portrait",
  provider: "fake",
};

export const demoJobsSeed: readonly Job[] = [
  {
    id: "demo-portrait-neutral",
    state: "completed",
    manifest: demoManifest,
    revision: 3,
    created_at: DEMO_CREATED_AT,
    updated_at: DEMO_CREATED_AT,
  },
];

export const demoDiagnostics: readonly Diagnostic[] = [
  {
    code: "portrait.palette.count",
    severity: "info",
    message: "Sample portrait uses 15 of 16 permitted palette entries.",
    where: "portrait/neutral.png",
    data: null,
  },
];

export const demoTimeline: readonly JobEvent[] = [
  { seq: 0, at: DEMO_CREATED_AT, kind: "created", message: "Demo job created from sample manifest." },
  { seq: 1, at: DEMO_CREATED_AT, kind: "planning", message: "Planned deterministic sample source prompts." },
  { seq: 2, at: DEMO_CREATED_AT, kind: "processing", message: "Rendered deterministic sample frames in memory." },
  { seq: 3, at: DEMO_CREATED_AT, kind: "completed", message: "Sample job completed. No real assets were produced." },
];
```

`web/src/demo/demoClient.ts`:
```ts
import type { ApiClient } from "../api/client";
import type { Job, Manifest } from "../api/types";
import {
  DEMO_CREATED_AT,
  demoAssets,
  demoDiagnostics,
  demoJobsSeed,
  demoProviders,
  demoSpecs,
} from "./fixtures";

const demoWorkflows: readonly string[] = [
  "text_to_portrait",
  "concept_to_portrait",
  "expression_refine",
  "masked_variant",
];

export function assertValidManifest(manifest: Manifest): void {
  const version: unknown = manifest.version;
  if (version !== "1.0") {
    throw new Error("Demo manifest must use version 1.0.");
  }
  const assetType: unknown = manifest.asset_type;
  if (assetType !== "portrait") {
    throw new Error("Demo manifest asset_type must be portrait.");
  }
  const targetSpec: unknown = manifest.target_spec;
  if (targetSpec !== "fe-gba-portrait-standard") {
    throw new Error("Demo manifest target_spec must be fe-gba-portrait-standard.");
  }
  const workflow: unknown = manifest.workflow;
  if (typeof workflow !== "string" || !demoWorkflows.includes(workflow)) {
    throw new Error("Demo manifest workflow is not recognized.");
  }
  const provider: unknown = manifest.provider;
  if (typeof provider !== "string" || !demoProviders.includes(provider)) {
    throw new Error("Demo manifest provider is not registered.");
  }
}

export function demoClient(): ApiClient {
  const jobs = new Map<string, Job>(demoJobsSeed.map((job) => [job.id, job]));
  let counter = 0;

  return {
    listAssets: async () => [...demoAssets],
    listSpecs: async () => [...demoSpecs],
    listProviders: async () => [...demoProviders],
    createJob: async (manifest) => {
      assertValidManifest(manifest);
      counter += 1;
      const job: Job = {
        id: `demo-job-${counter}`,
        state: "created",
        manifest,
        revision: 1,
        created_at: DEMO_CREATED_AT,
        updated_at: DEMO_CREATED_AT,
      };
      jobs.set(job.id, job);
      return job;
    },
    getJob: async (id) => {
      const job = jobs.get(id);
      if (!job) {
        throw new Error(`Demo job ${id} does not exist.`);
      }
      return job;
    },
    validate: async (spec, path) => {
      if (!demoSpecs.includes(spec)) {
        throw new Error(`Demo spec ${spec} is not registered.`);
      }
      if (typeof path !== "string" || path.trim().length === 0) {
        throw new Error("Demo validation requires a package directory.");
      }
      return demoDiagnostics.map((diagnostic) => ({ ...diagnostic }));
    },
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm run -w @laqieer/fecreator-web test -- demoClient`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/demo/fixtures.ts web/src/demo/demoClient.ts web/src/demo/demoClient.test.ts
git commit -m "feat(web): add in-memory DemoApiClient and synthetic fixtures

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Co-authored-by: laqieer <laqieer@126.com>"
```

---

## Task 3: Injected job event source and hook refactor (real source unchanged)

**Files:**
- Create: `web/src/jobs/eventSource.ts`, `web/src/jobs/webSocketEventSource.ts`, `web/src/jobs/eventSourceContext.tsx`
- Modify: `web/src/jobs/useJobEvents.ts`, `web/src/jobs/useJobEvents.test.tsx`, `web/src/test/util.tsx`
- Test: `web/src/jobs/webSocketEventSource.test.tsx` (new) + modified `useJobEvents.test.tsx`

**Interfaces:**
- Produces (`eventSource.ts`): `interface JobEventConnection { onopen: (() => void) | null; onmessage: ((event: { data: unknown }) => void) | null; onerror: (() => void) | null; onclose: (() => void) | null; close(): void; }` and `interface JobEventSource { connect(jobId: string): JobEventConnection; }`. Consumed by Tasks 4, 5.
- Produces (`webSocketEventSource.ts`): `webSocketJobEventSource(baseUrl?: string): JobEventSource`. Consumed by Tasks 5 and `test/util.tsx`.
- Produces (`eventSourceContext.tsx`): `JobEventSourceProvider({ source, children })` and `useJobEventSource(): JobEventSource`. Consumed by Tasks 4, 5 and the hook.
- Produces (modified `useJobEvents.ts`): `useJobEvents(jobId: string): JobEventsSnapshot` (no `baseUrl`); still exports `toWebSocketUrl(baseUrl, jobId)` and `parseJobEventsPayload(rawData, expectedJobId)`.

- [ ] **Step 1: Write the new failing test for the real source**

`web/src/jobs/webSocketEventSource.test.tsx`:
```tsx
import { afterEach, expect, test, vi } from "vitest";
import { webSocketJobEventSource } from "./webSocketEventSource";

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }
  close() {}
}

afterEach(() => {
  vi.unstubAllGlobals();
  MockWebSocket.instances = [];
});

test("the real source connects to the encoded websocket endpoint", () => {
  vi.stubGlobal("WebSocket", MockWebSocket);
  webSocketJobEventSource("http://127.0.0.1:8000").connect("job 7/alpha");
  expect(MockWebSocket.instances[0]?.url).toBe("ws://127.0.0.1:8000/ws/jobs/job%207%2Falpha");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm run -w @laqieer/fecreator-web test -- webSocketEventSource`
Expected: FAIL — cannot resolve `./webSocketEventSource`.

- [ ] **Step 3: Add the interfaces, real source, and context**

`web/src/jobs/eventSource.ts`:
```ts
export interface JobEventConnection {
  onopen: (() => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onerror: (() => void) | null;
  onclose: (() => void) | null;
  close(): void;
}

export interface JobEventSource {
  connect(jobId: string): JobEventConnection;
}
```

`web/src/jobs/webSocketEventSource.ts` (the real transport is unchanged — it still constructs `new WebSocket(toWebSocketUrl(baseUrl, jobId))`; the cast exposes the browser socket as the injected connection shape):
```ts
import type { JobEventConnection, JobEventSource } from "./eventSource";
import { toWebSocketUrl } from "./useJobEvents";

export function webSocketJobEventSource(baseUrl = ""): JobEventSource {
  return {
    connect: (jobId) => new WebSocket(toWebSocketUrl(baseUrl, jobId)) as unknown as JobEventConnection,
  };
}
```

`web/src/jobs/eventSourceContext.tsx`:
```tsx
import { createContext, useContext, type ReactNode } from "react";
import type { JobEventSource } from "./eventSource";

const JobEventSourceContext = createContext<JobEventSource | null>(null);

export function JobEventSourceProvider({ source, children }: { source: JobEventSource; children: ReactNode }) {
  return <JobEventSourceContext.Provider value={source}>{children}</JobEventSourceContext.Provider>;
}

export function useJobEventSource(): JobEventSource {
  const source = useContext(JobEventSourceContext);
  if (source === null) {
    throw new Error("JobEventSource not provided");
  }
  return source;
}
```

- [ ] **Step 4: Refactor the hook to consume the injected source**

Edit `web/src/jobs/useJobEvents.ts`. Add the import near the top:
```ts
import { useJobEventSource } from "./eventSourceContext";
```
Change only the hook signature/body (all parsing and state transitions stay identical). Replace the whole `useJobEvents` function with:
```ts
export function useJobEvents(jobId: string): JobEventsSnapshot {
  const source = useJobEventSource();
  const [snapshot, setSnapshot] = useState<JobEventsSnapshot>(initialSnapshot);

  useEffect(() => {
    if (!jobId) {
      setSnapshot(initialSnapshot);
      return undefined;
    }

    let active = true;
    let receivedSnapshot = false;
    let hasError = false;
    const socket = source.connect(jobId);
    setSnapshot({ events: [], connectionState: "connecting", error: null });

    socket.onopen = () => {
      if (!active) {
        return;
      }

      setSnapshot((current) => ({ ...current, connectionState: "live", error: null }));
    };

    socket.onmessage = (message) => {
      if (!active) {
        return;
      }

      try {
        const payload = parseJobEventsPayload(message.data, jobId);
        receivedSnapshot = true;
        hasError = false;
        setSnapshot({
          events: payload.events,
          connectionState: "live",
          error: null,
        });
      } catch (error) {
        hasError = true;
        setSnapshot({
          events: [],
          connectionState: "error",
          error: error instanceof Error ? error.message : "Job events payload failed validation.",
        });
        socket.close();
      }
    };

    socket.onerror = () => {
      if (!active) {
        return;
      }

      hasError = true;
      setSnapshot({
        events: [],
        connectionState: "error",
        error: "Timeline connection failed.",
      });
    };

    socket.onclose = () => {
      if (!active || hasError) {
        return;
      }

      setSnapshot((current) => ({
        ...current,
        connectionState: receivedSnapshot ? "complete" : "disconnected",
      }));
    };

    return () => {
      active = false;
      socket.close();
    };
  }, [jobId, source]);

  return snapshot;
}
```
Leave `JobEventsSnapshot`, `initialSnapshot`, the `isRecord`/`isJsonScalar`/`isJsonObject`/`isJobEvent` guards, `toWebSocketUrl`, and `parseJobEventsPayload` exactly as they are.

- [ ] **Step 5: Update `renderWithProviders` to supply a source**

Replace `web/src/test/util.tsx` with:
```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { ApiClientProvider } from "../api/context";
import type { ApiClient } from "../api/client";
import { JobEventSourceProvider } from "../jobs/eventSourceContext";
import type { JobEventSource } from "../jobs/eventSource";
import { webSocketJobEventSource } from "../jobs/webSocketEventSource";

export function renderWithProviders(
  ui: ReactElement,
  client: ApiClient,
  source: JobEventSource = webSocketJobEventSource(),
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <ApiClientProvider client={client}>
        <JobEventSourceProvider source={source}>{ui}</JobEventSourceProvider>
      </ApiClientProvider>
    </QueryClientProvider>,
  );
}
```

- [ ] **Step 6: Update the hook test to provide the source (behavior unchanged)**

Replace `web/src/jobs/useJobEvents.test.tsx` with (same MockWebSocket + assertions; the Probe now consumes the injected real source):
```tsx
import "@testing-library/jest-dom/vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useJobEvents } from "./useJobEvents";
import { JobEventSourceProvider } from "./eventSourceContext";
import { webSocketJobEventSource } from "./webSocketEventSource";

class MockWebSocket {
  static instances: MockWebSocket[] = [];

  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  close() {
    this.onclose?.();
  }
}

function Probe({ jobId }: { jobId: string }) {
  const snapshot = useJobEvents(jobId);
  return (
    <output>
      {snapshot.connectionState}:{snapshot.events.length}:{snapshot.error ?? "none"}
    </output>
  );
}

function renderProbe(jobId: string, baseUrl = "") {
  return render(
    <JobEventSourceProvider source={webSocketJobEventSource(baseUrl)}>
      <Probe jobId={jobId} />
    </JobEventSourceProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  MockWebSocket.instances = [];
});

test("opens the frozen websocket endpoint, encodes ids, and completes after one snapshot", async () => {
  vi.stubGlobal("WebSocket", MockWebSocket);

  renderProbe("job 7/alpha", "http://127.0.0.1:8000");

  expect(MockWebSocket.instances[0]?.url).toBe("ws://127.0.0.1:8000/ws/jobs/job%207%2Falpha");
  act(() => {
    MockWebSocket.instances[0]?.onopen?.();
    MockWebSocket.instances[0]?.onmessage?.({
      data: JSON.stringify({
        job_id: "job 7/alpha",
        events: [{ seq: 0, at: "2026-07-24T00:00:00+00:00", kind: "created", message: "job created" }],
      }),
    });
    MockWebSocket.instances[0]?.onclose?.();
  });

  await waitFor(() => expect(screen.getByText("complete:1:none")).toBeInTheDocument());
});

test("fails closed on malformed websocket json", async () => {
  vi.stubGlobal("WebSocket", MockWebSocket);

  renderProbe("job-7", "http://127.0.0.1:8000");

  act(() => {
    MockWebSocket.instances[0]?.onopen?.();
    MockWebSocket.instances[0]?.onmessage?.({ data: "{" });
  });

  await waitFor(() => expect(screen.getByText(/error:0:Malformed job events JSON\./)).toBeInTheDocument());
});

test("fails closed on websocket payloads without a valid events array", async () => {
  vi.stubGlobal("WebSocket", MockWebSocket);

  renderProbe("job-7", "http://127.0.0.1:8000");

  act(() => {
    MockWebSocket.instances[0]?.onopen?.();
    MockWebSocket.instances[0]?.onmessage?.({ data: JSON.stringify({ job_id: "job-7", events: [{}] }) });
  });

  await waitFor(() =>
    expect(screen.getByText(/error:0:Job events payload contains an invalid event\./)).toBeInTheDocument(),
  );
});

test("surfaces an unexpected disconnect before any snapshot", async () => {
  vi.stubGlobal("WebSocket", MockWebSocket);

  renderProbe("job-7", "http://127.0.0.1:8000");

  act(() => {
    MockWebSocket.instances[0]?.onclose?.();
  });

  await waitFor(() => expect(screen.getByText("disconnected:0:none")).toBeInTheDocument());
});
```

- [ ] **Step 7: Run the affected tests to verify they pass**

Run: `npm run -w @laqieer/fecreator-web test -- useJobEvents webSocketEventSource App`
Expected: PASS. `App.test.tsx` passes unchanged because `renderWithProviders` now supplies the real source and the global `WebSocket` stub is still honored.

- [ ] **Step 8: Commit**

```bash
git add web/src/jobs/eventSource.ts web/src/jobs/webSocketEventSource.ts web/src/jobs/webSocketEventSource.test.tsx web/src/jobs/eventSourceContext.tsx web/src/jobs/useJobEvents.ts web/src/jobs/useJobEvents.test.tsx web/src/test/util.tsx
git commit -m "refactor(web): inject job event source into useJobEvents

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Co-authored-by: laqieer <laqieer@126.com>"
```

---

## Task 4: Demo job event source (no WebSocket)

**Files:**
- Create: `web/src/demo/demoJobEventSource.ts`
- Test: `web/src/demo/demoJobEventSource.test.tsx`

**Interfaces:**
- Consumes: `JobEventSource`/`JobEventConnection` (Task 3), `JobEvent` (types), `demoTimeline` (Task 2), `JobEventSourceProvider` + `useJobEvents` (Task 3).
- Produces: `demoJobEventSource(timeline?: readonly JobEvent[]): JobEventSource` (default `demoTimeline`). Emits `open → one full snapshot → close` on timers; `close()` clears pending timers. Never references `WebSocket`.

- [ ] **Step 1: Write the failing test**

`web/src/demo/demoJobEventSource.test.tsx`:
```tsx
import "@testing-library/jest-dom/vitest";
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { demoJobEventSource } from "./demoJobEventSource";
import { JobEventSourceProvider } from "../jobs/eventSourceContext";
import { useJobEvents } from "../jobs/useJobEvents";

function Probe({ jobId }: { jobId: string }) {
  const snapshot = useJobEvents(jobId);
  return (
    <output>
      {snapshot.connectionState}:{snapshot.events.length}:{snapshot.error ?? "none"}
    </output>
  );
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("the demo source never constructs a WebSocket and completes a sample timeline", () => {
  const webSocketSpy = vi.fn();
  vi.stubGlobal("WebSocket", webSocketSpy);

  render(
    <JobEventSourceProvider source={demoJobEventSource()}>
      <Probe jobId="demo-job-1" />
    </JobEventSourceProvider>,
  );

  act(() => {
    vi.runAllTimers();
  });

  expect(webSocketSpy).not.toHaveBeenCalled();
  expect(screen.getByText("complete:4:none")).toBeInTheDocument();
});

test("closing clears pending timers before any callback fires", () => {
  const source = demoJobEventSource();
  const connection = source.connect("demo-job-1");
  const opened = vi.fn();
  connection.onopen = opened;

  connection.close();
  act(() => {
    vi.runAllTimers();
  });

  expect(opened).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm run -w @laqieer/fecreator-web test -- demoJobEventSource`
Expected: FAIL — cannot resolve `./demoJobEventSource`.

- [ ] **Step 3: Write the minimal implementation**

`web/src/demo/demoJobEventSource.ts`:
```ts
import type { JobEvent } from "../api/types";
import type { JobEventConnection, JobEventSource } from "../jobs/eventSource";
import { demoTimeline } from "./fixtures";

const STEP_MS = 5;

export function demoJobEventSource(timeline: readonly JobEvent[] = demoTimeline): JobEventSource {
  return {
    connect(jobId) {
      const timers: ReturnType<typeof setTimeout>[] = [];
      const connection: JobEventConnection = {
        onopen: null,
        onmessage: null,
        onerror: null,
        onclose: null,
        close() {
          for (const timer of timers) {
            clearTimeout(timer);
          }
          timers.length = 0;
        },
      };

      timers.push(setTimeout(() => connection.onopen?.(), 0));
      timers.push(
        setTimeout(() => {
          connection.onmessage?.({
            data: JSON.stringify({ job_id: jobId, events: timeline }),
          });
        }, STEP_MS),
      );
      timers.push(setTimeout(() => connection.onclose?.(), STEP_MS * 2));

      return connection;
    },
  };
}
```

The demo emits the same `{ job_id, events }` snapshot shape the real backend sends, so the injected hook parses and validates it through the identical `parseJobEventsPayload` path. The timeline ends with a `completed` event and the source closes after a snapshot, so `connectionState` reaches the terminal `complete` state.

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm run -w @laqieer/fecreator-web test -- demoJobEventSource`
Expected: PASS (2 tests). `complete:4:none` confirms four sample events and a terminal snapshot.

- [ ] **Step 5: Commit**

```bash
git add web/src/demo/demoJobEventSource.ts web/src/demo/demoJobEventSource.test.tsx
git commit -m "feat(web): add timer-driven demo job event source

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Co-authored-by: laqieer <laqieer@126.com>"
```

---

## Task 5: App composition, demo banner, and entry wiring

**Files:**
- Create: `web/src/demo/DemoBanner.tsx`, `web/src/app/composition.ts`, `web/src/app/AppRoot.tsx`
- Modify: `web/src/main.tsx`
- Test: `web/src/demo/DemoBanner.test.tsx`, `web/src/app/composition.test.ts`, `web/src/app/AppRoot.test.tsx`

**Interfaces:**
- Consumes: `demoClient` (T2), `httpClient` (existing), `webSocketJobEventSource` (T3), `demoJobEventSource` (T4), `JobEventSourceProvider` (T3), `ApiClientProvider` (existing), `App` (existing), `AppMode`/`DEMO_MODE` (T1), `appMode` (T1).
- Produces (`composition.ts`): `interface Composition { client: ApiClient; eventSource: JobEventSource; demo: boolean; }` and `createComposition(mode: AppMode): Composition`.
- Produces (`DemoBanner.tsx`): `DemoBanner(): JSX.Element` — an `aside role="note"` labelled `Demo mode notice`.
- Produces (`AppRoot.tsx`): `AppRoot({ composition }: { composition: Composition }): JSX.Element` owning the `QueryClient` and rendering the banner only when `composition.demo`.

- [ ] **Step 1: Write the failing tests**

`web/src/demo/DemoBanner.test.tsx`:
```tsx
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { DemoBanner } from "./DemoBanner";

test("the demo banner is an accessible, persistent notice about sample data", () => {
  render(<DemoBanner />);
  const banner = screen.getByRole("note", { name: "Demo mode notice" });
  expect(banner).toBeInTheDocument();
  expect(banner).toHaveTextContent(/sample data/i);
  expect(banner).toHaveTextContent(/cannot generate, validate, upload, or save/i);
  expect(banner).toHaveTextContent(/reset/i);
});
```

`web/src/app/composition.test.ts`:
```ts
import { afterEach, expect, test, vi } from "vitest";
import { createComposition } from "./composition";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("demo composition uses in-memory registries and never opens a socket", async () => {
  const webSocketSpy = vi.fn();
  vi.stubGlobal("WebSocket", webSocketSpy);
  const { client, eventSource, demo } = createComposition("demo");

  expect(demo).toBe(true);
  expect(await client.listAssets()).toEqual(["portrait"]);

  const connection = eventSource.connect("demo-job-1");
  connection.close();
  expect(webSocketSpy).not.toHaveBeenCalled();
});

test("local composition uses the HTTP client and the websocket event source", async () => {
  const fetchSpy = vi.fn().mockResolvedValue({ ok: true, json: async () => ["portrait"] });
  const webSocketSpy = vi.fn().mockImplementation(() => ({ close: () => undefined }));
  vi.stubGlobal("fetch", fetchSpy);
  vi.stubGlobal("WebSocket", webSocketSpy);
  const { client, eventSource, demo } = createComposition("local");

  expect(demo).toBe(false);
  await client.listAssets();
  expect(fetchSpy).toHaveBeenCalledWith("/api/assets", undefined);

  eventSource.connect("job-1");
  expect(webSocketSpy).toHaveBeenCalledWith("ws://localhost:3000/ws/jobs/job-1");
});
```

`web/src/app/AppRoot.test.tsx`:
```tsx
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { AppRoot } from "./AppRoot";
import { createComposition } from "./composition";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("demo composition shows the banner, runs an in-memory timeline, and makes no network calls", async () => {
  const fetchSpy = vi.fn();
  const webSocketSpy = vi.fn();
  vi.stubGlobal("fetch", fetchSpy);
  vi.stubGlobal("WebSocket", webSocketSpy);
  const user = userEvent.setup();

  render(<AppRoot composition={createComposition("demo")} />);

  expect(screen.getByRole("note", { name: "Demo mode notice" })).toBeInTheDocument();
  expect(await screen.findByText("1 asset type available")).toBeInTheDocument();

  await user.click(screen.getByRole("tab", { name: "Timeline" }));
  await user.click(screen.getByRole("button", { name: "Create timeline job" }));

  expect(await screen.findByText("Sample job completed. No real assets were produced.")).toBeInTheDocument();
  expect(await screen.findByText("Timeline snapshot complete.")).toBeInTheDocument();

  expect(fetchSpy).not.toHaveBeenCalled();
  expect(webSocketSpy).not.toHaveBeenCalled();
});

test("local composition omits the banner and uses the real HTTP client", async () => {
  const fetchSpy = vi.fn().mockResolvedValue({ ok: true, json: async () => ["portrait"] });
  vi.stubGlobal("fetch", fetchSpy);

  render(<AppRoot composition={createComposition("local")} />);

  expect(screen.queryByRole("note", { name: "Demo mode notice" })).not.toBeInTheDocument();
  expect(await screen.findByText("1 asset type available")).toBeInTheDocument();
  expect(fetchSpy).toHaveBeenCalledWith("/api/assets", undefined);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm run -w @laqieer/fecreator-web test -- DemoBanner composition AppRoot`
Expected: FAIL — cannot resolve `./DemoBanner` / `./composition` / `./AppRoot`.

- [ ] **Step 3: Write the minimal implementation**

`web/src/demo/DemoBanner.tsx`:
```tsx
export function DemoBanner() {
  return (
    <aside role="note" aria-label="Demo mode notice">
      <strong>Demo mode.</strong> This static preview uses built-in sample data. It cannot
      generate, validate, upload, or save real assets, and all changes reset when you reload
      the page.
    </aside>
  );
}
```

`web/src/app/composition.ts`:
```ts
import type { ApiClient } from "../api/client";
import { httpClient } from "../api/client";
import type { AppMode } from "../config/constants";
import { DEMO_MODE } from "../config/constants";
import { demoClient } from "../demo/demoClient";
import { demoJobEventSource } from "../demo/demoJobEventSource";
import type { JobEventSource } from "../jobs/eventSource";
import { webSocketJobEventSource } from "../jobs/webSocketEventSource";

export interface Composition {
  client: ApiClient;
  eventSource: JobEventSource;
  demo: boolean;
}

export function createComposition(mode: AppMode): Composition {
  if (mode === DEMO_MODE) {
    return { client: demoClient(), eventSource: demoJobEventSource(), demo: true };
  }
  return { client: httpClient(), eventSource: webSocketJobEventSource(), demo: false };
}
```

`web/src/app/AppRoot.tsx`:
```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { App } from "./App";
import type { Composition } from "./composition";
import { ApiClientProvider } from "../api/context";
import { JobEventSourceProvider } from "../jobs/eventSourceContext";
import { DemoBanner } from "../demo/DemoBanner";

export function AppRoot({ composition }: { composition: Composition }) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <ApiClientProvider client={composition.client}>
        <JobEventSourceProvider source={composition.eventSource}>
          {composition.demo ? <DemoBanner /> : null}
          <App />
        </JobEventSourceProvider>
      </ApiClientProvider>
    </QueryClientProvider>
  );
}
```

Replace `web/src/main.tsx` with the mode-aware entry point:
```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppRoot } from "./app/AppRoot";
import { createComposition } from "./app/composition";
import { appMode } from "./config/mode";

const rootElement = document.getElementById("root");

if (rootElement) {
  createRoot(rootElement).render(
    <StrictMode>
      <AppRoot composition={createComposition(appMode())} />
    </StrictMode>,
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm run -w @laqieer/fecreator-web test -- DemoBanner composition AppRoot`
Expected: PASS. The demo `AppRoot` test proves banner presence, in-memory job creation, a terminal timeline, and zero `fetch`/`WebSocket` calls; the local test proves the real HTTP client composes with no banner.

- [ ] **Step 5: Commit**

```bash
git add web/src/demo/DemoBanner.tsx web/src/demo/DemoBanner.test.tsx web/src/app/composition.ts web/src/app/composition.test.ts web/src/app/AppRoot.tsx web/src/app/AppRoot.test.tsx web/src/main.tsx
git commit -m "feat(web): compose demo vs local app at the entry point

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Co-authored-by: laqieer <laqieer@126.com>"
```

---

## Task 6: Gated GitHub Pages deployment in CI

**Files:**
- Modify: `.github/workflows/ci.yml`
- Test: `tests/test_ci_pages_workflow.py`

**Interfaces:**
- Consumes: the `build:demo` script (T1) and the demo build output at `src/fecreator/_web`.
- Produces: a `deploy-pages` job gated to `push` + `main`, needing `[python, web, package]`, with least-privilege permissions, the `github-pages` environment, `pages` concurrency, and the three official Pages actions; plus static asset-path checks in the `web` job (root-relative) and the `deploy-pages` job (`/FECreator/`).

- [ ] **Step 1: Write the failing test**

`tests/test_ci_pages_workflow.py`:
```python
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _deploy_job() -> dict:
    return _workflow()["jobs"]["deploy-pages"]


def test_deploy_pages_is_gated_to_main_pushes() -> None:
    condition = _deploy_job()["if"]
    assert "github.event_name == 'push'" in condition
    assert "github.ref == 'refs/heads/main'" in condition


def test_pull_requests_can_never_deploy() -> None:
    condition = _deploy_job()["if"]
    assert "pull_request" not in condition
    assert "github.event_name == 'push'" in condition


def test_deploy_pages_needs_all_build_and_test_jobs() -> None:
    assert set(_deploy_job()["needs"]) == {"python", "web", "package"}


def test_deploy_pages_builds_demo_and_uploads_the_web_bundle() -> None:
    steps = _deploy_job()["steps"]
    run_text = " ".join(step.get("run", "") for step in steps)
    assert "build:demo" in run_text
    upload = next(s for s in steps if s.get("uses", "").startswith("actions/upload-pages-artifact@"))
    assert upload["with"]["path"] == "src/fecreator/_web"


def test_deploy_pages_uses_official_pages_actions() -> None:
    uses = [step.get("uses", "") for step in _deploy_job()["steps"]]
    assert any(u.startswith("actions/configure-pages@") for u in uses)
    assert any(u.startswith("actions/upload-pages-artifact@") for u in uses)
    assert any(u.startswith("actions/deploy-pages@") for u in uses)


def test_deploy_pages_has_least_privilege_permissions() -> None:
    assert _deploy_job()["permissions"] == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }


def test_deploy_pages_targets_pages_environment_with_serial_concurrency() -> None:
    job = _deploy_job()
    assert job["environment"]["name"] == "github-pages"
    assert job["concurrency"]["group"] == "pages"
    assert job["concurrency"]["cancel-in-progress"] is False


def test_web_job_verifies_root_relative_assets() -> None:
    steps = _workflow()["jobs"]["web"]["steps"]
    run_text = " ".join(step.get("run", "") for step in steps)
    assert '"/assets/' in run_text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_ci_pages_workflow.py -q`
Expected: FAIL — `KeyError: 'deploy-pages'` (the job does not exist yet).

- [ ] **Step 3: Update the workflow**

Add a top-level least-privilege default immediately after the `on:` block in `.github/workflows/ci.yml` (job-level blocks override it):
```yaml
permissions:
  contents: read
```

Add a root-relative asset check to the `web` job, immediately after its existing `- run: npm run -w @laqieer/fecreator-web build` step:
```yaml
      - name: Verify the local build emits root-relative assets
        run: |
          grep -q '"/assets/' src/fecreator/_web/index.html
          if grep -q '/FECreator/' src/fecreator/_web/index.html; then
            echo "Local build must not use the demo base path"; exit 1
          fi
```

Append the `deploy-pages` job at the end of the `jobs:` map:
```yaml
  deploy-pages:
    if: ${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}
    needs: [python, web, package]
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pages: write
      id-token: write
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    concurrency:
      group: pages
      cancel-in-progress: false
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
      - run: npm ci
      - run: npm run -w @laqieer/fecreator-web build:demo
      - name: Verify the demo build emits /FECreator/ assets
        run: |
          grep -q '"/FECreator/assets/' src/fecreator/_web/index.html
          if grep -q '"/assets/' src/fecreator/_web/index.html; then
            echo "Demo build must use the /FECreator/ base path"; exit 1
          fi
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: src/fecreator/_web
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_ci_pages_workflow.py -q`
Expected: PASS (8 tests). If `pytest` reports `ModuleNotFoundError: yaml`, ensure the dev env is installed (`pip install -e ".[dev]"`); PyYAML ships with the `uvicorn[standard]` production dependency.

- [ ] **Step 5: Validate the workflow file parses and the guard is intact**

Run:
```
python -c "import yaml,pathlib; yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text()); print('workflow parses')"
npm ci
npm run -w @laqieer/fecreator-web build
python -m build
twine check dist/*
```
Expected: `workflow parses`; the local build then `python -m build` succeed — confirming the Hatch `_web` guard still passes because the local build emits `src/fecreator/_web/index.html`.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/ci.yml tests/test_ci_pages_workflow.py
git commit -m "ci: deploy the demo to GitHub Pages on gated main pushes

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Co-authored-by: laqieer <laqieer@126.com>"
```

---

## Task 7: Documentation

**Files:**
- Modify: `README.md`
- Create: `docs/github-pages-demo.md`

**Interfaces:**
- Consumes: the demo URL, banner copy (T5), build script `build:demo` (T1), and CI job (T6).
- Produces: user-facing documentation of the demo, its limitations, and its URL. Copy stays consistent with the `DemoBanner` text.

- [ ] **Step 1: Add the Live demo section to `README.md`**

Append to `README.md`:
```markdown
## Live demo

A static, sample-data demo is published to GitHub Pages:

**<https://laqieer.github.io/FECreator/>**

The demo runs entirely in the browser with built-in synthetic data. It **cannot**
generate, validate, upload, or save real assets, makes no HTTP or WebSocket calls,
and resets whenever the page is reloaded. See
[`docs/github-pages-demo.md`](docs/github-pages-demo.md) for build modes and
limitations.
```

- [ ] **Step 2: Create `docs/github-pages-demo.md`**

```markdown
# GitHub Pages demo

The FECreator web workspace builds in two explicit modes.

| Mode  | Env var                     | Vite base     | API client       | Job events            | Packaged into `_web` for FastAPI |
| ----- | --------------------------- | ------------- | ---------------- | --------------------- | -------------------------------- |
| Local | (unset)                     | `/`           | `httpClient()`   | real WebSocket        | yes                              |
| Demo  | `VITE_FE_CREATOR_MODE=demo` | `/FECreator/` | `demoClient()`   | in-memory timer source | published to Pages               |

## URL

<https://laqieer.github.io/FECreator/>

## What the demo is

A static, deterministic preview composed at the entry point (`web/src/main.tsx` →
`createComposition(appMode())`). A persistent, accessible banner states that the
page uses sample data. Sample content is synthetic and repository-owned
(`web/src/demo/fixtures.ts`).

## Limitations

- Runs entirely in the browser; there is no FastAPI backend, provider, or file access.
- Makes **no** `fetch`, `WebSocket`, upload, or File System Access calls.
- Cannot generate, validate, upload, or save real assets.
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
```

- [ ] **Step 3: Verify the docs reference the URL and limitations**

Run:
```
node -e "const t=require('fs').readFileSync('docs/github-pages-demo.md','utf8'); for (const s of ['laqieer.github.io/FECreator/','VITE_FE_CREATOR_MODE=demo','cannot generate, validate, upload, or save','resets']) if(!t.includes(s)) throw new Error('missing: '+s); console.log('docs OK')"
node -e "const t=require('fs').readFileSync('README.md','utf8'); if(!t.includes('https://laqieer.github.io/FECreator/')) throw new Error('README missing demo URL'); console.log('README OK')"
```
Expected: prints `docs OK` then `README OK`.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/github-pages-demo.md
git commit -m "docs: document the GitHub Pages demo and its limitations

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Co-authored-by: laqieer <laqieer@126.com>"
```

---

## Final full-gate verification

Run the complete gate locally before opening the PR. The demo build must run last only for a
Pages check; re-run the local build before packaging so the wheel ships root-relative assets.

```
# Python
pip install -e ".[dev]"
ruff check .
ruff format --check .
mypy src
pytest -q
# Web
npm ci
npm run -w @laqieer/fecreator-web typecheck
npm run -w @laqieer/fecreator-web lint
npm run -w @laqieer/fecreator-web test
npm run -w @laqieer/fecreator-web build
npm run -w @laqieer/fecreator-web build:demo
# Package (local build must precede python -m build)
npm run -w @laqieer/fecreator-web build
python -m build
twine check dist/*
```
Expected: every command passes. Open a pull request into `main`; require `python`, `web`, and
`package` to be green. On merge to `main`, the gated `deploy-pages` job publishes the demo.

---

## Self-review

**1. Spec coverage**

- **Build modes / base (§Build modes):** Task 1 — `VITE_FE_CREATOR_MODE`, `resolveBase`, `.env.demo`, `--mode demo`, base `/FECreator/` vs `/`.
- **Persistent accessible banner (§Build modes, §Application composition):** Task 5 — `DemoBanner` (`role="note"`), rendered only when `composition.demo`, composed at the entry point so `App` stays environment-unaware.
- **Demo API client (§Components, §Error handling):** Task 2 — `demoClient()` implements all six `ApiClient` methods; deterministic registries/jobs/validation; rejects invalid ids and malformed manifests; reload resets (fresh client = fresh state).
- **Demo event source (§Components):** Tasks 3–4 — injected `JobEventSource`; demo emits deterministic events on timers, follows the connection/cleanup contract, and never constructs a `WebSocket`; the real WebSocket transport is unchanged.
- **Application composition / data flow (§Application composition, §Data flow):** Task 5 — `createComposition` selects `httpClient()`+WebSocket source or `demoClient()`+demo source; components reuse the existing review-workbench UI; no demo action leaves the browser; nothing persists.
- **CI deployment (§CI deployment):** Task 6 — `deploy-pages` gated to `main` pushes; `needs: [python, web, package]`; Node 22 + `npm ci`; `build:demo`; `upload-pages-artifact` of `src/fecreator/_web`; `deploy-pages` to `github-pages`; permissions `contents: read`/`pages: write`/`id-token: write`; PRs never deploy.
- **Error handling (§Error handling):** Task 2 (fail-closed ids/manifests, no network fallback), Task 4 (demo failures reuse the same visible error state via the shared hook), Task 1 (no API URL inferred from `window.location`; the demo composes no HTTP client at all).
- **Security & privacy (§Security and privacy):** Tasks 2/4/5 — no embedded URLs/credentials/tokens; demo never calls `fetch`/`WebSocket`/File APIs/upload; synthetic repository-owned content; banner prevents mistaking the demo for a live service. Asserted by `composition.test.ts` and `AppRoot.test.tsx` (`fetch`/`WebSocket` spies never called).
- **Testing (§Testing):** banner shown (T5); deterministic registries/jobs (T2); in-memory create/select (T2, T5); simulated timeline reaches terminal (T4, T5); `fetch`/`WebSocket` never called in demo (T5, composition/AppRoot); malformed inputs fail closed (T2); local app composes real clients (T5 local test, unchanged `App.test.tsx`); demo build assets under `/FECreator/` and local build root-relative (T1 Step 5 + T6 CI grep steps + `test_ci_pages_workflow.py`); CI gated / PR cannot deploy (T6).
- **Non-goals:** No FastAPI/provider hosting, no localhost bridge, no remote API/CORS, no persistence, no published assets, no replacement of the local app — nothing in any task introduces these.

**2. Placeholder scan:** No TBD/TODO. Every code and test step contains complete, runnable content; every command lists an expected output.

**3. Type consistency:** `AppMode`/`DEMO_MODE` (T1) are used verbatim by `mode.ts`, `composition.ts`. `JobEventConnection`/`JobEventSource` (T3) are consumed identically by `webSocketEventSource.ts`, `demoJobEventSource.ts`, `eventSourceContext.tsx`, `composition.ts`, and the refactored `useJobEvents`. `useJobEvents(jobId)` drops `baseUrl` consistently across the hook, `App.tsx` (already base-less), and the updated tests. `demoTimeline`/`demoProviders` (T2) are the exact symbols imported by Task 4 and `demoClient`. `Composition { client; eventSource; demo }` (T5) matches its consumers in `AppRoot`/`main`/tests. `createComposition(mode: AppMode)` is called with `appMode()` in `main.tsx`. CI job/key names (`deploy-pages`, `needs`, `permissions`, `environment`, `concurrency`, `build:demo`, `src/fecreator/_web`) match `tests/test_ci_pages_workflow.py` exactly.
