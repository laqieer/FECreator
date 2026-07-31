import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { JobQueue } from "./JobQueue";
import type { Job, Manifest } from "../api/types";

const manifest: Manifest = {
  version: "1.0",
  asset_type: "portrait",
  target_spec: "fe-gba-portrait-standard",
  workflow: "text_to_portrait",
  provider: "fake",
  character_ref_pack: null,
  character_ref_pack_rev: null,
  parent_asset_id: null,
  sources: [],
  edit: null,
  metadata: null,
  params: {},
};

const jobs: Job[] = [
  {
    id: "created-job",
    state: "created",
    manifest,
    parent_candidate_id: null,
    revision: 1,
    created_at: "2026-07-24T00:00:00+00:00",
    updated_at: "2026-07-24T00:00:00+00:00",
  },
  { ...manifestJob("review-job"), state: "waiting_for_review" },
];

function manifestJob(id: string): Job {
  return {
    id,
    state: "created",
    manifest,
    parent_candidate_id: null,
    revision: 1,
    created_at: "2026-07-24T00:00:00+00:00",
    updated_at: "2026-07-24T00:00:00+00:00",
  };
}

test("selects a persisted job from the accessible queue", async () => {
  const onSelect = vi.fn();
  const user = userEvent.setup();

  render(<JobQueue jobs={jobs} selectedJobId={null} loading={false} error={null} onSelect={onSelect} />);

  await user.click(screen.getByRole("button", { name: /review-job.*waiting_for_review/i }));

  expect(onSelect).toHaveBeenCalledWith("review-job");
});

test("announces loading, errors, and an empty queue", () => {
  const { rerender } = render(
    <JobQueue jobs={[]} selectedJobId={null} loading error={null} onSelect={() => undefined} />,
  );
  expect(screen.getByRole("status")).toHaveTextContent("Loading jobs");

  rerender(<JobQueue jobs={[]} selectedJobId={null} loading={false} error="offline" onSelect={() => undefined} />);
  expect(screen.getByRole("alert")).toHaveTextContent("offline");

  rerender(<JobQueue jobs={[]} selectedJobId={null} loading={false} error={null} onSelect={() => undefined} />);
  expect(screen.getByText("No persisted jobs yet.")).toBeInTheDocument();
});
