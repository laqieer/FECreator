import { afterEach, expect, test, vi } from "vitest";
import { demoClient } from "./demoClient";
import type { Manifest } from "../api/types";

const PNG_SIGNATURE = [137, 80, 78, 71, 13, 10, 26, 10];
const CRC32_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let i = 0; i < table.length; i += 1) {
    let crc = i;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc & 1) !== 0 ? 0xedb88320 ^ (crc >>> 1) : crc >>> 1;
    }
    table[i] = crc >>> 0;
  }
  return table;
})();

const validManifest: Manifest = {
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

afterEach(() => {
  vi.unstubAllGlobals();
});

function readUint32BE(bytes: Uint8Array, offset: number): number {
  return (
    ((bytes[offset] ?? 0) << 24) |
    ((bytes[offset + 1] ?? 0) << 16) |
    ((bytes[offset + 2] ?? 0) << 8) |
    (bytes[offset + 3] ?? 0)
  ) >>> 0;
}

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc = CRC32_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (~crc) >>> 0;
}

function expectValidPng(bytes: Uint8Array): void {
  expect(Array.from(bytes.slice(0, 8))).toEqual(PNG_SIGNATURE);

  const chunks: Array<{ type: string }> = [];
  let offset = PNG_SIGNATURE.length;

  while (offset < bytes.length) {
    expect(offset + 8).toBeLessThanOrEqual(bytes.length);
    const length = readUint32BE(bytes, offset);
    offset += 4;
    const typeBytes = bytes.slice(offset, offset + 4);
    const type = String.fromCharCode(...typeBytes);
    offset += 4;
    expect(offset + length + 4).toBeLessThanOrEqual(bytes.length);

    const data = bytes.slice(offset, offset + length);
    offset += length;
    const expectedCrc = readUint32BE(bytes, offset);
    offset += 4;
    const actualCrc = crc32(new Uint8Array([...typeBytes, ...data]));

    expect(actualCrc).toBe(expectedCrc);
    chunks.push({ type });
  }

  expect(chunks.map((chunk) => chunk.type)).toEqual(["IHDR", "IDAT", "IEND"]);
  expect(readUint32BE(bytes, bytes.length - 12)).toBe(0);
  expect(offset).toBe(bytes.length);
}

test("demo candidate artifacts are valid PNG bytes with matching chunk CRCs", async () => {
  const client = demoClient();
  const created = await client.createJob(validManifest);

  await client.planSources(created.id);
  await client.submitSources(created.id, [new File(["candidate-bytes"], "neutral.png", { type: "image/png" })]);

  const blob = await client.getArtifact(created.id, "candidate/package/portrait.png");
  expect(blob.type).toBe("image/png");

  const bytes = new Uint8Array(await blob.arrayBuffer());
  expectValidPng(bytes);
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
  expect(candidate.artifacts).toEqual(
    expect.arrayContaining([expect.objectContaining({ role: "palette", media_type: "text/plain" })]),
  );
  expect(await (await client.getArtifact(created.id, "candidate/package/portrait.pal")).text()).toContain(
    "JASC-PAL",
  );
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
  expect((await client.getArtifact(created.id, "candidate/package/portrait.png")).type).toBe("image/png");
  expect((await client.getArtifact(created.id, "package/portrait.png")).type).toBe("image/png");

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

test("createJob fails closed on parent_asset_id that contradicts the workflow", async () => {
  const client = demoClient();
  const missingParent: Manifest = {
    ...validManifest,
    workflow: "expression_refine",
    sources: [{ kind: "approved_portrait", ref: "hero.png" }],
  };
  const unexpectedParent: Manifest = {
    ...validManifest,
    parent_asset_id: "demo-portrait-neutral-candidate",
  };
  const unknownParent: Manifest = {
    ...missingParent,
    parent_asset_id: "not-a-demo-asset",
  };

  await expect(client.createJob(missingParent)).rejects.toThrow(
    "Demo manifest workflow expression_refine requires a parent_asset_id naming its approved base.",
  );
  await expect(client.createJob(unexpectedParent)).rejects.toThrow(
    "Demo manifest workflow text_to_portrait must not set parent_asset_id.",
  );
  await expect(client.createJob(unknownParent)).rejects.toThrow(
    "Demo lineage asset not-a-demo-asset does not exist.",
  );
});

test("createJob records the approved base as a demo lineage parent", async () => {
  const client = demoClient();
  const derived: Manifest = {
    ...validManifest,
    workflow: "expression_refine",
    parent_asset_id: "demo-portrait-neutral-candidate",
    sources: [{ kind: "approved_portrait", ref: "hero.png" }],
  };

  const created = await client.createJob(derived);
  await client.planSources(created.id);
  await client.submitSources(created.id, [
    new File([new Uint8Array([1, 2, 3])], "neutral.png", { type: "image/png" }),
  ]);
  const candidate = await client.getJobCandidate(created.id);
  const ancestors = await client.getLineageAncestors(candidate.lineage_id);

  expect((await client.getLineage(candidate.lineage_id)).parents).toEqual([
    "demo-portrait-neutral-candidate",
  ]);
  expect(ancestors.map((node) => node.asset_id)).toContain("demo-portrait-neutral-candidate");
});

test("createJob accepts an approved base created during the demo session", async () => {
  const client = demoClient();
  const base = await client.createJob(validManifest);
  await client.planSources(base.id);
  await client.submitSources(base.id, [
    new File([new Uint8Array([1, 2, 3])], "neutral.png", { type: "image/png" }),
  ]);
  const baseCandidate = await client.getJobCandidate(base.id);

  const derived = await client.createJob({
    ...validManifest,
    workflow: "expression_refine",
    parent_asset_id: baseCandidate.lineage_id,
    sources: [{ kind: "approved_portrait", ref: "hero.png" }],
  });

  expect(derived.manifest.parent_asset_id).toBe(baseCandidate.lineage_id);
});

test("createJob still refuses a parent that no live demo lineage node names", async () => {
  const client = demoClient();

  await expect(
    client.createJob({
      ...validManifest,
      workflow: "masked_variant",
      parent_asset_id: "demo-job-99-candidate",
      sources: [{ kind: "approved_portrait", ref: "hero.png" }],
    }),
  ).rejects.toThrow("Demo lineage asset demo-job-99-candidate does not exist.");
});
