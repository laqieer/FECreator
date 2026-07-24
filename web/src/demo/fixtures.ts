import type { Diagnostic, Job, JobEvent, Manifest } from "../api/types";

export const DEMO_CREATED_AT = "2026-07-24T00:00:00+00:00";

export const demoAssets: readonly string[] = ["portrait"];
export const demoSpecs: readonly string[] = ["fe-gba-portrait-standard"];
export const demoProviders: readonly string[] = ["fake"];

export const demoManifest: Manifest = {
  version: "1.0",
  asset_type: "portrait",
  target_spec: "fe-gba-portrait-standard",
  workflow: "text_to_portrait",
  provider: "fake",
};

export const demoJobsSeed: readonly Job[] = [
  {
    id: "demo-portrait-neutral",
    state: "completed",
    manifest: demoManifest,
    revision: 3,
    created_at: DEMO_CREATED_AT,
    updated_at: DEMO_CREATED_AT,
  },
];

export const demoDiagnostics: readonly Diagnostic[] = [
  {
    code: "portrait.palette.count",
    severity: "info",
    message: "Sample portrait uses 15 of 16 permitted palette entries.",
    where: "portrait/neutral.png",
    data: null,
  },
];

export const demoTimeline: readonly JobEvent[] = [
  { seq: 0, at: DEMO_CREATED_AT, kind: "created", message: "Demo job created from sample manifest." },
  { seq: 1, at: DEMO_CREATED_AT, kind: "planning", message: "Planned deterministic sample source prompts." },
  { seq: 2, at: DEMO_CREATED_AT, kind: "processing", message: "Rendered deterministic sample frames in memory." },
  { seq: 3, at: DEMO_CREATED_AT, kind: "completed", message: "Sample job completed. No real assets were produced." },
];
