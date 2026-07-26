import type { ApiClient } from "../api/client";
import type {
  ApprovalRecord,
  Artifact,
  BundleEntry,
  CandidateSnapshot,
  Diagnostic,
  Job,
  LineageNode,
  Manifest,
  ReferencePack,
  Report,
  SourcePlan,
} from "../api/types";
import {
  DEMO_CREATED_AT,
  DEMO_PUBLISHED_AT,
  DEMO_REVIEWED_AT,
  demoApproval,
  demoAssets,
  demoCandidate,
  demoDiagnostics,
  demoJobsSeed,
  demoLineage,
  demoManifest,
  demoProviders,
  demoReferenceHistory,
  demoReport,
  demoSourcePlan,
  demoSpecs,
} from "./fixtures";

const demoWorkflows: readonly Manifest["workflow"][] = [
  "text_to_portrait",
  "concept_to_portrait",
  "expression_refine",
  "masked_variant",
];

interface DemoJobState {
  job: Job;
  sourcePlan: SourcePlan | null;
  candidate: CandidateSnapshot | null;
  approvals: ApprovalRecord[];
  report: Report | null;
  bundleEntries: BundleEntry[];
  artifactFiles: Map<string, Blob>;
  bundleFiles: Map<string, string>;
  retryJobId: string | null;
}

function clone<T>(value: T): T {
  return structuredClone(value);
}

function utf8Size(text: string): number {
  return new TextEncoder().encode(text).length;
}

function newBlob(text: string, type = "application/octet-stream"): Blob {
  return new Blob([text], { type });
}

const DEMO_PNG_BYTES = Uint8Array.from([
  137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 0, 1, 0, 0, 0, 1, 8,
  6, 0, 0, 0, 31, 21, 196, 137, 0, 0, 0, 13, 73, 68, 65, 84, 120, 156, 99, 144, 215, 52, 255,
  15, 0, 2, 105, 1, 127, 229, 103, 186, 4, 0, 0, 0, 0, 73, 69, 78, 68, 174, 66, 96, 130,
]);

function newPngBlob(): Blob {
  return new Blob([DEMO_PNG_BYTES], { type: "image/png" });
}

function cloneDiagnostics(): Diagnostic[] {
  return demoDiagnostics.map((diagnostic) => clone(diagnostic));
}

function sanitizeTextSource(manifest: Manifest): string {
  const source = manifest.sources.find((item) => item.kind === "text")?.ref?.trim();
  return source && source.length > 0 ? source : "a Fire Emblem GBA character portrait";
}

function manifestWithDefaults(manifest: Manifest): Manifest {
  return {
    version: "1.0",
    asset_type: manifest.asset_type,
    target_spec: manifest.target_spec,
    workflow: manifest.workflow,
    provider: manifest.provider,
    character_ref_pack: manifest.character_ref_pack,
    character_ref_pack_rev: manifest.character_ref_pack_rev,
    sources: clone(manifest.sources),
    edit: manifest.edit === null ? null : clone(manifest.edit),
    params: clone(manifest.params),
  };
}

function maybeReferencePack(manifest: Manifest): ReferencePack | null {
  if (manifest.character_ref_pack === null) {
    return null;
  }

  const pack = demoReferenceHistory.find(
    (candidate) => candidate.id === manifest.character_ref_pack,
  );
  if (!pack) {
    throw new Error(`Demo reference pack ${manifest.character_ref_pack} does not exist.`);
  }
  return pack;
}

function createSourcePlan(manifest: Manifest): SourcePlan {
  const pack = maybeReferencePack(manifest);
  const base = sanitizeTextSource(manifest);
  return {
    prompts: [`${base}, neutral expression, front-facing bust`],
    reference_roles: pack ? { concept_0: "refs/hero.png" } : {},
    expected_filenames: ["neutral.png"],
    required_expressions: ["neutral"],
    background_contract: demoSourcePlan.background_contract,
    forbidden_colors: [],
    submission_schema: {
      forbidden_changes: pack ? [...pack.forbidden_changes] : [],
      canonical_swatches: pack ? [...pack.swatches] : [],
      traits: pack ? { ...pack.traits } : {},
      provenance: pack?.provenance ?? "",
      rights: pack?.rights ?? "",
      files: demoSourcePlan.submission_schema.files,
    },
  };
}

function createCandidate(job: Job): CandidateSnapshot {
  return {
    version: "1.0",
    job_id: job.id,
    lineage_id: `${job.id}-candidate`,
    artifacts: [
      {
        role: "portrait",
        path: "candidate/package/portrait.png",
        sha256: "5".repeat(64),
        media_type: "image/png",
      },
    ],
    diagnostics: [],
    metrics: { score: 0.95 },
    created_at: DEMO_REVIEWED_AT,
  };
}

function createCandidateLineage(job: Job, candidate: CandidateSnapshot): LineageNode {
  return {
    asset_id: candidate.lineage_id,
    operation: "create_neutral",
    parents: job.parent_candidate_id === null ? [] : [job.parent_candidate_id],
    provider: job.manifest.provider,
    model: null,
    prompt: createSourcePlan(job.manifest).prompts[0],
    reference_pack: job.manifest.character_ref_pack,
    reference_pack_rev: job.manifest.character_ref_pack_rev,
    seed: 7,
    params: clone(job.manifest.params),
    mask: job.manifest.edit?.mask_path ?? null,
    protected_regions: clone(job.manifest.edit?.protected_regions ?? []),
    metrics: clone(candidate.metrics),
    approved_by: null,
    output_hashes: candidate.artifacts.map((artifact) => artifact.sha256),
    created_at: candidate.created_at,
  };
}

function createExportLineage(
  job: Job,
  candidate: CandidateSnapshot,
  actor: string,
  artifacts: Artifact[],
): LineageNode {
  return {
    asset_id: `${job.id}-export`,
    operation: "export_spec",
    parents: [candidate.lineage_id],
    provider: job.manifest.provider,
    model: null,
    prompt: null,
    reference_pack: job.manifest.character_ref_pack,
    reference_pack_rev: job.manifest.character_ref_pack_rev,
    seed: null,
    params: clone(job.manifest.params),
    mask: null,
    protected_regions: [],
    metrics: clone(candidate.metrics),
    approved_by: actor,
    output_hashes: artifacts.map((artifact) => artifact.sha256),
    created_at: DEMO_PUBLISHED_AT,
  };
}

function createApproval(
  jobId: string,
  actor: string,
  decision: ApprovalRecord["decision"],
  reason: string | null,
): ApprovalRecord {
  return {
    job_id: jobId,
    stage: "candidate",
    decision,
    actor,
    reason,
    at: DEMO_REVIEWED_AT,
  };
}

function createFinalArtifacts(): Artifact[] {
  return [
    {
      role: "portrait",
      path: "package/portrait.png",
      sha256: "6".repeat(64),
      media_type: "image/png",
    },
  ];
}

function createReport(
  job: Job,
  candidate: CandidateSnapshot,
  approval: ApprovalRecord,
  artifacts: Artifact[],
  lineage: LineageNode[],
  diagnostics: Diagnostic[],
): Report {
  return {
    job_id: job.id,
    state: "completed",
    revision: job.revision,
    created_at: job.created_at,
    updated_at: job.updated_at,
    manifest: clone(job.manifest),
    manifest_hash: "7".repeat(64),
    approval: clone(approval),
    stages: [
      {
        stage: "candidate",
        ok: true,
        artifacts: clone(candidate.artifacts),
        metrics: clone(candidate.metrics),
        diagnostics: clone(candidate.diagnostics),
      },
      {
        stage: "finalize",
        ok: true,
        artifacts: clone(artifacts),
        metrics: clone(candidate.metrics),
        diagnostics: clone(diagnostics),
      },
    ],
    diagnostics: clone(diagnostics),
    lineage: clone(lineage),
    output_hashes: Array.from(
      new Set([
        ...candidate.artifacts.map((artifact) => artifact.sha256),
        ...artifacts.map((artifact) => artifact.sha256),
      ]),
    ).sort(),
  };
}

function createBundleFiles(job: Job, report: Report, lineage: LineageNode[]): Map<string, string> {
  const manifestJson = JSON.stringify(job.manifest);
  const reportJson = JSON.stringify(report);
  const lineageJson = JSON.stringify(lineage);
  const hashesJson = JSON.stringify({ output_hashes: report.output_hashes });

  return new Map<string, string>([
    ["manifest.json", manifestJson],
    ["report.json", reportJson],
    ["lineage.json", lineageJson],
    ["hashes.json", hashesJson],
  ]);
}

function createBundleEntries(bundleFiles: Map<string, string>): BundleEntry[] {
  return Array.from(bundleFiles.entries())
    .map(([path, content]) => ({ path, size_bytes: utf8Size(content) }))
    .sort((left, right) => left.path.localeCompare(right.path));
}

function createSeedState(): DemoJobState {
  const artifactFiles = new Map<string, Blob>([
    [demoCandidate.artifacts[0]!.path, newPngBlob()],
    ["package/portrait.png", newPngBlob()],
  ]);
  const bundleFiles = new Map<string, string>([
    ["hashes.json", JSON.stringify({ output_hashes: demoReport.output_hashes })],
    ["lineage.json", JSON.stringify(demoLineage)],
    ["manifest.json", JSON.stringify(demoManifest)],
    ["report.json", JSON.stringify(demoReport)],
  ]);
  return {
    job: clone(demoJobsSeed[0]!),
    sourcePlan: clone(demoSourcePlan),
    candidate: clone(demoCandidate),
    approvals: [clone(demoApproval)],
    report: clone(demoReport),
    bundleEntries: createBundleEntries(bundleFiles),
    artifactFiles,
    bundleFiles,
    retryJobId: null,
  };
}

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
  if (typeof workflow !== "string" || !demoWorkflows.includes(workflow as Manifest["workflow"])) {
    throw new Error("Demo manifest workflow is not recognized.");
  }
  const provider: unknown = manifest.provider;
  if (typeof provider !== "string" || !demoProviders.includes(provider)) {
    throw new Error("Demo manifest provider is not registered.");
  }
  if (manifest.character_ref_pack_rev !== null && manifest.character_ref_pack === null) {
    throw new Error("Demo manifest character_ref_pack_rev requires character_ref_pack.");
  }
  maybeReferencePack(manifest);
}

export function demoClient(): ApiClient {
  const jobs = new Map<string, DemoJobState>([[demoJobsSeed[0]!.id, createSeedState()]]);
  const lineages = new Map<string, LineageNode>(demoLineage.map((node) => [node.asset_id, clone(node)]));
  let counter = 0;

  function getState(jobId: string): DemoJobState {
    const state = jobs.get(jobId);
    if (!state) {
      throw new Error(`Demo job ${jobId} does not exist.`);
    }
    return state;
  }

  function storeLineage(node: LineageNode): void {
    lineages.set(node.asset_id, clone(node));
  }

  function ensureState(jobId: string, expected: Job["state"]): DemoJobState {
    const state = getState(jobId);
    if (state.job.state !== expected) {
      throw new Error(`Demo job ${jobId} is not ${expected}.`);
    }
    return state;
  }

  function ensureNoCandidateDecision(state: DemoJobState): void {
    if (state.approvals.some((approval) => approval.stage === "candidate")) {
      throw new Error(`Demo candidate review already decided for job ${state.job.id}.`);
    }
  }

  function lineageAncestors(assetId: string): LineageNode[] {
    const seen = new Set<string>();
    const ordered: LineageNode[] = [];
    const queue = [...getLineage(assetId).parents];

    while (queue.length > 0) {
      const parentId = queue.shift()!;
      if (seen.has(parentId)) {
        continue;
      }
      seen.add(parentId);
      const parent = getLineage(parentId);
      ordered.push(parent);
      queue.push(...parent.parents);
    }

    return ordered.sort((left, right) => left.asset_id.localeCompare(right.asset_id));
  }

  function getLineage(assetId: string): LineageNode {
    const node = lineages.get(assetId);
    if (!node) {
      throw new Error(`Demo lineage asset ${assetId} does not exist.`);
    }
    return clone(node);
  }

  return {
    listAssets: async () => [...demoAssets],
    listSpecs: async () => [...demoSpecs],
    listProviders: async () => [...demoProviders],
    listJobs: async () =>
      [...jobs.values()]
        .map((state) => clone(state.job))
        .sort((left, right) => left.id.localeCompare(right.id)),
    createJob: async (manifest) => {
      assertValidManifest(manifest);
      counter += 1;
      const job: Job = {
        id: `demo-job-${counter}`,
        state: "created",
        manifest: manifestWithDefaults(manifest),
        parent_candidate_id: null,
        revision: 1,
        created_at: DEMO_CREATED_AT,
        updated_at: DEMO_CREATED_AT,
      };
      jobs.set(job.id, {
        job,
        sourcePlan: null,
        candidate: null,
        approvals: [],
        report: null,
        bundleEntries: [],
        artifactFiles: new Map(),
        bundleFiles: new Map(),
        retryJobId: null,
      });
      return clone(job);
    },
    getJob: async (id) => clone(getState(id).job),
    getJobCandidate: async (jobId) => {
      const candidate = getState(jobId).candidate;
      if (!candidate) {
        throw new Error(`Demo candidate for job ${jobId} does not exist.`);
      }
      return clone(candidate);
    },
    listApprovals: async (jobId) => clone(getState(jobId).approvals),
    planSources: async (jobId) => {
      const state = getState(jobId);
      if (state.job.state === "cancelled" || state.job.state === "completed" || state.job.state === "failed") {
        throw new Error(`Demo job ${jobId} cannot plan sources from state ${state.job.state}.`);
      }
      const plan = createSourcePlan(state.job.manifest);
      state.sourcePlan = clone(plan);
      state.job = { ...state.job, state: "waiting_for_sources", revision: state.job.revision + 1, updated_at: DEMO_REVIEWED_AT };
      return clone(plan);
    },
    submitSources: async (jobId, files) => {
      const state = ensureState(jobId, "waiting_for_sources");
      const candidate = createCandidate(state.job);
      const fileNames = files.map((file) => file.name).sort().join(", ");
      state.candidate = candidate;
      for (const artifact of candidate.artifacts) {
        state.artifactFiles.set(artifact.path, newPngBlob());
      }
      state.job = {
        ...state.job,
        state: "waiting_for_review",
        revision: state.job.revision + 1,
        updated_at: DEMO_REVIEWED_AT,
      };
      storeLineage(createCandidateLineage(state.job, candidate));
      if (state.sourcePlan === null) {
        state.sourcePlan = createSourcePlan(state.job.manifest);
      }
      state.artifactFiles.set(
        "candidate/source-summary.txt",
        newBlob(fileNames.length > 0 ? fileNames : "no files submitted", "text/plain"),
      );
      return clone(state.job);
    },
    validate: async (spec, path) => {
      if (!demoSpecs.includes(spec)) {
        throw new Error(`Demo spec ${spec} is not registered.`);
      }
      if (typeof path !== "string" || path.trim().length === 0) {
        throw new Error("Demo validation requires a package directory.");
      }
      return cloneDiagnostics();
    },
    validateJob: async (jobId) => {
      getState(jobId);
      return cloneDiagnostics();
    },
    getArtifact: async (jobId, path) => {
      const content = getState(jobId).artifactFiles.get(path);
      if (content === undefined) {
        throw new Error(`Demo artifact ${path} does not exist for job ${jobId}.`);
      }
      return content;
    },
    getJobReport: async (jobId) => {
      const report = getState(jobId).report;
      if (!report) {
        throw new Error(`Demo report for job ${jobId} does not exist.`);
      }
      return clone(report);
    },
    listBundleEntries: async (jobId) => {
      const state = getState(jobId);
      if (!state.report) {
        throw new Error(`Demo bundle for job ${jobId} does not exist.`);
      }
      return clone(state.bundleEntries);
    },
    getBundleFile: async (jobId, path) => {
      const state = getState(jobId);
      const content = state.bundleFiles.get(path);
      if (content === undefined) {
        throw new Error(`Demo bundle file ${path} does not exist for job ${jobId}.`);
      }
      return newBlob(content);
    },
    approveReview: async (jobId, actor) => {
      const state = ensureState(jobId, "waiting_for_review");
      ensureNoCandidateDecision(state);
      const approval = createApproval(jobId, actor, "approved", null);
      state.approvals = [approval];
      return clone(approval);
    },
    rejectReview: async (jobId, actor, reason) => {
      const state = ensureState(jobId, "waiting_for_review");
      ensureNoCandidateDecision(state);
      const approval = createApproval(jobId, actor, "rejected", reason);
      state.approvals = [approval];
      state.job = {
        ...state.job,
        state: "failed",
        revision: state.job.revision + 1,
        updated_at: DEMO_REVIEWED_AT,
      };
      return clone(approval);
    },
    finalizeJob: async (jobId) => {
      const state = ensureState(jobId, "waiting_for_review");
      const approval = state.approvals.find(
        (candidateApproval) =>
          candidateApproval.stage === "candidate" && candidateApproval.decision === "approved",
      );
      if (!approval || !state.candidate) {
        return {
          job_id: jobId,
          ok: false,
          artifacts: [],
          diagnostics: [
            {
              code: "APPROVAL_MISSING",
              severity: "error",
              message: "candidate is not approved",
            },
          ],
          lineage_id: null,
        };
      }

      const artifacts = createFinalArtifacts();
      const exportLineage = createExportLineage(state.job, state.candidate, approval.actor, artifacts);
      const lineage = [getLineage(state.candidate.lineage_id), exportLineage];
      storeLineage(exportLineage);

      state.job = {
        ...state.job,
        state: "completed",
        revision: state.job.revision + 1,
        updated_at: DEMO_PUBLISHED_AT,
      };
      state.artifactFiles.set("package/portrait.png", newPngBlob());
      state.report = createReport(
        state.job,
        state.candidate,
        approval,
        artifacts,
        lineage,
        cloneDiagnostics(),
      );
      state.bundleFiles = createBundleFiles(state.job, state.report, lineage);
      state.bundleEntries = createBundleEntries(state.bundleFiles);

      return {
        job_id: jobId,
        ok: true,
        artifacts: clone(artifacts),
        diagnostics: cloneDiagnostics(),
        lineage_id: exportLineage.asset_id,
      };
    },
    retryJob: async (jobId, actor) => {
      const state = ensureState(jobId, "failed");
      const rejected = state.approvals.find(
        (approval) => approval.stage === "candidate" && approval.decision === "rejected",
      );
      if (!rejected || !state.candidate) {
        throw new Error(`Demo job ${jobId} does not have a rejected candidate.`);
      }
      if (state.retryJobId !== null) {
        throw new Error(`Demo retry already exists for job ${jobId}.`);
      }

      counter += 1;
      const retryJob: Job = {
        id: `demo-job-${counter}`,
        state: "created",
        manifest: clone(state.job.manifest),
        parent_candidate_id: `${jobId}-candidate`,
        revision: 1,
        created_at: DEMO_CREATED_AT,
        updated_at: DEMO_CREATED_AT,
      };
      jobs.set(retryJob.id, {
        job: retryJob,
        sourcePlan: null,
        candidate: null,
        approvals: [],
        report: null,
        bundleEntries: [],
        artifactFiles: new Map(),
        bundleFiles: new Map(),
        retryJobId: null,
      });
      state.retryJobId = retryJob.id;
      state.artifactFiles.set("retry-created-by.txt", newBlob(actor, "text/plain"));
      return clone(retryJob);
    },
    cancelJob: async (jobId) => {
      const state = getState(jobId);
      if (state.job.state === "completed" || state.job.state === "failed" || state.job.state === "cancelled") {
        throw new Error(`Demo job ${jobId} cannot cancel from state ${state.job.state}.`);
      }
      state.job = {
        ...state.job,
        state: "cancelled",
        revision: state.job.revision + 1,
        updated_at: DEMO_REVIEWED_AT,
      };
      return clone(state.job);
    },
    listReferencePacks: async () => demoReferenceHistory.map((pack) => pack.id),
    listReferenceHistory: async (packId) => {
      const history = demoReferenceHistory.filter((pack) => pack.id === packId);
      if (history.length === 0) {
        throw new Error(`Demo reference pack ${packId} does not exist.`);
      }
      return clone(history);
    },
    getLineage: async (assetId) => getLineage(assetId),
    getLineageAncestors: async (assetId) => lineageAncestors(assetId),
    getLineageChildren: async (assetId) =>
      [...lineages.values()]
        .filter((node) => node.parents.includes(assetId))
        .map((node) => clone(node))
        .sort((left, right) => left.asset_id.localeCompare(right.asset_id)),
  };
}
