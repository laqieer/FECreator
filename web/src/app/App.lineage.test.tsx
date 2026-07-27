import "@testing-library/jest-dom/vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "./App";
import { createStubApiClient, renderWithProviders } from "../test/util";
import type { CandidateSnapshot, Job, LineageNode, Manifest } from "../api/types";

const APPROVED_BASE = "hero-neutral-candidate";

const derivedManifest: Manifest = {
  version: "1.0",
  asset_type: "portrait",
  target_spec: "fe-gba-portrait-standard",
  workflow: "expression_refine",
  provider: "fake",
  character_ref_pack: null,
  character_ref_pack_rev: null,
  parent_asset_id: APPROVED_BASE,
  sources: [{ kind: "approved_portrait", ref: "hero.png" }],
  edit: null,
  params: {},
};

const derivedJob: Job = {
  id: "derived-job",
  state: "waiting_for_review",
  manifest: derivedManifest,
  parent_candidate_id: null,
  revision: 1,
  created_at: "2026-07-24T00:00:00+00:00",
  updated_at: "2026-07-24T00:00:00+00:00",
};

const derivedCandidate: CandidateSnapshot = {
  version: "1.0",
  job_id: derivedJob.id,
  lineage_id: "derived-job-candidate",
  artifacts: [],
  diagnostics: [],
  metrics: {},
  created_at: derivedJob.created_at,
};

function lineageNode(overrides: Partial<LineageNode>): LineageNode {
  return {
    asset_id: "node",
    operation: "create_neutral",
    parents: [],
    provider: "fake",
    model: null,
    prompt: null,
    reference_pack: null,
    reference_pack_rev: null,
    seed: null,
    params: {},
    mask: null,
    protected_regions: [],
    metrics: {},
    approved_by: null,
    output_hashes: [],
    created_at: derivedJob.created_at,
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("shows the approved base a derived job was refined from", async () => {
  const user = userEvent.setup();
  renderWithProviders(
    <App />,
    createStubApiClient({
      listJobs: async () => [derivedJob],
      getJob: async () => derivedJob,
      getJobCandidate: async () => derivedCandidate,
      getLineage: async () =>
        lineageNode({
          asset_id: derivedCandidate.lineage_id,
          operation: "refine_expression",
          parents: [APPROVED_BASE],
        }),
      getLineageAncestors: async () => [
        lineageNode({ asset_id: APPROVED_BASE, approved_by: "reviewer" }),
      ],
      getLineageChildren: async () => [],
    }),
  );

  await user.click(await screen.findByRole("button", { name: /derived-job/i }));
  await user.click(await screen.findByRole("tab", { name: "Lineage" }));

  const view = await screen.findByRole("region", { name: "lineage-view" });
  const selected = within(view)
    .getByRole("heading", { name: "Selected asset" })
    .closest("section")!;
  const ancestors = within(view).getByRole("heading", { name: "Ancestors" }).closest("section")!;

  expect(within(selected).getByText(new RegExp(`parents: ${APPROVED_BASE}`))).toBeInTheDocument();
  expect(within(ancestors).getByText(APPROVED_BASE)).toBeInTheDocument();
});
