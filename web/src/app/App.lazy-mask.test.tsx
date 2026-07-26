import "@testing-library/jest-dom/vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { renderWithProviders } from "../test/util";
import { createStubApiClient } from "../test/util";
import { App } from "./App";

vi.mock("../canvas/MaskEditor", async () => {
  await new Promise((resolve) => setTimeout(resolve, 10));
  return {
    MaskEditor: () => <div>Mask editor ready</div>,
  };
});

const client = createStubApiClient();

test("shows a loading fallback before the lazy mask editor resolves", async () => {
  const user = userEvent.setup();
  renderWithProviders(<App />, client);

  await user.click(screen.getByRole("tab", { name: "Mask" }));

  expect(screen.getByRole("status")).toHaveTextContent("Loading mask editor…");
  expect(await screen.findByText("Mask editor ready")).toBeInTheDocument();
});
