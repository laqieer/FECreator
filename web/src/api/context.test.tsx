import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { ApiClientProvider, useApiClient } from "./context";
import { createStubApiClient } from "../test/util";

const fake = createStubApiClient({ listAssets: async () => [] });

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
