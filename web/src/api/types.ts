export type Severity = "error" | "warning" | "info";
export type AssetType = "portrait" | "dialogue_background";
export type TargetSpec = "fe-gba-portrait-standard" | "fe8-dialogue-background-source-240x160";
export type SourceKind =
  | "text"
  | "concept_art"
  | "approved_portrait"
  | "approved_dialogue_background";
export type Workflow =
  | "text_to_portrait"
  | "concept_to_portrait"
  | "expression_refine"
  | "masked_variant"
  | "text_to_dialogue_background"
  | "concept_to_dialogue_background";
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
  | "create_dialogue_background"
  | "import_dialogue_background_concept"
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

export interface SourceIdentity {
  kind: string;
  id: string;
  revision: string;
}

export interface AssetMetadata {
  name: string;
  purpose: string;
  source: SourceIdentity;
  license_note: string;
  source_note: string;
  requested_downstream_profile: "fe8-dialogue-background-feimg2" | null;
}

export interface Manifest {
  version: "1.0";
  asset_type: AssetType;
  target_spec: TargetSpec;
  workflow: Workflow;
  provider: string;
  character_ref_pack: string | null;
  character_ref_pack_rev: number | null;
  parent_asset_id: string | null;
  sources: SourceSpec[];
  edit: EditSpec | null;
  metadata: AssetMetadata | null;
  params: JsonObject;
}

export interface DialogueBackgroundSourceRecord {
  kind: string;
  id: string;
  revision: string;
  input_sha256: string;
}

export interface DialogueBackgroundPackageManifest {
  version: "1.0";
  contract_version: "1.0";
  asset_type: "dialogue_background";
  asset_type_version: "1.0";
  target_spec: "fe8-dialogue-background-source-240x160";
  target_spec_version: "1.0";
  name: string;
  purpose: string;
  width: 240;
  height: 160;
  opaque: true;
  provider: string;
  model: string | null;
  prompt: string | null;
  reference_pack: string | null;
  reference_pack_rev: number | null;
  source: DialogueBackgroundSourceRecord;
  png_sha256: string;
  license_note: string;
  source_note: string;
  requested_downstream_profile: "fe8-dialogue-background-feimg2" | null;
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
