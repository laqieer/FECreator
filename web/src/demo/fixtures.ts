import type {
  ApprovalRecord,
  Artifact,
  BundleEntry,
  CandidateSnapshot,
  Diagnostic,
  Job,
  JobEvent,
  LineageNode,
  Manifest,
  ReferencePack,
  Report,
  SourcePlan,
} from "../api/types";

export const DEMO_CREATED_AT = "2026-07-24T00:00:00+00:00";
export const DEMO_REVIEWED_AT = "2026-07-24T01:00:00+00:00";
export const DEMO_PUBLISHED_AT = "2026-07-24T02:00:00+00:00";

export const demoAssets: readonly string[] = ["portrait"];
export const demoSpecs: readonly string[] = ["fe-gba-portrait-standard"];
export const demoProviders: readonly string[] = ["fake"];

export const demoManifest: Manifest = {
  version: "1.0",
  asset_type: "portrait",
  target_spec: "fe-gba-portrait-standard",
  workflow: "text_to_portrait",
  provider: "fake",
  character_ref_pack: null,
  character_ref_pack_rev: null,
  parent_asset_id: null,
  sources: [{ kind: "text", ref: "hero" }],
  edit: null,
  params: {},
};

export const demoSourcePlan: SourcePlan = {
  prompts: ["hero, neutral expression, front-facing bust"],
  reference_roles: {},
  expected_filenames: ["neutral.png"],
  required_expressions: ["neutral"],
  background_contract: "green background at palette index 0, GBA 5-bit snapped",
  forbidden_colors: [],
  submission_schema: {
    forbidden_changes: [],
    canonical_swatches: [],
    traits: {},
    provenance: "",
    rights: "",
    files: "one indexed or RGB PNG per expected filename",
  },
};

export const demoDiagnostics: readonly Diagnostic[] = [
  {
    code: "portrait.palette.count",
    severity: "info",
    message: "Sample portrait uses 15 of 16 permitted palette entries.",
    where: "package/portrait.png",
    data: null,
  },
];

export const demoReferenceHistory: readonly ReferencePack[] = [
  {
    id: "hero-pack",
    revision: 99,
    source: "",
    concept_art: [
      {
        role: "concept_art",
        path: "refs/hero.png",
        sha256: "1".repeat(64),
        media_type: "image/png",
      },
    ],
    traits: { hair: "red" },
    swatches: ["#aa2222"],
    forbidden_changes: ["hair color"],
    provenance: "approved-board",
    rights: "original",
  },
];

export const demoFinalArtifacts: readonly Artifact[] = [
  {
    role: "portrait",
    path: "package/portrait.png",
    sha256: "2".repeat(64),
    media_type: "image/png",
  },
];

export const demoCandidate: CandidateSnapshot = {
  version: "1.0",
  job_id: "demo-portrait-neutral",
  lineage_id: "demo-portrait-neutral-candidate",
  artifacts: [
    {
      role: "portrait",
      path: "candidate/package/portrait.png",
      sha256: "3".repeat(64),
      media_type: "image/png",
    },
    {
      role: "palette",
      path: "candidate/package/portrait.pal",
      sha256: "5".repeat(64),
      media_type: "text/plain",
    },
  ],
  diagnostics: [],
  metrics: { score: 0.97 },
  created_at: DEMO_REVIEWED_AT,
};

export const demoApproval: ApprovalRecord = {
  job_id: "demo-portrait-neutral",
  stage: "candidate",
  decision: "approved",
  actor: "reviewer",
  reason: null,
  at: DEMO_REVIEWED_AT,
};

export const demoLineage: readonly LineageNode[] = [
  {
    asset_id: "demo-portrait-neutral-candidate",
    operation: "create_neutral",
    parents: [],
    provider: "fake",
    model: null,
    prompt: "hero, neutral expression, front-facing bust",
    reference_pack: "hero-pack",
    reference_pack_rev: 99,
    seed: 7,
    params: {},
    mask: null,
    protected_regions: [],
    metrics: { score: 0.97 },
    approved_by: null,
    output_hashes: ["3".repeat(64)],
    created_at: DEMO_REVIEWED_AT,
  },
  {
    asset_id: "demo-portrait-neutral-export",
    operation: "export_spec",
    parents: ["demo-portrait-neutral-candidate"],
    provider: "fake",
    model: null,
    prompt: null,
    reference_pack: "hero-pack",
    reference_pack_rev: 99,
    seed: null,
    params: {},
    mask: null,
    protected_regions: [],
    metrics: { score: 0.97 },
    approved_by: "reviewer",
    output_hashes: ["2".repeat(64)],
    created_at: DEMO_PUBLISHED_AT,
  },
];

export const demoReport: Report = {
  job_id: "demo-portrait-neutral",
  state: "completed",
  revision: 3,
  created_at: DEMO_CREATED_AT,
  updated_at: DEMO_PUBLISHED_AT,
  manifest: demoManifest,
  manifest_hash: "4".repeat(64),
  approval: demoApproval,
  stages: [
    {
      stage: "candidate",
      ok: true,
      artifacts: [...demoCandidate.artifacts],
      metrics: { ...demoCandidate.metrics },
      diagnostics: [],
    },
    {
      stage: "finalize",
      ok: true,
      artifacts: [...demoFinalArtifacts],
      metrics: { ...demoCandidate.metrics },
      diagnostics: [...demoDiagnostics],
    },
  ],
  diagnostics: [...demoDiagnostics],
  lineage: [...demoLineage],
  output_hashes: ["2".repeat(64), "3".repeat(64)],
};

export const demoBundleEntries: readonly BundleEntry[] = [
  { path: "hashes.json", size_bytes: 33 },
  { path: "lineage.json", size_bytes: 668 },
  { path: "manifest.json", size_bytes: 262 },
  { path: "report.json", size_bytes: 1210 },
];

export const demoTimeline: readonly JobEvent[] = [
  { seq: 0, at: DEMO_CREATED_AT, kind: "created", message: "Demo job created from sample manifest." },
  { seq: 1, at: DEMO_CREATED_AT, kind: "planning", message: "Planned deterministic sample source prompts." },
  { seq: 2, at: DEMO_REVIEWED_AT, kind: "processing", message: "Rendered deterministic sample frames in memory." },
  { seq: 3, at: DEMO_PUBLISHED_AT, kind: "completed", message: "Sample job completed. No real assets were produced." },
];

export const demoJobsSeed: readonly Job[] = [
  {
    id: "demo-portrait-neutral",
    state: "completed",
    manifest: demoManifest,
    parent_candidate_id: null,
    revision: 3,
    created_at: DEMO_CREATED_AT,
    updated_at: DEMO_PUBLISHED_AT,
  },
];
