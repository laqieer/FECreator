import "@testing-library/jest-dom/vitest";
import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "./App";
import { createStubApiClient, renderWithProviders } from "../test/util";
import type { ApiClient } from "../api/client";
import type { Job, Manifest } from "../api/types";

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

const manifest: Manifest = {
  version: "1.0",
  asset_type: "portrait",
  target_spec: "fe-gba-portrait-standard",
  workflow: "text_to_portrait",
  provider: "fake",
  character_ref_pack: null,
  character_ref_pack_rev: null,
  sources: [],
  edit: null,
  params: {},
};

function makeJob(id: string, state: Job["state"]): Job {
  return {
    id,
    state,
    manifest,
    parent_candidate_id: null,
    revision: 1,
    created_at: "2026-07-24T00:00:00+00:00",
    updated_at: "2026-07-24T00:00:00+00:00",
  };
}

function createClient(overrides?: Partial<ApiClient>): ApiClient {
  return createStubApiClient({
    createJob: async () => makeJob("job 7/alpha", "created"),
    getJob: async (id) => makeJob(id, "completed"),
    ...overrides,
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  MockWebSocket.instances = [];
});

test("creates a job from the timeline tab and streams a snapshot without a disconnect alert", async () => {
  vi.stubGlobal("WebSocket", MockWebSocket);
  const createJob = vi.fn(async () => makeJob("job 7/alpha", "created"));
  const getJob = vi.fn(async (id: string) => makeJob(id, "completed"));
  const client = createClient({ createJob, getJob });
  const user = userEvent.setup();

  renderWithProviders(<App />, client);

  await screen.findByText("1 asset type available");
  await user.click(screen.getByRole("tab", { name: "Timeline" }));

  expect(createJob).not.toHaveBeenCalled();
  expect(getJob).not.toHaveBeenCalled();
  expect(screen.getByText("Create or load a job to review timeline events.")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Create timeline job" }));

  expect(createJob).toHaveBeenCalledWith(
    expect.objectContaining({
      asset_type: "portrait",
      target_spec: "fe-gba-portrait-standard",
      workflow: "text_to_portrait",
      provider: "fake",
    }),
  );
  expect(await screen.findByDisplayValue("job 7/alpha")).toBeInTheDocument();
  expect(MockWebSocket.instances[0]?.url).toBe("ws://localhost:3000/ws/jobs/job%207%2Falpha");

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

  expect(await screen.findByText("Timeline snapshot complete.")).toBeInTheDocument();
  expect(screen.getByText("created")).toBeInTheDocument();
  expect(screen.queryByText("Timeline disconnected")).not.toBeInTheDocument();
});

test("loads a selected job explicitly and shows terminal state", async () => {
  vi.stubGlobal("WebSocket", MockWebSocket);
  const getJob = vi.fn(async (id: string) => makeJob(id, "completed"));
  const user = userEvent.setup();

  renderWithProviders(<App />, createClient({ getJob }));
  await user.click(screen.getByRole("tab", { name: "Timeline" }));
  await user.type(screen.getByLabelText("Job ID"), "done/job");
  await user.click(screen.getByRole("button", { name: "Load job" }));

  expect(getJob).toHaveBeenCalledWith("done/job");
  expect(MockWebSocket.instances[0]?.url).toBe("ws://localhost:3000/ws/jobs/done%2Fjob");
  expect(await screen.findByText("Job ended in completed.")).toBeInTheDocument();
});

test("shows a load error without opening a websocket", async () => {
  vi.stubGlobal("WebSocket", MockWebSocket);
  const user = userEvent.setup();

  renderWithProviders(
    <App />,
    createClient({
      getJob: async () => {
        throw new Error("missing job");
      },
    }),
  );

  await user.click(screen.getByRole("tab", { name: "Timeline" }));
  await user.type(screen.getByLabelText("Job ID"), "missing job");
  await user.click(screen.getByRole("button", { name: "Load job" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load job missing job.");
  expect(MockWebSocket.instances).toHaveLength(0);
});

test("implements roving tabindex keyboard navigation for tabs", async () => {
  const user = userEvent.setup();
  renderWithProviders(<App />, createClient());

  const review = screen.getByRole("tab", { name: "Review" });
  const references = screen.getByRole("tab", { name: "References" });
  const lineage = screen.getByRole("tab", { name: "Lineage" });
  const panel = screen.getByRole("tabpanel");

  expect(review).toHaveAttribute("tabindex", "0");
  expect(references).toHaveAttribute("tabindex", "-1");
  expect(panel).toHaveAttribute("tabindex", "0");
  expect(panel).toHaveAttribute("aria-labelledby", "review-tab");

  review.focus();
  await user.keyboard("{ArrowRight}");
  expect(references).toHaveFocus();
  expect(references).toHaveAttribute("aria-selected", "true");

  await user.keyboard("{End}");
  expect(lineage).toHaveFocus();

  await user.keyboard("{ArrowLeft}");
  expect(screen.getByRole("tab", { name: "Timeline" })).toHaveFocus();

  await user.keyboard("{Home}");
  expect(review).toHaveFocus();
});
