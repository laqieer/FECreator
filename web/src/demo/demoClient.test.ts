import { expect, test } from "vitest";
import { demoClient } from "./demoClient";
import type { Manifest } from "../api/types";

const validManifest: Manifest = {
  version: "1.0",
  asset_type: "portrait",
  target_spec: "fe-gba-portrait-standard",
  workflow: "text_to_portrait",
  provider: "fake",
};

test("registries are deterministic and match the frozen v1 surface", async () => {
  const client = demoClient();
  expect(await client.listAssets()).toEqual(["portrait"]);
  expect(await client.listSpecs()).toEqual(["fe-gba-portrait-standard"]);
  expect(await client.listProviders()).toEqual(["fake"]);
});

test("creating a job stores it in memory with a deterministic id", async () => {
  const client = demoClient();
  const job = await client.createJob(validManifest);
  expect(job.id).toBe("demo-job-1");
  expect(job.state).toBe("created");
  expect(await client.getJob("demo-job-1")).toEqual(job);
});

test("a fresh client resets in-memory state (reload semantics)", async () => {
  const first = demoClient();
  await first.createJob(validManifest);
  const second = demoClient();
  await expect(second.getJob("demo-job-1")).rejects.toThrow("Demo job demo-job-1 does not exist.");
});

test("getJob rejects unknown ids", async () => {
  await expect(demoClient().getJob("nope")).rejects.toThrow("Demo job nope does not exist.");
});

test("createJob fails closed on an unregistered provider", async () => {
  const client = demoClient();
  const malformed: Manifest = { ...validManifest, provider: "unregistered" };
  await expect(client.createJob(malformed)).rejects.toThrow("Demo manifest provider is not registered.");
});

test("createJob fails closed on a malformed target spec", async () => {
  const client = demoClient();
  const malformed = { ...validManifest, target_spec: "other" } as unknown as Manifest;
  await expect(client.createJob(malformed)).rejects.toThrow(
    "Demo manifest target_spec must be fe-gba-portrait-standard.",
  );
});

test("validate rejects unregistered specs and returns deterministic diagnostics", async () => {
  const client = demoClient();
  await expect(client.validate("wrong", "pkg")).rejects.toThrow("Demo spec wrong is not registered.");
  const diagnostics = await client.validate("fe-gba-portrait-standard", "pkg");
  expect(diagnostics).toHaveLength(1);
  expect(diagnostics[0]?.code).toBe("portrait.palette.count");
});

test("a preseeded sample job is available and completed", async () => {
  const job = await demoClient().getJob("demo-portrait-neutral");
  expect(job.state).toBe("completed");
});
