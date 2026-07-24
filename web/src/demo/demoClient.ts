import type { ApiClient } from "../api/client";
import type { Job, Manifest } from "../api/types";
import {
  DEMO_CREATED_AT,
  demoAssets,
  demoDiagnostics,
  demoJobsSeed,
  demoProviders,
  demoSpecs,
} from "./fixtures";

const demoWorkflows: readonly string[] = [
  "text_to_portrait",
  "concept_to_portrait",
  "expression_refine",
  "masked_variant",
];

export function assertValidManifest(manifest: Manifest): void {
  const version: unknown = manifest.version;
  if (version !== "1.0") {
    throw new Error("Demo manifest must use version 1.0.");
  }
  const assetType: unknown = manifest.asset_type;
  if (assetType !== "portrait") {
    throw new Error("Demo manifest asset_type must be portrait.");
  }
  const targetSpec: unknown = manifest.target_spec;
  if (targetSpec !== "fe-gba-portrait-standard") {
    throw new Error("Demo manifest target_spec must be fe-gba-portrait-standard.");
  }
  const workflow: unknown = manifest.workflow;
  if (typeof workflow !== "string" || !demoWorkflows.includes(workflow)) {
    throw new Error("Demo manifest workflow is not recognized.");
  }
  const provider: unknown = manifest.provider;
  if (typeof provider !== "string" || !demoProviders.includes(provider)) {
    throw new Error("Demo manifest provider is not registered.");
  }
}

export function demoClient(): ApiClient {
  const jobs = new Map<string, Job>(demoJobsSeed.map((job) => [job.id, job]));
  let counter = 0;

  return {
    listAssets: async () => [...demoAssets],
    listSpecs: async () => [...demoSpecs],
    listProviders: async () => [...demoProviders],
    createJob: async (manifest) => {
      assertValidManifest(manifest);
      counter += 1;
      const job: Job = {
        id: `demo-job-${counter}`,
        state: "created",
        manifest,
        revision: 1,
        created_at: DEMO_CREATED_AT,
        updated_at: DEMO_CREATED_AT,
      };
      jobs.set(job.id, job);
      return job;
    },
    getJob: async (id) => {
      const job = jobs.get(id);
      if (!job) {
        throw new Error(`Demo job ${id} does not exist.`);
      }
      return job;
    },
    validate: async (spec, path) => {
      if (!demoSpecs.includes(spec)) {
        throw new Error(`Demo spec ${spec} is not registered.`);
      }
      if (typeof path !== "string" || path.trim().length === 0) {
        throw new Error("Demo validation requires a package directory.");
      }
      return demoDiagnostics.map((diagnostic) => ({ ...diagnostic }));
    },
  };
}
