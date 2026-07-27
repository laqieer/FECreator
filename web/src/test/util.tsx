import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { ApiClientProvider } from "../api/context";
import type { ApiClient } from "../api/client";
import type {
  ApprovalRecord,
  BundleEntry,
  CandidateSnapshot,
  Job,
  JobResult,
  LineageNode,
  Manifest,
  ReferencePack,
  Report,
  SourcePlan,
} from "../api/types";
import { JobEventSourceProvider } from "../jobs/eventSourceContext";
import type { JobEventSource } from "../jobs/eventSource";
import { webSocketJobEventSource } from "../jobs/webSocketEventSource";

const stubManifest: Manifest = {
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
};

const stubJob: Job = {
  id: "stub-job",
  state: "created",
  manifest: stubManifest,
  parent_candidate_id: null,
  revision: 1,
  created_at: "2026-07-24T00:00:00+00:00",
  updated_at: "2026-07-24T00:00:00+00:00",
};

const stubSourcePlan: SourcePlan = {
  prompts: [],
  reference_roles: {},
  expected_filenames: [],
  required_expressions: [],
  background_contract: "",
  forbidden_colors: [],
  submission_schema: {
    forbidden_changes: [],
    canonical_swatches: [],
    traits: {},
    provenance: "",
    rights: "",
    files: "",
  },
};

const stubCandidate: CandidateSnapshot = {
  version: "1.0",
  job_id: stubJob.id,
  lineage_id: `${stubJob.id}-candidate`,
  artifacts: [],
  diagnostics: [],
  metrics: {},
  created_at: stubJob.created_at,
};

const stubApproval: ApprovalRecord = {
  job_id: stubJob.id,
  stage: "candidate",
  decision: "approved",
  actor: "reviewer",
  reason: null,
  at: stubJob.created_at,
};

const stubJobResult: JobResult = {
  job_id: stubJob.id,
  ok: true,
  artifacts: [],
  diagnostics: [],
  lineage_id: `${stubJob.id}-export`,
};

const stubLineage: LineageNode = {
  asset_id: `${stubJob.id}-export`,
  operation: "export_spec",
  parents: [`${stubJob.id}-candidate`],
  provider: "fake",
  model: null,
  prompt: null,
  reference_pack: null,
  reference_pack_rev: null,
  seed: null,
  params: {},
  mask: null,
  protected_regions: [],
  metrics: {},
  approved_by: "reviewer",
  output_hashes: [],
  created_at: stubJob.created_at,
};

const stubReport: Report = {
  job_id: stubJob.id,
  state: "completed",
  revision: 1,
  created_at: stubJob.created_at,
  updated_at: stubJob.updated_at,
  manifest: stubManifest,
  manifest_hash: "0".repeat(64),
  approval: stubApproval,
  stages: [],
  diagnostics: [],
  lineage: [stubLineage],
  output_hashes: [],
};

const stubBundleEntry: BundleEntry = { path: "manifest.json", size_bytes: 2 };
const stubReferencePack: ReferencePack = {
  id: "hero-pack",
  revision: 1,
  source: "",
  concept_art: [],
  traits: {},
  swatches: [],
  forbidden_changes: [],
  provenance: "",
  rights: "",
};

export function createStubApiClient(overrides?: Partial<ApiClient>): ApiClient {
  return {
    listAssets: async () => ["portrait"],
    listSpecs: async () => ["fe-gba-portrait-standard"],
    listProviders: async () => ["fake"],
    listJobs: async () => [stubJob],
    createJob: async () => stubJob,
    getJob: async () => stubJob,
    getJobCandidate: async () => stubCandidate,
    listApprovals: async () => [],
    planSources: async () => stubSourcePlan,
    submitSources: async () => ({ ...stubJob, state: "waiting_for_review" }),
    validate: async () => [],
    validateJob: async () => [],
    getArtifact: async () => new Blob(["artifact"]),
    getJobReport: async () => stubReport,
    listBundleEntries: async () => [stubBundleEntry],
    getBundleFile: async () => new Blob(["{}"]),
    approveReview: async () => stubApproval,
    rejectReview: async () => ({ ...stubApproval, decision: "rejected", reason: "reason" }),
    finalizeJob: async () => stubJobResult,
    retryJob: async () => ({ ...stubJob, id: "retry-job", parent_candidate_id: `${stubJob.id}-candidate` }),
    cancelJob: async () => ({ ...stubJob, state: "cancelled" }),
    listReferencePacks: async () => ["hero-pack"],
    listReferenceHistory: async () => [stubReferencePack],
    getLineage: async () => stubLineage,
    getLineageAncestors: async () => [stubLineage],
    getLineageChildren: async () => [],
    ...overrides,
  };
}

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
