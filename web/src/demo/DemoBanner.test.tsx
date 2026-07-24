import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { DemoBanner } from "./DemoBanner";

test("the demo banner is an accessible, persistent notice about sample data", () => {
  render(<DemoBanner />);
  const banner = screen.getByRole("note", { name: "Demo mode notice" });
  expect(banner).toBeInTheDocument();
  expect(banner).toHaveTextContent(/sample data/i);
  expect(banner).toHaveTextContent(/cannot generate, validate, upload, or save/i);
  expect(banner).toHaveTextContent(/reset/i);
});