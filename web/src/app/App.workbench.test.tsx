import "@testing-library/jest-dom/vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { App } from "./App";
import { createStubApiClient, renderWithProviders } from "../test/util";
import type { Job } from "../api/types";

const createdJob: Job = {
  id: "created-job",
  state: "created",
  manifest: {
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
  },
  parent_candidate_id: null,
  revision: 1,
  created_at: "2026-07-24T00:00:00+00:00",
  updated_at: "2026-07-24T00:00:00+00:00",
};

test("selects and loads a persisted job from the queue", async () => {
  const getJobCandidate = vi.fn(async () => ({
    version: "1.0" as const,
    job_id: "review-job",
    lineage_id: "review-candidate",
    artifacts: [],
    diagnostics: [],
    metrics: {},
    created_at: createdJob.created_at,
  }));
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [createdJob, { ...createdJob, id: "review-job", state: "waiting_for_review" }],
      getJob: async (id) => ({ ...createdJob, id, state: "waiting_for_review" }),
      getJobCandidate,
    }),
  );

  await user.click(await screen.findByRole("button", { name: /review-job.*waiting_for_review/i }));

  expect(await screen.findByText("Selected job review-job is waiting_for_review.")).toBeInTheDocument();
  expect(getJobCandidate).toHaveBeenCalledWith("review-job");
});
