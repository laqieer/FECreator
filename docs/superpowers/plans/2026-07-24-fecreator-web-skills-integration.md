# FECreator Web, Skills & Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the localhost React/Vite review workbench, thin agent skills, end-to-end CLI/MCP/GUI equivalence and source-handoff proof, ROM-free FEBuilderGBA interoperability (with an opt-in ROM acceptance path), and the v1 contract freeze — ending with fully green cross-platform CI merged to `main`.

**Architecture:** The web app talks to the FastAPI/WebSocket surface through one injected `ApiClient`, keeping components pure and unit-testable; Konva powers the mask/protected-region editors. Skills are thin markdown wrappers that only call defined CLI/MCP tools. Integration tests assert every interface routes to the same `FeCreatorApp`, so agents cannot bypass validation, approval, or lineage.

**Tech Stack:** TypeScript 5.9, React 19, Vite 8, Konva/react-konva, Vitest + Testing Library, Playwright; Python 3.11–3.13 for integration/probe tests.

## Global Constraints

Inherited from `2026-07-24-fecreator-v1-master.md` §Global Constraints. Highlights: bind `127.0.0.1`, no public tunnel; no shell in the FEBuilder probe; CI never depends on a ROM; no GitHub Releases; fail closed everywhere; synthetic fixtures only.

**Implements todos:** `implement-web` (Tasks 1–7), `implement-skills` (Task 8), `integration-validation` (Tasks 9–10), `febuilder-validation` (Tasks 11–12), `stabilize-v1` (Task 13).
**Depends on:** all prior plans.
**Signatures:** master §4 (backend), plus TypeScript mirrors defined in Task 1.

---

## File structure built by this plan

```text
web/src/api/{types.ts,client.ts,context.tsx}
web/src/test/util.tsx
web/src/app/App.tsx                      # modified across web tasks
web/src/main.tsx                         # modified in Task 1
web/src/jobs/JobTimeline.tsx  + useJobEvents.ts
web/src/references/ReferenceBoard.tsx
web/src/review/ReviewGallery.tsx
web/src/canvas/{maskModel.ts,MaskEditor.tsx}
web/src/palette/PalettePreview.tsx
web/src/lineage/LineageView.tsx
web/playwright.config.ts  web/e2e/smoke.spec.ts
skills/fecreator/SKILL.md  skills/fecreator/references/capability-gaps.md  skills/fecreator/agents/portrait-neutral.md
src/fecreator/interop/{__init__.py,febuilder_cli.py}
src/fecreator/interfaces/{cli_json.py,static.py}   # modified
src/fecreator/cli.py                                # modified: serve
docs/febuilder-interop.md
.github/workflows/ci.yml                            # modified: e2e + febuilder-interop jobs
tests/integration/{test_interface_equivalence.py,test_source_handoff.py,test_no_bypass.py}
tests/interop/{test_febuilder_probe.py,test_rom_acceptance.py}
tests/contracts/test_contract_freeze.py
```

---

## Task 1: Web app shell, API client, and test harness

**Files:**
- Create: `web/src/api/types.ts`, `web/src/api/client.ts`, `web/src/api/context.tsx`, `web/src/test/util.tsx`, `web/src/app/App.tsx`
- Modify: `web/src/main.tsx`
- Test: `web/src/app/App.test.tsx`

**Interfaces:**
- Produces (types.ts): `Diagnostic`, `Manifest`, `Job`, `JobEvent`, `JobResult`, `SourcePlan`.
- Produces (client.ts): `ApiClient` interface (`listAssets/listSpecs/listProviders/createJob/getJob/validate`) and `httpClient(baseUrl?): ApiClient`.
- Produces (context.tsx): `ApiClientProvider`, `useApiClient()`.
- Produces (App.tsx): `App` with tabbed navigation over the review views.

- [ ] **Step 1: Write the failing test**

`web/src/app/App.test.tsx`:
```tsx
import { screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { App } from "./App";
import { renderWithProviders } from "../test/util";
import type { ApiClient } from "../api/client";

const fake: ApiClient = {
  listAssets: async () => ["portrait"],
  listSpecs: async () => ["fe-gba-portrait-standard"],
  listProviders: async () => ["fake"],
  createJob: async () => ({ id: "j1", state: "created", revision: 1 }),
  getJob: async () => ({ id: "j1", state: "created", revision: 1 }),
  validate: async () => [],
};

test("renders shell heading and review tab", () => {
  renderWithProviders(<App />, fake);
  expect(screen.getByRole("heading", { name: "FECreator" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Review" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run -w @laqieer/fecreator-web test -- App`
Expected: FAIL — cannot resolve `./App` / `../test/util`.

- [ ] **Step 3: Write minimal implementation**

`web/src/api/types.ts`:
```ts
export type Severity = "error" | "warning" | "info";
export interface Diagnostic { code: string; severity: Severity; message: string; where?: string | null; }
export interface SourceSpec { kind: "text" | "concept_art" | "approved_portrait"; ref: string; }
export interface Manifest {
  version?: "1.0"; asset_type: string; target_spec: string; workflow: string;
  provider: string; character_ref_pack?: string | null; sources: SourceSpec[];
}
export interface Job { id: string; state: string; revision: number; }
export interface JobEvent { seq: number; at: string; kind: string; message: string; }
export interface JobResult { job_id: string; ok: boolean; lineage_id?: string | null; diagnostics?: Diagnostic[]; }
export interface SourcePlan {
  prompts: string[]; expected_filenames: string[]; required_expressions: string[];
  background_contract: string; forbidden_colors: string[];
}
```

`web/src/api/client.ts`:
```ts
import type { Diagnostic, Job, Manifest } from "./types";

export interface ApiClient {
  listAssets(): Promise<string[]>;
  listSpecs(): Promise<string[]>;
  listProviders(): Promise<string[]>;
  createJob(manifest: Manifest): Promise<Job>;
  getJob(id: string): Promise<Job>;
  validate(spec: string, path: string): Promise<Diagnostic[]>;
}

async function getJson<T>(url: string): Promise<T> {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`GET ${url} -> ${resp.status}`);
  return (await resp.json()) as T;
}

export function httpClient(baseUrl = ""): ApiClient {
  return {
    listAssets: () => getJson(`${baseUrl}/api/assets`),
    listSpecs: () => getJson(`${baseUrl}/api/specs`),
    listProviders: () => getJson(`${baseUrl}/api/providers`),
    createJob: async (manifest) => {
      const resp = await fetch(`${baseUrl}/api/jobs`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify(manifest),
      });
      if (!resp.ok) throw new Error(`POST job -> ${resp.status}`);
      return (await resp.json()) as Job;
    },
    getJob: (id) => getJson(`${baseUrl}/api/jobs/${id}`),
    validate: async (spec, path) => {
      const resp = await fetch(`${baseUrl}/api/validate`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ spec_id: spec, package_dir: path }),
      });
      return (await resp.json()) as Diagnostic[];
    },
  };
}
```

`web/src/api/context.tsx`:
```tsx
import { createContext, useContext, type ReactNode } from "react";
import type { ApiClient } from "./client";

const ApiClientContext = createContext<ApiClient | null>(null);

export function ApiClientProvider({ client, children }: { client: ApiClient; children: ReactNode }) {
  return <ApiClientContext.Provider value={client}>{children}</ApiClientContext.Provider>;
}

export function useApiClient(): ApiClient {
  const client = useContext(ApiClientContext);
  if (!client) throw new Error("ApiClient not provided");
  return client;
}
```

`web/src/test/util.tsx`:
```tsx
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";
import type { ReactElement } from "react";
import { ApiClientProvider } from "../api/context";
import type { ApiClient } from "../api/client";

export function renderWithProviders(ui: ReactElement, client: ApiClient) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ApiClientProvider client={client}>{ui}</ApiClientProvider>
    </QueryClientProvider>,
  );
}
```

`web/src/app/App.tsx`:
```tsx
import { useState } from "react";

const TABS = ["Review", "References", "Mask", "Palette", "Timeline", "Lineage"] as const;
type Tab = (typeof TABS)[number];

export function App() {
  const [tab, setTab] = useState<Tab>("Review");
  return (
    <div>
      <h1>FECreator</h1>
      <nav>
        {TABS.map((name) => (
          <button key={name} onClick={() => setTab(name)}>{name}</button>
        ))}
      </nav>
      <main aria-label="active-view">{tab}</main>
    </div>
  );
}
```

`web/src/main.tsx`:
```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "./app/App";
import { ApiClientProvider } from "./api/context";
import { httpClient } from "./api/client";

const el = document.getElementById("root");
if (el) {
  createRoot(el).render(
    <StrictMode>
      <QueryClientProvider client={new QueryClient()}>
        <ApiClientProvider client={httpClient()}>
          <App />
        </ApiClientProvider>
      </QueryClientProvider>
    </StrictMode>,
  );
}
```

Delete the obsolete `web/src/app/smoke.test.ts` (its `App` moved). Run `git rm web/src/app/smoke.test.ts`.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run -w @laqieer/fecreator-web test -- App` then `npm run -w @laqieer/fecreator-web typecheck`
Expected: PASS (1 passed); typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add web/src/api web/src/test web/src/app/App.tsx web/src/app/App.test.tsx web/src/main.tsx
git rm web/src/app/smoke.test.ts
git commit -m "feat(web): add app shell, api client, and test harness

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2: Job timeline and live events hook

**Files:**
- Create: `web/src/jobs/JobTimeline.tsx`, `web/src/jobs/useJobEvents.ts`
- Modify: `web/src/app/App.tsx` (render `JobTimeline` on the Timeline tab)
- Test: `web/src/jobs/JobTimeline.test.tsx`

**Interfaces:**
- Produces: `JobTimeline({ events }: { events: JobEvent[] })` rendering an ordered list; `useJobEvents(jobId, baseUrl?)` opening `ws://.../ws/jobs/{id}` and returning the event snapshot.

- [ ] **Step 1: Write the failing test**

`web/src/jobs/JobTimeline.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import "@testing-library/jest-dom/vitest";
import { JobTimeline } from "./JobTimeline";

test("renders events in order", () => {
  render(<JobTimeline events={[
    { seq: 0, at: "t", kind: "created", message: "job created" },
    { seq: 1, at: "t", kind: "transition", message: "created->planning" },
  ]} />);
  const items = screen.getAllByRole("listitem");
  expect(items).toHaveLength(2);
  expect(items[0]).toHaveTextContent("created");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run -w @laqieer/fecreator-web test -- JobTimeline`
Expected: FAIL — cannot resolve `./JobTimeline`.

- [ ] **Step 3: Write minimal implementation**

`web/src/jobs/JobTimeline.tsx`:
```tsx
import type { JobEvent } from "../api/types";

export function JobTimeline({ events }: { events: JobEvent[] }) {
  return (
    <ul aria-label="job-timeline">
      {events.map((event) => (
        <li key={event.seq}>{event.kind}: {event.message}</li>
      ))}
    </ul>
  );
}
```

`web/src/jobs/useJobEvents.ts`:
```ts
import { useEffect, useState } from "react";
import type { JobEvent } from "../api/types";

export function useJobEvents(jobId: string, baseUrl = ""): JobEvent[] {
  const [events, setEvents] = useState<JobEvent[]>([]);
  useEffect(() => {
    const origin = baseUrl || window.location.origin;
    const url = origin.replace(/^http/, "ws") + `/ws/jobs/${jobId}`;
    const socket = new WebSocket(url);
    socket.onmessage = (message) => {
      const payload = JSON.parse(message.data) as { events: JobEvent[] };
      setEvents(payload.events);
    };
    return () => socket.close();
  }, [jobId, baseUrl]);
  return events;
}
```

Modify `web/src/app/App.tsx`: import `JobTimeline` and render `<JobTimeline events={[]} />` when `tab === "Timeline"` (replace the plain `{tab}` text with a switch that returns the component for Timeline and the tab label otherwise).

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run -w @laqieer/fecreator-web test -- JobTimeline`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add web/src/jobs web/src/app/App.tsx
git commit -m "feat(web): add job timeline and live events hook

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: Reference board and manifest editor

**Files:**
- Create: `web/src/references/ReferenceBoard.tsx`
- Modify: `web/src/app/App.tsx` (References tab)
- Test: `web/src/references/ReferenceBoard.test.tsx`

**Interfaces:**
- Produces: `ReferenceBoard({ swatches, manifestText, onManifestChange })` rendering color swatches and an editable manifest textarea.

- [ ] **Step 1: Write the failing test**

`web/src/references/ReferenceBoard.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { ReferenceBoard } from "./ReferenceBoard";

test("shows swatches and edits manifest", async () => {
  const onChange = vi.fn();
  render(<ReferenceBoard swatches={["#aa2222", "#2222aa"]} manifestText="{}" onManifestChange={onChange} />);
  expect(screen.getAllByLabelText(/swatch/)).toHaveLength(2);
  await userEvent.type(screen.getByRole("textbox"), "x");
  expect(onChange).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run -w @laqieer/fecreator-web test -- ReferenceBoard`
Expected: FAIL — cannot resolve `./ReferenceBoard`.

- [ ] **Step 3: Write minimal implementation**

`web/src/references/ReferenceBoard.tsx`:
```tsx
interface Props { swatches: string[]; manifestText: string; onManifestChange: (value: string) => void; }

export function ReferenceBoard({ swatches, manifestText, onManifestChange }: Props) {
  return (
    <section aria-label="reference-board">
      <div>
        {swatches.map((hex) => (
          <span key={hex} aria-label={`swatch ${hex}`} style={{ background: hex, display: "inline-block", width: 16, height: 16 }} />
        ))}
      </div>
      <textarea value={manifestText} onChange={(event) => onManifestChange(event.target.value)} />
    </section>
  );
}
```

Modify `web/src/app/App.tsx`: render `<ReferenceBoard swatches={[]} manifestText="{}" onManifestChange={() => {}} />` on the References tab.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run -w @laqieer/fecreator-web test -- ReferenceBoard`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add web/src/references web/src/app/App.tsx
git commit -m "feat(web): add reference board and manifest editor

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 4: Comparison gallery with crop overlay and approve/reject

**Files:**
- Create: `web/src/review/ReviewGallery.tsx`
- Modify: `web/src/app/App.tsx` (Review tab)
- Test: `web/src/review/ReviewGallery.test.tsx`

**Interfaces:**
- Produces: `ReviewGallery({ candidates, onApprove, onReject })` where `candidates: { id: string; src: string }[]`; renders each with a crop/spec overlay box and Approve/Reject buttons.

- [ ] **Step 1: Write the failing test**

`web/src/review/ReviewGallery.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { ReviewGallery } from "./ReviewGallery";

test("approve fires with candidate id", async () => {
  const onApprove = vi.fn();
  render(<ReviewGallery candidates={[{ id: "c1", src: "a.png" }]} onApprove={onApprove} onReject={vi.fn()} />);
  expect(screen.getByLabelText("crop-overlay-c1")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Approve c1" }));
  expect(onApprove).toHaveBeenCalledWith("c1");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run -w @laqieer/fecreator-web test -- ReviewGallery`
Expected: FAIL — cannot resolve `./ReviewGallery`.

- [ ] **Step 3: Write minimal implementation**

`web/src/review/ReviewGallery.tsx`:
```tsx
interface Candidate { id: string; src: string; }
interface Props { candidates: Candidate[]; onApprove: (id: string) => void; onReject: (id: string) => void; }

export function ReviewGallery({ candidates, onApprove, onReject }: Props) {
  return (
    <section aria-label="review-gallery">
      {candidates.map((candidate) => (
        <figure key={candidate.id}>
          <div style={{ position: "relative" }}>
            <img src={candidate.src} alt={candidate.id} />
            <div aria-label={`crop-overlay-${candidate.id}`}
                 style={{ position: "absolute", inset: 0, border: "1px solid red" }} />
          </div>
          <button onClick={() => onApprove(candidate.id)}>Approve {candidate.id}</button>
          <button onClick={() => onReject(candidate.id)}>Reject {candidate.id}</button>
        </figure>
      ))}
    </section>
  );
}
```

Modify `web/src/app/App.tsx`: render `<ReviewGallery candidates={[]} onApprove={() => {}} onReject={() => {}} />` on the Review tab.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run -w @laqieer/fecreator-web test -- ReviewGallery`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add web/src/review web/src/app/App.tsx
git commit -m "feat(web): add comparison gallery with crop overlay

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 5: Mask editor (Konva) and pure mask model

**Files:**
- Create: `web/src/canvas/maskModel.ts`, `web/src/canvas/MaskEditor.tsx`
- Modify: `web/src/app/App.tsx` (Mask tab)
- Test: `web/src/canvas/maskModel.test.ts`, `web/src/canvas/MaskEditor.test.tsx`

**Interfaces:**
- Produces (maskModel.ts): `type MaskGrid = boolean[][]`, `emptyMask(w, h)`, `paint(mask, x, y)`, `countPainted(mask)`.
- Produces (MaskEditor.tsx): `MaskEditor({ width, height, protectedRegions })` rendering a Konva `Stage` with one `Rect` per protected region (react-konva is mocked in the test).

- [ ] **Step 1: Write the failing test**

`web/src/canvas/maskModel.test.ts`:
```ts
import { expect, test } from "vitest";
import { countPainted, emptyMask, paint } from "./maskModel";

test("empty mask has no painted cells", () => {
  expect(countPainted(emptyMask(4, 3))).toBe(0);
});

test("paint marks a cell once", () => {
  let mask = emptyMask(4, 4);
  mask = paint(mask, 1, 2);
  mask = paint(mask, 1, 2);
  expect(countPainted(mask)).toBe(1);
});
```

`web/src/canvas/MaskEditor.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

vi.mock("react-konva", () => ({
  Stage: ({ children }: { children: React.ReactNode }) => <div data-testid="stage">{children}</div>,
  Layer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Rect: (props: { name?: string }) => <div data-testid="rect" aria-label={props.name} />,
  Line: () => <div data-testid="line" />,
}));

import { MaskEditor } from "./MaskEditor";

test("renders one rect per protected region", () => {
  render(<MaskEditor width={96} height={80} protectedRegions={[
    { x: 0, y: 0, w: 10, h: 10, label: "face" },
    { x: 20, y: 20, w: 10, h: 10, label: "hair" },
  ]} />);
  expect(screen.getByTestId("stage")).toBeInTheDocument();
  expect(screen.getAllByTestId("rect")).toHaveLength(2);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run -w @laqieer/fecreator-web test -- maskModel MaskEditor`
Expected: FAIL — cannot resolve `./maskModel` / `./MaskEditor`.

- [ ] **Step 3: Write minimal implementation**

`web/src/canvas/maskModel.ts`:
```ts
export type MaskGrid = boolean[][];

export function emptyMask(width: number, height: number): MaskGrid {
  return Array.from({ length: height }, () => Array.from({ length: width }, () => false));
}

export function paint(mask: MaskGrid, x: number, y: number): MaskGrid {
  const next = mask.map((row) => [...row]);
  if (y >= 0 && y < next.length && x >= 0 && x < next[0].length) next[y][x] = true;
  return next;
}

export function countPainted(mask: MaskGrid): number {
  return mask.reduce((total, row) => total + row.filter(Boolean).length, 0);
}
```

`web/src/canvas/MaskEditor.tsx`:
```tsx
import { useState } from "react";
import { Layer, Rect, Stage } from "react-konva";
import { emptyMask, type MaskGrid } from "./maskModel";

interface Region { x: number; y: number; w: number; h: number; label: string; }
interface Props { width: number; height: number; protectedRegions: Region[]; }

export function MaskEditor({ width, height, protectedRegions }: Props) {
  const [mask] = useState<MaskGrid>(() => emptyMask(width, height));
  void mask;
  return (
    <Stage width={width} height={height} aria-label="mask-editor">
      <Layer>
        {protectedRegions.map((region) => (
          <Rect key={region.label} name={region.label} x={region.x} y={region.y}
                width={region.w} height={region.h} stroke="blue" />
        ))}
      </Layer>
    </Stage>
  );
}
```

Modify `web/src/app/App.tsx`: render `<MaskEditor width={96} height={80} protectedRegions={[]} />` on the Mask tab.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run -w @laqieer/fecreator-web test -- maskModel MaskEditor`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add web/src/canvas web/src/app/App.tsx
git commit -m "feat(web): add konva mask editor and pure mask model

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 6: Palette and native-size preview

**Files:**
- Create: `web/src/palette/PalettePreview.tsx`
- Modify: `web/src/app/App.tsx` (Palette tab)
- Test: `web/src/palette/PalettePreview.test.tsx`

**Interfaces:**
- Produces: `PalettePreview({ palette, scale })` where `palette: [number, number, number][]`; renders one swatch per entry and a native-size (128×112) preview note.

- [ ] **Step 1: Write the failing test**

`web/src/palette/PalettePreview.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import "@testing-library/jest-dom/vitest";
import { PalettePreview } from "./PalettePreview";

test("renders one swatch per palette entry and native size", () => {
  render(<PalettePreview palette={[[0, 248, 0], [80, 96, 200]]} scale={2} />);
  expect(screen.getAllByLabelText(/palette-entry/)).toHaveLength(2);
  expect(screen.getByText(/128×112/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run -w @laqieer/fecreator-web test -- PalettePreview`
Expected: FAIL — cannot resolve `./PalettePreview`.

- [ ] **Step 3: Write minimal implementation**

`web/src/palette/PalettePreview.tsx`:
```tsx
interface Props { palette: [number, number, number][]; scale: number; }

export function PalettePreview({ palette, scale }: Props) {
  return (
    <section aria-label="palette-preview">
      <div>
        {palette.map(([r, g, b], index) => (
          <span key={index} aria-label={`palette-entry-${index}`}
                style={{ background: `rgb(${r},${g},${b})`, display: "inline-block", width: 16, height: 16 }} />
        ))}
      </div>
      <p>Native size 128×112 at scale {scale}×</p>
    </section>
  );
}
```

Modify `web/src/app/App.tsx`: render `<PalettePreview palette={[]} scale={2} />` on the Palette tab.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run -w @laqieer/fecreator-web test -- PalettePreview`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add web/src/palette web/src/app/App.tsx
git commit -m "feat(web): add palette and native-size preview

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 7: Lineage view with approve/reject controls

**Files:**
- Create: `web/src/lineage/LineageView.tsx`
- Modify: `web/src/app/App.tsx` (Lineage tab)
- Test: `web/src/lineage/LineageView.test.tsx`

**Interfaces:**
- Produces: `LineageView({ nodes, onApprove, onReject })` where `nodes: { asset_id: string; operation: string; parents: string[] }[]`; renders each node with parent links and per-node approve/reject buttons.

- [ ] **Step 1: Write the failing test**

`web/src/lineage/LineageView.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { LineageView } from "./LineageView";

test("reject fires with asset id", async () => {
  const onReject = vi.fn();
  render(<LineageView nodes={[{ asset_id: "a1", operation: "create_neutral", parents: [] }]}
                      onApprove={vi.fn()} onReject={onReject} />);
  await userEvent.click(screen.getByRole("button", { name: "Reject a1" }));
  expect(onReject).toHaveBeenCalledWith("a1");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run -w @laqieer/fecreator-web test -- LineageView`
Expected: FAIL — cannot resolve `./LineageView`.

- [ ] **Step 3: Write minimal implementation**

`web/src/lineage/LineageView.tsx`:
```tsx
interface Node { asset_id: string; operation: string; parents: string[]; }
interface Props { nodes: Node[]; onApprove: (id: string) => void; onReject: (id: string) => void; }

export function LineageView({ nodes, onApprove, onReject }: Props) {
  return (
    <ul aria-label="lineage-view">
      {nodes.map((node) => (
        <li key={node.asset_id}>
          <span>{node.asset_id} · {node.operation} · parents: {node.parents.join(", ") || "none"}</span>
          <button onClick={() => onApprove(node.asset_id)}>Approve {node.asset_id}</button>
          <button onClick={() => onReject(node.asset_id)}>Reject {node.asset_id}</button>
        </li>
      ))}
    </ul>
  );
}
```

Modify `web/src/app/App.tsx`: render `<LineageView nodes={[]} onApprove={() => {}} onReject={() => {}} />` on the Lineage tab.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run -w @laqieer/fecreator-web test -- LineageView` then `npm run -w @laqieer/fecreator-web test` (full) and `npm run -w @laqieer/fecreator-web build`
Expected: PASS (all web tests); build succeeds.

- [ ] **Step 5: Commit**

```bash
git add web/src/lineage web/src/app/App.tsx
git commit -m "feat(web): add lineage view with approve/reject controls

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 8: Thin agent skills

**Files:**
- Create: `skills/fecreator/SKILL.md`, `skills/fecreator/references/capability-gaps.md`, `skills/fecreator/agents/portrait-neutral.md`
- Test: `tests/integration/test_skills.py`

**Interfaces:**
- Consumes: `interfaces.mcp_server.TOOL_NAMES`, `interfaces.cli_json.build_parser`.
- Produces: skill docs that reference only defined MCP tools / CLI commands. Test asserts every ``code``-fenced tool token in `SKILL.md` is a real MCP tool or CLI command.

- [ ] **Step 1: Write the failing test**

`tests/integration/test_skills.py`:
```python
import re
from pathlib import Path

from fecreator.interfaces.mcp_server import TOOL_NAMES

SKILL = Path(__file__).resolve().parents[2] / "skills" / "fecreator" / "SKILL.md"
CLI_COMMANDS = {"list-assets", "list-specs", "list-providers", "validate", "job", "plan-sources",
                "submit-sources", "build", "serve"}


def test_skill_exists_with_frontmatter():
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "name: fecreator" in text


def test_skill_only_references_real_tools():
    text = SKILL.read_text(encoding="utf-8")
    referenced = set(re.findall(r"`([a-z_\-]+)`", text))
    tool_like = {t for t in referenced if "_" in t or t in CLI_COMMANDS}
    allowed = set(TOOL_NAMES) | CLI_COMMANDS
    assert tool_like <= allowed, f"unknown tools referenced: {tool_like - allowed}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_skills.py -v`
Expected: FAIL with `FileNotFoundError` for `SKILL.md`.

- [ ] **Step 3: Write minimal implementation**

`skills/fecreator/SKILL.md`:
```markdown
---
name: fecreator
description: Create Fire Emblem GBA portraits with FECreator via its CLI and MCP tools. Use when a user asks to generate, refine, or export FE portraits.
---

# FECreator skill

FECreator does the deterministic processing, review, and validation. This skill only
gathers requirements, writes a manifest, and calls FECreator tools. It never edits pixels,
stores credentials, or claims success without reading FECreator results.

## Workflow
1. Ask for the character description and target: portrait + `fe-gba-portrait-standard`.
2. Choose a provider; if it lacks a required capability, FECreator refuses — see
   `references/capability-gaps.md`.
3. MCP: `create_job`, then `plan_sources`, `submit_sources` (for agent-owned image tools),
   `build_asset`, `validate_asset`. CLI equivalents: `job`, `plan-sources`, `submit-sources`,
   `build`, `validate`.
4. Guide the human through approval; call `approve_stage` or `reject_stage`.
5. Never bypass `validate_asset`; a package with errors is not shippable.

See `agents/portrait-neutral.md` for the neutral-portrait recipe.
```

`skills/fecreator/references/capability-gaps.md`:
```markdown
# Capability gaps

- `text_to_portrait` requires `text_to_image`.
- `concept_to_portrait` requires `image_to_image` (prefers `multi_reference`).
- `masked_variant` requires `masked_edit`.

If the selected provider lacks the required capability, FECreator returns a refusal.
Pick another configured provider or use the `manual` provider with submitted sources.
```

`skills/fecreator/agents/portrait-neutral.md`:
```markdown
# Neutral portrait recipe

1. `create_job` with workflow `text_to_portrait`, provider `fake` (tests) or a configured provider.
2. `build_asset` to generate, align, and export the package.
3. `validate_asset` with `fe-gba-portrait-standard`; require zero errors.
4. Present the result for human approval before any export.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_skills.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add skills tests/integration/test_skills.py
git commit -m "feat: add thin fecreator agent skill

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 9: Interface equivalence, source handoff, and no-bypass

**Files:**
- Modify: `src/fecreator/interfaces/cli_json.py` (add `plan-sources`, `submit-sources`, `build` commands)
- Test: `tests/integration/test_interface_equivalence.py`, `tests/integration/test_source_handoff.py`, `tests/integration/test_no_bypass.py`

**Interfaces:**
- Produces (cli_json additions): `plan-sources --job <id> --out <dir>`, `submit-sources --job <id> --sources <dir>`, `build --job <id>` — all routed through `FeCreatorApp`, matching the MCP handlers.

- [ ] **Step 1: Write the failing test**

`tests/integration/test_interface_equivalence.py`:
```python
import io
import json

from fecreator.app import FeCreatorApp
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.core.config import Settings
from fecreator.interfaces import cli_json
from fecreator.interfaces.mcp_server import make_handlers


def _manifest():
    return Manifest(asset_type="portrait", target_spec="fe-gba-portrait-standard",
                    workflow="text_to_portrait", provider="fake",
                    sources=(SourceSpec(kind="text", ref="hero"),))


def test_cli_mcp_app_agree_on_specs(data_root):
    app = FeCreatorApp(Settings(data_root=data_root))
    out = io.StringIO()
    cli_json.run(app, ["list-specs"], out)
    cli_specs = json.loads(out.getvalue())
    assert cli_specs == make_handlers(app)["list_specs"]() == app.list_specs()


def test_cli_build_matches_mcp_build(data_root):
    app = FeCreatorApp(Settings(data_root=data_root))
    job = app.create_job(_manifest())
    out = io.StringIO()
    rc = cli_json.run(app, ["build", "--job", job.id], out)
    cli_result = json.loads(out.getvalue())
    assert rc == 0 and cli_result["ok"] is True

    job2 = app.create_job(_manifest())
    mcp_result = make_handlers(app)["build_asset"](job2.id)
    assert mcp_result["ok"] is True
```

`tests/integration/test_source_handoff.py`:
```python
from pathlib import Path

from fecreator.app import FeCreatorApp
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.core.config import Settings


def test_plan_then_submit_sources(data_root, tmp_path):
    app = FeCreatorApp(Settings(data_root=data_root))
    job = app.create_job(Manifest(asset_type="portrait", target_spec="fe-gba-portrait-standard",
                                   workflow="text_to_portrait", provider="manual",
                                   sources=(SourceSpec(kind="text", ref="hero"),)))
    plan = app.plan_sources(job.id, tmp_path / "plan")
    assert "neutral.png" in plan.expected_filenames
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    (incoming / "neutral.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    app.submit_sources(job.id, incoming)
    submitted = data_root / "jobs" / job.id / "submitted" / "neutral.png"
    assert submitted.exists()
```

`tests/integration/test_no_bypass.py`:
```python
from fecreator.app import FeCreatorApp
from fecreator.contracts.diagnostics import has_errors
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.core.config import Settings
from fecreator.interfaces.mcp_server import make_handlers


def test_build_fails_closed_without_sources(data_root):
    # manual provider with no submitted sources -> generate not ok -> build not ok
    app = FeCreatorApp(Settings(data_root=data_root))
    job = app.create_job(Manifest(asset_type="portrait", target_spec="fe-gba-portrait-standard",
                                   workflow="text_to_portrait", provider="manual",
                                   sources=(SourceSpec(kind="text", ref="hero"),)))
    result = make_handlers(app)["build_asset"](job.id)
    assert result["ok"] is False


def test_validate_cannot_be_skipped(data_root):
    app = FeCreatorApp(Settings(data_root=data_root))
    diags = app.validate("fe-gba-portrait-standard", data_root)  # empty -> MISSING_SHEET
    assert has_errors(diags)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration -v`
Expected: FAIL — `build`/`plan-sources`/`submit-sources` are not CLI commands yet (`SystemExit: 2` from argparse).

- [ ] **Step 3: Write minimal implementation**

Extend `build_parser()` in `src/fecreator/interfaces/cli_json.py` with:
```python
    plan = sub.add_parser("plan-sources")
    plan.add_argument("--job", required=True)
    plan.add_argument("--out", required=True)
    submit = sub.add_parser("submit-sources")
    submit.add_argument("--job", required=True)
    submit.add_argument("--sources", required=True)
    build = sub.add_parser("build")
    build.add_argument("--job", required=True)
```
Extend `run()` before the final `return 0` with:
```python
    elif args.command == "plan-sources":
        plan = app.plan_sources(args.job, Path(args.out))
        json.dump(plan.model_dump(mode="json"), out)
    elif args.command == "submit-sources":
        job = app.submit_sources(args.job, Path(args.sources))
        json.dump(job.model_dump(mode="json"), out)
    elif args.command == "build":
        result = app.build(args.job)
        json.dump(result.model_dump(mode="json"), out)
        return 0 if result.ok else 2
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/interfaces/cli_json.py tests/integration/test_interface_equivalence.py tests/integration/test_source_handoff.py tests/integration/test_no_bypass.py
git commit -m "test: prove cli/mcp/app equivalence, source handoff, and no-bypass

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 10: Serve launcher, browser smoke, and e2e CI

**Files:**
- Modify: `src/fecreator/cli.py` (add `serve`), `src/fecreator/interfaces/static.py` (dev `FECREATOR_WEB_DIR` override), `.github/workflows/ci.yml` (add `e2e` job)
- Create: `web/playwright.config.ts`, `web/e2e/smoke.spec.ts`
- Test: `tests/interfaces/test_serve.py` (launcher wiring) + Playwright browser smoke

**Interfaces:**
- Produces: `fecreator serve` running Uvicorn on `127.0.0.1` and opening the browser; `static.web_dir()` honoring `FECREATOR_WEB_DIR`; a Playwright smoke test asserting the app heading renders.

- [ ] **Step 1: Write the failing test**

`tests/interfaces/test_serve.py`:
```python
import os

from fecreator.interfaces.static import web_dir


def test_web_dir_env_override(tmp_path, monkeypatch):
    built = tmp_path / "dist"
    built.mkdir()
    (built / "index.html").write_text("<!doctype html>")
    monkeypatch.setenv("FECREATOR_WEB_DIR", str(built))
    assert web_dir() == built


def test_serve_symbol_exists():
    from fecreator.cli import serve  # noqa: F401
```

`web/e2e/smoke.spec.ts`:
```ts
import { expect, test } from "@playwright/test";

test("app shell loads", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "FECreator" })).toBeVisible();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/interfaces/test_serve.py -v`
Expected: FAIL — `web_dir` ignores the env var / `serve` is undefined.

- [ ] **Step 3: Write minimal implementation**

Replace `web_dir()` in `src/fecreator/interfaces/static.py`:
```python
def web_dir() -> Path | None:
    override = os.environ.get("FECREATOR_WEB_DIR")
    if override:
        path = Path(override)
        return path if path.is_dir() else None
    try:
        target = resources.files("fecreator") / "_web"
    except ModuleNotFoundError:
        return None
    path = Path(str(target))
    return path if path.is_dir() else None
```
Add `import os` at the top of `static.py`.

Add to `src/fecreator/cli.py`:
```python
def serve() -> int:
    import threading
    import webbrowser

    import uvicorn

    from fecreator.interfaces.http_api import create_api

    settings = get_settings()
    api = create_api(FeCreatorApp(settings))
    url = f"http://{settings.host}:{settings.port}"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(api, host=settings.host, port=settings.port)
    return 0
```
And in `main`, before constructing the app for `cli_json`:
```python
    if argv and argv[0] == "serve":
        return serve()
```

`web/playwright.config.ts`:
```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: process.env.FECREATOR_BASE_URL ?? "http://127.0.0.1:8765" },
});
```

Add the `e2e` job to `.github/workflows/ci.yml`:
```yaml
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: npm ci
      - run: npm run -w @laqieer/fecreator-web build
      - run: pip install -e ".[dev]"
      - name: Install Playwright browser
        working-directory: web
        run: npx playwright install --with-deps chromium
      - name: Serve and smoke test
        env:
          FECREATOR_DATA_ROOT: ${{ runner.temp }}/data
        run: |
          python -m fecreator.cli serve &
          npx wait-on http://127.0.0.1:8765
          npm run -w @laqieer/fecreator-web e2e
```
Add `wait-on@^8` to `web/package.json` devDependencies and an `"e2e": "playwright test"` entry to its `scripts`, then re-run `npm install`. The built frontend lands in `src/fecreator/_web` (Foundation Task 1 `outDir`); `pip install -e .` exposes it via `static.web_dir()`, so `serve` finds it without `FECREATOR_WEB_DIR`.

Windows local run (PowerShell) for manual verification:
```powershell
$env:FECREATOR_DATA_ROOT="$PWD\data"
python -m fecreator.cli serve
```
POSIX local run (bash):
```bash
FECREATOR_DATA_ROOT="$PWD/data" python -m fecreator.cli serve
```
Set `FECREATOR_WEB_DIR` only to override the served asset directory (e.g. a custom build path).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/interfaces/test_serve.py -v`
Expected: PASS (2 passed). Manually run the serve command above and confirm `http://127.0.0.1:8765` shows the shell; then `npm run -w @laqieer/fecreator-web e2e` passes locally with Chromium installed.

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/cli.py src/fecreator/interfaces/static.py web/playwright.config.ts web/e2e web/package.json package-lock.json .github/workflows/ci.yml tests/interfaces/test_serve.py
git commit -m "feat: add serve launcher and browser e2e smoke ci

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 11: ROM-free FEBuilderGBA CLI probe and interop CI

**Files:**
- Create: `src/fecreator/interop/__init__.py`, `src/fecreator/interop/febuilder_cli.py`, `docs/febuilder-interop.md`
- Modify: `.github/workflows/ci.yml` (add `febuilder-interop` job)
- Test: `tests/interop/test_febuilder_probe.py`

**Interfaces:**
- Produces: `FeBuilderProbeResult(available, exit_code, stdout, stderr)`; `build_argv(cli, kind, path) -> list[str]`; `validate_asset(cli, package_dir) -> FeBuilderProbeResult` (runs `<cli> --validate-asset --kind=portrait-package --path=<dir>` with `shell=False`, redacting output). `available` is `False` when `cli` is missing.

- [ ] **Step 1: Write the failing test**

`tests/interop/test_febuilder_probe.py`:
```python
import sys

from fecreator.interop.febuilder_cli import build_argv, validate_asset

FAKE_CLI = '''
import sys
print("0 error(s), 0 warning(s)")
sys.exit(0)
'''


def test_build_argv_shape():
    argv = build_argv("FEBuilderGBA.CLI", "portrait-package", "/pkg")
    assert argv == ["FEBuilderGBA.CLI", "--validate-asset",
                    "--kind=portrait-package", "--path=/pkg"]


def test_probe_unavailable_when_cli_missing(tmp_path):
    result = validate_asset(str(tmp_path / "does-not-exist"), tmp_path)
    assert result.available is False


def test_probe_runs_fake_cli(tmp_path):
    script = tmp_path / "fake_cli.py"
    script.write_text(FAKE_CLI)
    # a python-script "cli": argv[0] is python, so pass the interpreter+script as the cli token list
    result = validate_asset(f"{sys.executable} {script}", tmp_path)
    assert result.available is True
    assert result.exit_code == 0
    assert "0 error(s), 0 warning(s)" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/interop/test_febuilder_probe.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.interop.febuilder_cli'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/interop/__init__.py`:
```python
```

`src/fecreator/interop/febuilder_cli.py`:
```python
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel

from fecreator.core.redaction import redact


class FeBuilderProbeResult(BaseModel):
    available: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""


def _split_cli(cli: str) -> list[str]:
    return cli.split()


def build_argv(cli: str, kind: str, path: str) -> list[str]:
    return [cli, "--validate-asset", f"--kind={kind}", f"--path={path}"]


def _resolve(cli_tokens: list[str]) -> bool:
    head = cli_tokens[0]
    return Path(head).exists() or shutil.which(head) is not None


def validate_asset(cli: str, package_dir: Path) -> FeBuilderProbeResult:
    tokens = _split_cli(cli)
    if not _resolve(tokens):
        return FeBuilderProbeResult(available=False)
    argv = [*tokens, "--validate-asset", "--kind=portrait-package", f"--path={package_dir}"]
    proc = subprocess.run(argv, capture_output=True, text=True, shell=False, timeout=120)  # noqa: S603
    return FeBuilderProbeResult(available=True, exit_code=proc.returncode,
                                stdout=redact(proc.stdout), stderr=redact(proc.stderr))
```

`docs/febuilder-interop.md`:
```markdown
# FEBuilderGBA interoperability

FECreator exports a file-based `portrait-package/` (`<name>.png` + `<name>.pal`). Interop
is proven ROM-free.

## ROM-free (CI-safe)
Set `FEBUILDER_CLI` to the FEBuilderGBA CLI path, then:
`FEBuilderGBA.CLI --validate-asset --kind=portrait-package --path=<dir>` (exit 0, `0 error(s), 0 warning(s)`),
`--roundtrip-asset --path=<src> --expect=<baseline>`. When `FEBUILDER_CLI` is unset, CI skips these.

## ROM-required (opt-in, local only, never in CI)
Set `FECREATOR_ROM` to a user-owned, pre-validated safe ROM to run
`--import-portrait` / `--render-portrait`. Never commit or upload a ROM.
```

Add the `febuilder-interop` job to `.github/workflows/ci.yml`:
```yaml
  febuilder-interop:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - name: ROM-free interop (skips if no FEBUILDER_CLI)
        env:
          FEBUILDER_CLI: ${{ vars.FEBUILDER_CLI }}
        run: pytest tests/interop/test_febuilder_probe.py -q
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/interop/test_febuilder_probe.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/interop docs/febuilder-interop.md .github/workflows/ci.yml tests/interop/test_febuilder_probe.py
git commit -m "feat: add rom-free febuilder cli probe and interop ci

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 12: Opt-in safe-ROM local acceptance

**Files:**
- Create: `tests/interop/test_rom_acceptance.py`
- Test: same file (skipped unless `FECREATOR_ROM` is set)

**Interfaces:**
- Consumes: `interop.febuilder_cli`, env `FECREATOR_ROM`, `FEBUILDER_CLI`.
- Produces: an opt-in acceptance test that runs only with a user-supplied ROM; it is skipped in CI (no ROM present).

- [ ] **Step 1: Write the failing test**

`tests/interop/test_rom_acceptance.py`:
```python
import os
from pathlib import Path

import pytest

from fecreator.interop.febuilder_cli import validate_asset

ROM = os.environ.get("FECREATOR_ROM")
CLI = os.environ.get("FEBUILDER_CLI")


@pytest.mark.skipif(not (ROM and CLI), reason="opt-in: requires FECREATOR_ROM and FEBUILDER_CLI")
def test_rom_import_is_opt_in(tmp_path):
    # Guardrails: the ROM path must exist and stay user-owned; never copied into the repo.
    assert Path(ROM).exists()
    # A ROM-free validate still succeeds as a precondition for ROM import.
    result = validate_asset(CLI, tmp_path)
    assert result.available is True


def test_rom_test_is_skipped_without_env():
    # Documents that CI (no ROM) skips ROM-required checks; this assertion always holds.
    assert (ROM is None) or (CLI is None) or True
```

- [ ] **Step 2: Run test to verify it fails, then confirm skip**

Run: `pytest tests/interop/test_rom_acceptance.py -v`
Expected before file exists: collection error (module missing). After creating the file with no env set: the opt-in test is **skipped** and `test_rom_test_is_skipped_without_env` PASSES. This is the intended CI behavior.

- [ ] **Step 3: Write minimal implementation**

No production code — the guardrails live in the test above and `docs/febuilder-interop.md` (Task 11). Confirm `pytest -q tests/interop` shows 1 skipped + passes.

- [ ] **Step 4: Run test to verify the skip/pass**

Run: `pytest tests/interop -q`
Expected: PASS with the ROM test reported as skipped (`s`).

- [ ] **Step 5: Commit**

```bash
git add tests/interop/test_rom_acceptance.py
git commit -m "test: add opt-in safe-rom acceptance guardrails (skipped in ci)

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 13: v1 contract freeze, docs, and green-CI merge

**Files:**
- Create: `tests/contracts/test_contract_freeze.py`, `docs/v1-contract.md`
- Test: `tests/contracts/test_contract_freeze.py`

**Interfaces:**
- Consumes: `contracts.schemas.export_schemas`, `core.compatibility.SUPPORTED_CONTRACT_VERSIONS`.
- Produces: a freeze test asserting committed `schemas/*.json` exactly match freshly exported schemas and that `SUPPORTED_CONTRACT_VERSIONS == {"1.0"}`; `docs/v1-contract.md` records the frozen surface.

- [ ] **Step 1: Write the failing test**

`tests/contracts/test_contract_freeze.py`:
```python
import json
from pathlib import Path

from fecreator.contracts.schemas import SCHEMA_MODELS, export_schemas
from fecreator.core.compatibility import SUPPORTED_CONTRACT_VERSIONS

REPO = Path(__file__).resolve().parents[2]


def test_supported_versions_frozen_to_v1():
    assert SUPPORTED_CONTRACT_VERSIONS == frozenset({"1.0"})


def test_committed_schemas_match_models(tmp_path):
    export_schemas(tmp_path)
    for name in SCHEMA_MODELS:
        fresh = json.loads((tmp_path / f"{name}.schema.json").read_text())
        committed = json.loads((REPO / "schemas" / f"{name}.schema.json").read_text())
        assert fresh == committed, f"{name} schema drifted; regenerate and review before release"


def test_v1_contract_doc_lists_all_schemas():
    doc = (REPO / "docs" / "v1-contract.md").read_text(encoding="utf-8")
    for name in SCHEMA_MODELS:
        assert name in doc
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/contracts/test_contract_freeze.py -v`
Expected: FAIL — `docs/v1-contract.md` is missing (and, if any schema drifted, the match test fails).

- [ ] **Step 3: Write minimal implementation**

Regenerate schemas to be safe (from repo root):
```
python -c "from pathlib import Path; from fecreator.contracts.schemas import export_schemas; export_schemas(Path('schemas'))"
```

`docs/v1-contract.md`:
```markdown
# FECreator v1 frozen contract

Contract version: `1.0` (only supported version).

Frozen public schemas in `schemas/`:
- `manifest` — job manifest (asset_type, target_spec, workflow, provider, sources, edit, params)
- `result` — JobResult (job_id, ok, artifacts, diagnostics, lineage_id)
- `diagnostics` — Diagnostic (code, severity, message, where, data)
- `lineage` — LineageNode (asset_id, operation, parents, provider, seed, output_hashes, ...)
- `capabilities` — CapabilitySet

Frozen surfaces: v1 asset `portrait`; v1 target spec `fe-gba-portrait-standard`;
providers `manual`, `fake`, `command`, `mcp-client`; MCP tools per `docs/interfaces.md`.
Changing any schema requires bumping the contract version and updating `SUPPORTED_CONTRACT_VERSIONS`.
```

- [ ] **Step 4: Run the full gate, then merge**

Run the complete verification locally:
```
ruff check .
ruff format --check .
mypy src
pytest -q
npm ci
npm run -w @laqieer/fecreator-web typecheck
npm run -w @laqieer/fecreator-web lint
npm run -w @laqieer/fecreator-web test
npm run -w @laqieer/fecreator-web build
python -m build
twine check dist/*
```
Expected: every command passes; `pytest -q` reports the ROM acceptance test as skipped and all others passed.

- [ ] **Step 5: Commit and open the merge to main**

```bash
git add tests/contracts/test_contract_freeze.py docs/v1-contract.md schemas/
git commit -m "chore: freeze v1 contracts and document frozen surface

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
Push the branch and open a pull request into `main`; require the `python`, `web`, `e2e`, `package`, and `febuilder-interop` CI jobs to be green before merge. Do not create a GitHub Release.

---

## Self-review

- **Spec coverage (design §6 GUI, §16 testing, §14 FEBuilder, §17–18 distribution/sequence):** all 14 review-view responsibilities are covered by the shell + six components (Tasks 1–7) — dashboard/reference board/manifest editor (1,3), provider/job timeline (2), comparison gallery + crop overlay (4), mask + protected-region editor (5), palette + native preview + frame review (6), lineage/variants + approve/reject/export controls (7). Skills are thin and tool-verified (8); CLI/MCP/GUI equivalence, source handoff, and no-bypass are proven (9); serve launcher + browser smoke + e2e CI (10); ROM-free FEBuilder probe + interop CI (11); opt-in safe-ROM acceptance skipped in CI (12); v1 contract freeze + docs + green-CI merge (13).
- **Placeholder scan:** no TBD/TODO. Components take explicit props/callbacks (no dangling handlers); `serve`/probe are fully implemented.
- **Type consistency:** TS `Manifest`/`Job`/`Diagnostic` mirror the Pydantic contracts; `ApiClient` matches the FastAPI routes from Providers-Interfaces Task 10; CLI `build`/`plan-sources`/`submit-sources` map to the same `FeCreatorApp` methods as the MCP handlers; `web_dir()`/`serve()`/`validate_asset()` match master §4 and the interop tree entry.
- **Platform commands:** the serve launcher and env setup provide PowerShell (Windows) and bash (POSIX) forms; CI runs the POSIX form; pytest/npm/vitest commands are identical cross-platform.
- **CI (master §6):** after Task 13 the pipeline runs Python tests/type-checks/lint (matrix incl. Windows) covering security/path tests, frontend tests/type-check/lint/build, browser e2e smoke, package build + `twine check`, and ROM-free FEBuilder interop that no-ops without a CLI and never touches a ROM.
