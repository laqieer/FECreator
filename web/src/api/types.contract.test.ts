import { expectTypeOf, test } from "vitest";
import type { ApiClient } from "./client";
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
} from "./types";

test("Manifest mirrors the canonical manifest contract", () => {
  expectTypeOf<Manifest>().toEqualTypeOf<{
    version: "1.0";
    asset_type: "portrait";
    target_spec: "fe-gba-portrait-standard";
    workflow:
      | "text_to_portrait"
      | "concept_to_portrait"
      | "expression_refine"
      | "masked_variant";
    provider: string;
    character_ref_pack: string | null;
    character_ref_pack_rev: number | null;
    sources: {
      kind: "text" | "concept_art" | "approved_portrait";
      ref: string;
    }[];
    edit: {
      mask_path: string;
      protected_regions: {
        x: number;
        y: number;
        w: number;
        h: number;
        label: string;
      }[];
    } | null;
    params: Record<string, string | number | boolean>;
  }>();
});

test("Job exposes the persisted parent candidate link", () => {
  expectTypeOf<Job["parent_candidate_id"]>().toEqualTypeOf<string | null>();
});

test("CandidateSnapshot and ApprovalRecord mirror review data", () => {
  expectTypeOf<CandidateSnapshot>().toEqualTypeOf<{
    version: "1.0";
    job_id: string;
    lineage_id: string;
    artifacts: {
      role: string;
      path: string;
      sha256: string;
      media_type: string;
    }[];
    diagnostics: {
      code: string;
      severity: "error" | "warning" | "info";
      message: string;
      where?: string | null;
      data?: Record<string, string | number | boolean> | null;
    }[];
    metrics: Record<string, number>;
    created_at: string;
  }>();

  expectTypeOf<ApprovalRecord>().toEqualTypeOf<{
    job_id: string;
    stage: string;
    decision: "approved" | "rejected";
    actor: string;
    reason: string | null;
    at: string;
  }>();
});

test("SourcePlan mirrors the source handoff contract", () => {
  expectTypeOf<SourcePlan>().toEqualTypeOf<{
    prompts: string[];
    reference_roles: Record<string, string>;
    expected_filenames: string[];
    required_expressions: string[];
    background_contract: string;
    forbidden_colors: string[];
    submission_schema: {
      forbidden_changes: string[];
      canonical_swatches: string[];
      traits: Record<string, string>;
      provenance: string;
      rights: string;
      files: string;
    };
  }>();
});

test("ReferencePack and LineageNode retain their canonical fields", () => {
  expectTypeOf<ReferencePack>().toEqualTypeOf<{
    id: string;
    revision: number;
    source: string;
    concept_art: {
      role: string;
      path: string;
      sha256: string;
      media_type: string;
    }[];
    traits: Record<string, string>;
    swatches: string[];
    forbidden_changes: string[];
    provenance: string;
    rights: string;
  }>();

  expectTypeOf<LineageNode>().toEqualTypeOf<{
    asset_id: string;
    operation: "import_concept" | "create_neutral" | "refine_expression" | "variant_masked_edit" | "export_spec";
    parents: string[];
    provider: string | null;
    model: string | null;
    prompt: string | null;
    reference_pack: string | null;
    reference_pack_rev: number | null;
    seed: number | null;
    params: Record<string, string | number | boolean>;
    mask: string | null;
    protected_regions: {
      x: number;
      y: number;
      w: number;
      h: number;
      label: string;
    }[];
    metrics: Record<string, number>;
    approved_by: string | null;
    output_hashes: string[];
    created_at: string;
  }>();
});

test("JobResult, Report, and BundleEntry mirror finalized publication data", () => {
  expectTypeOf<JobResult>().toEqualTypeOf<{
    job_id: string;
    ok: boolean;
    artifacts: {
      role: string;
      path: string;
      sha256: string;
      media_type: string;
    }[];
    diagnostics: {
      code: string;
      severity: "error" | "warning" | "info";
      message: string;
      where?: string | null;
      data?: Record<string, string | number | boolean> | null;
    }[];
    lineage_id: string | null;
  }>();

  expectTypeOf<Report>().toEqualTypeOf<{
    job_id: string;
    state: Job["state"];
    revision: number;
    created_at: string;
    updated_at: string;
    manifest: Manifest;
    manifest_hash: string;
    approval: ApprovalRecord | null;
    stages: {
      stage: string;
      ok: boolean;
      artifacts: JobResult["artifacts"];
      metrics: Record<string, number>;
      diagnostics: JobResult["diagnostics"];
    }[];
    diagnostics: JobResult["diagnostics"];
    lineage: LineageNode[];
    output_hashes: string[];
  }>();

  expectTypeOf<BundleEntry>().toEqualTypeOf<{
    path: string;
    size_bytes: number;
  }>();
});

test("ApiClient exposes the complete local and demo lifecycle", () => {
  expectTypeOf<ApiClient["listJobs"]>().toEqualTypeOf<() => Promise<Job[]>>();
  expectTypeOf<ApiClient["planSources"]>().toEqualTypeOf<(jobId: string) => Promise<SourcePlan>>();
  expectTypeOf<ApiClient["submitSources"]>().toEqualTypeOf<
    (jobId: string, files: File[]) => Promise<Job>
  >();
  expectTypeOf<ApiClient["getJobCandidate"]>().toEqualTypeOf<
    (jobId: string) => Promise<CandidateSnapshot>
  >();
  expectTypeOf<ApiClient["listApprovals"]>().toEqualTypeOf<
    (jobId: string) => Promise<ApprovalRecord[]>
  >();
  expectTypeOf<ApiClient["approveReview"]>().toEqualTypeOf<
    (jobId: string, actor: string) => Promise<ApprovalRecord>
  >();
  expectTypeOf<ApiClient["rejectReview"]>().toEqualTypeOf<
    (jobId: string, actor: string, reason: string) => Promise<ApprovalRecord>
  >();
  expectTypeOf<ApiClient["finalizeJob"]>().toEqualTypeOf<
    (jobId: string) => Promise<JobResult>
  >();
  expectTypeOf<ApiClient["retryJob"]>().toEqualTypeOf<
    (jobId: string, actor: string) => Promise<Job>
  >();
  expectTypeOf<ApiClient["cancelJob"]>().toEqualTypeOf<(jobId: string) => Promise<Job>>();
  expectTypeOf<ApiClient["validateJob"]>().toEqualTypeOf<
    (jobId: string) => Promise<JobResult["diagnostics"]>
  >();
  expectTypeOf<ApiClient["getArtifact"]>().toEqualTypeOf<
    (jobId: string, path: string) => Promise<Blob>
  >();
  expectTypeOf<ApiClient["getJobReport"]>().toEqualTypeOf<
    (jobId: string) => Promise<Report>
  >();
  expectTypeOf<ApiClient["listBundleEntries"]>().toEqualTypeOf<
    (jobId: string) => Promise<BundleEntry[]>
  >();
  expectTypeOf<ApiClient["getBundleFile"]>().toEqualTypeOf<
    (jobId: string, path: string) => Promise<Blob>
  >();
  expectTypeOf<ApiClient["listReferencePacks"]>().toEqualTypeOf<() => Promise<string[]>>();
  expectTypeOf<ApiClient["listReferenceHistory"]>().toEqualTypeOf<
    (packId: string) => Promise<ReferencePack[]>
  >();
  expectTypeOf<ApiClient["getLineage"]>().toEqualTypeOf<
    (assetId: string) => Promise<LineageNode>
  >();
  expectTypeOf<ApiClient["getLineageAncestors"]>().toEqualTypeOf<
    (assetId: string) => Promise<LineageNode[]>
  >();
  expectTypeOf<ApiClient["getLineageChildren"]>().toEqualTypeOf<
    (assetId: string) => Promise<LineageNode[]>
  >();
});
