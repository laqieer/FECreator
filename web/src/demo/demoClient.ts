import type { ApiClient } from "../api/client";
import { NotFoundError } from "../api/client";
import type {
  ApprovalRecord,
  Artifact,
  AssetMetadata,
  BundleEntry,
  CandidateSnapshot,
  Diagnostic,
  DialogueBackgroundPackageManifest,
  Job,
  LineageNode,
  Manifest,
  ReferencePack,
  Report,
  SourcePlan,
} from "../api/types";
import { portableStorageIdError } from "../validation/storageId";
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
  "text_to_dialogue_background",
  "concept_to_dialogue_background",
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
const DEMO_DIALOGUE_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAPAAAACgCAIAAAC9uXYyAAABRUlEQVR42u3SQREAMAjAsDElSEAK/tWggg+XSOg1svrBFV8CDA2GBkODoTE0GBoMDYYGQ2NoMDQYGgwNhsbQYGgwNBgaDI2hwdBgaDA0GBpDg6HB0GBoMDSGBkODocHQYGgMDYYGQ4OhMTQYGgwNhgZDY2gwNBgaDA2GxtBgaDA0GBoMjaHB0GBoMDQYGkODocHQYGgwNIYGQ4OhwdBgaAwNhgZDg6HB0BgaDA2GBkNjaDA0GBoMDYbG0GBoMDQYGgyNocHQYGgwNBgaQ4OhwdBgaDA0hgZDg6HB0GBoDA2GBkODocHQGBoMDYYGQ2NoMDQYGgwNhsbQYGgwNBgaDI2hwdBgaDA0GBpDg6HB0GBoMDSGBkODocHQYGgMDYYGQ4OhwdAYGgwNhgZDg6ExNBgaDA2GxtBgaDA0GBoMjaHB0GBo2DEqSwHgG4gVDAAAAABJRU5ErkJggg==";
const DEMO_DIALOGUE_PNG_SHA256 =
  "c51e60b44140e13a75b27d12cebb14b3a88b11e640673b663e6d64dd68ad7aae";
const DEMO_JASC_PALETTE = `JASC-PAL
0100
2
0 248 0
80 96 200
`;

function newPngBlob(): Blob {
  return new Blob([DEMO_PNG_BYTES], { type: "image/png" });
}

function newDialoguePngBlob(): Blob {
  const binary = atob(DEMO_DIALOGUE_PNG_BASE64);
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  return new Blob([bytes], { type: "image/png" });
}

function newPaletteBlob(): Blob {
  return newBlob(DEMO_JASC_PALETTE, "text/plain");
}

async function sha256Text(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function cloneDiagnostics(): Diagnostic[] {
  return demoDiagnostics.map((diagnostic) => clone(diagnostic));
}

function diagnosticsFor(manifest: Manifest): Diagnostic[] {
  return manifest.asset_type === "portrait" ? cloneDiagnostics() : [];
}

function normalizedNonEmpty(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`Demo dialogue_background ${field} must be a non-empty string.`);
  }
  return value.trim();
}

function normalizeDialogueBackgroundMetadata(value: unknown): AssetMetadata {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Demo dialogue_background manifest requires metadata.");
  }
  const metadata = value as Record<string, unknown>;
  if (typeof metadata.name !== "string" || metadata.name === "") {
    throw new Error("Demo dialogue_background asset name must be a non-empty string.");
  }
  const name = metadata.name;
  const assetNameError = portableStorageIdError(name);
  if (assetNameError !== null) {
    throw new Error(`Demo dialogue_background asset name ${assetNameError}`);
  }
  const sourceValue = metadata.source;
  if (typeof sourceValue !== "object" || sourceValue === null || Array.isArray(sourceValue)) {
    throw new Error("Demo dialogue_background source kind must be a non-empty string.");
  }
  const source = sourceValue as Record<string, unknown>;
  const requestedDownstreamProfile =
    metadata.requested_downstream_profile === undefined
      ? null
      : metadata.requested_downstream_profile;
  if (
    requestedDownstreamProfile !== null &&
    requestedDownstreamProfile !== "fe8-dialogue-background-feimg2"
  ) {
    throw new Error(
      "Demo dialogue_background requested_downstream_profile is not supported.",
    );
  }
  return {
    name,
    purpose: normalizedNonEmpty(metadata.purpose, "purpose"),
    source: {
      kind: normalizedNonEmpty(source.kind, "source kind"),
      id: normalizedNonEmpty(source.id, "source id"),
      revision: normalizedNonEmpty(source.revision, "source revision"),
    },
    license_note: normalizedNonEmpty(metadata.license_note, "license note"),
    source_note: normalizedNonEmpty(metadata.source_note, "source note"),
    requested_downstream_profile: requestedDownstreamProfile,
  };
}

function sanitizeTextSource(manifest: Manifest): string {
  const source = manifest.sources.find((item) => item.kind === "text")?.ref?.trim();
  if (source && source.length > 0) {
    return source;
  }
  return manifest.asset_type === "portrait"
    ? "a Fire Emblem GBA character portrait"
    : "a Fire Emblem GBA dialogue background";
}

function createDialogueBackgroundPrompt(
  manifest: Manifest,
  pack: ReferencePack | null,
): string {
  const metadata = normalizeDialogueBackgroundMetadata(manifest.metadata);
  const text = manifest.sources
    .filter((source) => source.kind === "text")
    .map((source) => source.ref)
    .join(" ");
  const subject = text || metadata.purpose;
  const forbidden =
    pack && pack.forbidden_changes.length > 0
      ? `; preserve: ${pack.forbidden_changes.join(", ")}`
      : "";
  return (
    `${subject}${forbidden}; Fire Emblem 8 dialogue background source; ` +
    "240x160 composition; no text, logos, portrait frames, or characters; " +
    "keep critical focal detail out of the lower 48 pixels"
  );
}

function createDialogueBackgroundPackageManifest(
  manifest: Manifest,
  pngSha256: string,
): DialogueBackgroundPackageManifest {
  const metadata = normalizeDialogueBackgroundMetadata(manifest.metadata);
  return {
    version: "1.0",
    contract_version: "1.0",
    asset_type: "dialogue_background",
    asset_type_version: "1.0",
    target_spec: "fe8-dialogue-background-source-240x160",
    target_spec_version: "1.0",
    name: metadata.name,
    purpose: metadata.purpose,
    width: 240,
    height: 160,
    opaque: true,
    provider: manifest.provider,
    model: null,
    prompt: createDialogueBackgroundPrompt(manifest, maybeReferencePack(manifest)),
    reference_pack: manifest.character_ref_pack,
    reference_pack_rev: manifest.character_ref_pack_rev,
    source: {
      kind: metadata.source.kind,
      id: metadata.source.id,
      revision: metadata.source.revision,
      input_sha256: "4".repeat(64),
    },
    png_sha256: pngSha256,
    license_note: metadata.license_note,
    source_note: metadata.source_note,
    requested_downstream_profile: metadata.requested_downstream_profile,
  };
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
    parent_asset_id: manifest.parent_asset_id,
    sources: clone(manifest.sources),
    edit: manifest.edit === null ? null : clone(manifest.edit),
    metadata:
      manifest.asset_type === "dialogue_background"
        ? normalizeDialogueBackgroundMetadata(manifest.metadata)
        : null,
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
  if (manifest.asset_type === "dialogue_background") {
    const metadata = normalizeDialogueBackgroundMetadata(manifest.metadata);
    return {
      prompts: [createDialogueBackgroundPrompt(manifest, pack)],
      reference_roles: pack ? { concept_0: "refs/hero.png" } : {},
      expected_filenames: [`${metadata.name}.png`],
      required_expressions: [],
      background_contract: "one opaque 240x160 RGB or indexed PNG",
      forbidden_colors: [],
      submission_schema: {
        forbidden_changes: pack ? [...pack.forbidden_changes] : [],
        canonical_swatches: pack ? [...pack.swatches] : [],
        traits: pack ? { ...pack.traits } : {},
        provenance: metadata.source_note,
        rights: metadata.license_note,
        files: `one opaque 240x160 PNG named ${metadata.name}.png`,
      },
    };
  }
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

async function createCandidate(job: Job): Promise<CandidateSnapshot> {
  let artifacts: Artifact[];
  if (job.manifest.asset_type === "dialogue_background") {
    const metadata = normalizeDialogueBackgroundMetadata(job.manifest.metadata);
    const manifestJson = JSON.stringify(
      createDialogueBackgroundPackageManifest(job.manifest, DEMO_DIALOGUE_PNG_SHA256),
    );
    artifacts = [
      {
        role: "background",
        path: `candidate/package/${metadata.name}.png`,
        sha256: DEMO_DIALOGUE_PNG_SHA256,
        media_type: "image/png",
      },
      {
        role: "manifest",
        path: `candidate/package/${metadata.name}.manifest.json`,
        sha256: await sha256Text(manifestJson),
        media_type: "application/json",
      },
    ];
  } else {
    artifacts = [
      {
        role: "portrait",
        path: "candidate/package/portrait.png",
        sha256: "5".repeat(64),
        media_type: "image/png",
      },
      {
        role: "palette",
        path: "candidate/package/portrait.pal",
        sha256: "8".repeat(64),
        media_type: "text/plain",
      },
    ];
  }
  return {
    version: "1.0",
    job_id: job.id,
    lineage_id: `${job.id}-candidate`,
    artifacts,
    diagnostics: [],
    metrics: { score: 0.95 },
    created_at: DEMO_REVIEWED_AT,
  };
}

function createCandidateLineage(job: Job, candidate: CandidateSnapshot): LineageNode {
  const parents = [job.manifest.parent_asset_id, job.parent_candidate_id].filter(
    (parent): parent is string => parent !== null,
  );
  return {
    asset_id: candidate.lineage_id,
    operation:
      job.manifest.asset_type === "dialogue_background"
        ? job.manifest.workflow === "concept_to_dialogue_background"
          ? "import_dialogue_background_concept"
          : job.manifest.workflow === "masked_variant"
            ? "variant_masked_edit"
            : "create_dialogue_background"
        : "create_neutral",
    parents,
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

async function createFinalArtifacts(job: Job): Promise<Artifact[]> {
  if (job.manifest.asset_type === "dialogue_background") {
    const metadata = normalizeDialogueBackgroundMetadata(job.manifest.metadata);
    const manifestJson = JSON.stringify(
      createDialogueBackgroundPackageManifest(job.manifest, DEMO_DIALOGUE_PNG_SHA256),
    );
    return [
      {
        role: "background",
        path: `package/${metadata.name}.png`,
        sha256: DEMO_DIALOGUE_PNG_SHA256,
        media_type: "image/png",
      },
      {
        role: "manifest",
        path: `package/${metadata.name}.manifest.json`,
        sha256: await sha256Text(manifestJson),
        media_type: "application/json",
      },
    ];
  }
  return [
    {
      role: "portrait",
      path: "package/portrait.png",
      sha256: "6".repeat(64),
      media_type: "image/png",
    },
  ];
}

function artifactBlob(job: Job, artifact: Artifact, artifacts: Artifact[]): Blob {
  if (artifact.media_type === "application/json") {
    const background = artifacts.find((candidate) => candidate.role === "background");
    if (background === undefined) {
      throw new Error(`Demo package manifest ${artifact.path} has no background artifact.`);
    }
    return newBlob(
      JSON.stringify(createDialogueBackgroundPackageManifest(job.manifest, background.sha256)),
      "application/json",
    );
  }
  if (job.manifest.asset_type === "dialogue_background") {
    return newDialoguePngBlob();
  }
  return artifact.role === "palette" ? newPaletteBlob() : newPngBlob();
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
  const artifactFiles = new Map<string, Blob>(
    demoCandidate.artifacts.map((artifact) => [
      artifact.path,
      artifact.role === "palette" ? newPaletteBlob() : newPngBlob(),
    ]),
  );
  artifactFiles.set("package/portrait.png", newPngBlob());
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

export function assertValidManifest(
  manifest: Manifest,
  lineageHasAsset: (assetId: string) => boolean,
): void {
  const version: unknown = manifest.version;
  if (version !== "1.0") {
    throw new Error("Demo manifest must use version 1.0.");
  }
  const assetType: unknown = manifest.asset_type;
  if (assetType !== "portrait" && assetType !== "dialogue_background") {
    throw new Error("Demo manifest asset_type is not registered.");
  }
  const workflow: unknown = manifest.workflow;
  if (typeof workflow !== "string" || !demoWorkflows.includes(workflow as Manifest["workflow"])) {
    throw new Error("Demo manifest workflow is not recognized.");
  }
  const targetSpec: unknown = manifest.target_spec;
  if (assetType === "portrait") {
    if (targetSpec !== "fe-gba-portrait-standard") {
      throw new Error("Demo manifest target_spec must be fe-gba-portrait-standard.");
    }
    if (
      workflow !== "text_to_portrait" &&
      workflow !== "concept_to_portrait" &&
      workflow !== "expression_refine" &&
      workflow !== "masked_variant"
    ) {
      throw new Error(`Demo portrait workflow ${workflow} is not supported.`);
    }
    if (manifest.metadata !== null) {
      throw new Error("Demo portrait manifest must not set metadata.");
    }
  } else {
    if (targetSpec !== "fe8-dialogue-background-source-240x160") {
      throw new Error(
        "Demo dialogue_background target_spec must be fe8-dialogue-background-source-240x160.",
      );
    }
    if (
      workflow !== "text_to_dialogue_background" &&
      workflow !== "concept_to_dialogue_background" &&
      workflow !== "masked_variant"
    ) {
      throw new Error(`Demo dialogue_background workflow ${workflow} is not supported.`);
    }
    normalizeDialogueBackgroundMetadata(manifest.metadata);
  }
  const provider: unknown = manifest.provider;
  if (typeof provider !== "string" || !demoProviders.includes(provider)) {
    throw new Error("Demo manifest provider is not registered.");
  }
  if (manifest.character_ref_pack_rev !== null && manifest.character_ref_pack === null) {
    throw new Error("Demo manifest character_ref_pack_rev requires character_ref_pack.");
  }
  const usesApprovedBase =
    workflow === "expression_refine" || workflow === "masked_variant";
  const parentAssetId = manifest.parent_asset_id;
  if (usesApprovedBase && (parentAssetId === null || parentAssetId.trim() === "")) {
    throw new Error(
      `Demo manifest workflow ${workflow} requires a parent_asset_id naming its approved base.`,
    );
  }
  if (!usesApprovedBase && parentAssetId !== null) {
    throw new Error(`Demo manifest workflow ${workflow} must not set parent_asset_id.`);
  }
  // The live lineage map is consulted, not the initial fixture array: a demo
  // session creates candidate and export nodes of its own, and those are just
  // as valid an approved base as the seeded ones.
  if (parentAssetId !== null && !lineageHasAsset(parentAssetId)) {
    throw new Error(`Demo lineage asset ${parentAssetId} does not exist.`);
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
      assertValidManifest(manifest, (assetId) => lineages.has(assetId));
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
        throw new NotFoundError(`Demo candidate for job ${jobId} does not exist.`);
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
      const candidate = await createCandidate(state.job);
      const fileNames = files.map((file) => file.name).sort().join(", ");
      state.candidate = candidate;
      for (const artifact of candidate.artifacts) {
        state.artifactFiles.set(
          artifact.path,
          artifactBlob(state.job, artifact, candidate.artifacts),
        );
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
      return spec === "fe-gba-portrait-standard" ? cloneDiagnostics() : [];
    },
    validateJob: async (jobId) => {
      return diagnosticsFor(getState(jobId).job.manifest);
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
    buildJob: async (jobId) => {
      const state = ensureState(jobId, "waiting_for_review");
      const candidate = state.candidate;
      if (!candidate) {
        throw new Error(`Demo job ${jobId} has no candidate.`);
      }
      return {
        job_id: jobId,
        ok: true,
        artifacts: clone(candidate.artifacts),
        diagnostics: clone(candidate.diagnostics),
        lineage_id: candidate.lineage_id,
      };
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

      const artifacts = await createFinalArtifacts(state.job);
      const exportLineage = createExportLineage(state.job, state.candidate, approval.actor, artifacts);
      const lineage = [getLineage(state.candidate.lineage_id), exportLineage];
      storeLineage(exportLineage);

      state.job = {
        ...state.job,
        state: "completed",
        revision: state.job.revision + 1,
        updated_at: DEMO_PUBLISHED_AT,
      };
      for (const artifact of artifacts) {
        state.artifactFiles.set(artifact.path, artifactBlob(state.job, artifact, artifacts));
      }
      const diagnostics = diagnosticsFor(state.job.manifest);
      state.report = createReport(
        state.job,
        state.candidate,
        approval,
        artifacts,
        lineage,
        diagnostics,
      );
      state.bundleFiles = createBundleFiles(state.job, state.report, lineage);
      state.bundleEntries = createBundleEntries(state.bundleFiles);

      return {
        job_id: jobId,
        ok: true,
        artifacts: clone(artifacts),
        diagnostics: clone(diagnostics),
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
