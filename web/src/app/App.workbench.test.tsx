import "@testing-library/jest-dom/vitest";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "./App";
import { createStubApiClient, renderWithProviders } from "../test/util";
import type { Job, SourcePlan } from "../api/types";

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

afterEach(() => {
  vi.unstubAllGlobals();
});

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

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((nextResolve) => {
    resolve = nextResolve;
  });
  return { promise, resolve };
}

test("keeps the newest selected job when an older load resolves last", async () => {
  const jobA = { ...createdJob, id: "job-a" };
  const jobB = { ...createdJob, id: "job-b", state: "waiting_for_review" as const };
  const jobALoad = deferred<Job>();
  const jobBLoad = deferred<Job>();
  const jobLoads = new Map<string, typeof jobALoad>([
    ["job-a", jobALoad],
    ["job-b", jobBLoad],
  ]);
  const candidateA = deferred<{
    version: "1.0";
    job_id: string;
    lineage_id: string;
    artifacts: [];
    diagnostics: [];
    metrics: Record<string, number>;
    created_at: string;
  }>();
  const candidateB = deferred<{
    version: "1.0";
    job_id: string;
    lineage_id: string;
    artifacts: [];
    diagnostics: [];
    metrics: Record<string, number>;
    created_at: string;
  }>();
  const candidateLoads = new Map([
    ["job-a", candidateA],
    ["job-b", candidateB],
  ]);
  const getJob = vi.fn((id: string) => jobLoads.get(id)!.promise);
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [jobA, jobB],
      getJob,
      getJobCandidate: (id) => candidateLoads.get(id)!.promise,
    }),
  );

  await waitFor(() => expect(getJob).toHaveBeenCalledWith("job-a"));
  await user.click(await screen.findByRole("button", { name: /job-b.*waiting_for_review/i }));
  await waitFor(() => expect(getJob).toHaveBeenCalledWith("job-b"));
  jobLoads.get("job-b")!.resolve(jobB);
  await waitFor(() => expect(candidateLoads.get("job-b")!.resolve).toBeTypeOf("function"));
  candidateB.resolve({
    version: "1.0",
    job_id: "job-b",
    lineage_id: "candidate-b",
    artifacts: [],
    diagnostics: [],
    metrics: {},
    created_at: createdJob.created_at,
  });
  expect(await screen.findByText("Selected job job-b is waiting_for_review.")).toBeInTheDocument();

  jobLoads.get("job-a")!.resolve(jobA);
  candidateA.resolve({
    version: "1.0",
    job_id: "job-a",
    lineage_id: "candidate-a",
    artifacts: [],
    diagnostics: [],
    metrics: {},
    created_at: createdJob.created_at,
  });

  await waitFor(() =>
    expect(screen.getByText("Selected job job-b is waiting_for_review.")).toBeInTheDocument(),
  );
});

test("refreshes selected job details and candidate after a persisted event", async () => {
  let selectedJob = createdJob;
  const refreshedJob = { ...createdJob, state: "waiting_for_review" as const, revision: 2 };
  const listJobs = vi.fn(async () => [selectedJob]);
  const getJob = vi.fn(async () => selectedJob);
  const getJobCandidate = vi.fn(async () => ({
    version: "1.0" as const,
    job_id: selectedJob.id,
    lineage_id: "candidate",
    artifacts: [],
    diagnostics: [],
    metrics: {},
    created_at: selectedJob.created_at,
  }));
  const connection = {
    onopen: null as (() => void) | null,
    onmessage: null as ((event: { data: unknown }) => void) | null,
    onerror: null as (() => void) | null,
    onclose: null as (() => void) | null,
    close: vi.fn(),
  };
  const events = { connect: vi.fn(() => connection) };
  renderWithProviders(
    <App />,
    createStubApiClient({ listJobs, getJob, getJobCandidate }),
    events,
  );

  expect(await screen.findByText("Selected job created-job is created.")).toBeInTheDocument();
  selectedJob = refreshedJob;
  act(() => {
    connection.onmessage?.({
      data: JSON.stringify({
        job_id: createdJob.id,
        events: [{ seq: 1, at: createdJob.updated_at, kind: "state", message: "ready" }],
      }),
    });
  });

  expect(
    await screen.findByText("Selected job created-job is waiting_for_review."),
  ).toBeInTheDocument();
  expect(listJobs.mock.calls.length).toBeGreaterThanOrEqual(2);
  expect(getJob.mock.calls.length).toBeGreaterThanOrEqual(2);
  expect(getJobCandidate.mock.calls.length).toBeGreaterThanOrEqual(2);
});

test("keeps source planning errors visible until planning succeeds", async () => {
  const planSources = vi
    .fn<() => Promise<SourcePlan>>()
    .mockRejectedValueOnce(new Error("plan unavailable"))
    .mockResolvedValueOnce({
      prompts: [],
      reference_roles: {},
      expected_filenames: [],
      required_expressions: [],
      background_contract: "transparent",
      forbidden_colors: [],
      submission_schema: {
        forbidden_changes: [],
        canonical_swatches: [],
        traits: {},
        provenance: "",
        rights: "",
        files: "PNG",
      },
    });
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [createdJob],
      getJob: async () => createdJob,
      planSources,
    }),
  );

  await screen.findByText("Selected job created-job is created.");
  await user.click(screen.getByRole("button", { name: "Plan sources" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("plan unavailable");

  await user.click(screen.getByRole("button", { name: "Plan sources" }));
  await waitFor(() => expect(screen.queryByText("plan unavailable")).not.toBeInTheDocument());
});

test("loads review images through the selected job artifact API", async () => {
  const reviewJob = { ...createdJob, id: "review-job", state: "waiting_for_review" as const };
  const getArtifact = vi.fn(async () => new Blob(["image"], { type: "image/png" }));
  class ReviewUrl extends URL {
    static createObjectURL = vi.fn(() => "blob:review-image");
    static revokeObjectURL = vi.fn();
  }
  vi.stubGlobal("URL", ReviewUrl);
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [reviewJob],
      getJob: async () => reviewJob,
      getJobCandidate: async () => ({
        version: "1.0",
        job_id: reviewJob.id,
        lineage_id: "candidate",
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
      }),
      getArtifact,
    }),
  );

  expect(
    await screen.findByAltText("Candidate candidate/package/portrait.png"),
  ).toHaveAttribute("src", "blob:review-image");
  expect(getArtifact).toHaveBeenCalledWith("review-job", "candidate/package/portrait.png");
});
