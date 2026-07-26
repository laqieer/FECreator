import { afterEach, expect, test, vi } from "vitest";
import { demoClient } from "./demoClient";
import type { Manifest } from "../api/types";

const validManifest: Manifest = {
  version: "1.0",
  asset_type: "portrait",
  target_spec: "fe-gba-portrait-standard",
  workflow: "text_to_portrait",
  provider: "fake",
  character_ref_pack: null,
  character_ref_pack_rev: null,
  sources: [{ kind: "text", ref: "hero" }],
  edit: null,
  params: {},
};

afterEach(() => {
  vi.unstubAllGlobals();
});

test("registries are deterministic and match the frozen v1 surface", async () => {
  const client = demoClient();
  expect(await client.listAssets()).toEqual(["portrait"]);
  expect(await client.listSpecs()).toEqual(["fe-gba-portrait-standard"]);
  expect(await client.listProviders()).toEqual(["fake"]);
  expect(await client.listReferencePacks()).toEqual(["hero-pack"]);
});

test("a fresh client resets in-memory state (reload semantics)", async () => {
  const first = demoClient();
  await first.createJob(validManifest);
  const second = demoClient();
  await expect(second.getJob("demo-job-1")).rejects.toThrow("Demo job demo-job-1 does not exist.");
});

test("demo lifecycle stays in memory, clones state, and never touches fetch, websockets, or file bytes", async () => {
  const fetchSpy = vi.fn(() => {
    throw new Error("demo mode must not fetch");
  });
  const webSocketSpy = vi.fn(() => {
    throw new Error("demo mode must not open sockets");
  });
  vi.stubGlobal("fetch", fetchSpy);
  vi.stubGlobal("WebSocket", webSocketSpy);

  const file = new File(["candidate-bytes"], "neutral.png", { type: "image/png" });
  const arrayBufferSpy = vi.spyOn(file, "arrayBuffer");
  const textSpy = vi.spyOn(file, "text");
  const client = demoClient();

  const created = await client.createJob(validManifest);
  expect(created.id).toBe("demo-job-1");
  expect(created.state).toBe("created");

  const planned = await client.planSources(created.id);
  expect(planned.expected_filenames).toEqual(["neutral.png"]);
  expect((await client.getJob(created.id)).state).toBe("waiting_for_sources");

  const submitted = await client.submitSources(created.id, [file]);
  expect(submitted.state).toBe("waiting_for_review");

  const candidate = await client.getJobCandidate(created.id);
  candidate.metrics.score = 0;
  expect((await client.getJobCandidate(created.id)).metrics.score).toBe(0.95);
  expect(await client.listApprovals(created.id)).toEqual([]);
  expect(await client.validate("fe-gba-portrait-standard", "pkg")).toHaveLength(1);
  expect(await client.validateJob(created.id)).toHaveLength(1);

  const approved = await client.approveReview(created.id, "reviewer");
  expect(approved.decision).toBe("approved");
  expect(approved.reason).toBeNull();
  expect(await client.listApprovals(created.id)).toEqual([approved]);

  const finalized = await client.finalizeJob(created.id);
  expect(finalized.ok).toBe(true);
  expect(finalized.lineage_id).toBe(`${created.id}-export`);
  expect((await client.getJob(created.id)).state).toBe("completed");

  const report = await client.getJobReport(created.id);
  expect(report.approval?.actor).toBe("reviewer");
  report.output_hashes.push("mutated");
  expect((await client.getJobReport(created.id)).output_hashes).not.toContain("mutated");

  const bundle = await client.listBundleEntries(created.id);
  expect(bundle.map((entry) => entry.path)).toEqual(["hashes.json", "lineage.json", "manifest.json", "report.json"]);
  expect((await client.getBundleFile(created.id, "manifest.json")).size).toBeGreaterThan(0);
  await expect((await client.getArtifact(created.id, "package/portrait.png")).text()).resolves.toContain(
    created.id,
  );

  expect(await client.listJobs()).toEqual(
    expect.arrayContaining([expect.objectContaining({ id: created.id })]),
  );
  expect(await client.listReferenceHistory("hero-pack")).toEqual([
    expect.objectContaining({ id: "hero-pack", revision: 99 }),
  ]);
  expect(await client.getLineage(`${created.id}-export`)).toEqual(
    expect.objectContaining({ parents: [`${created.id}-candidate`] }),
  );
  expect(await client.getLineageAncestors(`${created.id}-export`)).toEqual(
    expect.arrayContaining([expect.objectContaining({ asset_id: `${created.id}-candidate` })]),
  );
  expect(await client.getLineageChildren(`${created.id}-candidate`)).toEqual(
    expect.arrayContaining([expect.objectContaining({ asset_id: `${created.id}-export` })]),
  );

  expect(fetchSpy).not.toHaveBeenCalled();
  expect(webSocketSpy).not.toHaveBeenCalled();
  expect(arrayBufferSpy).not.toHaveBeenCalled();
  expect(textSpy).not.toHaveBeenCalled();
});

test("rejected candidates create one deterministic retry linked by parent_candidate_id", async () => {
  const client = demoClient();
  const file = new File(["candidate-bytes"], "neutral.png", { type: "image/png" });
  const created = await client.createJob(validManifest);

  await client.planSources(created.id);
  await client.submitSources(created.id, [file]);
  const rejected = await client.rejectReview(created.id, "reviewer", "bad silhouette");

  expect(rejected.decision).toBe("rejected");
  expect(rejected.reason).toBe("bad silhouette");
  expect((await client.getJob(created.id)).state).toBe("failed");

  const retry = await client.retryJob(created.id, "reviewer");
  expect(retry.id).toBe("demo-job-2");
  expect(retry.parent_candidate_id).toBe(`${created.id}-candidate`);
  expect(retry.state).toBe("created");

  await expect(client.retryJob(created.id, "other-reviewer")).rejects.toThrow(
    "Demo retry already exists for job demo-job-1.",
  );
});

test("getJob rejects unknown ids and seeded demo publication stays available", async () => {
  await expect(demoClient().getJob("nope")).rejects.toThrow("Demo job nope does not exist.");

  const client = demoClient();
  const job = await client.getJob("demo-portrait-neutral");
  expect(job.state).toBe("completed");
  expect((await client.getJobReport(job.id)).job_id).toBe(job.id);
  expect(await client.listBundleEntries(job.id)).toEqual(
    expect.arrayContaining([expect.objectContaining({ path: "manifest.json" })]),
  );
});

test("createJob and validate fail closed on malformed demo inputs", async () => {
  const client = demoClient();
  const malformedProvider: Manifest = { ...validManifest, provider: "unregistered" };
  const malformedTarget = {
    ...validManifest,
    target_spec: "other",
  } as unknown as Manifest;

  await expect(client.createJob(malformedProvider)).rejects.toThrow(
    "Demo manifest provider is not registered.",
  );
  await expect(client.createJob(malformedTarget)).rejects.toThrow(
    "Demo manifest target_spec must be fe-gba-portrait-standard.",
  );
  await expect(client.validate("wrong", "pkg")).rejects.toThrow("Demo spec wrong is not registered.");
});
