import "@testing-library/jest-dom/vitest";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "./App";
import { NotFoundError } from "../api/client";
import { createStubApiClient, renderWithProviders } from "../test/util";
import type { ApprovalRecord, Job, SourcePlan } from "../api/types";

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
    parent_asset_id: null,
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

test("keeps the loaded job when the queue re-selects the already selected job", async () => {
  const selectedJob: Job = { ...createdJob, id: "review-job", state: "waiting_for_review" };
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [selectedJob],
      getJob: async () => selectedJob,
    }),
  );

  const queued = await screen.findByRole("button", { name: /review-job.*waiting_for_review/i });
  expect(await screen.findByText("Selected job review-job is waiting_for_review.")).toBeInTheDocument();

  await user.click(queued);

  expect(await screen.findByText("Selected job review-job is waiting_for_review.")).toBeInTheDocument();
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

test("persists review actions and refreshes the selected job after each success", async () => {
  let job: Job = { ...createdJob, id: "review-job", state: "waiting_for_review" };
  const listJobs = vi.fn(async () => [job]);
  const getJob = vi.fn(async () => job);
  const listApprovals = vi.fn(async () =>
    job.state === "waiting_for_review"
      ? []
      : [
          {
            job_id: job.id,
            stage: "candidate",
            decision: "approved" as const,
            actor: "local-user",
            reason: null,
            at: job.updated_at,
          },
        ],
  );
  const getJobCandidate = vi.fn(async () => ({
    version: "1.0" as const,
    job_id: job.id,
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
    created_at: job.created_at,
  }));
  const approveReview = vi.fn(async () => {
    job = { ...job, state: "validating", revision: 2 };
    return {
      job_id: job.id,
      stage: "candidate",
      decision: "approved" as const,
      actor: "local-user",
      reason: null,
      at: job.updated_at,
    };
  });
  const finalizeJob = vi.fn(async () => {
    job = { ...job, state: "completed", revision: 3 };
    return { job_id: job.id, ok: true, artifacts: [], diagnostics: [], lineage_id: "review-candidate" };
  });
  class ReviewUrl extends URL {
    static createObjectURL = vi.fn(() => "blob:review-image");
    static revokeObjectURL = vi.fn();
  }
  vi.stubGlobal("URL", ReviewUrl);
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs,
      getJob,
      getJobCandidate,
      listApprovals,
      approveReview,
      finalizeJob,
    }),
  );

  await screen.findByAltText("Candidate candidate/package/portrait.png");

  await user.type(screen.getByLabelText("Reviewer name"), "local-user");
  await user.click(screen.getByRole("button", { name: /approve candidate\/package\/portrait\.png/i }));
  await waitFor(() => expect(approveReview).toHaveBeenCalledWith("review-job", "local-user"));
  expect(await screen.findByText("Selected job review-job is validating.")).toBeInTheDocument();
  expect(await screen.findByText("Latest review: approved by local-user.")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Finalize review" }));
  await waitFor(() => expect(finalizeJob).toHaveBeenCalledWith("review-job"));
  expect(await screen.findByText("Selected job review-job is completed.")).toBeInTheDocument();
  expect(approveReview.mock.invocationCallOrder[0]).toBeLessThan(finalizeJob.mock.invocationCallOrder[0]!);
  expect(listJobs.mock.calls.length).toBeGreaterThanOrEqual(3);
  expect(getJobCandidate.mock.calls.length).toBeGreaterThanOrEqual(3);
});

test("keeps a review failure visible without presenting a successful state", async () => {
  const reviewJob = { ...createdJob, id: "review-job", state: "waiting_for_review" as const };
  class ReviewUrl extends URL {
    static createObjectURL = vi.fn(() => "blob:review-image");
    static revokeObjectURL = vi.fn();
  }
  vi.stubGlobal("URL", ReviewUrl);
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [reviewJob],
      getJob: async () => reviewJob,
      getJobCandidate: async () => ({
        version: "1.0",
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
      }),
      approveReview: async () => {
        throw new Error("approval unavailable");
      },
    }),
  );

  await screen.findByAltText("Candidate candidate/package/portrait.png");

  await user.type(screen.getByLabelText("Reviewer name"), "local-user");
  await user.click(screen.getByRole("button", { name: /approve candidate\/package\/portrait\.png/i }));

  expect(await screen.findByRole("alert")).toHaveTextContent("approval unavailable");
  expect(screen.getByText("Selected job review-job is waiting_for_review.")).toBeInTheDocument();
});

test("persists a non-empty rejection reason for the selected review job", async () => {
  const reviewJob = { ...createdJob, id: "review-job", state: "waiting_for_review" as const };
  const rejectReview = vi.fn(async () => ({
    job_id: reviewJob.id,
    stage: "candidate",
    decision: "rejected" as const,
    actor: "local-user",
    reason: "bad eyes",
    at: reviewJob.updated_at,
  }));
  class ReviewUrl extends URL {
    static createObjectURL = vi.fn(() => "blob:review-image");
    static revokeObjectURL = vi.fn();
  }
  vi.stubGlobal("URL", ReviewUrl);
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [reviewJob],
      getJob: async () => reviewJob,
      getJobCandidate: async () => ({
        version: "1.0",
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
      }),
      rejectReview,
    }),
  );

  await screen.findByAltText("Candidate candidate/package/portrait.png");

  await user.type(screen.getByLabelText("Reviewer name"), "local-user");
  await user.type(
    screen.getByLabelText("Rejection reason for candidate/package/portrait.png"),
    "bad eyes",
  );
  await user.click(screen.getByRole("button", { name: /reject candidate\/package\/portrait\.png/i }));

  await waitFor(() =>
    expect(rejectReview).toHaveBeenCalledWith("review-job", "local-user", "bad eyes"),
  );
});

test("surfaces a non-throwing finalization rejection without refreshing the job", async () => {
  const reviewJob = { ...createdJob, id: "review-job", state: "waiting_for_review" as const };
  class ReviewUrl extends URL {
    static createObjectURL = vi.fn(() => "blob:review-image");
    static revokeObjectURL = vi.fn();
  }
  vi.stubGlobal("URL", ReviewUrl);
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [reviewJob],
      getJob: async () => reviewJob,
      getJobCandidate: async () => ({
        version: "1.0",
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
      }),
      finalizeJob: async () => ({
        job_id: reviewJob.id,
        ok: false,
        artifacts: [],
        diagnostics: [
          { code: "APPROVAL_MISSING", severity: "error", message: "candidate is not approved" },
        ],
        lineage_id: null,
      }),
    }),
  );

  await screen.findByAltText("Candidate candidate/package/portrait.png");

  await user.type(screen.getByLabelText("Reviewer name"), "local-user");
  await user.click(screen.getByRole("button", { name: "Finalize review" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("candidate is not approved");
  expect(screen.getByText("Selected job review-job is waiting_for_review.")).toBeInTheDocument();
});

const reviewJob: Job = { ...createdJob, id: "review-job", state: "waiting_for_review" };

const reviewCandidate = {
  version: "1.0" as const,
  job_id: reviewJob.id,
  lineage_id: "review-candidate",
  artifacts: [
    {
      role: "sheet",
      path: "candidate/package/portrait.png",
      sha256: "0".repeat(64),
      media_type: "image/png",
    },
  ],
  diagnostics: [],
  metrics: {},
  created_at: reviewJob.created_at,
};

function stubObjectUrls() {
  class ReviewUrl extends URL {
    static createObjectURL = vi.fn(() => "blob:review-image");
    static revokeObjectURL = vi.fn();
  }
  vi.stubGlobal("URL", ReviewUrl);
}

test("surfaces an approval history failure without success-shaped history", async () => {
  stubObjectUrls();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [reviewJob],
      getJob: async () => reviewJob,
      getJobCandidate: async () => reviewCandidate,
      listApprovals: async () => {
        throw new Error("approval store is locked");
      },
    }),
  );

  expect(await screen.findByText(/approval store is locked/)).toBeInTheDocument();
  expect(screen.queryByText("No review decisions recorded.")).not.toBeInTheDocument();
  expect(screen.queryByText(/Latest review/)).not.toBeInTheDocument();
});

test("treats a missing candidate as an expected empty review state", async () => {
  stubObjectUrls();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [reviewJob],
      getJob: async () => reviewJob,
      getJobCandidate: async () => {
        throw new NotFoundError("candidate for job review-job does not exist");
      },
    }),
  );

  expect(await screen.findByText("No review candidates available.")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("surfaces an unexpected candidate load failure", async () => {
  stubObjectUrls();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [reviewJob],
      getJob: async () => reviewJob,
      getJobCandidate: async () => {
        throw new Error("candidate store is corrupt");
      },
    }),
  );

  expect(await screen.findByText(/candidate store is corrupt/)).toBeInTheDocument();
});

test("keeps review controls disabled through the post-action refresh and ignores repeat clicks", async () => {
  stubObjectUrls();
  const approveGate = deferred<ApprovalRecord>();
  const refreshGate = deferred<Job>();
  let jobLoads = 0;
  const approveReview = vi.fn(() => approveGate.promise);
  const getJob = vi.fn(() => {
    jobLoads += 1;
    return jobLoads <= 1 ? Promise.resolve(reviewJob) : refreshGate.promise;
  });
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [reviewJob],
      getJob,
      getJobCandidate: async () => reviewCandidate,
      approveReview,
    }),
  );

  const approve = await screen.findByRole("button", { name: /approve candidate/i });
  await user.type(screen.getByLabelText("Reviewer name"), "local-user");
  await user.click(approve);
  await user.click(approve);
  expect(approveReview).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "Finalize review" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Retry job" })).toBeDisabled();

  approveGate.resolve({
    job_id: reviewJob.id,
    stage: "candidate",
    decision: "approved",
    actor: "local-user",
    reason: null,
    at: reviewJob.updated_at,
  });

  await waitFor(() => expect(getJob.mock.calls.length).toBeGreaterThanOrEqual(2));
  expect(screen.getByRole("button", { name: /approve candidate/i })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Finalize review" })).toBeDisabled();

  refreshGate.resolve({ ...reviewJob, state: "validating", revision: 2 });
  await waitFor(() =>
    expect(screen.getByRole("button", { name: /approve candidate/i })).toBeEnabled(),
  );
  expect(approveReview).toHaveBeenCalledTimes(1);
});

test("retries a rejected candidate and follows the retry job", async () => {
  stubObjectUrls();
  const retried: Job = { ...createdJob, id: "retry-job", parent_candidate_id: "review-candidate" };
  let listed: Job[] = [reviewJob];
  const retryJob = vi.fn(async () => {
    listed = [reviewJob, retried];
    return retried;
  });
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => listed,
      getJob: async (id) => (id === retried.id ? retried : reviewJob),
      getJobCandidate: async () => reviewCandidate,
      retryJob,
    }),
  );

  await screen.findByRole("button", { name: /approve candidate/i });
  await user.type(screen.getByLabelText("Reviewer name"), "local-user");
  await user.click(screen.getByRole("button", { name: "Retry job" }));

  await waitFor(() => expect(retryJob).toHaveBeenCalledWith("review-job", "local-user"));
  expect(await screen.findByText("Selected job retry-job is created.")).toBeInTheDocument();
});

test("does not follow a retry result when a newer job is already selected", async () => {
  stubObjectUrls();
  const otherJob: Job = { ...createdJob, id: "other-job" };
  const retried: Job = { ...createdJob, id: "retry-job" };
  const retryGate = deferred<Job>();
  const retryJob = vi.fn(() => retryGate.promise);
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [otherJob, reviewJob],
      getJob: async (id) =>
        id === reviewJob.id ? reviewJob : id === retried.id ? retried : otherJob,
      getJobCandidate: async () => reviewCandidate,
      retryJob,
    }),
  );

  await user.click(await screen.findByRole("button", { name: /review-job.*waiting_for_review/i }));
  await screen.findByText("Selected job review-job is waiting_for_review.");
  await user.type(screen.getByLabelText("Reviewer name"), "local-user");
  await user.click(screen.getByRole("button", { name: "Retry job" }));
  await waitFor(() => expect(retryJob).toHaveBeenCalledWith("review-job", "local-user"));

  await user.click(screen.getByRole("button", { name: /other-job.*created/i }));
  await screen.findByText("Selected job other-job is created.");
  retryGate.resolve(retried);

  await waitFor(() =>
    expect(screen.getByText("Selected job other-job is created.")).toBeInTheDocument(),
  );
  expect(screen.queryByText("Selected job retry-job is created.")).not.toBeInTheDocument();
});

test("does not announce panel loading without a selected job", async () => {
  const user = userEvent.setup();
  renderWithProviders(<App />, createStubApiClient({ listJobs: async () => [] }));

  await user.click(screen.getByRole("tab", { name: "Validation" }));
  expect(screen.queryByText("Validating selected job…")).not.toBeInTheDocument();
  expect(screen.getByText("Select a job to validate.")).toBeInTheDocument();

  await user.click(screen.getByRole("tab", { name: "Report" }));
  expect(screen.queryByText("Loading sanitized report…")).not.toBeInTheDocument();
  expect(screen.queryByText("Loading bundle entries…")).not.toBeInTheDocument();

  await user.click(screen.getByRole("tab", { name: "Lineage" }));
  expect(screen.queryByText("Loading lineage…")).not.toBeInTheDocument();
  expect(screen.getByText("No lineage node selected.")).toBeInTheDocument();
});

test("gives the manifest and reference-board selectors unique accessible names", async () => {
  const user = userEvent.setup();
  renderWithProviders(<App />, createStubApiClient({ listJobs: async () => [] }));

  await user.click(screen.getByRole("tab", { name: "References" }));

  expect(await screen.findByLabelText("Reference pack for new job")).toBeInTheDocument();
  expect(await screen.findByLabelText("Reference pack to inspect")).toBeInTheDocument();
  expect(screen.getByLabelText("Reference revision for new job")).toBeInTheDocument();
  expect(screen.getByLabelText("Reference revision to inspect")).toBeInTheDocument();
});
