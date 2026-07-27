import { afterEach, expect, test, vi } from "vitest";
import { ApiError, httpClient } from "./client";
import type {
  ApprovalRecord,
  BundleEntry,
  CandidateSnapshot,
  Diagnostic,
  Job,
  JobResult,
  LineageNode,
  Manifest,
  ReferencePack,
  Report,
  SourcePlan,
} from "./types";

const manifest: Manifest = {
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

const jobFixture: Job = {
  id: "job/with spaces",
  state: "waiting_for_review",
  manifest,
  parent_candidate_id: null,
  revision: 2,
  created_at: "2026-07-24T00:00:00+00:00",
  updated_at: "2026-07-24T01:00:00+00:00",
};

const candidateFixture: CandidateSnapshot = {
  version: "1.0",
  job_id: jobFixture.id,
  lineage_id: `${jobFixture.id}-candidate`,
  artifacts: [
    {
      role: "portrait",
      path: "candidate/package/neutral.png",
      sha256: "a".repeat(64),
      media_type: "image/png",
    },
  ],
  diagnostics: [],
  metrics: { score: 0.95 },
  created_at: "2026-07-24T01:30:00+00:00",
};

const approvalFixture: ApprovalRecord = {
  job_id: jobFixture.id,
  stage: "candidate",
  decision: "approved",
  actor: "reviewer",
  reason: null,
  at: "2026-07-24T01:45:00+00:00",
};

const sourcePlanFixture: SourcePlan = {
  prompts: ["hero, neutral expression, front-facing bust"],
  reference_roles: { concept_0: "refs/hero.png" },
  expected_filenames: ["neutral.png"],
  required_expressions: ["neutral"],
  background_contract: "green background at palette index 0, GBA 5-bit snapped",
  forbidden_colors: [],
  submission_schema: {
    forbidden_changes: ["hair color"],
    canonical_swatches: ["#aa2222"],
    traits: { hair: "red" },
    provenance: "approved-board",
    rights: "original",
    files: "one indexed or RGB PNG per expected filename",
  },
};

const reportFixture: Report = {
  job_id: jobFixture.id,
  state: "completed",
  revision: 3,
  created_at: jobFixture.created_at,
  updated_at: "2026-07-24T02:00:00+00:00",
  manifest,
  manifest_hash: "b".repeat(64),
  approval: approvalFixture,
  stages: [
    {
      stage: "candidate",
      ok: true,
      artifacts: candidateFixture.artifacts,
      metrics: candidateFixture.metrics,
      diagnostics: candidateFixture.diagnostics,
    },
  ],
  diagnostics: [],
  lineage: [],
  output_hashes: ["a".repeat(64)],
};

const bundleFixture: BundleEntry[] = [
  { path: "hashes.json", size_bytes: 128 },
  { path: "manifest.json", size_bytes: 256 },
];

const referencePackFixture: ReferencePack = {
  id: "hero-pack",
  revision: 99,
  source: "",
  concept_art: [],
  traits: { hair: "red" },
  swatches: ["#aa2222"],
  forbidden_changes: ["hair color"],
  provenance: "approved-board",
  rights: "original",
};

const candidateLineageFixture: LineageNode = {
  asset_id: candidateFixture.lineage_id,
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
  metrics: { score: 0.95 },
  approved_by: null,
  output_hashes: [candidateFixture.artifacts[0]!.sha256],
  created_at: "2026-07-24T01:30:00+00:00",
};

const lineageFixture: LineageNode = {
  asset_id: "hero-export",
  operation: "export_spec",
  parents: [candidateFixture.lineage_id],
  provider: "fake",
  model: null,
  prompt: null,
  reference_pack: "hero-pack",
  reference_pack_rev: 99,
  seed: null,
  params: {},
  mask: null,
  protected_regions: [],
  metrics: { score: 0.95 },
  approved_by: "reviewer",
  output_hashes: ["a".repeat(64)],
  created_at: "2026-07-24T02:00:00+00:00",
};

const finalizationFixture: JobResult = {
  job_id: jobFixture.id,
  ok: true,
  artifacts: [
    {
      role: "portrait",
      path: "package/portrait.png",
      sha256: "c".repeat(64),
      media_type: "image/png",
    },
  ],
  diagnostics: [],
  lineage_id: lineageFixture.asset_id,
};

const validationFixture: Diagnostic[] = [
  {
    code: "portrait.palette.count",
    severity: "info",
    message: "Sample portrait uses 15 of 16 permitted palette entries.",
    where: "package/portrait.png",
    data: null,
  },
];

function jsonResponse(payload: unknown, init?: ResponseInit): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "content-type": "application/json" },
    ...init,
  });
}

function blobResponse(body: string, init?: ResponseInit): Response {
  return new Response(body, {
    headers: { "content-type": "application/octet-stream" },
    ...init,
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("job review, report, reference, and lineage routes mirror the HTTP API surface", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(jsonResponse([jobFixture]))
    .mockResolvedValueOnce(jsonResponse(candidateFixture))
    .mockResolvedValueOnce(jsonResponse([approvalFixture]))
    .mockResolvedValueOnce(jsonResponse(sourcePlanFixture))
    .mockResolvedValueOnce(jsonResponse(validationFixture))
    .mockResolvedValueOnce(jsonResponse(reportFixture))
    .mockResolvedValueOnce(jsonResponse(bundleFixture))
    .mockResolvedValueOnce(jsonResponse(["hero-pack"]))
    .mockResolvedValueOnce(jsonResponse([referencePackFixture]))
    .mockResolvedValueOnce(jsonResponse(lineageFixture))
    .mockResolvedValueOnce(jsonResponse([candidateLineageFixture]))
    .mockResolvedValueOnce(jsonResponse([]));
  vi.stubGlobal("fetch", fetchMock);

  const client = httpClient("http://127.0.0.1:8000/");

  await expect(client.listJobs()).resolves.toEqual([jobFixture]);
  await expect(client.getJobCandidate(jobFixture.id)).resolves.toEqual(candidateFixture);
  await expect(client.listApprovals(jobFixture.id)).resolves.toEqual([approvalFixture]);
  await expect(client.planSources(jobFixture.id)).resolves.toEqual(sourcePlanFixture);
  await expect(client.validateJob(jobFixture.id)).resolves.toEqual(validationFixture);
  await expect(client.getJobReport(jobFixture.id)).resolves.toEqual(reportFixture);
  await expect(client.listBundleEntries(jobFixture.id)).resolves.toEqual(bundleFixture);
  await expect(client.listReferencePacks()).resolves.toEqual(["hero-pack"]);
  await expect(client.listReferenceHistory("hero pack")).resolves.toEqual([referencePackFixture]);
  await expect(client.getLineage("hero export")).resolves.toEqual(lineageFixture);
  await expect(client.getLineageAncestors("hero export")).resolves.toEqual([
    candidateLineageFixture,
  ]);
  await expect(client.getLineageChildren("hero export")).resolves.toEqual([]);

  expect(fetchMock).toHaveBeenNthCalledWith(1, "http://127.0.0.1:8000/api/jobs", undefined);
  expect(fetchMock).toHaveBeenNthCalledWith(
    2,
    "http://127.0.0.1:8000/api/jobs/job%2Fwith%20spaces/candidate",
    undefined,
  );
  expect(fetchMock).toHaveBeenNthCalledWith(
    3,
    "http://127.0.0.1:8000/api/jobs/job%2Fwith%20spaces/approvals",
    undefined,
  );
  expect(fetchMock).toHaveBeenNthCalledWith(
    4,
    "http://127.0.0.1:8000/api/jobs/job%2Fwith%20spaces/plan-sources",
    expect.objectContaining({ method: "POST" }),
  );
  expect(fetchMock).toHaveBeenNthCalledWith(
    5,
    "http://127.0.0.1:8000/api/jobs/job%2Fwith%20spaces/validate",
    expect.objectContaining({ method: "POST" }),
  );
  expect(fetchMock).toHaveBeenNthCalledWith(
    6,
    "http://127.0.0.1:8000/api/jobs/job%2Fwith%20spaces/report",
    undefined,
  );
  expect(fetchMock).toHaveBeenNthCalledWith(
    7,
    "http://127.0.0.1:8000/api/jobs/job%2Fwith%20spaces/bundle",
    undefined,
  );
  expect(fetchMock).toHaveBeenNthCalledWith(8, "http://127.0.0.1:8000/api/references", undefined);
  expect(fetchMock).toHaveBeenNthCalledWith(
    9,
    "http://127.0.0.1:8000/api/references/hero%20pack/history",
    undefined,
  );
  expect(fetchMock).toHaveBeenNthCalledWith(
    10,
    "http://127.0.0.1:8000/api/lineage/hero%20export",
    undefined,
  );
  expect(fetchMock).toHaveBeenNthCalledWith(
    11,
    "http://127.0.0.1:8000/api/lineage/hero%20export/ancestors",
    undefined,
  );
  expect(fetchMock).toHaveBeenNthCalledWith(
    12,
    "http://127.0.0.1:8000/api/lineage/hero%20export/children",
    undefined,
  );
});

test("lifecycle mutations use exact JSON and multipart payloads and read blobs raw", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(jsonResponse(jobFixture, { status: 201 }))
    .mockResolvedValueOnce(jsonResponse(jobFixture))
    .mockResolvedValueOnce(jsonResponse(approvalFixture))
    .mockResolvedValueOnce(
      jsonResponse({ ...approvalFixture, decision: "rejected", reason: "bad silhouette" }),
    )
    .mockResolvedValueOnce(jsonResponse(finalizationFixture))
    .mockResolvedValueOnce(
      jsonResponse({
        ...jobFixture,
        id: "retry job",
        parent_candidate_id: `${jobFixture.id}-candidate`,
        state: "created",
      }),
    )
    .mockResolvedValueOnce(jsonResponse({ ...jobFixture, state: "cancelled" }))
    .mockResolvedValueOnce(blobResponse("artifact-bytes"))
    .mockResolvedValueOnce(blobResponse("bundle-bytes"))
    .mockResolvedValueOnce(jsonResponse(validationFixture));
  vi.stubGlobal("fetch", fetchMock);

  const client = httpClient("http://127.0.0.1:8000");
  const sourceFile = new File(["png-bytes"], "neutral ref.png", { type: "image/png" });

  await expect(client.createJob(manifest)).resolves.toEqual(jobFixture);
  await expect(client.submitSources(jobFixture.id, [sourceFile])).resolves.toEqual(jobFixture);
  await expect(client.approveReview(jobFixture.id, "reviewer")).resolves.toEqual(approvalFixture);
  await expect(client.rejectReview(jobFixture.id, "reviewer", "bad silhouette")).resolves.toEqual({
    ...approvalFixture,
    decision: "rejected",
    reason: "bad silhouette",
  });
  await expect(client.finalizeJob(jobFixture.id)).resolves.toEqual(finalizationFixture);
  await expect(client.retryJob(jobFixture.id, "reviewer")).resolves.toMatchObject({
    id: "retry job",
    parent_candidate_id: `${jobFixture.id}-candidate`,
  });
  await expect(client.cancelJob(jobFixture.id)).resolves.toMatchObject({ state: "cancelled" });
  await expect((await client.getArtifact(jobFixture.id, "package/portrait 1.png")).text()).resolves.toBe(
    "artifact-bytes",
  );
  await expect((await client.getBundleFile(jobFixture.id, "package/portrait 1.png")).text()).resolves.toBe(
    "bundle-bytes",
  );
  await expect(client.validate("fe-gba-portrait-standard", "C:/work")).resolves.toEqual(
    validationFixture,
  );

  expect(fetchMock).toHaveBeenNthCalledWith(
    1,
    "http://127.0.0.1:8000/api/jobs",
    expect.objectContaining({
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(manifest),
    }),
  );

  const submitRequest = fetchMock.mock.calls[1];
  expect(submitRequest?.[0]).toBe("http://127.0.0.1:8000/api/jobs/job%2Fwith%20spaces/sources");
  expect(submitRequest?.[1]).toMatchObject({ method: "POST" });
  expect(submitRequest?.[1]?.body).toBeInstanceOf(FormData);
  expect((submitRequest?.[1]?.body as FormData).getAll("files")).toEqual([sourceFile]);

  expect(fetchMock).toHaveBeenNthCalledWith(
    3,
    "http://127.0.0.1:8000/api/jobs/job%2Fwith%20spaces/approve",
    expect.objectContaining({
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ actor: "reviewer" }),
    }),
  );
  expect(fetchMock).toHaveBeenNthCalledWith(
    4,
    "http://127.0.0.1:8000/api/jobs/job%2Fwith%20spaces/reject",
    expect.objectContaining({
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ actor: "reviewer", reason: "bad silhouette" }),
    }),
  );
  expect(fetchMock).toHaveBeenNthCalledWith(
    5,
    "http://127.0.0.1:8000/api/jobs/job%2Fwith%20spaces/finalize",
    expect.objectContaining({ method: "POST" }),
  );
  expect(fetchMock).toHaveBeenNthCalledWith(
    6,
    "http://127.0.0.1:8000/api/jobs/job%2Fwith%20spaces/retry",
    expect.objectContaining({
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ actor: "reviewer" }),
    }),
  );
  expect(fetchMock).toHaveBeenNthCalledWith(
    7,
    "http://127.0.0.1:8000/api/jobs/job%2Fwith%20spaces/cancel",
    expect.objectContaining({ method: "POST" }),
  );
  expect(fetchMock).toHaveBeenNthCalledWith(
    8,
    "http://127.0.0.1:8000/api/jobs/job%2Fwith%20spaces/artifacts/package/portrait%201.png",
    undefined,
  );
  expect(fetchMock).toHaveBeenNthCalledWith(
    9,
    "http://127.0.0.1:8000/api/jobs/job%2Fwith%20spaces/bundle/package/portrait%201.png",
    undefined,
  );
  expect(fetchMock).toHaveBeenNthCalledWith(
    10,
    "http://127.0.0.1:8000/api/validate",
    expect.objectContaining({
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ spec_id: "fe-gba-portrait-standard", package_dir: "C:/work" }),
    }),
  );
});

test("http client surfaces structured diagnostics for non-ok responses", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      jsonResponse(
        [
          {
            code: "APPROVE_REVIEW_FAILED",
            severity: "error",
            message: "could not approve candidate review",
            where: jobFixture.id,
            data: { detail: "bad state" },
          },
        ],
        { status: 409 },
      ),
    ),
  );

  const promise = httpClient("http://127.0.0.1:8000").approveReview(jobFixture.id, "reviewer");

  await expect(promise).rejects.toBeInstanceOf(ApiError);
  await expect(promise).rejects.toMatchObject({
    message: "POST http://127.0.0.1:8000/api/jobs/job%2Fwith%20spaces/approve -> 409",
    status: 409,
    diagnostics: [
      expect.objectContaining({
        code: "APPROVE_REVIEW_FAILED",
        where: jobFixture.id,
      }),
    ],
  });
});
