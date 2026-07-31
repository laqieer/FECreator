import "@testing-library/jest-dom/vitest";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "./App";
import { createStubApiClient, renderWithProviders } from "../test/util";
import type { Job, JobEvent } from "../api/types";

vi.mock("react-konva", () => ({
  Stage: ({ children }: { children: React.ReactNode }) => <div data-testid="stage">{children}</div>,
  Layer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Rect: (props: { name?: string }) => <div data-testid="rect" aria-label={props.name} />,
}));

const reviewJob: Job = {
  id: "review-job",
  state: "waiting_for_review",
  manifest: {
    version: "1.0",
    asset_type: "portrait",
    target_spec: "fe-gba-portrait-standard",
    workflow: "masked_variant",
    provider: "fake",
    character_ref_pack: null,
    character_ref_pack_rev: null,
    parent_asset_id: "approved-base",
    sources: [],
    edit: { mask_path: "masks/base.png", protected_regions: [] },
    metadata: null,
    params: {},
  },
  parent_candidate_id: null,
  revision: 1,
  created_at: "2026-07-24T00:00:00+00:00",
  updated_at: "2026-07-24T00:00:00+00:00",
};

const candidate = {
  version: "1.0" as const,
  job_id: reviewJob.id,
  lineage_id: "review-candidate",
  artifacts: [
    {
      role: "portrait",
      path: "candidate/package/portrait.png",
      sha256: "0".repeat(64),
      media_type: "image/png",
    },
  ],
  diagnostics: [],
  metrics: {},
  created_at: reviewJob.created_at,
};

class ReviewUrl extends URL {
  static createObjectURL = vi.fn(() => "blob:review-image");
  static revokeObjectURL = vi.fn();
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function manualEventSource() {
  const connection = {
    onopen: null as (() => void) | null,
    onmessage: null as ((event: { data: unknown }) => void) | null,
    onerror: null as (() => void) | null,
    onclose: null as (() => void) | null,
    close: vi.fn(),
  };
  return {
    source: { connect: vi.fn(() => connection) },
    async emit(jobId: string, events: JobEvent[]) {
      await act(async () => {
        connection.onmessage?.({ data: JSON.stringify({ job_id: jobId, events }) });
      });
    },
  };
}

test("passes the entered reviewer name to approve, reject, and retry", async () => {
  vi.stubGlobal("URL", ReviewUrl);
  const approveReview = vi.fn(async () => ({
    job_id: reviewJob.id,
    stage: "candidate",
    decision: "approved" as const,
    actor: "Ada Lovelace",
    reason: null,
    at: reviewJob.updated_at,
  }));
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [reviewJob],
      getJob: async () => reviewJob,
      getJobCandidate: async () => candidate,
      approveReview,
    }),
  );

  await screen.findByAltText("Candidate candidate/package/portrait.png");
  await user.type(screen.getByLabelText("Reviewer name"), "  Ada Lovelace  ");
  await user.click(
    screen.getByRole("button", { name: /approve candidate\/package\/portrait\.png/i }),
  );

  await waitFor(() => expect(approveReview).toHaveBeenCalledWith("review-job", "Ada Lovelace"));
});

test("refuses review actions until a reviewer name is entered", async () => {
  vi.stubGlobal("URL", ReviewUrl);
  const approveReview = vi.fn();
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [reviewJob],
      getJob: async () => reviewJob,
      getJobCandidate: async () => candidate,
      approveReview,
    }),
  );

  await screen.findByAltText("Candidate candidate/package/portrait.png");
  await user.type(screen.getByLabelText("Reviewer name"), "   ");
  await user.click(
    screen.getByRole("button", { name: /approve candidate\/package\/portrait\.png/i }),
  );

  expect(approveReview).not.toHaveBeenCalled();
  expect(await screen.findByRole("alert")).toHaveTextContent("A reviewer name is required.");
});

test("does not hard-code a reviewer identity", async () => {
  vi.stubGlobal("URL", ReviewUrl);
  const rejectReview = vi.fn(async () => ({
    job_id: reviewJob.id,
    stage: "candidate",
    decision: "rejected" as const,
    actor: "Grace",
    reason: "bad eyes",
    at: reviewJob.updated_at,
  }));
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [reviewJob],
      getJob: async () => reviewJob,
      getJobCandidate: async () => candidate,
      rejectReview,
    }),
  );

  await screen.findByAltText("Candidate candidate/package/portrait.png");
  await user.type(screen.getByLabelText("Reviewer name"), "Grace");
  await user.type(
    screen.getByLabelText("Rejection reason for candidate/package/portrait.png"),
    "bad eyes",
  );
  await user.click(
    screen.getByRole("button", { name: /reject candidate\/package\/portrait\.png/i }),
  );

  await waitFor(() =>
    expect(rejectReview).toHaveBeenCalledWith("review-job", "Grace", "bad eyes"),
  );
  expect(rejectReview).not.toHaveBeenCalledWith("review-job", "local-user", "bad eyes");
});

test("keeps unsaved manifest and mask drafts across same-job event refreshes", async () => {
  vi.stubGlobal("URL", ReviewUrl);
  const events = manualEventSource();
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [reviewJob],
      getJob: async () => ({ ...reviewJob, revision: reviewJob.revision + 1 }),
      getJobCandidate: async () => candidate,
    }),
    events.source,
  );

  await screen.findByAltText("Candidate candidate/package/portrait.png");
  await user.click(screen.getByRole("tab", { name: "References" }));
  const manifestBox = await screen.findByLabelText("Manifest JSON");
  await user.clear(manifestBox);
  await user.type(manifestBox, '{{"unsaved": true}');
  expect(manifestBox).toHaveValue('{"unsaved": true}');

  await events.emit(reviewJob.id, [
    { seq: 1, at: reviewJob.updated_at, kind: "transition", message: "processing->review" },
  ]);

  expect(await screen.findByLabelText("Manifest JSON")).toHaveValue('{"unsaved": true}');
});

test("re-seeds drafts only when a different job is selected", async () => {
  vi.stubGlobal("URL", ReviewUrl);
  const otherJob: Job = {
    ...reviewJob,
    id: "other-job",
    manifest: { ...reviewJob.manifest, edit: { mask_path: "masks/other.png", protected_regions: [] } },
  };
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [otherJob, reviewJob],
      getJob: async (id) => (id === reviewJob.id ? reviewJob : otherJob),
      getJobCandidate: async () => candidate,
    }),
    manualEventSource().source,
  );

  await screen.findByText("Selected job other-job is waiting_for_review.");
  await user.click(screen.getByRole("tab", { name: "References" }));
  const manifestBox = await screen.findByLabelText("Manifest JSON");
  await user.clear(manifestBox);
  await user.type(manifestBox, "draft");

  await user.click(screen.getByRole("button", { name: /review-job.*waiting_for_review/i }));

  await waitFor(() =>
    expect(screen.getByLabelText("Manifest JSON")).toHaveValue(
      JSON.stringify(reviewJob.manifest, null, 2),
    ),
  );
});

test("keeps mask pixels, path, regions, and undo history across a same-job event refresh", async () => {
  vi.stubGlobal("URL", ReviewUrl);
  const events = manualEventSource();
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [reviewJob],
      getJob: async () => ({ ...reviewJob, revision: reviewJob.revision + 1 }),
      getJobCandidate: async () => candidate,
    }),
    events.source,
  );

  await screen.findByText(/Selected job review-job is waiting_for_review\./);
  await user.click(screen.getByRole("tab", { name: "Mask" }));
  const surface = await screen.findByLabelText("mask-paint-surface");
  surface.focus();
  await user.keyboard("{Enter}");
  await user.clear(screen.getByLabelText("Mask path"));
  await user.type(screen.getByLabelText("Mask path"), "masks/unsaved.png");
  await user.type(screen.getByLabelText("x"), "1");
  await user.type(screen.getByLabelText("y"), "2");
  await user.type(screen.getByLabelText("w"), "3");
  await user.type(screen.getByLabelText("h"), "4");
  await user.type(screen.getByLabelText("label"), "chin");
  await user.click(screen.getByRole("button", { name: "Add protected region" }));

  expect(screen.getByText("Painted mask cells: 1")).toBeInTheDocument();
  expect(screen.getByText("Protected regions: 1")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Undo mask stroke" })).toBeEnabled();

  await events.emit(reviewJob.id, [
    { seq: 1, at: reviewJob.updated_at, kind: "transition", message: "processing->review" },
  ]);

  expect(screen.getByText("Painted mask cells: 1")).toBeInTheDocument();
  expect(screen.getByText("Protected regions: 1")).toBeInTheDocument();
  expect(screen.getByLabelText("Mask path")).toHaveValue("masks/unsaved.png");
  expect(screen.getByRole("button", { name: "Undo mask stroke" })).toBeEnabled();
});

test("keeps unsaved drafts across an action-triggered same-job refresh", async () => {
  vi.stubGlobal("URL", ReviewUrl);
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [reviewJob],
      getJob: async () => ({ ...reviewJob, revision: reviewJob.revision + 1 }),
      getJobCandidate: async () => candidate,
    }),
    manualEventSource().source,
  );

  await screen.findByAltText("Candidate candidate/package/portrait.png");
  await user.click(screen.getByRole("tab", { name: "References" }));
  const manifestBox = await screen.findByLabelText("Manifest JSON");
  await user.clear(manifestBox);
  await user.type(manifestBox, "unsaved-draft");

  await user.click(screen.getByRole("tab", { name: "Review" }));
  await user.type(screen.getByLabelText("Reviewer name"), "Grace");
  await user.click(
    screen.getByRole("button", { name: /approve candidate\/package\/portrait\.png/i }),
  );
  await waitFor(() => expect(screen.queryByText(/Review action in progress/)).toBeNull());

  await user.click(screen.getByRole("tab", { name: "References" }));
  expect(await screen.findByLabelText("Manifest JSON")).toHaveValue("unsaved-draft");
});
