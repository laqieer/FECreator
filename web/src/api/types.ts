export type Severity = "error" | "warning" | "info";
export type SourceKind = "text" | "concept_art" | "approved_portrait";
export type Workflow =
  | "text_to_portrait"
  | "concept_to_portrait"
  | "expression_refine"
  | "masked_variant";
export type JobState =
  | "created"
  | "planning"
  | "waiting_for_provider"
  | "waiting_for_sources"
  | "processing"
  | "waiting_for_review"
  | "validating"
  | "completed"
  | "failed"
  | "cancelled";
export type Operation =
  | "import_concept"
  | "create_neutral"
  | "refine_expression"
  | "variant_masked_edit"
  | "export_spec";
export type JsonScalar = string | number | boolean;
export type JsonObject = Record<string, JsonScalar>;
export type MetricMap = Record<string, number>;

export interface Diagnostic {
  code: string;
  severity: Severity;
  message: string;
  where?: string | null;
  data?: JsonObject | null;
}

export interface Region {
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
}

export interface SourceSpec {
  kind: SourceKind;
  ref: string;
}

export interface EditSpec {
  mask_path: string;
  protected_regions: Region[];
}

export interface Manifest {
  version: "1.0";
  asset_type: "portrait";
  target_spec: "fe-gba-portrait-standard";
  workflow: Workflow;
  provider: string;
  character_ref_pack: string | null;
  character_ref_pack_rev: number | null;
  sources: SourceSpec[];
  edit: EditSpec | null;
  params: JsonObject;
}

export interface Job {
  id: string;
  state: JobState;
  manifest: Manifest;
  parent_candidate_id: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface JobEvent {
  seq: number;
  at: string;
  kind: string;
  message: string;
  data?: JsonObject;
}

export interface JobEventsPayload {
  job_id: string;
  events: JobEvent[];
}

export interface Artifact {
  role: string;
  path: string;
  sha256: string;
  media_type: string;
}

export interface CandidateSnapshot {
  version: "1.0";
  job_id: string;
  lineage_id: string;
  artifacts: Artifact[];
  diagnostics: Diagnostic[];
  metrics: MetricMap;
  created_at: string;
}

export interface ApprovalRecord {
  job_id: string;
  stage: string;
  decision: "approved" | "rejected";
  actor: string;
  reason: string | null;
  at: string;
}

export interface SubmissionSchema {
  forbidden_changes: string[];
  canonical_swatches: string[];
  traits: Record<string, string>;
  provenance: string;
  rights: string;
  files: string;
}

export interface SourcePlan {
  prompts: string[];
  reference_roles: Record<string, string>;
  expected_filenames: string[];
  required_expressions: string[];
  background_contract: string;
  forbidden_colors: string[];
  submission_schema: SubmissionSchema;
}

export interface LineageNode {
  asset_id: string;
  operation: Operation;
  parents: string[];
  provider: string | null;
  model: string | null;
  prompt: string | null;
  reference_pack: string | null;
  reference_pack_rev: number | null;
  seed: number | null;
  params: JsonObject;
  mask: string | null;
  protected_regions: Region[];
  metrics: MetricMap;
  approved_by: string | null;
  output_hashes: string[];
  created_at: string;
}

export interface ReferencePack {
  id: string;
  revision: number;
  source: string;
  concept_art: Artifact[];
  traits: Record<string, string>;
  swatches: string[];
  forbidden_changes: string[];
  provenance: string;
  rights: string;
}

export interface JobResult {
  job_id: string;
  ok: boolean;
  artifacts: Artifact[];
  diagnostics: Diagnostic[];
  lineage_id: string | null;
}

export interface ReportStage {
  stage: string;
  ok: boolean;
  artifacts: Artifact[];
  metrics: MetricMap;
  diagnostics: Diagnostic[];
}

export interface Report {
  job_id: string;
  state: JobState;
  revision: number;
  created_at: string;
  updated_at: string;
  manifest: Manifest;
  manifest_hash: string;
  approval: ApprovalRecord | null;
  stages: ReportStage[];
  diagnostics: Diagnostic[];
  lineage: LineageNode[];
  output_hashes: string[];
}

export interface BundleEntry {
  path: string;
  size_bytes: number;
}
