import "@testing-library/jest-dom/vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { renderWithProviders } from "../test/util";
import type { ApiClient } from "../api/client";
import { App } from "./App";

vi.mock("../canvas/MaskEditor", async () => {
  await new Promise((resolve) => setTimeout(resolve, 10));
  return {
    MaskEditor: () => <div>Mask editor ready</div>,
  };
});

const client: ApiClient = {
  listAssets: async () => ["portrait"],
  listSpecs: async () => ["fe-gba-portrait-standard"],
  listProviders: async () => ["fake"],
  createJob: async () => {
    throw new Error("not used");
  },
  getJob: async () => {
    throw new Error("not used");
  },
  validate: async () => [],
};

test("shows a loading fallback before the lazy mask editor resolves", async () => {
  const user = userEvent.setup();
  renderWithProviders(<App />, client);

  await user.click(screen.getByRole("tab", { name: "Mask" }));

  expect(screen.getByRole("status")).toHaveTextContent("Loading mask editor…");
  expect(await screen.findByText("Mask editor ready")).toBeInTheDocument();
});
