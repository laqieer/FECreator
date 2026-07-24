import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { ApiClientProvider, useApiClient } from "./context";
import type { ApiClient } from "./client";

const fake: ApiClient = {
  listAssets: async () => [],
  listSpecs: async () => [],
  listProviders: async () => [],
  createJob: async () => {
    throw new Error("not used");
  },
  getJob: async () => {
    throw new Error("not used");
  },
  validate: async () => [],
};

function Probe() {
  const client = useApiClient();
  return <span>{typeof client.listAssets}</span>;
}

test("useApiClient reads the provided client", () => {
  render(
    <ApiClientProvider client={fake}>
      <Probe />
    </ApiClientProvider>,
  );

  expect(screen.getByText("function")).toBeInTheDocument();
});
