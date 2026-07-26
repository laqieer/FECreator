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

  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(readonly url: string) {
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
    listJobs: async () => [],
    createJob: async () => makeJob("job 7/alpha", "created"),
    getJob: async (id) => makeJob(id, "created"),
    ...overrides,
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  MockWebSocket.instances = [];
});

test("creates a manifest job and streams its selected timeline", async () => {
  vi.stubGlobal("WebSocket", MockWebSocket);
  const createJob = vi.fn(async () => makeJob("job 7/alpha", "created"));
  const user = userEvent.setup();
  renderWithProviders(<App />, createClient({ createJob }));

  await user.click(await screen.findByRole("button", { name: "Create job" }));
  expect(createJob).toHaveBeenCalledWith(
    expect.objectContaining({
      asset_type: "portrait",
      target_spec: "fe-gba-portrait-standard",
      workflow: "text_to_portrait",
      provider: "fake",
    }),
  );
  await screen.findByText("Selected job job 7/alpha is created.");

  await user.click(screen.getByRole("tab", { name: "Timeline" }));
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
});

test("shows job loading failures in the dashboard", async () => {
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createClient({
      listJobs: async () => [makeJob("missing-job", "created")],
      getJob: async () => {
        throw new Error("missing job");
      },
    }),
  );

  await user.click(await screen.findByRole("button", { name: /missing-job.*created/i }));

  expect(await screen.findByText("missing job", { selector: '[role="alert"]' })).toBeInTheDocument();
});

test("implements roving tabindex keyboard navigation for tabs", async () => {
  const user = userEvent.setup();
  renderWithProviders(<App />, createClient());

  const review = screen.getByRole("tab", { name: "Review" });
  const references = screen.getByRole("tab", { name: "References" });
  const report = screen.getByRole("tab", { name: "Report" });
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
  expect(report).toHaveFocus();

  await user.keyboard("{ArrowLeft}");
  expect(screen.getByRole("tab", { name: "Validation" })).toHaveFocus();

  await user.keyboard("{Home}");
  expect(review).toHaveFocus();
});
