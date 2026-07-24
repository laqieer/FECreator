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
  protected_regions?: Region[];
}

export interface Manifest {
  version: "1.0";
  asset_type: "portrait";
  target_spec: "fe-gba-portrait-standard";
  workflow: Workflow;
  provider: string;
  character_ref_pack?: string | null;
  sources?: SourceSpec[];
  edit?: EditSpec | null;
  params?: JsonObject;
}

export interface Job {
  id: string;
  state: JobState;
  manifest: Manifest;
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

export interface JobResult {
  job_id: string;
  ok: boolean;
  artifacts?: Artifact[];
  diagnostics?: Diagnostic[];
  lineage_id?: string | null;
}

export interface SourcePlan {
  prompts: string[];
  expected_filenames: string[];
  required_expressions: string[];
  background_contract: string;
  forbidden_colors: string[];
}

export interface LineageNode {
  asset_id: string;
  operation: Operation;
  parents: string[];
  provider?: string | null;
  model?: string | null;
  prompt?: string | null;
  reference_pack?: string | null;
  reference_pack_rev?: number | null;
  seed?: number | null;
  params?: JsonObject;
  mask?: string | null;
  protected_regions?: Region[];
  metrics?: Record<string, number>;
  approved_by?: string | null;
  output_hashes?: string[];
  created_at?: string;
}
