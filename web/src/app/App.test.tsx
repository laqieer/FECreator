import "@testing-library/jest-dom/vitest";
import { screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { App } from "./App";
import { renderWithProviders } from "../test/util";
import type { ApiClient } from "../api/client";
import type { Manifest } from "../api/types";

const manifest: Manifest = {
  version: "1.0",
  asset_type: "portrait",
  target_spec: "fe-gba-portrait-standard",
  workflow: "text_to_portrait",
  provider: "fake",
  sources: [],
  params: {},
};

const fake: ApiClient = {
  listAssets: async () => ["portrait"],
  listSpecs: async () => ["fe-gba-portrait-standard"],
  listProviders: async () => ["fake"],
  createJob: async () => ({
    id: "j1",
    state: "created",
    manifest,
    revision: 1,
    created_at: "2026-07-24T00:00:00+00:00",
    updated_at: "2026-07-24T00:00:00+00:00",
  }),
  getJob: async () => ({
    id: "j1",
    state: "created",
    manifest,
    revision: 1,
    created_at: "2026-07-24T00:00:00+00:00",
    updated_at: "2026-07-24T00:00:00+00:00",
  }),
  validate: async () => [],
};

test("renders shell heading and review tab", async () => {
  renderWithProviders(<App />, fake);
  expect(screen.getByRole("heading", { name: "FECreator" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Review" })).toBeInTheDocument();
  expect(await screen.findByText("1 asset type available")).toBeInTheDocument();
});
